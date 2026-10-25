"""Replies, follow-up sequences, do-not-contact list, write-back, file versions and the
'when the spreadsheet is updated' trigger — all through the real API."""
from datetime import datetime, timedelta, timezone

from app.db import session_scope
from app.models import Agent, MemoryEntry

SEQ_PROMPT = ("Every Monday at 9am, read my sales spreadsheet, identify new leads and draft personalized follow-up emails "
              "for my approval. If they don't reply in 3 days, follow up again, up to 3 times, and mark them as contacted.")


def _run(client, auth, agent_id, mode):
    r = client.post(f"/api/agents/{agent_id}/runs", headers=auth, json={"mode": mode})
    assert r.status_code == 200, r.text
    return client.get(f"/api/runs/{r.json()['id']}", headers=auth).json()


def _approve_all(client, auth, run):
    ap = client.get(f"/api/approvals/{run['approval_id']}", headers=auth).json()
    r = client.post(f"/api/approvals/{ap['id']}/decide", headers=auth,
                    json={"decisions": [{"id": i["id"], "status": "approved"} for i in ap["items"]]})
    assert r.status_code == 200, r.text
    return client.get(f"/api/runs/{run['id']}", headers=auth).json()


def _age_memory(agent_id, days):
    with session_scope() as db:
        for m in db.query(MemoryEntry).filter_by(agent_id=agent_id):
            m.updated_at = datetime.now(timezone.utc) - timedelta(days=days)


def test_sequence_writeback_replies_unsubscribe(client, auth):
    a = client.post("/api/studio", headers=auth, json={"prompt": SEQ_PROMPT}).json()
    req = a["requirement"]
    assert a["status"] == "ready", a["questions"]
    assert req["sequence"] == {"enabled": True, "after_days": 3, "max_touches": 3}
    assert req["writeback"]["enabled"] and req["writeback"]["value"] == "Contacted"
    tools = [s["tool"] for s in a["workflow"]["steps"]]
    assert tools.index("compliance.suppress") < tools.index("ai.draft")
    assert tools.index("spreadsheet.update") > tools.index("email.send")
    assert any(c["id"] == "compliance" and c["status"] == "pass" for c in a["workflow"]["validation"]["checks"])

    # test run: sheet untouched
    t = _run(client, auth, a["id"], "test")
    assert t["status"] == "completed"
    files = {f["name"]: f for f in client.get("/api/files", headers=auth).json()}
    assert files["sales_leads.csv"]["version"] == 1

    client.post(f"/api/agents/{a['id']}/deploy", headers=auth)
    run = _run(client, auth, a["id"], "live")
    run = _approve_all(client, auth, run)
    assert run["summary"]["sent"] == 15

    # write-back produced version 2 with 15 rows marked Contacted
    f = next(f for f in client.get("/api/files", headers=auth).json() if f["name"] == "sales_leads.csv")
    assert f["version"] == 2
    detail = client.get(f"/api/files/{f['id']}", headers=auth).json()
    assert sum(1 for r in detail["rows"] if r["Status"] == "Contacted") == 20  # 5 originally + 15 marked
    assert all(r["Last contacted"] for r in detail["rows"] if r["Email"] in {m["to"] for m in client.get("/api/outbox", headers=auth).json()})
    versions = client.get(f"/api/files/{f['id']}/versions", headers=auth).json()
    assert [v["version"] for v in versions] == [2, 1] and versions[0]["source"] == "agent"
    assert client.get(f"/api/files/{f['id']}/download?version=1", headers=auth).status_code == 200

    outbox = [m for m in client.get("/api/outbox", headers=auth).json() if m["execution_id"] == run["id"]]
    by_email = {m["to"]: m for m in outbox}

    # replies: one interested, one unsubscribe
    r1 = client.post(f"/api/outbox/{by_email['priya.nair@freshmart.example']['id']}/reply", headers=auth,
                     json={"body": "Thanks Priya, this sounds great — happy to set up a call next week."}).json()
    assert r1["category"] == "interested" and r1["suggested_reply"]
    r2 = client.post(f"/api/outbox/{by_email['arjun@medisure.example']['id']}/reply", headers=auth,
                     json={"body": "Please remove me from your list."}).json()
    assert r2["category"] == "unsubscribe" and r2["suggested_reply"] is None
    sup = [s["email"] for s in client.get("/api/suppressions", headers=auth).json()]
    assert "arjun@medisure.example" in sup
    q = client.post(f"/api/outbox/{by_email['kavya.reddy@swiftcargo.example']['id']}/reply", headers=auth,
                    json={"body": "How quickly can delayed shipments be flagged?"}).json()
    assert q["category"] == "question" and "Delayed shipments are flagged" in q["suggested_reply"]

    # too early for follow-ups: everyone is waiting
    run2 = _run(client, auth, a["id"], "live")
    assert run2["status"] == "completed" and run2["summary"]["drafted"] == 0

    # 4 days later: 15 emailed − 3 replied = 12 follow-ups; Arjun also blocked by the do-not-contact list
    _age_memory(a["id"], 4)
    run3 = _run(client, auth, a["id"], "live")
    assert run3["status"] == "awaiting_approval"
    logs = {l["tool"]: l for l in run3["logs"]}
    assert logs["compliance.suppress"]["output"]["removed"][0]["email"] == "arjun@medisure.example"
    assert logs["memory.exclude"]["output"]["followups"] == 12
    ap = client.get(f"/api/approvals/{run3['approval_id']}", headers=auth).json()
    assert ap["counts"]["total"] == 12
    assert all(i["payload"]["subject"].startswith("Re: ") for i in ap["items"])
    assert "priya.nair@freshmart.example" not in {i["payload"]["to"] for i in ap["items"]}
    run3 = _approve_all(client, auth, run3)
    assert run3["summary"]["sent"] == 12
    with session_scope() as db:
        touches = {m.key: m.value["touches"] for m in db.query(MemoryEntry).filter_by(agent_id=a["id"])}
    assert touches["sanya@quickship.example"] == 2

    # respond to the interested lead from the replies inbox
    resp = client.post(f"/api/replies/{r1['id']}/respond", headers=auth,
                       json={"subject": "Re: call", "body": r1["suggested_reply"]}).json()
    assert resp["status"] == "handled" and resp["response_id"]
    assert client.post(f"/api/replies/{r2['id']}/respond", headers=auth,
                       json={"subject": "x", "body": "y"}).status_code == 409  # unsubscribed

    # inbound webhook requires the workspace key
    key = client.get("/api/settings", headers=auth).json()["inbound_key"]
    assert client.post("/api/inbound/email", json={"from_email": "x@y.example", "text": "hi"}).status_code == 401
    ok = client.post("/api/inbound/email", headers={"X-AgentJerry-Key": key},
                     json={"from_email": "meera@stylestreet.example", "text": "I'm out of office until Monday."}).json()
    assert ok["category"] == "out_of_office"


def test_file_update_trigger(client, auth):
    csv = b"Candidate Name,Email,Applied For,Stage\nAnu,anu@m.example,Designer,Shortlisted\n"
    f = client.post("/api/files", headers=auth, files={"file": ("walkin_candidates.csv", csv, "text/csv")}).json()
    a = client.post("/api/studio", headers=auth, json={
        "prompt": "Whenever walkin_candidates.csv is updated, draft interview invitations for shortlisted candidates for me to review"}).json()
    assert a["status"] == "ready", a["questions"]
    assert a["trigger"]["type"] == "file_updated" and a["trigger"]["file_id"] == f["id"]
    assert "walkin_candidates.csv is updated" in a["trigger_label"]
    _run(client, auth, a["id"], "test")
    client.post(f"/api/agents/{a['id']}/deploy", headers=auth)
    csv2 = csv + b"Ravi,ravi@m.example,Developer,Shortlisted\n"
    r = client.post(f"/api/files/{f['id']}/replace", headers=auth, files={"file": ("walkin_candidates.csv", csv2, "text/csv")}).json()
    assert r["version"] == 2 and r["triggered"] and r["triggered"][0]["agent_id"] == a["id"]
    run = client.get(f"/api/runs/{r['triggered'][0]['run_id']}", headers=auth).json()
    assert run["triggered_by"] == "file_updated" and run["status"] == "awaiting_approval"
    ap = client.get(f"/api/approvals/{run['approval_id']}", headers=auth).json()
    assert ap["counts"]["total"] == 2
