"""Clarification + completion.

`build_requirement` merges the parsed instruction with workspace context
(uploaded files, knowledge sources, org safety policy, the user) and with the
user's answers. `checklist` compares the result against a completeness
checklist and emits targeted questions only for genuinely missing or ambiguous
fields. Everything here is deterministic and auditable."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..tools.spreadsheet import distinct_values, infer_roles, read_table

WEEKDAY_LABEL = {d: d.capitalize() for d in
                 ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}

PURPOSE_NOUN = {
    "follow_up": "follow-up emails",
    "payment_reminder": "payment reminders",
    "interview_invite": "interview invitations",
    "welcome": "welcome emails",
    "thank_you": "thank-you notes",
    "custom": "emails",
    "report": "summary report",
}

MEMORY_POLICY = {
    # purpose -> (namespace, cooldown days; None = never contact again for this purpose)
    "follow_up": ("contacted", None),
    "payment_reminder": ("reminded", 7),
    "interview_invite": ("invited", None),
    "welcome": ("welcomed", None),
    "thank_you": ("thanked", None),
    "custom": ("emailed", None),
}

DEFAULT_ENTITY = {
    "follow_up": {"singular": "lead", "plural": "leads"},
    "payment_reminder": {"singular": "invoice", "plural": "invoices"},
    "interview_invite": {"singular": "candidate", "plural": "candidates"},
    "report": {"singular": "lead", "plural": "leads"},
}
DEFAULT_DEPT = {"follow_up": "sales", "payment_reminder": "finance", "interview_invite": "hr", "report": "sales"}

WRITEBACK_DEFAULT = {"follow_up": "Contacted", "payment_reminder": "Reminder sent", "interview_invite": "Invited",
                     "welcome": "Welcomed", "thank_you": "Thanked", "custom": "Emailed"}

# Synonyms used when resolving a filter word ("new", "overdue") against the
# values that actually exist in the status column.
FILTER_SYNONYMS = {
    "new": ["new", "fresh", "not contacted", "uncontacted", "open", "untouched"],
    "fresh": ["new", "fresh"],
    "overdue": ["overdue", "late", "past due", "unpaid"],
    "unpaid": ["unpaid", "overdue", "pending", "due"],
    "late": ["late", "overdue", "past due"],
    "due": ["due", "pending", "unpaid"],
    "pending": ["pending", "awaiting", "in progress"],
    "shortlisted": ["shortlisted", "shortlist", "selected", "interview"],
    "selected": ["selected", "shortlisted"],
    "qualified": ["qualified", "sql", "mql"],
    "hot": ["hot"], "warm": ["warm"], "cold": ["cold"],
    "inactive": ["inactive", "dormant", "churned"],
    "dormant": ["dormant", "inactive"],
    "interested": ["interested", "warm"],
    "won": ["won", "closed won"], "lost": ["lost", "closed lost"],
}


@dataclass
class Context:
    user_name: str
    user_email: str
    org_name: str
    org_domain: str
    files: list[dict[str, Any]]            # {id, name, path, kind, columns, row_count}
    knowledge: list[dict[str, Any]]        # {id, title}
    policy: dict[str, Any] = field(default_factory=dict)


def _q(qid: str, field_: str, kind: str, prompt: str, why: str, options=None, default=None,
       blocking: bool = True, placeholder: str = "") -> dict[str, Any]:
    return {"id": qid, "field": field_, "kind": kind, "prompt": prompt, "why": why,
            "options": options or [], "default": default, "blocking": blocking, "placeholder": placeholder}


_IGNORE = {"my", "our", "the", "spreadsheet", "sheet", "sheets", "excel", "csv", "xlsx", "tracker", "list", "of",
           "workbook", "every", "and", "email", "emails", "send", "read", "check", "data", "file", "report", "it",
           "to", "me", "for", "with", "from", "in", "on", "at", "a", "an", "them", "weekly", "daily", "monthly"}


def _match_files(hint: str | None, entity: dict | None, files: list[dict], text: str = "") -> list[tuple[dict, int]]:
    words = set(re.findall(r"[a-z]+", (hint or "").lower()))
    # words elsewhere in the instruction also count, at lower weight
    extra = {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3} - _IGNORE
    words -= {"my", "our", "the", "spreadsheet", "sheet", "sheets", "excel", "csv", "xlsx", "tracker", "list", "of", "workbook"}
    if entity and re.search(rf"\b{re.escape(entity['singular'])}", text.lower()):
        words |= {entity["singular"], entity["plural"]}
    scored = []
    for f in files:
        name_words = set(re.findall(r"[a-z]+", f["name"].lower()))
        name_words |= {w.rstrip("s") for w in name_words}
        score = 2 * (len(words & name_words) + len({w.rstrip("s") for w in words} & name_words))
        score += len((extra | {w.rstrip("s") for w in extra}) & name_words)
        scored.append((f, score))
    scored.sort(key=lambda x: -x[1])
    return scored


def _resolve_filter(word: str | None, rows: list[dict], roles: dict) -> dict | None:
    """Resolve "new" -> {column: Status, op: equals, value: New}."""
    if not word:
        return None
    status_col = roles.get("status")
    if word in ("overdue", "late") and roles.get("due_date"):
        # overdue can be computed: due date in the past and not paid
        return {"column": roles["due_date"], "op": "before_today", "value": None,
                "and_not": {"column": status_col, "values": ["paid", "settled", "closed"]} if status_col else None,
                "label": f"{word.capitalize()}: due date has passed and not paid"}
    if not status_col:
        return None
    values = [v for v, _ in distinct_values(rows, status_col, 30)]
    syns = FILTER_SYNONYMS.get(word, [word])
    for s in syns:
        for v in values:
            if v.lower() == s:
                return {"column": status_col, "op": "equals", "value": v, "label": f"{status_col} is “{v}”"}
    for s in syns:
        for v in values:
            if s in v.lower():
                return {"column": status_col, "op": "equals", "value": v, "label": f"{status_col} is “{v}”"}
    return None


def _trigger_from_preset(preset: str) -> dict[str, Any]:
    presets = {
        "manual": {"type": "manual"},
        "weekly_monday": {"type": "schedule", "frequency": "weekly", "day_of_week": "monday", "time": "09:00"},
        "weekdays": {"type": "schedule", "frequency": "weekdays", "time": "09:00"},
        "daily": {"type": "schedule", "frequency": "daily", "time": "09:00"},
        "monthly": {"type": "schedule", "frequency": "monthly", "day_of_month": 1, "time": "10:00"},
        "file_updated": {"type": "file_updated"},
    }
    return dict(presets.get(preset, {"type": "manual"}))


def trigger_label(tr: dict | None) -> str:
    if tr and tr.get("type") == "file_updated":
        return f"Runs when {tr.get('file_name') or 'the spreadsheet'} is updated"
    if not tr or tr.get("type") in (None, "manual"):
        return "Runs when you click Run"
    time = tr.get("time") or "09:00"
    h, m = map(int, time.split(":"))
    ampm = f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    f = tr.get("frequency")
    if f == "weekly":
        return f"Every {WEEKDAY_LABEL.get(tr.get('day_of_week') or 'monday')} at {ampm}"
    if f == "weekdays":
        return f"Every weekday at {ampm}"
    if f == "daily":
        return f"Every day at {ampm}"
    if f == "monthly":
        d = tr.get("day_of_month") or 1
        suffix = "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
        return f"On the {d}{suffix} of every month at {ampm}"
    return "Runs when you click Run"


def build_requirement(parsed: dict[str, Any], answers: dict[str, Any], ctx: Context,
                      previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge parse + answers + workspace context into the full requirement."""
    prev = previous or {}
    req: dict[str, Any] = {}
    purpose = answers.get("purpose") or parsed.get("purpose") or prev.get("purpose")
    req["purpose"] = purpose
    req["pattern"] = "report" if purpose == "report" else ("outreach" if purpose else None)
    if answers.get("purpose") and not parsed.get("entity"):
        req["entity"] = DEFAULT_ENTITY.get(purpose, {"singular": "contact", "plural": "contacts"})
    else:
        req["entity"] = parsed.get("entity") or (prev.get("entity") if prev.get("purpose") else None) or \
            DEFAULT_ENTITY.get(purpose or "", {"singular": "record", "plural": "records"})
    req["department"] = (parsed.get("department") if parsed.get("purpose") else None) or \
        (DEFAULT_DEPT.get(purpose) if answers.get("purpose") else None) or \
        (prev.get("department") if prev.get("purpose") else None) or DEFAULT_DEPT.get(purpose or "", "general")
    req["spans"] = parsed.get("spans", [])
    assumptions: list[str] = []

    # ---- trigger ----
    tr = dict(parsed.get("trigger") or {})
    if "trigger" in answers:
        tr = _trigger_from_preset(answers["trigger"])
    if tr.get("type") == "schedule":
        if tr.get("frequency") == "weekly" and not tr.get("day_of_week"):
            if answers.get("trigger_day"):
                tr["day_of_week"] = answers["trigger_day"]
        if not tr.get("time"):
            tr["time"] = "09:00"
            assumptions.append("Runs at 9:00 AM (no time was mentioned)")
    req["trigger"] = tr if tr.get("type") else None

    # ---- data source ----
    source = dict(parsed.get("source") or {})
    file_id = answers.get("source_file") or (prev.get("source") or {}).get("file_id")
    chosen = next((f for f in ctx.files if f["id"] == file_id), None) if file_id else None
    candidates = []
    if not chosen and source.get("hint"):
        exact = [f for f in ctx.files if f["name"].lower() in source["hint"].lower()]
        if exact:
            chosen = exact[0]
            assumptions.append(f"Reads “{chosen['name']}”, the file you named")
    if not chosen and ctx.files:
        candidates = _match_files(source.get("hint"), req["entity"], ctx.files, parsed.get("text", ""))
        top = [c for c in candidates if c[1] > 0]
        if top and (len(top) == 1 or top[0][1] > top[1][1]):
            chosen = top[0][0]
            assumptions.append(f"Reads “{chosen['name']}”, the closest match to your description")
    if chosen and req["pattern"] == "report" and not re.search(rf"\b{re.escape(req['entity']['singular'])}", parsed.get("text", "").lower()):
        if re.search(r"pipeline|deal|opportunit", chosen["name"].lower()):
            req["entity"] = {"singular": "deal", "plural": "deals"}
    req["source"] = {"kind": "spreadsheet", "hint": source.get("hint"),
                     "file_id": chosen["id"] if chosen else None,
                     "file_name": chosen["name"] if chosen else None}
    req["_file_candidates"] = [c[0]["id"] for c in candidates if c[1] > 0] or [f["id"] for f in ctx.files]

    columns: list[str] = []
    rows: list[dict] = []
    roles: dict[str, str] = {}
    if chosen:
        try:
            columns, rows = read_table(chosen["path"], chosen["kind"])
            roles = infer_roles(columns, rows)
        except Exception as exc:  # unreadable file -> surfaced as a question
            req["source"]["error"] = str(exc)
    for k, v in (answers.get("roles") or {}).items():
        roles[k] = v
    if answers.get("recipient_column"):
        roles["email"] = answers["recipient_column"]
    if req["trigger"] and req["trigger"].get("type") == "file_updated":
        req["trigger"]["file_id"] = req["source"]["file_id"]
        req["trigger"]["file_name"] = req["source"]["file_name"]
    req["columns"] = columns
    req["roles"] = roles
    req["row_count"] = len(rows)

    # ---- filter ----
    fw = parsed.get("filter_word") or prev.get("filter_word")
    req["filter_word"] = fw
    filt = None
    if answers.get("filter") == "__all__":
        filt = None
    elif answers.get("filter"):
        col = roles.get("status") or answers.get("filter_column")
        filt = {"column": col, "op": "equals", "value": answers["filter"], "label": f"{col} is “{answers['filter']}”"}
    elif fw and rows:
        filt = _resolve_filter(fw, rows, roles)
    req["filter"] = filt

    # ---- message ----
    tone = answers.get("tone") or parsed.get("tone") or (prev.get("message") or {}).get("tone")
    if not tone:
        tone = "formal" if purpose in ("payment_reminder", "interview_invite") else "friendly"
        if req["pattern"] == "outreach":
            assumptions.append(f"Writes in a {tone} tone")
    sender = answers.get("sender") or parsed.get("sender") or (prev.get("message") or {}).get("sender") or ctx.user_name
    if req["pattern"] and not (answers.get("sender") or parsed.get("sender")):
        assumptions.append(f"Signs emails as {sender}, {ctx.org_name}")
    req["message"] = {"purpose": purpose, "noun": PURPOSE_NOUN.get(purpose or "custom", "emails"),
                      "tone": tone, "sender": sender, "company": ctx.org_name,
                      "mentions": parsed.get("mentions") or [],
                      "instructions": answers.get("instructions") or (prev.get("message") or {}).get("instructions") or ""}

    # ---- recipients ----
    if req["pattern"] == "report":
        to = answers.get("report_to") or parsed.get("fixed_email") or (prev.get("recipient") or {}).get("email")
        req["recipient"] = {"mode": "fixed", "email": to, "role": parsed.get("report_to_role")}
        sum_col = roles.get("amount")
        req["report"] = {"group_by": roles.get("status") or roles.get("owner"), "sum": sum_col,
                         "owner": roles.get("owner")}
    else:
        req["recipient"] = {"mode": "per_row", "column": roles.get("email"), "name_column": roles.get("name") or roles.get("first_name")}

    # ---- approval / safety ----
    external = True
    if req["pattern"] == "report" and req["recipient"].get("email"):
        external = not req["recipient"]["email"].lower().endswith("@" + ctx.org_domain.lower())
    policy_requires = ctx.policy.get("require_approval_external", True) if external else ctx.policy.get("require_approval_internal", False)
    explicit = answers.get("approval")
    if explicit is None:
        explicit = parsed.get("approval_explicit")
    elif isinstance(explicit, str):
        explicit = explicit == "review"
    required = bool(policy_requires or explicit is True or (explicit is None and req["pattern"] == "outreach"))
    req["approval"] = {
        "required": required,
        "explicit": explicit,
        "policy_enforced": bool(policy_requires),
        "external": external,
        "reason": ("Your workspace safety policy requires approval before emailing people outside "
                   f"{ctx.org_name}." if policy_requires and external else
                   "You asked to review before anything is sent." if explicit else
                   "Emails go to real people, so Jerry asks before sending." if required else
                   "Internal report — sends without approval."),
    }
    if required and explicit is not True and policy_requires:
        assumptions.append("Asks for your approval before sending (workspace safety policy)")

    # ---- memory ----
    if req["pattern"] == "outreach":
        ns, cooldown = MEMORY_POLICY.get(purpose, ("emailed", None))
        key_col = roles.get("invoice") if purpose == "payment_reminder" and roles.get("invoice") else roles.get("email")
        req["memory"] = {"enabled": True, "namespace": ns, "key_column": key_col, "cooldown_days": cooldown,
                         "description": (f"Remembers every {req['entity']['singular']} it has emailed so nobody gets the same email twice"
                                         if cooldown is None else
                                         f"Waits {cooldown} days before reminding the same {req['entity']['singular']} again")}
    else:
        req["memory"] = {"enabled": False}

    # ---- follow-up sequence (outreach only) ----
    seq = answers.get("sequence") if "sequence" in answers else (parsed.get("sequence") or prev.get("sequence"))
    if seq and req["pattern"] == "outreach" and seq.get("after_days"):
        req["sequence"] = {"enabled": True, "after_days": int(seq["after_days"]), "max_touches": int(seq.get("max_touches") or 2)}
        req["memory"]["description"] = (f"Follows up again after {seq['after_days']} days with no reply — up to "
                                        f"{req['sequence']['max_touches']} emails per {req['entity']['singular']} — and stops the moment someone replies")
    else:
        req["sequence"] = {"enabled": False}

    # ---- write-back to the source spreadsheet ----
    wb = answers.get("writeback") if "writeback" in answers else (parsed.get("writeback") or prev.get("writeback"))
    if wb and req["pattern"] == "outreach" and req["source"].get("file_id") and (wb.get("enabled", True)):
        value = wb.get("value") or WRITEBACK_DEFAULT.get(purpose or "", "Emailed")
        req["writeback"] = {"enabled": True, "column": roles.get("status") or "Status", "value": value,
                            "date_column": "Last contacted"}
    else:
        req["writeback"] = {"enabled": False}

    # ---- compliance ----
    req["compliance"] = {"suppression": req["pattern"] == "outreach"}

    # ---- knowledge ----
    picked = pick_knowledge(ctx.knowledge, req["department"], purpose)
    req["knowledge"] = {"enabled": bool(picked) and req["pattern"] == "outreach",
                        "source_ids": [k["id"] for k in picked],
                        "titles": [k["title"] for k in picked],
                        "hint": parsed.get("knowledge_hint")}

    # ---- name + goal ----
    req["name"] = make_name(req)
    req["goal"] = make_goal(req)
    req["assumptions"] = assumptions
    return req


KNOWLEDGE_TOPICS = {
    "sales": ["product", "brief", "pricing", "price", "case", "catalog", "catalogue", "brochure", "offer", "features", "plans"],
    "finance": ["payment", "invoice", "billing", "terms", "credit", "collection", "finance"],
    "hr": ["hiring", "interview", "recruit", "handbook", "onboarding", "hr", "leave", "people"],
    "support": ["faq", "support", "troubleshoot", "help", "returns", "refund", "warranty"],
}


def pick_knowledge(sources: list[dict], department: str, purpose: str | None) -> list[dict]:
    """Attach the documents relevant to this agent's job (all of them if none match)."""
    if not sources:
        return []
    words = KNOWLEDGE_TOPICS.get(department or "", [])
    if purpose == "welcome":
        words = words + ["onboarding", "getting started"]
    picked = [k for k in sources if any(w in k["title"].lower() for w in words)]
    return picked or sources


def make_name(req: dict) -> str:
    tr = req.get("trigger") or {}
    prefix = ""
    if tr.get("frequency") == "weekly":
        prefix = (tr.get("day_of_week") or "weekly").capitalize() + " "
        if prefix.strip() == "Weekly":
            prefix = "Weekly "
    elif tr.get("frequency") in ("daily", "weekdays"):
        prefix = "Daily "
    elif tr.get("frequency") == "monthly":
        prefix = "Monthly "
    ent = req["entity"]["singular"]
    p = req.get("purpose")
    if p == "report":
        return f"{prefix}{ent} report".strip().capitalize() if not prefix else f"{prefix}{ent} report"
    noun = {"follow_up": "follow-ups", "payment_reminder": "payment reminders", "interview_invite": "interview invites",
            "welcome": "welcome emails", "thank_you": "thank-you notes"}.get(p, "outreach")
    fw = req.get("filter_word")
    core = f"{fw + ' ' if fw and p != 'payment_reminder' else ''}{ent} {noun}"
    if p == "payment_reminder":
        core = f"{'overdue ' if fw in ('overdue', 'late', 'unpaid') else ''}{ent} reminders"
    name = f"{prefix}{core}"
    return name[0].upper() + name[1:]


def make_goal(req: dict) -> str:
    ent = req["entity"]["plural"]
    src = req["source"].get("file_name") or "your spreadsheet"
    when = trigger_label(req.get("trigger")).replace("Runs when you click Run", "When you run it")
    if (req.get("trigger") or {}).get("type") == "file_updated":
        when = f"Whenever {req['source'].get('file_name') or 'the spreadsheet'} is updated"
    if req.get("pattern") == "report":
        to = req["recipient"].get("email") or "the recipient you choose"
        return f"{when}, read {src}, summarise your {ent} and email the report to {to}."
    filt = req.get("filter")
    who = f"{req.get('filter_word')} {ent}" if req.get("filter_word") else ent
    goal = f"{when}, read {src}, find {who}"
    if filt:
        goal += f" ({filt['label']})"
    goal += f", skip anyone already handled, and draft personalised {req['message']['noun']}"
    goal += ", then send only the ones you approve" if req["approval"]["required"] else ", then send them"
    if (req.get("sequence") or {}).get("enabled"):
        goal += f", following up after {req['sequence']['after_days']} days if there’s no reply"
    if (req.get("writeback") or {}).get("enabled"):
        goal += f", and mark them “{req['writeback']['value']}” in the sheet"
    goal += "."
    return goal


def checklist(req: dict, ctx: Context) -> list[dict[str, Any]]:
    """Completeness checklist -> targeted clarification questions."""
    qs: list[dict[str, Any]] = []
    if not req.get("purpose"):
        qs.append(_q("purpose", "goal", "choice",
                     "What should this agent do?",
                     "I couldn’t tell the main job from your description. Pick the closest one, or describe it again.",
                     options=[
                         {"value": "follow_up", "label": "Follow up with leads", "hint": "Sales"},
                         {"value": "payment_reminder", "label": "Remind about overdue invoices", "hint": "Finance"},
                         {"value": "interview_invite", "label": "Invite shortlisted candidates", "hint": "HR"},
                         {"value": "report", "label": "Email a summary report", "hint": "Any team"},
                     ]))
        return qs

    src = req["source"]
    if not src.get("file_id") or src.get("error"):
        cand = [f for f in ctx.files if f["id"] in req.get("_file_candidates", [])] or ctx.files
        qs.append(_q("source_file", "source", "file",
                     f"Which spreadsheet has your {req['entity']['plural']}?",
                     (src.get("error") + " — choose another file." if src.get("error") else
                      "More than one file could match, so I want to be sure I read the right one." if len(cand) > 1 else
                      "You haven’t uploaded a spreadsheet yet. Upload one and I’ll read its columns."),
                     options=[{"value": f["id"], "label": f["name"], "hint": f"{f['row_count']} rows · {len(f['columns'])} columns"} for f in cand]))
        return qs  # the remaining checks need the file's columns

    roles = req["roles"]
    if req["pattern"] == "outreach" and not roles.get("email"):
        qs.append(_q("recipient_column", "recipient", "choice",
                     "Which column has the email addresses?",
                     "I need an email address for every person, and no column looked like one.",
                     options=[{"value": c, "label": c} for c in req["columns"]]))

    if req.get("filter_word") and not req.get("filter"):
        status_col = roles.get("status")
        if status_col:
            opts = [{"value": v, "label": v, "hint": f"{n} rows"} for v, n in
                    distinct_values(_rows_cache(req, ctx), status_col)]
            opts.append({"value": "__all__", "label": f"All {req['entity']['plural']}", "hint": "No filter"})
            qs.append(_q("filter", "filter", "choice",
                         f"How do I recognise a “{req['filter_word']}” {req['entity']['singular']}?",
                         f"Your “{status_col}” column has no value called “{req['filter_word']}”. Pick the one that means it.",
                         options=opts))
        else:
            qs.append(_q("filter", "filter", "choice",
                         f"How do I recognise a “{req['filter_word']}” {req['entity']['singular']}?",
                         "There’s no status column, so I can’t tell them apart yet.",
                         options=[{"value": "__all__", "label": f"Include all {req['entity']['plural']}"}]))

    tr = req.get("trigger")
    if tr is None:
        qs.append(_q("trigger", "trigger", "choice", "When should it run?",
                     "You didn’t say when. You can always run it by hand as well.",
                     options=[
                         {"value": "manual", "label": "Only when I click Run"},
                         {"value": "weekly_monday", "label": "Every Monday at 9:00 AM"},
                         {"value": "weekdays", "label": "Every weekday at 9:00 AM"},
                         {"value": "monthly", "label": "1st of every month at 10:00 AM"},
                         {"value": "file_updated", "label": "Whenever the spreadsheet is updated", "hint": "Runs on each new upload"},
                     ], default="manual"))
    elif tr.get("frequency") == "weekly" and not tr.get("day_of_week"):
        qs.append(_q("trigger_day", "trigger", "choice", "Which day of the week?",
                     "You said weekly but not which day.",
                     options=[{"value": d, "label": WEEKDAY_LABEL[d]} for d in
                              ["monday", "tuesday", "wednesday", "thursday", "friday"]], default="monday"))

    if req["pattern"] == "report" and not req["recipient"].get("email"):
        role = req["recipient"].get("role")
        qs.append(_q("report_to", "recipient", "email",
                     f"What’s your {role}’s email address?" if role else "Who should receive the report?",
                     "The report is emailed, so I need an address.", placeholder=f"name@{ctx.org_domain}"))

    if req["pattern"] == "outreach" and req["approval"]["explicit"] is None and not req["approval"]["policy_enforced"]:
        qs.append(_q("approval", "approval", "choice", "Should I wait for your approval before sending?",
                     "These emails go to real people. Reviewing first is safer.",
                     options=[{"value": "review", "label": "Yes, show me the drafts first", "hint": "Recommended"},
                              {"value": "auto", "label": "No, send them automatically"}], default="review"))
    return qs


_ROWS: dict[str, list[dict]] = {}


def _rows_cache(req: dict, ctx: Context) -> list[dict]:
    fid = req["source"]["file_id"]
    f = next((x for x in ctx.files if x["id"] == fid), None)
    if not f:
        return []
    try:
        return read_table(f["path"], f["kind"])[1]
    except Exception:
        return []
