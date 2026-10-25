"""Content generation. Claude writes the drafts when available; otherwise the
offline writer composes them from the row's own fields plus the best-matching
sentence from the knowledge base (so drafts stay grounded and specific)."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..runtime.knowledge import best_sentence
from ..tools.spreadsheet import first_name, parse_date, parse_number
from . import llm


def _money(v: str) -> str:
    n = parse_number(v)
    if n is None:
        return v
    return f"₹{n:,.0f}" if n >= 1 else v


def _fmt_date(v: str) -> str:
    d = parse_date(v)
    return d.strftime("%d %b %Y") if d else v


def _get(row: dict, roles: dict, role: str) -> str:
    col = roles.get(role)
    return (row.get(col) or "").strip() if col else ""


def source_phrase(source: str) -> str:
    s = (source or "").lower()
    if not s:
        return "Thanks for your interest in what we do."
    if "referral" in s:
        return "Thanks for taking the time after the introduction."
    if any(w in s for w in ("website", "demo request", "chat", "google", "search", "form")):
        return "Thanks for reaching out through our website."
    if "webinar" in s:
        return "Thanks for joining our webinar."
    if any(w in s for w in ("instagram", "facebook", " ad", "ad ")) or s.endswith(" ad"):
        return "Thanks for getting in touch after seeing our ad."
    if "email" in s:
        return "Thanks for replying to my email."
    if "linkedin" in s:
        return "Thanks for connecting on LinkedIn."
    return f"It was great meeting you at {source}."


def _you(notes: str) -> str:
    if not notes:
        return ""
    n = notes[0].lower() + notes[1:]
    n = re.sub(r"\btheir\b", "your", n)
    n = re.sub(r"\bthey\b", "you", n)
    return n.rstrip(".")


CLOSINGS = {"friendly": "Best", "formal": "Kind regards", "concise": "Thanks"}


def offline_draft(row: dict, roles: dict, spec: dict, passages: list[dict]) -> dict[str, Any]:
    purpose = spec.get("purpose") or "custom"
    tone = spec.get("tone") or "friendly"
    sender = spec.get("sender") or "The team"
    company = spec.get("company") or ""
    name = _get(row, roles, "name")
    first = _get(row, roles, "first_name") or first_name(name) or "there"
    org = _get(row, roles, "company")
    industry = _get(row, roles, "industry")
    interest = _get(row, roles, "interest")
    source = _get(row, roles, "source")
    notes = _get(row, roles, "notes")
    role = _get(row, roles, "role")
    grounding = ""
    used = None
    if passages:
        q = " ".join(x for x in (industry, interest, role, notes) if x) or purpose
        grounding = best_sentence(passages[0]["text"], q)
        used = 0
    greet = "Hi" if tone != "formal" else "Dear"
    close = CLOSINGS.get(tone, "Best")
    sig = f"{close},\n{sender}\n{company}".rstrip()
    paras: list[str] = []

    if purpose == "follow_up":
        topic = interest or (f"{industry.lower()} operations" if industry else "our conversation")
        subject = {"friendly": f"{first}, following up on {topic}",
                   "formal": f"Following up: {topic} for {org}" if org else f"Following up on {topic}",
                   "concise": f"Quick follow-up on {topic}"}[tone]
        opener = source_phrase(source)
        note = _you(notes)
        if note:
            paras.append(f"{opener} I noted that you {note}.")
        else:
            paras.append(f"{opener} It was good to learn about {org or 'your team'}.")
        if grounding:
            lead_in = {"friendly": f"Something that may be useful for {org or 'you'}:",
                       "formal": f"You may find this relevant for {org or 'your organisation'}:",
                       "concise": "Relevant here:"}[tone]
            paras.append(f"{lead_in} {grounding[0].lower() + grounding[1:] if grounding[:2] != grounding[:2].upper() else grounding}")
        elif interest:
            paras.append(f"I’d love to show you how {company} can help {org or 'your team'} with {interest.lower()}.")
        paras.append({"friendly": "Would a 20-minute call next week work for you? Happy to fit around your schedule.",
                      "formal": "Would you be available for a brief 20-minute call next week? Please let me know a convenient time.",
                      "concise": "Open to a 15-minute call next week?"}[tone])
    elif purpose == "payment_reminder":
        inv = _get(row, roles, "invoice") or "your invoice"
        amount = _money(_get(row, roles, "amount"))
        due_raw = _get(row, roles, "due_date")
        due = _fmt_date(due_raw)
        d = parse_date(due_raw)
        overdue_days = (date.today() - d).days if d else None
        subject = f"Reminder: invoice {inv} ({amount}) is overdue" if amount else f"Reminder: invoice {inv} is overdue"
        line = f"This is a reminder that invoice {inv}"
        if amount:
            line += f" for {amount}"
        if due:
            line += f", due on {due},"
        line += " is still outstanding"
        if overdue_days and overdue_days > 0:
            line += f" ({overdue_days} days past the due date)"
        paras.append(line + ".")
        if grounding:
            paras.append(grounding)
        paras.append("If you’ve already made the payment, please ignore this note and accept our thanks. "
                     "If anything is holding it up, just reply and we’ll sort it out together.")
    elif purpose == "interview_invite":
        position = role or "the open role"
        subject = f"Interview invitation: {position} at {company}" if company else f"Interview invitation: {position}"
        paras.append(f"Thank you for applying for the {position} role at {company}. We enjoyed reading your application "
                     "and would like to invite you to an interview.")
        if grounding:
            paras.append(grounding)
        paras.append("Please reply with two or three time slots that suit you this week, and we’ll confirm one.")
    elif purpose == "welcome":
        subject = f"Welcome to {company}, {first}"
        paras.append(f"Welcome aboard! We’re glad to have {org or 'you'} with us.")
        if grounding:
            paras.append(grounding)
        paras.append("Reply to this email any time — it comes straight to me.")
    elif purpose == "thank_you":
        subject = f"Thank you, {first}"
        paras.append(f"A quick note to say thank you{(' for choosing ' + company) if company else ''}.")
        if grounding:
            paras.append(grounding)
    else:
        subject = f"A note from {company}" if company else "A quick note"
        paras.append(spec.get("instructions") or f"I wanted to reach out personally{(' from ' + company) if company else ''}.")
        if grounding:
            paras.append(grounding)

    body = f"{greet} {first},\n\n" + "\n\n".join(paras) + f"\n\n{sig}"
    return {"subject": subject, "body": body, "engine": "offline", "used_passage": used}


def draft_all(rows: list[dict], roles: dict, spec: dict, passages_per_row: list[list[dict]]) -> tuple[list[dict], str]:
    """Return (drafts, engine). Each draft keeps the row so later steps can use it."""
    results: list[dict[str, Any] | None] = [None] * len(rows)
    engine = "offline"
    if llm.enabled() and rows:
        try:
            items = [{"index": i, "record": r,
                      "knowledge_passages": [p["text"] for p in passages_per_row[i][:2]]} for i, r in enumerate(rows)]
            for chunk_start in range(0, len(items), 15):
                out = llm.draft_batch(spec, items[chunk_start:chunk_start + 15])
                for o in out:
                    i = int(o.get("index", -1))
                    if 0 <= i < len(rows) and o.get("subject") and o.get("body"):
                        results[i] = {"subject": str(o["subject"])[:300], "body": str(o["body"]),
                                      "engine": "claude", "used_passage": o.get("used_passage")}
            engine = "claude"
        except llm.LLMUnavailable:
            engine = "offline"
    for i, r in enumerate(rows):
        if results[i] is None:
            results[i] = offline_draft(r, roles, spec, passages_per_row[i] if i < len(passages_per_row) else [])
    return results, engine  # type: ignore[return-value]


def report_draft(summary: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    ent = spec.get("entity") or {"plural": "records"}
    lines = [f"Here’s this week’s summary of your {ent['plural']}.", ""]
    lines.append(f"• Total {ent['plural']}: {summary['count']}")
    if summary.get("total") is not None:
        lines.append(f"• Combined value: ₹{summary['total']:,.0f}")
    if summary.get("groups"):
        lines.append("")
        lines.append(f"By {summary['group_by']}:")
        for g in summary["groups"]:
            extra = f" — ₹{g['total']:,.0f}" if g.get("total") is not None else ""
            lines.append(f"  – {g['value']}: {g['count']}{extra}")
    if summary.get("owners"):
        lines.append("")
        lines.append("By owner:")
        for g in summary["owners"]:
            lines.append(f"  – {g['value']}: {g['count']}")
    if summary.get("top"):
        lines.append("")
        lines.append("Largest items:")
        for t in summary["top"]:
            lines.append(f"  – {t['label']}: ₹{t['value']:,.0f}")
    close = CLOSINGS.get(spec.get("tone") or "friendly", "Best")
    body = "Hi,\n\n" + "\n".join(lines) + f"\n\n{close},\n{spec.get('sender')}\n{spec.get('company')}"
    subject = f"{ent['plural'].capitalize()} summary — {date.today().strftime('%d %b %Y')}"
    return {"subject": subject, "body": body, "engine": "offline"}
