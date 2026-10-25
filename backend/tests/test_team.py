"""Team, approver routing and the four-eyes policy."""


def _login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_approver_routing_and_four_eyes(client, auth):
    arun = _login(client, "arun@brightpath.example")
    team = client.get("/api/team", headers=auth).json()
    by = {m["email"]: m for m in team}
    priya_id, arun_id = by["priya@brightpath.example"]["id"], by["arun@brightpath.example"]["id"]
    assert "Daily overdue invoice reminders" in by["priya@brightpath.example"]["approves_for"]

    # seeded finance approval: built by Arun, assigned to Priya
    pend = client.get("/api/approvals?status=pending", headers=arun).json()
    fin = next(p for p in pend if "payment reminders" in p["title"])
    assert fin["assigned_to"]["id"] == priya_id and fin["can_decide"] is False
    assert "assigned to Priya" in fin["blocked_reason"]
    assert all(p["id"] != fin["id"] for p in client.get("/api/approvals?status=pending&mine=true", headers=arun).json())
    ap = client.get(f"/api/approvals/{fin['id']}", headers=arun).json()
    r = client.post(f"/api/approvals/{fin['id']}/decide", headers=arun,
                    json={"decisions": [{"id": i["id"], "status": "approved"} for i in ap["items"]]})
    assert r.status_code == 409

    # members can't add people; admins can
    assert client.post("/api/team", headers=arun, json={"name": "X Y", "email": "x@brightpath.example"}).status_code == 403
    new = client.post("/api/team", headers=auth, json={"name": "Divya Nair", "email": "divya@brightpath.example",
                                                       "title": "Sales Executive"}).json()
    assert new["temporary_password"]
    assert client.post("/api/auth/login", json={"email": "divya@brightpath.example",
                                                "password": new["temporary_password"]}).status_code == 200

    # four-eyes: Priya can't approve emails from an agent she built
    client.patch("/api/settings", headers=auth, json={"policy": {"four_eyes": True}})
    a = client.post("/api/studio", headers=auth, json={"prompt": "Every Monday at 9am, find shortlisted candidates in candidates.csv "
                                                       "and draft formal interview invitations for me to review."}).json()
    assert a["status"] == "ready", a["questions"]
    client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "test"})
    r = client.post(f"/api/agents/{a['id']}/runs", headers=auth, json={"mode": "live"})
    assert r.status_code == 200, r.text
    r = r.json()
    run = client.get(f"/api/runs/{r['id']}", headers=auth).json()
    ap = client.get(f"/api/approvals/{run['approval_id']}", headers=auth).json()
    assert ap["can_decide"] is False and "second person" in ap["blocked_reason"]
    # route it to Arun instead -> he can decide, pending approval re-assigned
    client.patch(f"/api/agents/{a['id']}", headers=auth, json={"approver_id": arun_id})
    ap = client.get(f"/api/approvals/{run['approval_id']}", headers=arun).json()
    assert ap["assigned_to"]["id"] == arun_id and ap["can_decide"] is True
    r = client.post(f"/api/approvals/{ap['id']}/decide", headers=arun,
                    json={"decisions": [{"id": i["id"], "status": "rejected"} for i in ap["items"]]})
    assert r.status_code == 200
    client.patch("/api/settings", headers=auth, json={"policy": {"four_eyes": False}})
    # notifications are targeted
    notes = client.get("/api/notifications", headers=arun).json()["items"]
    assert any("need your approval" in n["title"] for n in notes)
