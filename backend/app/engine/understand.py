"""Requirement Understanding (offline engine).

Turns a free-text instruction into the structured requirement schema and
records *which words* produced each field (spans), so the UI can show the user
exactly how their sentence was understood. The Claude-backed path in
`llm.py` produces the same schema; both feed the same deterministic
clarification + planning pipeline."""
from __future__ import annotations

import re
from typing import Any

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WD_SHORT = {d[:3]: d for d in WEEKDAYS}

ENTITY_LEXICON: dict[str, tuple[str, str, str]] = {
    # word -> (singular, plural, department)
    "lead": ("lead", "leads", "sales"),
    "prospect": ("prospect", "prospects", "sales"),
    "customer": ("customer", "customers", "sales"),
    "client": ("client", "clients", "sales"),
    "contact": ("contact", "contacts", "sales"),
    "candidate": ("candidate", "candidates", "hr"),
    "applicant": ("applicant", "applicants", "hr"),
    "employee": ("employee", "employees", "hr"),
    "new hire": ("new hire", "new hires", "hr"),
    "invoice": ("invoice", "invoices", "finance"),
    "payment": ("payment", "payments", "finance"),
    "vendor": ("vendor", "vendors", "finance"),
    "ticket": ("ticket", "tickets", "support"),
    "student": ("student", "students", "general"),
    "member": ("member", "members", "general"),
    "deal": ("deal", "deals", "sales"),
}

PURPOSES: list[tuple[str, str]] = [
    # (regex, purpose) — order matters: first match wins for purpose
    (r"\b(weekly|daily|monthly)?\s*(summary|summari[sz]e|report|digest|overview|recap|dashboard)\b", "report"),
    (r"\bfollow[\s-]?ups?\b", "follow_up"),
    (r"\b(payment\s+)?remind(er|ers)?\b|\bchase\b|\bcollect(ion)?\b", "payment_reminder"),
    (r"\binterview\b|\binvit(e|ation|ations)\b", "interview_invite"),
    (r"\bwelcome\b|\bonboard(ing)?\b", "welcome"),
    (r"\bthank(\s+you|s)?\b", "thank_you"),
    (r"\bemails?\b|\bmessages?\b|\bmail\b|\breach\s+out\b|\bwrite\s+to\b|\bnotify\b", "custom"),
]

PURPOSE_DEFAULT_ENTITY = {
    "follow_up": "lead", "payment_reminder": "invoice", "interview_invite": "candidate",
    "welcome": "customer", "thank_you": "customer", "custom": "contact", "report": "lead",
}

ACTION_PATTERNS = [
    (r"\b(generate|draft|write|create|prepare|compose)\b[^.,;]*?\b(e-?mails?|messages?|follow[\s-]?ups?|reminders?|invitations?|invites?)\b", "draft"),
    (r"\bpersonali[sz]ed\b", "personalize"),
    (r"\b(send|email|mail|notify)\b", "send"),
    (r"\b(identify|find|pick|filter|select|spot|detect|check for|look for)\b", "identify"),
    (r"\b(read|check|scan|open|look at|go through|review my|load)\b", "read"),
]

FILTER_ADJ = r"(new|fresh|hot|warm|cold|qualified|unqualified|shortlisted|selected|rejected|overdue|unpaid|pending|late|inactive|active|lost|won|open|closed|interested|unresponsive|dormant|due)"

APPROVAL_YES = r"(for (my )?approval|approv(e|al)|show (them|it|those|these)?\s*to me|show me|before (sending|send|it goes|they go)|let me (review|check|see)|review (them|it)? ?first|my (ok|okay|sign[\s-]?off)|confirm with me|ask me (first|before))"
APPROVAL_NO = r"(automatically send|send (them )?automatically|without (asking|approval|my approval|review)|no approval|directly send|send directly|auto[\s-]?send)"

SPREADSHEET_WORDS = r"(spreadsheets?|sheets?|excel|xlsx|csv|crm export|tracker|lead list|list of [a-z ]+|google sheet|workbook)"
DOC_WORDS = r"(pdfs?|documents?|docs|policy|policies|brochure|guidelines?|knowledge base|handbook|product brief|price list|pricing)"

TONE_WORDS = {
    "friendly": r"\b(friendly|warm|casual|cheerful)\b",
    "formal": r"\b(formal|professional|polite|respectful)\b",
    "concise": r"\b(short|brief|concise|crisp|to the point)\b",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _span(spans: list[dict], m: re.Match, field: str, label: str, group: int = 0) -> None:
    s, e = m.span(group)
    if s < 0:
        return
    for sp in spans:  # avoid overlaps — first claim wins
        if not (e <= sp["start"] or s >= sp["end"]):
            return
    spans.append({"start": s, "end": e, "text": m.group(group), "field": field, "label": label})


def parse_time(text: str) -> tuple[str | None, re.Match | None]:
    m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", text, re.I)
    if m:
        h = int(m.group(1)); mi = int(m.group(2) or 0); ap = (m.group(3) or "").lower().replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if not ap and 1 <= h <= 7:  # "at 5" in a work context means 5 pm
            h += 12
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}", m
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
    if m:
        h = int(m.group(1)); mi = int(m.group(2) or 0)
        if m.group(3).lower() == "pm" and h < 12:
            h += 12
        if m.group(3).lower() == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}", m
    for word, t in (("first thing", "09:00"), ("morning", "09:00"), ("noon", "12:00"), ("afternoon", "14:00"),
                    ("end of (the )?day", "17:30"), ("evening", "18:00")):
        m = re.search(rf"\b{word}\b", text, re.I)
        if m:
            return t, m
    return None, None


def parse_trigger(text: str, spans: list[dict]) -> dict[str, Any]:
    t = text.lower()
    trig: dict[str, Any] = {"type": None, "frequency": None, "day_of_week": None, "day_of_month": None, "time": None}
    m = re.search(r"\b(every|each|on)\s+(" + "|".join(WEEKDAYS) + r")s?\b", t) or \
        re.search(r"\b(" + "|".join(WEEKDAYS) + r")s\b", t)
    if m:
        day = m.group(m.lastindex)
        trig.update(type="schedule", frequency="weekly", day_of_week=day.rstrip("s") if day.rstrip("s") in WEEKDAYS else day)
        _span(spans, m, "trigger", "When it runs")
    elif (m := re.search(r"\b(every\s+weekday|weekdays|monday\s+to\s+friday|mon-fri)\b", t)):
        trig.update(type="schedule", frequency="weekdays")
        _span(spans, m, "trigger", "When it runs")
    elif (m := re.search(r"\b(every\s+day|daily|each\s+day|every\s+morning|every\s+evening|each\s+morning)\b", t)):
        trig.update(type="schedule", frequency="daily")
        _span(spans, m, "trigger", "When it runs")
    elif (m := re.search(r"\b(every\s+week|weekly|once\s+a\s+week)\b", t)):
        trig.update(type="schedule", frequency="weekly")
        _span(spans, m, "trigger", "When it runs")
    elif (m := re.search(r"\b(every\s+month|monthly|once\s+a\s+month|(on\s+the\s+)?(1st|first)\s+of\s+(every|each|the)\s+month|end\s+of\s+(every|each|the)\s+month)\b", t)):
        trig.update(type="schedule", frequency="monthly", day_of_month=28 if "end of" in m.group(0) else 1)
        _span(spans, m, "trigger", "When it runs")
    elif (m := re.search(r"\b(when i (click|ask|say|press)|on demand|manually|whenever i (want|ask|need))\b", t)):
        trig.update(type="manual")
        _span(spans, m, "trigger", "When it runs")
    tm, tmatch = parse_time(text)
    if tm and trig["type"] == "schedule":
        trig["time"] = tm
        _span(spans, tmatch, "trigger", "Time of day")
    return trig


def understand(text: str, user_name: str = "") -> dict[str, Any]:
    """Parse the instruction. Returns a *partial* requirement: fields that were
    not mentioned stay None so the completeness checklist can find them."""
    spans: list[dict] = []
    t = text.lower()

    trigger = parse_trigger(text, spans)

    # purpose
    purpose = None
    purpose_match = None
    for pat, p in PURPOSES:
        m = re.search(pat, t)
        if m:
            purpose = p
            purpose_match = m
            break

    # entity + filter adjective ("new leads", "overdue invoices")
    entity_key = None
    filter_word = None
    ent_alt = "|".join(sorted((re.escape(k) for k in ENTITY_LEXICON), key=len, reverse=True))
    m = re.search(rf"\b{FILTER_ADJ}\s+({ent_alt})(e?s)?\b", t)
    if m:
        filter_word = m.group(1)
        entity_key = m.group(2)
        _span(spans, m, "audience", "Who it targets")
    else:
        m = re.search(rf"\b(all|every|each)?\s*(my\s+)?({ent_alt})(e?s)?\b", t)
        if m:
            entity_key = m.group(3)
            _span(spans, m, "audience", "Who it targets", 0)
        m2 = re.search(rf"\b(that are|which are|who are|marked( as)?|with status)\s+[\"']?{FILTER_ADJ}[\"']?", t)
        if m2:
            filter_word = m2.group(3)
            _span(spans, m2, "audience", "Who it targets")
    if purpose == "payment_reminder" and not filter_word and re.search(r"\boverdue|unpaid|late\b", t):
        filter_word = re.search(r"\b(overdue|unpaid|late)\b", t).group(1)

    if purpose is None and entity_key:
        purpose = "custom"
    if entity_key is None and purpose:
        entity_key = PURPOSE_DEFAULT_ENTITY.get(purpose)
    singular, plural, dept = ENTITY_LEXICON.get(entity_key or "", (entity_key or "record", f"{entity_key or 'record'}s", "general"))
    if purpose == "interview_invite":
        dept = "hr"
    if purpose == "payment_reminder":
        dept = "finance"

    # actions mentioned (for the annotation + to detect "draft only")
    actions = []
    for pat, a in ACTION_PATTERNS:
        for m in re.finditer(pat, t):
            actions.append(a)
            _span(spans, m, "action", "What it does")
    if purpose_match:
        _span(spans, purpose_match, "action", "What it does")
    wants_send = "send" in actions or purpose in ("follow_up", "payment_reminder", "interview_invite", "welcome", "thank_you", "report")

    # data source
    source = {"kind": None, "hint": None}
    m = re.search(r"\b[\w-]+\.(csv|xlsx)\b", t)
    if m:
        source = {"kind": "spreadsheet", "hint": m.group(0)}
        _span(spans, m, "data", "Where the data is")
    else:
        m = re.search(rf"\b((my|our|the)\s+)?([a-z]+\s+)?{SPREADSHEET_WORDS}", t)
        if m:
            source = {"kind": "spreadsheet", "hint": m.group(0).strip()}
            _span(spans, m, "data", "Where the data is")

    knowledge_hint = None
    m = re.search(rf"\b(using|based on|from|with|per|according to)\s+(our|my|the)?\s*([a-z]+\s+)?{DOC_WORDS}", t)
    if m:
        knowledge_hint = m.group(0)
        _span(spans, m, "knowledge", "Knowledge it uses")

    # approval
    approval_explicit = None
    m = re.search(APPROVAL_NO, t)
    if m:
        approval_explicit = False
        _span(spans, m, "approval", "Safety check")
    else:
        m = re.search(APPROVAL_YES, t)
        if m:
            approval_explicit = True
            _span(spans, m, "approval", "Safety check")

    # tone
    tone = None
    for name, pat in TONE_WORDS.items():
        m = re.search(pat, t)
        if m:
            tone = name
            _span(spans, m, "output", "Writing style")
            break

    # explicit recipient e-mail (reports to a manager etc.)
    fixed_email = None
    m = EMAIL_RE.search(text)
    if m:
        fixed_email = m.group(0)
        _span(spans, m, "output", "Who receives it")
    recipient_mode = "fixed" if purpose == "report" else "per_row"
    m = re.search(r"\b(to|for)\s+(my|our|the)\s+(manager|boss|team|head|director|founder|ceo|finance team|sales team)\b", t)
    report_to_role = None
    if m:
        report_to_role = m.group(3)
        if purpose == "report":
            _span(spans, m, "output", "Who receives it")

    # sign-off name ("sign as Ravi", "from Ravi")
    sender = None
    m = re.search(r"\b(sign(ed)?\s+(it\s+|them\s+)?(as|by|off as)|signed\s+by)\s+([A-Z][a-zA-Z]+(\s+[A-Z][a-zA-Z]+)?)", text)
    if m:
        sender = m.group(5)
        _span(spans, m, "output", "Signed by")

    spans.sort(key=lambda s: s["start"])
    return {
        "purpose": purpose,
        "entity": {"singular": singular, "plural": plural} if entity_key or purpose else None,
        "department": dept,
        "trigger": trigger,
        "source": source,
        "filter_word": filter_word,
        "wants_send": wants_send,
        "approval_explicit": approval_explicit,
        "tone": tone,
        "fixed_email": fixed_email,
        "report_to_role": report_to_role,
        "recipient_mode": recipient_mode,
        "sender": sender,
        "knowledge_hint": knowledge_hint,
        "actions": sorted(set(actions)),
        "spans": spans,
        "understood": purpose is not None,
    }
