"""Insights, auto-pause health guard, duplicate and export/import."""
from app.db import session_scope
from app.models import DataFile


def test_insights_duplicate_export(client, auth):
    agents = client.get("/api/agents", headers=auth).json()
    sales = next(a for a in agents if a["stats"].get("emails_sent"))
    ins = client.get(f"/api/agents/{sales['id']}/insights", headers=auth).json()
    m = ins["metrics"]
    assert m["sent"] >= 1 and m["approved"] >= m["sent"] - m["followups_sent"] - 1
    assert m["approval_rate"] is not None and 0 <= m["approval_rate"] <= 1
    assert len(m["weeks"]) == 8 and sum(w["sent"] for w in m["weeks"]) == m["sent"]
    org = client.get("/api/insights", headers=auth).json()
    stages = [f["stage"] for f in org["funnel"]]
    assert stages == ["Drafts reviewed", "Approved", "Sent", "Replied", "Interested"]
    vals = [f["value"] for f in org["funnel"]]
    assert vals[1] <= vals[0] and vals[4] <= vals[3]

    exp = client.get(f"/api/agents/{sales['id']}/export", headers=auth)
    assert exp.status_code == 200 and "attachment" in exp.headers["content-disposition"]
    recipe = exp.json()
    assert recipe["format"] == "agentjerry.recipe/v1" and recipe["prompt"]
    imp = client.post("/api/agents/import", headers=auth, json={"recipe": recipe}).json()
    assert imp["id"] != sales["id"]
    assert client.post("/api/agents/import", headers=auth, json={"recipe": {"x": 1}}).status_code == 422

    dup = client.post(f"/api/agents/{sales['id']}/duplicate", headers=auth).json()
    d = client.get(f"/api/agents/{dup['id']}", headers=auth).json()
    assert d["name"].startswith("Copy of") and d["status"] in ("ready", "draft") and d["tested_version"] is None


def test_auto_pause_after_three_failures(client, auth):
    csv = b"Name,Email,Status\nA,a@x.example,New\n"
    f = client.post("/api/files", headers=auth, files={"file": ("fragile_leads.csv", csv, "text/csv")}).json()
    a = client.post("/api/studio", headers=auth, json={
        "prompt": "Every Monday at 9am send follow-up emails to new leads in fragile_leads.csv after I approve"}).json()
    assert a["status"] == "ready", a["questions"]
    client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "test"})
    client.post(f"/api/agents/{a['id']}/deploy", headers=auth)
    with session_scope() as db:  # break the file: the Email column disappears
        df = db.get(DataFile, f["id"])
        open(df.path, "w").write("Name,Status\nA,New\n")
    for _ in range(3):
        r = client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "live"}).json()
        run = client.get(f"/api/runs/{r['id']}", headers=auth).json()
        assert run["status"] == "failed" and "no longer has the column" in run["error"]
    ag = client.get(f"/api/agents/{a['id']}", headers=auth).json()
    assert ag["status"] == "paused"
    assert any(e["action"] == "agent.auto_paused" for e in client.get("/api/activity", headers=auth).json())
