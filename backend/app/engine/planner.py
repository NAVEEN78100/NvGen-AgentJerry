"""Planning / Workflow Generation + Tool grounding.

Converts a *complete* requirement into an ordered step graph where every step
is bound to a registered tool with concrete parameters and a plain-language
reason for existing (auditability)."""
from __future__ import annotations

from typing import Any

from ..tools.registry import TOOLS


def _step(sid: str, tool: str, label: str, description: str, why: str, params: dict[str, Any],
          depends_on: list[str]) -> dict[str, Any]:
    t = TOOLS[tool]
    return {"id": sid, "tool": tool, "label": label, "description": description, "why": why,
            "params": params, "depends_on": depends_on, "category": t.category,
            "sensitive": t.sensitive, "side_effect": t.side_effect}


def plan(req: dict[str, Any]) -> list[dict[str, Any]]:
    ent = req["entity"]
    roles = req.get("roles", {})
    steps: list[dict[str, Any]] = []

    def add(tool: str, label: str, description: str, why: str, params: dict[str, Any]) -> str:
        sid = f"s{len(steps) + 1}"
        deps = [steps[-1]["id"]] if steps else []
        steps.append(_step(sid, tool, label, description, why, params, deps))
        return sid

    add("spreadsheet.read", f"Read {req['source']['file_name']}",
        f"Load all {ent['plural']} from your spreadsheet.",
        "Your instruction names this spreadsheet as the data source.",
        {"file_id": req["source"]["file_id"], "file_name": req["source"]["file_name"]})

    f = req.get("filter")
    if f:
        add("data.filter", f"Keep only {req.get('filter_word') or 'matching'} {ent['plural']}",
            f"Keep rows where {f['label']}.",
            f"You asked for {req.get('filter_word')} {ent['plural']} only.",
            {k: v for k, v in f.items() if k != "label"} | {"label": f["label"]})

    if req["pattern"] == "report":
        rep = req.get("report", {})
        add("data.summarize", f"Summarise your {ent['plural']}",
            "Count rows, total values and pick out highlights.",
            "A report needs the numbers before it can be written.",
            {"group_by": rep.get("group_by"), "sum": rep.get("sum"), "owner": rep.get("owner"),
             "name_column": roles.get("name"), "company_column": roles.get("company")})
        add("ai.draft_report", "Write the report email",
            f"Turn the summary into an email for {req['recipient']['email']}.",
            "You asked for the summary to be emailed.",
            {"to": req["recipient"]["email"], "tone": req["message"]["tone"], "sender": req["message"]["sender"],
             "company": req["message"]["company"], "entity": ent})
    else:
        mem = req["memory"]
        add("memory.exclude", f"Skip {ent['plural']} already {mem['namespace']}",
            mem["description"] + ".",
            "Prevents duplicate emails across weekly runs.",
            {"namespace": mem["namespace"], "key_column": mem["key_column"], "cooldown_days": mem.get("cooldown_days")})
        if req["knowledge"]["enabled"]:
            add("knowledge.retrieve", "Look up relevant company knowledge",
                f"Search {', '.join(req['knowledge']['titles'][:3])} for what’s relevant to each {ent['singular']}.",
                "Grounds every email in your real product and policy facts instead of generic text.",
                {"source_ids": req["knowledge"]["source_ids"],
                 "query_columns": [c for c in (roles.get("industry"), roles.get("interest"), roles.get("role"), roles.get("notes")) if c],
                 "purpose": req["purpose"]})
        add("ai.draft", f"Draft personalised {req['message']['noun']}",
            f"Write one {req['message']['tone']} email per {ent['singular']} using their details.",
            f"Your instruction asks for {req['message']['noun']}.",
            {"purpose": req["purpose"], "tone": req["message"]["tone"], "sender": req["message"]["sender"],
             "company": req["message"]["company"], "roles": roles, "instructions": req["message"].get("instructions", ""),
             "mentions": req["message"].get("mentions", []),
             "entity": ent})

    add("safety.check", "Check every draft", "Flag invalid addresses, missing names, placeholders and risky wording.",
        "Catches mistakes before a person ever sees them.", {})

    if req["approval"]["required"]:
        add("approval.request", "Wait for your approval",
            "Pause and show every draft. You can approve, edit or reject each one.",
            req["approval"]["reason"], {"action": "email.send"})

    add("email.send", "Send approved emails" if req["approval"]["required"] else "Send emails",
        "Send each email once, using the approved version.",
        "Delivers the emails you asked for.",
        {"recipient_column": roles.get("email"), "name_column": roles.get("name")})

    if req["pattern"] == "outreach":
        mem = req["memory"]
        add("memory.record", "Remember who was emailed", "Save each recipient so future runs skip them.",
            "Lets the next run know who has already been handled.",
            {"namespace": mem["namespace"], "key_column": mem["key_column"]})

    add("notify.summary", "Send you a summary", "Post what happened to your notifications.",
        "So you always know what the agent did.", {})
    return steps
