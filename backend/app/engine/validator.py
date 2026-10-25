"""Workflow Validation — deterministic graph checks, no ML. A workflow that
fails any check cannot be tested or run."""
from __future__ import annotations

from typing import Any

from ..tools.registry import TOOLS


def _check(cid: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def validate(steps: list[dict[str, Any]], req: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or {}
    checks: list[dict[str, str]] = []
    ids = [s["id"] for s in steps]
    index = {s["id"]: i for i, s in enumerate(steps)}
    tools_in_order = [s["tool"] for s in steps]

    # 1. every step bound to a registered tool
    unknown = [s["tool"] for s in steps if s["tool"] not in TOOLS]
    checks.append(_check("tools", "Every step uses a known tool",
                         "fail" if unknown else "pass",
                         f"Unknown tools: {', '.join(unknown)}" if unknown else f"{len(steps)} steps, all bound to registered tools."))

    # 2. required params present
    missing = []
    for s in steps:
        t = TOOLS.get(s["tool"])
        if not t:
            continue
        for p in t.required_params:
            if s["params"].get(p) in (None, "", []):
                missing.append(f"{s['label']} → {p}")
    checks.append(_check("params", "Every step has the settings it needs",
                         "fail" if missing else "pass",
                         "Missing: " + "; ".join(missing) if missing else "All required settings are filled in."))

    # 3. graph: unique ids, deps exist and point backwards (acyclic)
    bad = []
    if len(set(ids)) != len(ids):
        bad.append("duplicate step ids")
    for s in steps:
        for d in s.get("depends_on", []):
            if d not in index:
                bad.append(f"{s['id']} depends on missing {d}")
            elif index[d] >= index[s["id"]]:
                bad.append(f"{s['id']} depends on a later step ({d}) — cycle")
    checks.append(_check("graph", "Steps run in a valid order with no loops",
                         "fail" if bad else "pass", "; ".join(bad) if bad else "The step graph is acyclic."))

    # 4. data dependencies: each step's inputs were produced earlier
    produced: set[str] = set()
    unmet = []
    for s in steps:
        t = TOOLS.get(s["tool"])
        if not t:
            continue
        for need in t.consumes:
            # approval output "approved" satisfies drafts consumers downstream
            if need not in produced and not (need == "drafts" and "approved" in produced):
                unmet.append(f"{s['label']} needs {need}")
        produced.update(t.produces)
    checks.append(_check("data", "Each step gets the data it needs",
                         "fail" if unmet else "pass",
                         "; ".join(unmet) if unmet else "Every input is produced by an earlier step."))

    # 5. ordering rules: generate before send, approval before send when required
    order_issues = []
    if "email.send" in tools_in_order:
        send_i = tools_in_order.index("email.send")
        gen = [i for i, t in enumerate(tools_in_order) if t in ("ai.draft", "ai.draft_report")]
        if not gen or min(gen) > send_i:
            order_issues.append("emails are sent before they are written")
        if "safety.check" in tools_in_order and tools_in_order.index("safety.check") > send_i:
            order_issues.append("safety check happens after sending")
    if "memory.record" in tools_in_order and "email.send" in tools_in_order:
        if tools_in_order.index("memory.record") < tools_in_order.index("email.send"):
            order_issues.append("memory is updated before emails are sent")
    checks.append(_check("order", "Nothing is sent before it’s written and checked",
                         "fail" if order_issues else "pass",
                         "; ".join(order_issues).capitalize() if order_issues else "Draft → check → send order is correct."))

    # 6. safety: sensitive actions gated by approval when policy/requirement says so
    approval_needed = req.get("approval", {}).get("required", True)
    gate_issues = []
    for i, s in enumerate(steps):
        if s.get("sensitive") or TOOLS.get(s["tool"], None) and TOOLS[s["tool"]].sensitive:
            has_gate = "approval.request" in tools_in_order[:i]
            if approval_needed and not has_gate:
                gate_issues.append(f"“{s['label']}” runs without an approval step")
    if gate_issues:
        checks.append(_check("safety", "Sensitive actions wait for approval", "fail", "; ".join(gate_issues)))
    elif approval_needed:
        checks.append(_check("safety", "Sensitive actions wait for approval", "pass",
                             "Sending is gated behind your approval."))
    else:
        checks.append(_check("safety", "Sensitive actions wait for approval", "warn",
                             "This agent sends without asking — allowed for internal email by your workspace policy."))

    # 7. dedupe memory for outreach
    if req.get("pattern") == "outreach":
        ok = "memory.exclude" in tools_in_order and "memory.record" in tools_in_order
        key = req.get("memory", {}).get("key_column")
        checks.append(_check("memory", "Never emails the same person twice",
                             "pass" if ok and key else "fail",
                             f"Uses “{key}” to remember who was emailed." if ok and key else
                             "No memory key — duplicates possible."))

    # 7b. do-not-contact list respected before drafting
    if req.get("pattern") == "outreach" and "compliance.suppress" in tools_in_order:
        ok = tools_in_order.index("compliance.suppress") < tools_in_order.index("ai.draft") if "ai.draft" in tools_in_order else True
        checks.append(_check("compliance", "Respects the do-not-contact list", "pass" if ok else "fail",
                             "Opted-out people are removed before any email is written." if ok else
                             "The do-not-contact check runs after drafting."))
    if "spreadsheet.update" in tools_in_order and "email.send" in tools_in_order:
        ok = tools_in_order.index("spreadsheet.update") > tools_in_order.index("email.send")
        checks.append(_check("writeback", "Updates the sheet only after sending", "pass" if ok else "fail",
                             "Only people who were actually emailed are marked in the sheet." if ok else
                             "The sheet would be updated before emails are sent."))

    # 8. recipient
    if "email.send" in tools_in_order:
        if req.get("pattern") == "report":
            ok = bool(req.get("recipient", {}).get("email"))
            detail = f"Report goes to {req['recipient']['email']}." if ok else "No recipient address."
        else:
            col = req.get("roles", {}).get("email")
            ok = bool(col) and col in (req.get("columns") or [col])
            detail = f"Addresses come from the “{col}” column." if ok else "No email column found."
        checks.append(_check("recipient", "Every email has a recipient", "pass" if ok else "fail", detail))

    # 9. volume cap
    cap = int(policy.get("max_emails_per_run", 50))
    rc = req.get("row_count") or 0
    if req.get("pattern") == "outreach":
        checks.append(_check("volume", f"Stays under {cap} emails per run",
                             "warn" if rc > cap else "pass",
                             f"The file has {rc} rows; runs stop at {cap} emails." if rc > cap else
                             f"The file has {rc} rows — within the {cap}-email limit."))

    status = "fail" if any(c["status"] == "fail" for c in checks) else (
        "warn" if any(c["status"] == "warn" for c in checks) else "pass")
    return {"valid": status != "fail", "status": status, "checks": checks}
