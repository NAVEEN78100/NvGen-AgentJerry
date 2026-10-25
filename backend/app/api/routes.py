"""REST API. Every route is scoped to the caller's organization."""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..engine import llm, service
from ..models import (Agent, Approval, AuditEvent, DataFile, Execution, ExecutionLog, KnowledgeSource, MemoryEntry,
                      Metric, Notification, Organization, OutboxMessage, User, Workflow, uid)
from ..runtime import executor, scheduler
from ..runtime.knowledge import BM25Retriever, ingest
from ..security import audit, create_token, current_user, require_admin, verify_password
from ..tools.registry import catalog
from ..tools.spreadsheet import SpreadsheetError, read_table
from . import serialize as S

router = APIRouter(prefix="/api")


def _agent(db: Session, user: User, agent_id: str) -> Agent:
    a = db.get(Agent, agent_id)
    if a is None or a.org_id != user.org_id:
        raise HTTPException(404, "Agent not found.")
    return a


def _stats(db: Session, agent_id: str) -> dict[str, Any]:
    runs = db.scalar(select(func.count()).select_from(Execution).where(Execution.agent_id == agent_id, Execution.mode == "live")) or 0
    sent = db.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.agent_id == agent_id)) or 0
    mem = db.scalar(select(func.count()).select_from(MemoryEntry).where(MemoryEntry.agent_id == agent_id)) or 0
    last = db.scalars(select(Execution).where(Execution.agent_id == agent_id).order_by(Execution.started_at.desc())).first()
    pending = db.scalar(select(func.count()).select_from(Approval).where(Approval.agent_id == agent_id, Approval.status == "pending")) or 0
    return {"live_runs": runs, "emails_sent": sent, "memory": mem, "pending_approvals": pending,
            "last_run": S.execution_out(last) if last else None}


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalars(select(User).where(func.lower(User.email) == body.email.strip().lower())).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "That email and password don’t match an account.")
    org = db.get(Organization, u.org_id)
    audit(db, u.org_id, u.name, "auth.login", "user", u.id, "Signed in")
    db.commit()
    return {"token": create_token(u), "user": S.user_out(u), "org": {"id": org.id, "name": org.name}}


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, user.org_id)
    return {"user": S.user_out(user), "org": {"id": org.id, "name": org.name}, "engine": llm.status()}


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org_id = user.org_id
    agents = db.scalars(select(Agent).where(Agent.org_id == org_id)).all()
    by_status: dict[str, int] = {}
    for a in agents:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    since = datetime.now(timezone.utc) - timedelta(days=7)
    runs_7d = db.scalars(select(Execution).where(Execution.org_id == org_id, Execution.started_at >= since)).all()
    sent_total = db.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.org_id == org_id)) or 0
    processed = db.scalar(select(func.coalesce(func.sum(Metric.value), 0)).where(Metric.org_id == org_id)) or 0
    pending = db.scalars(select(Approval).where(Approval.org_id == org_id, Approval.status == "pending")
                         .order_by(Approval.created_at.desc())).all()
    names = {a.id: a.name for a in agents}
    days = []
    for d in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=d)).date()
        rs = [r for r in runs_7d if S.iso(r.started_at)[:10] == day.isoformat()]
        days.append({"date": day.isoformat(), "test": sum(1 for r in rs if r.mode == "test"),
                     "live": sum(1 for r in rs if r.mode == "live")})
    recent = db.scalars(select(Execution).where(Execution.org_id == org_id).order_by(Execution.started_at.desc()).limit(6)).all()
    activity = db.scalars(select(AuditEvent).where(AuditEvent.org_id == org_id, AuditEvent.action != "auth.login")
                          .order_by(AuditEvent.created_at.desc()).limit(8)).all()
    return {
        "kpis": {
            "agents_live": by_status.get("deployed", 0), "agents_total": len(agents),
            "runs_7d": sum(1 for r in runs_7d if r.mode == "live"), "tests_7d": sum(1 for r in runs_7d if r.mode == "test"),
            "emails_sent": sent_total, "pending_approvals": len(pending),
            "hours_saved": round(float(processed) * config.MINUTES_SAVED_PER_ITEM / 60, 1),
            "minutes_per_item": config.MINUTES_SAVED_PER_ITEM,
        },
        "by_status": by_status,
        "days": days,
        "pending": [S.approval_out(p, names.get(p.agent_id), with_items=False) for p in pending[:5]],
        "recent_runs": [S.execution_out(r, names.get(r.agent_id)) for r in recent],
        "agents": [S.agent_brief(a) for a in sorted(agents, key=lambda a: a.updated_at, reverse=True)[:6]],
        "activity": [_event(e) for e in activity],
        "engine": llm.status(),
    }


def _event(e: AuditEvent) -> dict[str, Any]:
    return {"id": e.id, "actor": e.actor, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id,
            "detail": e.detail, "meta": e.meta, "at": S.iso(e.created_at)}


# ------------------------------------------------------------------ studio
class PromptIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class AnswersIn(BaseModel):
    answers: dict[str, Any]


class RefineIn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)


TEMPLATES = [
    {"id": "sales", "department": "sales", "title": "Weekly lead follow-ups",
     "prompt": "Every Monday at 9am, read my sales spreadsheet, identify new leads, generate personalized follow-up emails, and show them to me for approval."},
    {"id": "sequence", "department": "sales", "title": "Follow-up sequence that stops on reply",
     "prompt": "Every Monday at 9am, read my sales spreadsheet, identify new leads and draft personalized follow-up emails for my approval. If they don't reply in 3 days, follow up again, up to 3 times, and mark them as contacted."},
    {"id": "finance", "department": "finance", "title": "Overdue invoice reminders",
     "prompt": "Every weekday at 10am, check the invoices sheet for overdue invoices and send a polite payment reminder to each client after I approve."},
    {"id": "hr", "department": "hr", "title": "Interview invitations",
     "prompt": "Find shortlisted candidates in the candidates spreadsheet and draft formal interview invitations for me to review before sending."},
    {"id": "report", "department": "sales", "title": "Weekly pipeline report",
     "prompt": "Every Friday at 5pm, summarize the sales pipeline and email it to my manager."},
    {"id": "event", "department": "hr", "title": "Runs when a file is updated",
     "prompt": "Whenever the candidates spreadsheet is updated, draft interview invitations for shortlisted candidates for me to review."},
]


def _full(db: Session, a: Agent) -> dict[str, Any]:
    return S.agent_full(a, service.latest_workflow(db, a.id), _stats(db, a.id))


@router.get("/studio/templates")
def templates(user: User = Depends(current_user)):
    return TEMPLATES


@router.post("/studio")
def studio_start(body: PromptIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.start(db, user, body.prompt.strip())
    audit(db, user.org_id, user.name, "agent.drafted", "agent", a.id, f"Described: “{body.prompt.strip()[:120]}”")
    db.commit()
    return _full(db, a)


@router.post("/studio/{agent_id}/answer")
def studio_answer(agent_id: str, body: AnswersIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    was_live = a.status in ("deployed", "paused")
    service.answer(db, a, user, body.answers)
    _after_change(db, a, user, was_live)
    db.commit()
    return _full(db, a)


@router.post("/studio/{agent_id}/refine")
def studio_refine(agent_id: str, body: RefineIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    was_live = a.status in ("deployed", "paused")
    service.refine(db, a, user, body.text.strip())
    _after_change(db, a, user, was_live)
    db.commit()
    return _full(db, a)


def _after_change(db: Session, a: Agent, user: User, was_live: bool) -> None:
    if was_live and a.status not in ("deployed", "paused"):
        scheduler.sync(a)
        audit(db, user.org_id, user.name, "agent.changed", "agent", a.id,
              "Changed a live agent — it was taken offline until a new test passes")


# ------------------------------------------------------------------ agents
@router.get("/agents")
def agents_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Agent).where(Agent.org_id == user.org_id).order_by(Agent.updated_at.desc())).all()
    return [S.agent_brief(a, _stats(db, a.id)) for a in rows]


@router.get("/agents/{agent_id}")
def agent_get(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _full(db, _agent(db, user, agent_id))


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    approver_id: str | None = None


@router.patch("/agents/{agent_id}")
def agent_patch(agent_id: str, body: AgentPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    if body.name:
        a.name = body.name.strip()
        audit(db, user.org_id, user.name, "agent.renamed", "agent", a.id, f"Renamed to “{a.name}”")
    if body.approver_id:
        ap_user = db.get(User, body.approver_id)
        if not ap_user or ap_user.org_id != user.org_id:
            raise HTTPException(404, "That person isn’t in your workspace.")
        a.approver_id = ap_user.id
        for pend in db.scalars(select(Approval).where(Approval.agent_id == a.id, Approval.status == "pending")):
            pend.assigned_to = ap_user.id
            from ..security import notify as _notify
            _notify(db, user.org_id, "approval", f"{len(pend.items)} drafts need your approval",
                    f"{user.name} asked you to approve “{a.name}”.", f"/approvals/{pend.id}", user_id=ap_user.id)
        audit(db, user.org_id, user.name, "agent.approver", "agent", a.id, f"{ap_user.name} now approves “{a.name}”")
    db.commit()
    return _full(db, a)


@router.delete("/agents/{agent_id}")
def agent_delete(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    if db.scalars(select(Execution).where(Execution.agent_id == a.id, Execution.status.in_(["running", "queued"]))).first():
        raise HTTPException(409, "This agent is running. Wait for it to finish, then delete it.")
    a.status = "archived"
    scheduler.sync(a)
    name = a.name
    for ap in db.scalars(select(Approval).where(Approval.agent_id == a.id, Approval.status == "pending")):
        ap.status = "expired"
    db.delete(a)
    audit(db, user.org_id, user.name, "agent.deleted", "agent", agent_id, f"Deleted “{name}”")
    db.commit()
    return {"ok": True}


@router.post("/agents/{agent_id}/deploy")
def agent_deploy(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    wf = service.latest_workflow(db, a.id)
    if not wf or a.last_test_passed_version != wf.version:
        raise HTTPException(409, "Run a successful test of the latest version before going live.")
    a.status = "deployed"
    a.deployed_at = datetime.now(timezone.utc)
    scheduler.sync(a)
    audit(db, user.org_id, user.name, "agent.deployed", "agent", a.id,
          f"Took “{a.name}” live — {S.trigger_label(a.trigger)}")
    db.commit()
    return _full(db, a)


@router.post("/agents/{agent_id}/pause")
def agent_pause(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    if a.status != "deployed":
        raise HTTPException(409, "Only live agents can be paused.")
    a.status = "paused"
    scheduler.sync(a)
    audit(db, user.org_id, user.name, "agent.paused", "agent", a.id, f"Paused “{a.name}”")
    db.commit()
    return _full(db, a)


class RunIn(BaseModel):
    mode: str = Field(pattern="^(test|live)$")


@router.post("/agents/{agent_id}/runs")
def agent_run(agent_id: str, body: RunIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    try:
        ex = executor.start_execution(db, a, body.mode, "manual", user)
    except executor.RunError as exc:
        raise HTTPException(409, str(exc))
    return S.execution_out(ex, a.name)


@router.get("/agents/{agent_id}/runs")
def agent_runs(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    rows = db.scalars(select(Execution).where(Execution.agent_id == a.id).order_by(Execution.started_at.desc()).limit(50)).all()
    return [S.execution_out(r, a.name) for r in rows]


@router.get("/agents/{agent_id}/memory")
def agent_memory(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    rows = db.scalars(select(MemoryEntry).where(MemoryEntry.agent_id == a.id).order_by(MemoryEntry.updated_at.desc())).all()
    return [{"id": m.id, "namespace": m.namespace, "key": m.key, "value": m.value, "execution_id": m.execution_id,
             "updated_at": S.iso(m.updated_at)} for m in rows]


@router.delete("/agents/{agent_id}/memory/{entry_id}")
def agent_memory_forget(agent_id: str, entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    m = db.get(MemoryEntry, entry_id)
    if not m or m.agent_id != a.id:
        raise HTTPException(404, "Memory entry not found.")
    db.delete(m)
    audit(db, user.org_id, user.name, "memory.forgotten", "agent", a.id, f"Forgot {m.key}")
    db.commit()
    return {"ok": True}


@router.delete("/agents/{agent_id}/memory")
def agent_memory_clear(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    n = db.execute(delete(MemoryEntry).where(MemoryEntry.agent_id == a.id)).rowcount
    audit(db, user.org_id, user.name, "memory.cleared", "agent", a.id, f"Cleared {n} memory entries")
    db.commit()
    return {"ok": True, "cleared": n}


@router.get("/agents/{agent_id}/versions")
def agent_versions(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, agent_id)
    rows = db.scalars(select(Workflow).where(Workflow.agent_id == a.id).order_by(Workflow.version.desc())).all()
    return [{"version": w.version, "steps": len(w.steps), "status": w.validation.get("status"),
             "created_at": S.iso(w.created_at), "tested": a.last_test_passed_version == w.version} for w in rows]


# ------------------------------------------------------------------ runs
@router.get("/runs")
def runs_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Execution).where(Execution.org_id == user.org_id).order_by(Execution.started_at.desc()).limit(100)).all()
    names = {a.id: a.name for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id))}
    return [S.execution_out(r, names.get(r.agent_id)) for r in rows]


@router.get("/runs/{run_id}")
def run_get(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ex = db.get(Execution, run_id)
    if not ex or ex.org_id != user.org_id:
        raise HTTPException(404, "Run not found.")
    logs = db.scalars(select(ExecutionLog).where(ExecutionLog.execution_id == ex.id)).all()
    ap = db.scalars(select(Approval).where(Approval.execution_id == ex.id)).first()
    a = db.get(Agent, ex.agent_id)
    return S.execution_out(ex, a.name if a else None, logs, ap.id if ap else None)


@router.post("/runs/{run_id}/cancel")
def run_cancel(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ex = db.get(Execution, run_id)
    if not ex or ex.org_id != user.org_id:
        raise HTTPException(404, "Run not found.")
    try:
        executor.cancel(run_id, user)
    except executor.RunError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


# ------------------------------------------------------------------ approvals
@router.get("/approvals")
def approvals_list(status: str = "pending", mine: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Approval).where(Approval.org_id == user.org_id)
    if status != "all":
        q = q.where(Approval.status == status)
    rows = db.scalars(q.order_by(Approval.created_at.desc()).limit(100)).all()
    names = {a.id: a.name for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id))}
    users = {u.id: u for u in db.scalars(select(User).where(User.org_id == user.org_id))}
    out = []
    for r in rows:
        reason = executor.approval_permission(db, r, user) if r.status == "pending" else None
        a_u = users.get(r.assigned_to)
        out.append(S.approval_out(r, names.get(r.agent_id), with_items=False,
                                  decided_by_name=users[r.decided_by].name if r.decided_by in users else None,
                                  assignee={"id": a_u.id, "name": a_u.name} if a_u else None,
                                  can_decide=reason is None, blocked_reason=reason))
    if mine:
        out = [o for o in out if o["can_decide"]]
    return out


@router.get("/approvals/{approval_id}")
def approval_get(approval_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ap = db.get(Approval, approval_id)
    if not ap or ap.org_id != user.org_id:
        raise HTTPException(404, "Approval not found.")
    a = db.get(Agent, ap.agent_id)
    u = db.get(User, ap.decided_by) if ap.decided_by else None
    asg = db.get(User, ap.assigned_to) if ap.assigned_to else None
    reason = executor.approval_permission(db, ap, user) if ap.status == "pending" else None
    return S.approval_out(ap, a.name if a else None, decided_by_name=u.name if u else None,
                          assignee={"id": asg.id, "name": asg.name} if asg else None,
                          can_decide=reason is None, blocked_reason=reason)


class Decision(BaseModel):
    id: int
    status: str
    subject: str | None = None
    body: str | None = None
    to: str | None = None


class DecideIn(BaseModel):
    decisions: list[Decision]


@router.post("/approvals/{approval_id}/decide")
def approval_decide(approval_id: str, body: DecideIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        executor.decide(approval_id, user, [d.model_dump() for d in body.decisions], user.org_id)
    except executor.RunError as exc:
        raise HTTPException(409, str(exc))
    db.expire_all()
    return approval_get(approval_id, user, db)


# ------------------------------------------------------------------ files
MAX_UPLOAD = 15 * 1024 * 1024


def _save_upload(up: UploadFile, allowed: tuple[str, ...]) -> tuple[Path, str, str]:
    name = Path(up.filename or "upload").name
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed:
        raise HTTPException(415, f"Upload a {' or '.join('.' + a for a in allowed)} file.")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    dest = config.UPLOAD_DIR / f"{uid('up')}_{safe}"
    size = 0
    with dest.open("wb") as fh:
        while chunk := up.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "Files must be under 15 MB.")
            fh.write(chunk)
    return dest, name, ext


@router.get("/files")
def files_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DataFile).where(DataFile.org_id == user.org_id).order_by(DataFile.created_at.desc())).all()
    used: dict[str, list[str]] = {}
    for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id)):
        fid = (((a.requirement or {}).get("spec") or {}).get("source") or {}).get("file_id")
        if fid:
            used.setdefault(fid, []).append(a.name)
    return [S.file_out(f) | {"used_by": used.get(f.id, [])} for f in rows]


@router.post("/files")
def files_upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    dest, name, ext = _save_upload(file, ("csv", "xlsx"))
    try:
        cols, rows = read_table(dest, ext)
    except SpreadsheetError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))
    f = DataFile(org_id=user.org_id, uploaded_by=user.id, name=name, kind=ext, path=str(dest), columns=cols, row_count=len(rows))
    db.add(f)
    db.flush()
    from ..runtime.files import ensure_initial_version as _eiv
    _eiv(db, f, user.name)
    audit(db, user.org_id, user.name, "file.uploaded", "file", f.id, f"Uploaded {name} ({len(rows)} rows)")
    db.commit()
    return S.file_out(f)


@router.get("/files/{file_id}")
def file_get(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(DataFile, file_id)
    if not f or f.org_id != user.org_id:
        raise HTTPException(404, "File not found.")
    cols, rows = read_table(f.path, f.kind)
    return S.file_out(f) | {"rows": rows[:200]}


@router.delete("/files/{file_id}")
def file_delete(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(DataFile, file_id)
    if not f or f.org_id != user.org_id:
        raise HTTPException(404, "File not found.")
    users_of = [a.name for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id))
                if (((a.requirement or {}).get("spec") or {}).get("source") or {}).get("file_id") == f.id]
    if users_of:
        raise HTTPException(409, f"“{users_of[0]}” reads this file. Delete or change that agent first.")
    Path(f.path).unlink(missing_ok=True)
    db.delete(f)
    audit(db, user.org_id, user.name, "file.deleted", "file", file_id, f"Deleted {f.name}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ knowledge
@router.get("/knowledge")
def knowledge_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(KnowledgeSource).where(KnowledgeSource.org_id == user.org_id).order_by(KnowledgeSource.created_at.desc())).all()
    return [S.knowledge_out(k) for k in rows]


@router.post("/knowledge")
def knowledge_upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    dest, name, ext = _save_upload(file, ("pdf", "txt", "md"))
    title = re.sub(r"[_-]+", " ", name.rsplit(".", 1)[0]).strip().capitalize()
    k = KnowledgeSource(org_id=user.org_id, file_name=name, source_type=ext, title=title, status="processing")
    db.add(k)
    db.flush()
    try:
        ingest(db, k, dest)
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"Couldn’t read {name}: {exc}")
    if k.status == "empty":
        db.rollback()
        raise HTTPException(422, f"No readable text found in {name}. Scanned PDFs need OCR first.")
    audit(db, user.org_id, user.name, "knowledge.added", "knowledge", k.id, f"Added {name} ({k.chunk_count} passages)")
    db.commit()
    return S.knowledge_out(k)


@router.get("/knowledge/{kid}")
def knowledge_get(kid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    k = db.get(KnowledgeSource, kid)
    if not k or k.org_id != user.org_id:
        raise HTTPException(404, "Document not found.")
    return S.knowledge_out(k) | {"chunks": [{"idx": c.idx, "section": c.section, "text": c.text} for c in sorted(k.chunks, key=lambda c: c.idx)]}


@router.delete("/knowledge/{kid}")
def knowledge_delete(kid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    k = db.get(KnowledgeSource, kid)
    if not k or k.org_id != user.org_id:
        raise HTTPException(404, "Document not found.")
    db.delete(k)
    audit(db, user.org_id, user.name, "knowledge.removed", "knowledge", kid, f"Removed {k.file_name}")
    db.commit()
    return {"ok": True}


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)


@router.post("/knowledge/search")
def knowledge_search(body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    retr = BM25Retriever(db, user.org_id)
    hits = retr.search(body.query, k=5, min_score=0.3)
    if hits:
        top = hits[0].score
        hits = [h for h in hits if h.score >= top * 0.3]
    return [p.as_dict() for p in hits]


# ------------------------------------------------------------------ outbox, activity, notifications
@router.get("/outbox")
def outbox(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(OutboxMessage).where(OutboxMessage.org_id == user.org_id).order_by(OutboxMessage.sent_at.desc()).limit(300)).all()
    names = {a.id: a.name for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id))}
    return [S.outbox_out(m, names.get(m.agent_id)) for m in rows]


@router.get("/activity")
def activity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.org_id == user.org_id).order_by(AuditEvent.created_at.desc()).limit(300)).all()
    return [_event(e) for e in rows]


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.org_id == user.org_id,
                                                (Notification.user_id.is_(None)) | (Notification.user_id == user.id))
                      .order_by(Notification.created_at.desc()).limit(30)).all()
    return {"unread": sum(1 for n in rows if not n.read),
            "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "read": n.read,
                       "at": S.iso(n.created_at)} for n in rows]}


@router.post("/notifications/read")
def notifications_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.org_id == user.org_id, Notification.read.is_(False),
                                                   (Notification.user_id.is_(None)) | (Notification.user_id == user.id))):
        n.read = True
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ settings
@router.get("/settings")
def settings_get(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, user.org_id)
    smtp = dict((org.settings or {}).get("smtp") or {})
    if smtp.get("password"):
        smtp["password"] = "••••••••"
    if not (org.settings or {}).get("inbound_key"):
        import secrets
        org.settings = {**(org.settings or {}), "inbound_key": secrets.token_urlsafe(18)}
        db.commit()
    return {"org": {"id": org.id, "name": org.name}, "policy": service.default_policy(org), "smtp": smtp,
            "inbound_key": org.settings.get("inbound_key") if user.role == "admin" else None,
            "engine": llm.status(), "tools": catalog(), "is_admin": user.role == "admin"}


class PolicyIn(BaseModel):
    require_approval_external: bool | None = None
    require_approval_internal: bool | None = None
    max_emails_per_run: int | None = Field(default=None, ge=1, le=500)
    four_eyes: bool | None = None


class SmtpIn(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str | None = None
    from_email: str = ""
    from_name: str = ""


class SettingsIn(BaseModel):
    policy: PolicyIn | None = None
    smtp: SmtpIn | None = None


@router.patch("/settings")
def settings_patch(body: SettingsIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, user.org_id)
    st = dict(org.settings or {})
    if body.policy:
        pol = dict(st.get("policy") or {})
        pol.update({k: v for k, v in body.policy.model_dump().items() if v is not None})
        st["policy"] = pol
        audit(db, org.id, user.name, "settings.policy", "organization", org.id, "Updated safety policy", **pol)
    if body.smtp:
        old = dict(st.get("smtp") or {})
        new = body.smtp.model_dump()
        if not new.get("password") or new["password"] == "••••••••":
            new["password"] = old.get("password", "")
        st["smtp"] = new
        audit(db, org.id, user.name, "settings.email", "organization", org.id,
              "Enabled SMTP delivery" if new["enabled"] else "Using sandbox outbox")
    org.settings = st
    db.commit()
    return settings_get(user, db)


@router.get("/samples/{name}")
def sample_download(name: str, user: User = Depends(current_user)):
    path = (config.SAMPLES_DIR / Path(name).name)
    if not path.exists():
        raise HTTPException(404, "Sample not found.")
    return FileResponse(path, filename=path.name)


@router.post("/demo/reset")
def demo_reset(user: User = Depends(require_admin)):
    from ..seed import reset_demo
    reset_demo()
    return {"ok": True}


# ------------------------------------------------------------------ replies & do-not-contact
from ..models import FileVersion, Reply, Suppression  # noqa: E402
from ..runtime import replies as R  # noqa: E402
from ..runtime.files import ensure_initial_version, write_new_version  # noqa: E402


@router.get("/replies")
def replies_list(category: str = "all", status: str = "open", user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Reply).where(Reply.org_id == user.org_id)
    if status != "all":
        q = q.where(Reply.status == status)
    if category != "all":
        q = q.where(Reply.category == category)
    rows = db.scalars(q.order_by(Reply.received_at.desc()).limit(200)).all()
    names = {a.id: a.name for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id))}
    counts: dict[str, int] = {}
    for r in db.scalars(select(Reply).where(Reply.org_id == user.org_id, Reply.status == "open")):
        counts[r.category] = counts.get(r.category, 0) + 1
    return {"items": [R.reply_out(r, db.get(OutboxMessage, r.outbox_id) if r.outbox_id else None, names.get(r.agent_id)) for r in rows],
            "open_counts": counts}


class SimReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


@router.post("/outbox/{msg_id}/reply")
def outbox_simulate_reply(msg_id: str, body: SimReplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sandbox: record a reply from the recipient (in production replies arrive via /api/inbound/email)."""
    m = db.get(OutboxMessage, msg_id)
    if not m or m.org_id != user.org_id:
        raise HTTPException(404, "Message not found.")
    org = db.get(Organization, user.org_id)
    rep = R.record_reply(db, org, m.to, body.body, from_name=m.to_name, outbox_id=m.id, actor=f"{m.to_name or m.to} (sandbox reply)")
    db.commit()
    return R.reply_out(rep, m)


class InboundIn(BaseModel):
    from_email: str
    from_name: str = ""
    subject: str = ""
    text: str


@router.post("/inbound/email")
def inbound_email(body: InboundIn, request_key: str | None = None, db: Session = Depends(get_db),
                  x_agentjerry_key: str | None = Header(default=None)):
    """Webhook for your email provider's inbound parse (SendGrid, Mailgun, Postmark…)."""
    key = x_agentjerry_key or request_key
    org = next((o for o in db.scalars(select(Organization)) if key and (o.settings or {}).get("inbound_key") == key), None)
    if org is None:
        raise HTTPException(401, "Invalid inbound key.")
    rep = R.record_reply(db, org, body.from_email, body.text, body.subject, body.from_name)
    db.commit()
    return {"ok": True, "id": rep.id, "category": rep.category}


class RespondIn(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10000)


@router.post("/replies/{rid}/respond")
def reply_respond(rid: str, body: RespondIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..tools.email_transport import DeliveryError, deliver
    rep = db.get(Reply, rid)
    if not rep or rep.org_id != user.org_id:
        raise HTTPException(404, "Reply not found.")
    if rep.response_id:
        raise HTTPException(409, "You already responded to this reply.")
    if db.scalars(select(Suppression).where(Suppression.org_id == user.org_id, Suppression.email == rep.from_email)).first():
        raise HTTPException(409, "This person is on the do-not-contact list.")
    org = db.get(Organization, user.org_id)
    try:
        transport = deliver(org.settings or {}, rep.from_email, rep.from_name, body.subject, body.body)
    except DeliveryError as exc:
        raise HTTPException(502, f"Couldn’t send: {exc}")
    m = OutboxMessage(org_id=org.id, agent_id=rep.agent_id or "", execution_id="manual", idempotency_key=f"reply:{rep.id}",
                      to=rep.from_email, to_name=rep.from_name, subject=body.subject, body=body.body, transport=transport,
                      approved_by=user.id, touch=0)
    db.add(m)
    db.flush()
    rep.response_id = m.id
    rep.status = "handled"
    audit(db, org.id, user.name, "reply.responded", "reply", rep.id, f"Responded to {rep.from_name or rep.from_email}")
    db.commit()
    return R.reply_out(rep, db.get(OutboxMessage, rep.outbox_id) if rep.outbox_id else None)


@router.post("/replies/{rid}/status")
def reply_status(rid: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rep = db.get(Reply, rid)
    if not rep or rep.org_id != user.org_id:
        raise HTTPException(404, "Reply not found.")
    st = body.get("status")
    if st not in ("open", "handled"):
        raise HTTPException(422, "Status must be open or handled.")
    rep.status = st
    db.commit()
    return {"ok": True}


@router.get("/suppressions")
def suppressions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Suppression).where(Suppression.org_id == user.org_id).order_by(Suppression.created_at.desc())).all()
    return [{"id": s.id, "email": s.email, "reason": s.reason, "source": s.source, "created_by": s.created_by,
             "created_at": S.iso(s.created_at)} for s in rows]


class SuppIn(BaseModel):
    emails: str = Field(min_length=3, max_length=20000)
    reason: str = ""


@router.post("/suppressions")
def suppression_add(body: SuppIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..tools.spreadsheet import EMAIL_RE
    found = [e.strip().lower() for e in re.split(r"[\s,;]+", body.emails) if e.strip()]
    bad = [e for e in found if not EMAIL_RE.match(e)]
    if bad:
        raise HTTPException(422, f"Not a valid address: {bad[0]}")
    added = sum(R.add_suppression(db, user.org_id, e, body.reason or "Added manually", "manual", user.name) for e in found)
    db.commit()
    return {"added": added, "already_listed": len(found) - added}


@router.delete("/suppressions/{sid}")
def suppression_remove(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(Suppression, sid)
    if not s or s.org_id != user.org_id:
        raise HTTPException(404, "Not found.")
    db.delete(s)
    audit(db, user.org_id, user.name, "suppression.removed", "suppression", s.email, f"Removed {s.email} from the do-not-contact list")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ file versions & event trigger
@router.get("/files/{file_id}/versions")
def file_versions(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(DataFile, file_id)
    if not f or f.org_id != user.org_id:
        raise HTTPException(404, "File not found.")
    ensure_initial_version(db, f)
    db.commit()
    rows = db.scalars(select(FileVersion).where(FileVersion.file_id == f.id).order_by(FileVersion.version.desc())).all()
    return [{"version": v.version, "row_count": v.row_count, "source": v.source, "note": v.note, "created_by": v.created_by,
             "created_at": S.iso(v.created_at), "current": v.version == f.version} for v in rows]


@router.get("/files/{file_id}/download")
def file_download(file_id: str, version: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(DataFile, file_id)
    if not f or f.org_id != user.org_id:
        raise HTTPException(404, "File not found.")
    path = f.path
    if version and version != f.version:
        v = db.scalars(select(FileVersion).where(FileVersion.file_id == f.id, FileVersion.version == version)).first()
        if not v:
            raise HTTPException(404, "Version not found.")
        path = v.path
    stem = Path(f.name).stem
    return FileResponse(path, filename=f"{stem}_v{version or f.version}.{f.kind}")


@router.post("/files/{file_id}/replace")
def file_replace(file_id: str, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(DataFile, file_id)
    if not f or f.org_id != user.org_id:
        raise HTTPException(404, "File not found.")
    dest, name, ext = _save_upload(file, ("csv", "xlsx"))
    if ext != f.kind:
        dest.unlink(missing_ok=True)
        raise HTTPException(415, f"Upload a .{f.kind} file to replace {f.name}.")
    try:
        cols, rows = read_table(dest, ext)
    except SpreadsheetError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))
    v = write_new_version(db, f, cols, rows, source="upload", created_by=user.name, note=f"Uploaded {name}")
    dest.unlink(missing_ok=True)
    audit(db, user.org_id, user.name, "file.replaced", "file", f.id, f"Uploaded version {v} of {f.name} ({len(rows)} rows)")
    db.commit()
    started = []
    for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id, Agent.status == "deployed")).all():
        tr = a.trigger or {}
        if tr.get("type") == "file_updated" and tr.get("file_id") == f.id:
            try:
                ex = executor.start_execution(db, a, "live", "file_updated", user)
                started.append({"agent_id": a.id, "agent_name": a.name, "run_id": ex.id})
            except executor.RunError as exc:
                from ..security import notify as _n
                _n(db, user.org_id, "info", f"{a.name} didn’t start", str(exc), f"/agents/{a.id}")
                db.commit()
    return S.file_out(f) | {"triggered": started}
