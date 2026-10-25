"""The design document's section 11 test scenario, executed end to end through
the real API: understand -> clarify -> generate -> validate -> test mode ->
approval gate (approve 12 / reject 3) -> send -> memory -> re-run."""

PROMPT = ("Every Monday, check my sales spreadsheet, identify new leads, generate personalized "
          "follow-up emails, and show them to me before sending.")


def _run(client, auth, agent_id, mode):
    r = client.post(f"/api/agents/{agent_id}/runs", headers=auth, json={"mode": mode})
    assert r.status_code == 200, r.text
    return client.get(f"/api/runs/{r.json()['id']}", headers=auth).json()


def test_scenario(client, auth):
    # 1. extraction
    a = client.post("/api/studio", headers=auth, json={"prompt": PROMPT}).json()
    req = a["requirement"]
    assert req["purpose"] == "follow_up"
    assert req["trigger"]["frequency"] == "weekly" and req["trigger"]["day_of_week"] == "monday"
    assert req["source"]["file_name"] == "sales_leads.csv"
    assert req["approval"]["required"] is True
    fields = {s["field"] for s in a["conversation"][0]["spans"]}
    assert {"trigger", "data", "audience", "action", "approval"} <= fields
    # knowledge picked for sales only
    assert req["knowledge"]["titles"] == ["Brightpath product brief"]

    # 2. no blocking clarification for this instruction
    assert a["questions"] == []
    assert a["status"] == "ready"

    # 3-4. workflow generated (9-10 steps) and validated
    wf = a["workflow"]
    tools = [s["tool"] for s in wf["steps"]]
    assert 9 <= len(tools) <= 10
    assert tools.index("ai.draft") < tools.index("approval.request") < tools.index("email.send") < tools.index("memory.record")
    assert wf["validation"]["valid"] and wf["validation"]["status"] == "pass"

    # live run is blocked before a passing test
    r = client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "live"})
    assert r.status_code == 409

    # 5. test mode: every step passes, nothing sent
    sent_before = len(client.get("/api/outbox", headers=auth).json())
    run = _run(client, auth, a["id"], "test")
    assert run["status"] == "completed", run
    assert all(l["status"] == "passed" for l in run["logs"])
    assert len(client.get("/api/outbox", headers=auth).json()) == sent_before
    assert client.get(f"/api/agents/{a['id']}/memory", headers=auth).json() == []

    # 6. 20 leads, 5 already processed (Contacted) -> 15
    logs = {l["tool"]: l for l in run["logs"]}
    assert logs["spreadsheet.read"]["output"]["count"] == 20
    assert logs["data.filter"]["output"]["kept"] == 15

    # 7. drafts reference the right fields and are grounded in knowledge
    samples = logs["ai.draft"]["output"]["samples"]
    for d in samples:
        assert d["row"]["Company"] in d["body"] or d["row"]["Name"].split()[0] in d["body"]
        assert d["to"] == d["row"]["Email"]
    assert any(d["citations"] for d in samples)

    # deploy
    a2 = client.post(f"/api/agents/{a['id']}/deploy", headers=auth).json()
    assert a2["status"] == "deployed" and a2["next_run"]

    # 8. approval gate pauses the live run
    run = _run(client, auth, a["id"], "live")
    assert run["status"] == "awaiting_approval"
    ap = client.get(f"/api/approvals/{run['approval_id']}", headers=auth).json()
    assert ap["counts"]["total"] == 15
    assert len(client.get("/api/outbox", headers=auth).json()) == sent_before  # nothing sent yet

    # a second live run is refused while waiting
    assert client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "live"}).status_code == 409

    # partial decisions are refused
    items = ap["items"]
    r = client.post(f"/api/approvals/{ap['id']}/decide", headers=auth,
                    json={"decisions": [{"id": items[0]["id"], "status": "approved"}]})
    assert r.status_code == 409

    # 9. approve 12 (one edited), reject 3
    decisions = []
    for i, it in enumerate(items):
        d = {"id": it["id"], "status": "approved" if i < 12 else "rejected"}
        if i == 0:
            d["subject"] = "Edited subject line"
        decisions.append(d)
    r = client.post(f"/api/approvals/{ap['id']}/decide", headers=auth, json={"decisions": decisions})
    assert r.status_code == 200, r.text
    run = client.get(f"/api/runs/{run['id']}", headers=auth).json()
    assert run["status"] == "completed", run
    assert run["summary"]["sent"] == 12 and run["summary"]["rejected"] == 3
    outbox = client.get("/api/outbox", headers=auth).json()
    mine = [m for m in outbox if m["execution_id"] == run["id"]]
    assert len(mine) == 12
    assert any(m["subject"] == "Edited subject line" for m in mine)
    rejected_emails = {it["payload"]["to"] for it in items[12:]}
    assert not rejected_emails & {m["to"] for m in mine}

    mem = client.get(f"/api/agents/{a['id']}/memory", headers=auth).json()
    assert len(mem) == 12

    # 10. next Monday: 12 remembered leads are excluded -> 3 remain
    run2 = _run(client, auth, a["id"], "live")
    assert run2["status"] == "awaiting_approval"
    logs2 = {l["tool"]: l for l in run2["logs"]}
    assert len(logs2["memory.exclude"]["output"]["skipped"]) == 12
    ap2 = client.get(f"/api/approvals/{run2['approval_id']}", headers=auth).json()
    assert ap2["counts"]["total"] == 3
    assert {it["payload"]["to"] for it in ap2["items"]} == rejected_emails

    # 11. audit trail shows who approved
    acts = client.get("/api/activity", headers=auth).json()
    assert any(e["action"] == "approval.decided" and e["actor"] == "Priya Raman" for e in acts)
    assert any(e["action"] == "email.sent" for e in acts)

    # cancel the pending run cleanly
    assert client.post(f"/api/runs/{run2['id']}/cancel", headers=auth).status_code == 200
    assert client.get(f"/api/approvals/{run2['approval_id']}", headers=auth).json()["status"] == "expired"


def test_safety_bypass_blocked(client, auth):
    """A workflow edited to remove the approval gate must fail validation, and
    the send tool itself refuses to send without an approval."""
    from app.engine.validator import validate
    a = client.post("/api/studio", headers=auth, json={"prompt": PROMPT}).json()
    steps = [s for s in a["workflow"]["steps"] if s["tool"] != "approval.request"]
    report = validate(steps, a["requirement"], {"require_approval_external": True})
    assert not report["valid"]
    assert any(c["id"] == "safety" and c["status"] == "fail" for c in report["checks"])

    # tamper directly with the stored workflow -> executor refuses to run it
    from app.db import session_scope
    from app.models import Workflow
    with session_scope() as db:
        wf = db.query(Workflow).filter_by(agent_id=a["id"]).one()
        wf.steps = steps
        wf.validation = {"valid": True, "status": "pass", "checks": []}  # even if validation is forged
    client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "test"})
    from app.models import Agent
    with session_scope() as db:
        ag = db.get(Agent, a["id"])
        ag.last_test_passed_version = 1
    r = client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "live"}).json()
    run = client.get(f"/api/runs/{r['id']}", headers=auth).json()
    assert run["status"] == "failed"
    send = next(l for l in run["logs"] if l["tool"] == "email.send")
    assert send["status"] == "failed" and "approval" in send["message"].lower()


def test_clarification_and_refine(client, auth):
    a = client.post("/api/studio", headers=auth,
                    json={"prompt": "Weekly, summarize the sales pipeline and email it to my manager"}).json()
    ids = {q["id"] for q in a["questions"]}
    assert "trigger_day" in ids or "source_file" in ids or "report_to" in ids
    # answer everything asked, possibly over several rounds
    for _ in range(4):
        if not a["questions"]:
            break
        ans = {}
        for q in a["questions"]:
            if q["kind"] == "email":
                ans[q["id"]] = "manager@brightpath.example"
            elif q["options"]:
                pick = next((o["value"] for o in q["options"] if "pipeline" in o["label"]), q["options"][0]["value"])
                ans[q["id"]] = pick
        a = client.post(f"/api/studio/{a['id']}/answer", headers=auth, json={"answers": ans}).json()
    assert a["status"] == "ready", a["questions"]
    req = a["requirement"]
    assert req["pattern"] == "report" and req["recipient"]["email"] == "manager@brightpath.example"
    assert req["approval"]["required"] is False  # internal address, policy allows
    run = _run(client, auth, a["id"], "test")
    assert run["status"] == "completed"
    # refine: change schedule and tone in plain words
    a = client.post(f"/api/studio/{a['id']}/refine", headers=auth, json={"text": "make it run every Friday at 5pm"}).json()
    assert a["requirement"]["trigger"]["day_of_week"] == "friday"
    assert a["requirement"]["trigger"]["time"] == "17:00"
    assert a["workflow"]["version"] == 2 and a["status"] == "ready"  # needs a new test


def test_unknown_instruction_asks_for_goal(client, auth):
    a = client.post("/api/studio", headers=auth, json={"prompt": "help me with my work please"}).json()
    assert a["status"] == "draft"
    assert a["questions"][0]["id"] == "purpose"
    a = client.post(f"/api/studio/{a['id']}/answer", headers=auth, json={"answers": {"purpose": "interview_invite"}}).json()
    # candidates.csv matches "candidate"; filter not mentioned -> all; builds
    assert a["requirement"]["entity"]["singular"] == "candidate"


def test_hr_shortlisted(client, auth):
    a = client.post("/api/studio", headers=auth, json={
        "prompt": "Find shortlisted candidates in the candidates spreadsheet and draft formal interview invitations for me to review before sending."}).json()
    assert [q["id"] for q in a["questions"]] == ["trigger"]  # no schedule mentioned -> asks
    a = client.post(f"/api/studio/{a['id']}/answer", headers=auth, json={"answers": {"trigger": "manual"}}).json()
    assert a["status"] == "ready", a["questions"]
    assert a["trigger_label"] == "Runs when you click Run"
    assert a["requirement"]["filter"]["value"] == "Shortlisted"
    assert a["requirement"]["knowledge"]["titles"] == ["Hiring process"]
    run = _run(client, auth, a["id"], "test")
    drafts = next(l for l in run["logs"] if l["tool"] == "ai.draft")["output"]
    assert drafts["count"] == 4


def test_uploads_and_knowledge_search(client, auth):
    csv = b"Full Name,Work Email,Lead Status\nAsha,asha@x.example,New\nBen,not-an-email,New\n"
    r = client.post("/api/files", headers=auth, files={"file": ("trade_show_leads.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["row_count"] == 2
    bad = client.post("/api/files", headers=auth, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 415
    hits = client.post("/api/knowledge/search", headers=auth, json={"query": "late fee on unpaid invoices"}).json()
    assert hits and hits[0]["source_title"] == "Payment terms policy"
    pdf_hits = client.post("/api/knowledge/search", headers=auth, json={"query": "expiry alerts for pharmacy batches"}).json()
    assert pdf_hits and pdf_hits[0]["source_title"] == "Brightpath product brief"  # from the PDF


def test_safety_check_flags_invalid_address(client, auth):
    a = client.post("/api/studio", headers=auth, json={
        "prompt": "Every day at 11am send a follow-up email to new leads in trade_show_leads.csv after I approve"}).json()
    assert a["status"] == "ready", a["questions"]
    run = _run(client, auth, a["id"], "test")
    safety = next(l for l in run["logs"] if l["tool"] == "safety.check")
    assert safety["output"]["errors"] == 1


def test_auth_required(client):
    assert client.get("/api/agents").status_code == 401
    assert client.post("/api/auth/login", json={"email": "priya@brightpath.example", "password": "nope"}).status_code == 401
