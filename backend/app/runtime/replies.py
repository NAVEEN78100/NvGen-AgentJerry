"""Reply handling.

* classify an inbound reply (rules; Claude when available)
* stop follow-up sequences for that person in every agent's memory
* unsubscribe -> workspace do-not-contact list (automatic, audited)
* interested -> notification
* suggest a grounded response the user can edit and send
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engine import llm
from ..models import MemoryEntry, Organization, OutboxMessage, Reply, Suppression, User
from ..security import audit, notify
from ..tools.spreadsheet import first_name
from .knowledge import BM25Retriever, best_sentence

CATEGORY_LABEL = {
    "interested": "Interested", "question": "Has a question", "not_now": "Not right now",
    "not_interested": "Not interested", "unsubscribe": "Unsubscribe", "out_of_office": "Out of office", "other": "Other",
}

RULES: list[tuple[str, str, float]] = [
    ("unsubscribe", r"\b(unsubscribe|remove me|take me off|stop (emailing|contacting|sending)|do not (contact|email)|don'?t (contact|email) me|opt[\s-]?out)\b", 0.95),
    ("out_of_office", r"\b(out of (the )?office|on (annual |sick |maternity |paternity )?leave|away until|auto[\s-]?reply|automatic reply|back on)\b", 0.9),
    ("not_interested", r"\b(not interested|no thanks|no thank you|already (have|use|using) (a|another)|we('re| are) (good|set)|not a fit|pass on this)\b", 0.85),
    ("not_now", r"\b(not (right )?now|next (month|quarter|year)|later this year|busy (right now|at the moment)|circle back|reach out (again )?(in|after)|no budget|after (diwali|the holidays|march|april))\b", 0.8),
    ("interested", r"\b(interested|let'?s (talk|connect|chat|meet)|book a (call|demo|meeting)|schedule (a|the)|sounds (good|great)|happy to (chat|talk|meet)|keen|send (me )?(the )?(details|pricing|proposal)|works for me|available (on|this|next)|set up a (call|demo))\b", 0.8),
]


def classify(text: str) -> tuple[str, float, str]:
    t = (text or "").lower()
    if llm.enabled():
        try:
            out = llm.call_json(
                "Classify a reply to a business email. Return JSON {\"category\": one of interested, question, not_now, "
                "not_interested, unsubscribe, out_of_office, other, \"confidence\": 0-1, \"summary\": one short sentence}.",
                text[:3000], max_tokens=200)
            if out.get("category") in CATEGORY_LABEL:
                return out["category"], float(out.get("confidence") or 0.7), str(out.get("summary") or "")[:300]
        except llm.LLMUnavailable:
            pass
    for cat, pat, conf in RULES:
        if re.search(pat, t):
            return cat, conf, _summary(cat, text)
    if "?" in t:
        return "question", 0.7, _summary("question", text)
    return "other", 0.4, _summary("other", text)


def _summary(cat: str, text: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", (text or "").strip())[0][:180]
    return {"interested": "Wants to talk", "question": f"Asked: {first}", "not_now": "Not now — check back later",
            "not_interested": "Declined", "unsubscribe": "Asked to be removed from emails",
            "out_of_office": "Auto-reply: away", "other": first}.get(cat, first)


def suggest_reply(db: Session, rep: Reply, org: Organization, sender: str) -> str | None:
    name = first_name(rep.from_name) or "there"
    sig = f"\n\nBest,\n{sender}\n{org.name}"
    if rep.category in ("unsubscribe", "out_of_office"):
        return None
    if rep.category == "not_interested":
        return f"Hi {name},\n\nThanks for letting me know — I won’t follow up further. If anything changes, just reply to this email.{sig}"
    if rep.category == "not_now":
        return (f"Hi {name},\n\nCompletely understand — thanks for the honest reply. I’ll check back in a few months; "
                f"until then, feel free to reach out whenever it’s useful.{sig}")
    fact = ""
    hits = BM25Retriever(db, org.id).search(rep.body, k=1, min_score=1.2)
    if hits:
        fact = best_sentence(hits[0].text, rep.body)
    if rep.category == "question":
        line = f"Good question. {fact}" if fact else "Good question — let me get you a precise answer."
        return f"Hi {name},\n\n{line}\n\nHappy to walk you through it on a short call — would Tuesday or Thursday afternoon suit you?{sig}"
    if rep.category == "interested":
        extra = f"\n\nAhead of the call, one thing you might find useful: {fact[0].lower() + fact[1:]}" if fact else ""
        return (f"Hi {name},\n\nGreat to hear from you! Would Tuesday at 11:00 AM or Thursday at 3:00 PM work for a "
                f"20-minute call? If neither suits, send me a time that does.{extra}{sig}")
    return f"Hi {name},\n\nThanks for getting back to me.{(' ' + fact) if fact else ''}{sig}"


def record_reply(db: Session, org: Organization, from_email: str, body: str, subject: str = "",
                 from_name: str = "", outbox_id: str | None = None, actor: str = "Inbound email") -> Reply:
    email = from_email.strip().lower()
    msg = None
    if outbox_id:
        msg = db.get(OutboxMessage, outbox_id)
        if msg and msg.org_id != org.id:
            msg = None
    if msg is None:
        msg = db.scalars(select(OutboxMessage).where(OutboxMessage.org_id == org.id, OutboxMessage.to == email)
                         .order_by(OutboxMessage.sent_at.desc())).first() or \
              db.scalars(select(OutboxMessage).where(OutboxMessage.org_id == org.id)
                         .where(OutboxMessage.to.ilike(email)).order_by(OutboxMessage.sent_at.desc())).first()
    cat, conf, summary = classify(body)
    rep = Reply(org_id=org.id, outbox_id=msg.id if msg else None, agent_id=msg.agent_id if msg else None,
                from_email=email, from_name=from_name or (msg.to_name if msg else ""),
                subject=subject or (f"Re: {msg.subject}" if msg else ""), body=body, category=cat,
                confidence=conf, summary=summary)
    db.add(rep)
    db.flush()
    now = datetime.now(timezone.utc)
    if msg:
        msg.replied_at = now
        msg.reply_category = cat

    # stop follow-ups for this person in every agent's memory
    stopped = 0
    from ..models import Agent
    for m in db.scalars(select(MemoryEntry).join(Agent, Agent.id == MemoryEntry.agent_id).where(Agent.org_id == org.id)):
        v = m.value or {}
        if m.key == email or (v.get("email") or "").lower() == email:
            if not v.get("replied"):
                m.value = {**v, "replied": True, "replied_at": now.isoformat(), "reply_category": cat}
                stopped += 1

    if cat == "unsubscribe":
        add_suppression(db, org.id, email, f"Replied asking to unsubscribe: “{body.strip()[:120]}”", "reply", "AgentJerry")
    owner = db.scalars(select(User).where(User.org_id == org.id, User.role == "admin")).first()
    rep.suggested_reply = suggest_reply(db, rep, org, (owner.name.split(" ")[0] if owner else org.name))
    title = {"interested": f"{rep.from_name or email} is interested",
             "question": f"{rep.from_name or email} has a question",
             "unsubscribe": f"{rep.from_name or email} unsubscribed"}.get(cat, f"New reply from {rep.from_name or email}")
    notify(db, org.id, "reply", title, summary, f"/replies?open={rep.id}")
    audit(db, org.id, actor, "reply.received", "reply", rep.id,
          f"Reply from {rep.from_name or email}: {CATEGORY_LABEL[cat]}"
          + (f" · follow-ups stopped in {stopped} agent memories" if stopped else "")
          + (" · added to do-not-contact list" if cat == "unsubscribe" else ""), category=cat)
    return rep


def add_suppression(db: Session, org_id: str, email: str, reason: str, source: str, actor: str) -> bool:
    email = email.strip().lower()
    if db.scalars(select(Suppression).where(Suppression.org_id == org_id, Suppression.email == email)).first():
        return False
    db.add(Suppression(org_id=org_id, email=email, reason=reason, source=source, created_by=actor))
    audit(db, org_id, actor, "suppression.added", "suppression", email, f"Added {email} to the do-not-contact list")
    return True


def reply_out(r: Reply, msg: OutboxMessage | None = None, agent_name: str | None = None) -> dict[str, Any]:
    from ..api.serialize import iso
    return {"id": r.id, "from_email": r.from_email, "from_name": r.from_name, "subject": r.subject, "body": r.body,
            "category": r.category, "category_label": CATEGORY_LABEL.get(r.category, r.category),
            "confidence": r.confidence, "summary": r.summary, "status": r.status, "suggested_reply": r.suggested_reply,
            "response_id": r.response_id, "agent_id": r.agent_id, "agent_name": agent_name,
            "received_at": iso(r.received_at),
            "original": ({"id": msg.id, "subject": msg.subject, "body": msg.body, "sent_at": iso(msg.sent_at),
                          "touch": msg.touch} if msg else None)}
