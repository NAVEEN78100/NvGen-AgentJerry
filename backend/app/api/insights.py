"""Insights, agent health actions, duplicate and export/import.

Insights turn the run history into numbers people act on: how often drafts are
approved as-is, edited or rejected, how many people reply, and concrete
suggestions (each with the exact sentence to type into the Studio)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..engine import service
from ..models import Agent, Approval, ApprovalItem, Execution, OutboxMessage, Reply, User
from ..security import audit, current_user
from . import serialize as S

router = APIRouter(prefix="/api")


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def agent_metrics(db: Session, agent: Agent) -> dict[str, Any]:
    aps = db.scalars(select(Approval).where(Approval.agent_id == agent.id, Approval.status == "decided")).all()
    items = [it for ap in aps for it in ap.items]
    approved = sum(1 for i in items if i.status == "approved")
    rejected = sum(1 for i in items if i.status == "rejected")
    edited = sum(1 for i in items if i.edited and i.status == "approved")
    waits = [(_aware(ap.decided_at) - _aware(ap.created_at)).total_seconds() / 3600 for ap in aps if ap.decided_at]
    msgs = db.scalars(select(OutboxMessage).where(OutboxMessage.agent_id == agent.id, OutboxMessage.touch > 0)).all()
    reps = db.scalars(select(Reply).where(Reply.agent_id == agent.id)).all()
    replied_msgs = {r.outbox_id for r in reps}
    runs = db.scalars(select(Execution).where(Execution.agent_id == agent.id, Execution.mode == "live")).all()
    failed = sum(1 for r in runs if r.status == "failed")
    cats: dict[str, int] = {}
    for r in reps:
        cats[r.category] = cats.get(r.category, 0) + 1
    reviewed = approved + rejected
    sent = len(msgs)
    now = datetime.now(timezone.utc)
    weeks = []
    for w in range(7, -1, -1):
        start = now - timedelta(days=7 * (w + 1))
        end = now - timedelta(days=7 * w)
        weeks.append({
            "week": end.date().isoformat(),
            "sent": sum(1 for m in msgs if start < _aware(m.sent_at) <= end),
            "replies": sum(1 for r in reps if start < _aware(r.received_at) <= end),
        })
    return {
        "live_runs": len(runs), "failed_runs": failed, "reviewed": reviewed, "approved": approved, "rejected": rejected,
        "edited": edited, "approval_rate": round(approved / reviewed, 3) if reviewed else None,
        "edit_rate": round(edited / approved, 3) if approved else None,
        "sent": sent, "followups_sent": sum(1 for m in msgs if m.touch > 1),
        "replied": len(replied_msgs), "reply_rate": round(len(replied_msgs) / sent, 3) if sent else None,
        "reply_categories": cats, "interested": cats.get("interested", 0), "unsubscribed": cats.get("unsubscribe", 0),
        "avg_wait_hours": round(sum(waits) / len(waits), 1) if waits else None,
        "hours_saved": round(sent * config.MINUTES_SAVED_PER_ITEM / 60, 1),
        "weeks": weeks,
    }


def suggestions(agent: Agent, m: dict[str, Any]) -> list[dict[str, Any]]:
    spec = (agent.requirement or {}).get("spec") or {}
    out: list[dict[str, Any]] = []
    if m["reviewed"] >= 5 and (m["edit_rate"] or 0) >= 0.3:
        out.append({"id": "edits", "tone": "warn", "title": f"You edit {round(m['edit_rate'] * 100)}% of drafts before approving",
                    "body": "Tell Jerry what you keep changing, so future drafts need less work.",
                    "refine": "make the emails shorter and more direct"})
    if m["reviewed"] >= 5 and (m["approval_rate"] or 1) < 0.75:
        out.append({"id": "rejects", "tone": "warn", "title": f"{m['rejected']} of {m['reviewed']} drafts were rejected",
                    "body": "That usually means the agent targets people it shouldn’t. Narrow who it emails.",
                    "refine": None})
    seq = (spec.get("sequence") or {}).get("enabled")
    if spec.get("pattern") == "outreach" and not seq and m["sent"] >= 5 and (m["reply_rate"] or 0) < 0.3:
        out.append({"id": "sequence", "tone": "idea", "title": "Most people don’t reply to a single email",
                    "body": "Add a polite follow-up that stops automatically when someone replies.",
                    "refine": "if they don't reply in 3 days, follow up again, up to 3 times"})
    if spec.get("pattern") == "outreach" and not (spec.get("writeback") or {}).get("enabled") and m["sent"] >= 1:
        out.append({"id": "writeback", "tone": "idea", "title": "Keep your spreadsheet up to date automatically",
                    "body": "Jerry can mark everyone it emails in the sheet, as a new version you can download.",
                    "refine": "mark them as contacted"})
    if m["unsubscribed"] >= 2:
        out.append({"id": "unsubs", "tone": "warn", "title": f"{m['unsubscribed']} people unsubscribed",
                    "body": "They’re on the do-not-contact list. A softer tone or fewer follow-ups may help.",
                    "refine": "make it friendly and low-pressure"})
    if (m["avg_wait_hours"] or 0) > 24:
        out.append({"id": "wait", "tone": "warn", "title": f"Approvals wait {m['avg_wait_hours']:.0f} hours on average",
                    "body": "Assign an approver who reviews faster, so emails go out on time.", "refine": None})
    if m["failed_runs"]:
        out.append({"id": "fail", "tone": "warn", "title": f"{m['failed_runs']} live runs failed",
                    "body": "Open the failed run to see which step stopped and why.", "refine": None})
    if m["interested"]:
        out.append({"id": "wins", "tone": "good", "title": f"{m['interested']} people said they’re interested",
                    "body": "They’re waiting in Replies with a suggested response ready.", "refine": None})
    return out


@router.get("/agents/{agent_id}/insights")
def agent_insights(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Agent, agent_id)
    if not a or a.org_id != user.org_id:
        raise HTTPException(404, "Agent not found.")
    m = agent_metrics(db, a)
    return {"metrics": m, "suggestions": suggestions(a, m), "health": {"failure_streak": a.failure_streak}}


@router.get("/insights")
def org_insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    agents = db.scalars(select(Agent).where(Agent.org_id == user.org_id)).all()
    rows = []
    tot = {"drafted": 0, "approved": 0, "sent": 0, "replied": 0, "interested": 0}
    for a in agents:
        m = agent_metrics(db, a)
        drafted = m["reviewed"]
        rows.append({"agent": S.agent_brief(a), "metrics": {k: v for k, v in m.items() if k != "weeks"}})
        tot["drafted"] += drafted
        tot["approved"] += m["approved"]
        tot["sent"] += m["sent"]
        tot["replied"] += m["replied"]
        tot["interested"] += m["interested"]
    weeks: dict[str, dict[str, int]] = {}
    for a in agents:
        for w in agent_metrics(db, a)["weeks"]:
            cur = weeks.setdefault(w["week"], {"week": w["week"], "sent": 0, "replies": 0})
            cur["sent"] += w["sent"]
            cur["replies"] += w["replies"]
    return {"funnel": [
        {"stage": "Drafts reviewed", "value": tot["drafted"]},
        {"stage": "Approved", "value": tot["approved"]},
        {"stage": "Sent", "value": tot["sent"]},
        {"stage": "Replied", "value": tot["replied"]},
        {"stage": "Interested", "value": tot["interested"]},
    ], "agents": sorted(rows, key=lambda r: -r["metrics"]["sent"]), "weeks": sorted(weeks.values(), key=lambda w: w["week"]),
        "hours_saved": round(tot["sent"] * config.MINUTES_SAVED_PER_ITEM / 60, 1)}


@router.post("/agents/{agent_id}/duplicate")
def agent_duplicate(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Agent, agent_id)
    if not a or a.org_id != user.org_id:
        raise HTTPException(404, "Agent not found.")
    state = json.loads(json.dumps(a.requirement or {}))
    copy = Agent(org_id=a.org_id, user_id=user.id, name=f"Copy of {a.name}"[:200], goal=a.goal, prompt=a.prompt,
                 department=a.department, status="draft", requirement=state, trigger=a.trigger,
                 knowledge_ids=a.knowledge_ids, engine=a.engine,
                 conversation=[m for m in (a.conversation or []) if m.get("kind") in ("prompt", "refine", "answer")])
    db.add(copy)
    db.flush()
    result = service.evaluate(db, copy, user)
    if not [q for q in result["questions"] if q.get("blocking")]:
        service.build(db, copy, user)
    copy.name = f"Copy of {a.name}"[:200]
    audit(db, user.org_id, user.name, "agent.duplicated", "agent", copy.id, f"Duplicated “{a.name}”")
    db.commit()
    return {"id": copy.id, "name": copy.name, "status": copy.status}


@router.get("/agents/{agent_id}/export")
def agent_export(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Agent, agent_id)
    if not a or a.org_id != user.org_id:
        raise HTTPException(404, "Agent not found.")
    wf = service.latest_workflow(db, a.id)
    recipe = {
        "format": "agentjerry.recipe/v1", "name": a.name, "department": a.department, "prompt": a.prompt,
        "refinements": [m["text"] for m in (a.conversation or []) if m.get("kind") == "refine"],
        "goal": a.goal, "exported_at": datetime.now(timezone.utc).isoformat(),
        "workflow": [{"tool": s["tool"], "label": s["label"], "why": s["why"]} for s in (wf.steps if wf else [])],
    }
    fname = "".join(c if c.isalnum() else "_" for c in a.name.lower()).strip("_") + ".agent.json"
    return Response(json.dumps(recipe, indent=2, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class ImportIn(BaseModel):
    recipe: dict


@router.post("/agents/import")
def agent_import(body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = body.recipe
    if r.get("format") != "agentjerry.recipe/v1" or not str(r.get("prompt") or "").strip():
        raise HTTPException(422, "That file isn’t an AgentJerry recipe.")
    a = service.start(db, user, str(r["prompt"])[:2000])
    for text in (r.get("refinements") or [])[:10]:
        if isinstance(text, str) and text.strip():
            service.refine(db, a, user, text.strip()[:1000])
    if r.get("name"):
        a.name = str(r["name"])[:200]
    audit(db, user.org_id, user.name, "agent.imported", "agent", a.id, f"Imported “{a.name}” from a recipe")
    db.commit()
    return {"id": a.id, "name": a.name, "status": a.status}
