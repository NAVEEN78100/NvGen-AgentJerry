from __future__ import annotations

from typing import Any

from ..engine.clarify import trigger_label
from ..models import (Agent, Approval, DataFile, Execution, ExecutionLog, KnowledgeSource, OutboxMessage, User,
                      Workflow)
from ..runtime.scheduler import next_run


def iso(dt) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:  # SQLite drops tzinfo; everything is stored in UTC
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "title": u.title}


def agent_brief(a: Agent, stats: dict | None = None) -> dict[str, Any]:
    spec = (a.requirement or {}).get("spec") or {}
    return {
        "id": a.id, "name": a.name, "goal": a.goal, "status": a.status, "department": a.department,
        "trigger": a.trigger, "trigger_label": trigger_label(a.trigger),
        "next_run": next_run(a.trigger) if a.status == "deployed" else None,
        "pattern": spec.get("pattern"), "purpose": spec.get("purpose"),
        "source_file": (spec.get("source") or {}).get("file_name"),
        "approval_required": (spec.get("approval") or {}).get("required"),
        "created_at": iso(a.created_at), "updated_at": iso(a.updated_at), "deployed_at": iso(a.deployed_at),
        "engine": a.engine, "stats": stats or {},
    }


def workflow_out(w: Workflow | None) -> dict[str, Any] | None:
    if w is None:
        return None
    return {"id": w.id, "version": w.version, "steps": w.steps, "validation": w.validation, "created_at": iso(w.created_at)}


def agent_full(a: Agent, w: Workflow | None, stats: dict | None = None) -> dict[str, Any]:
    st = a.requirement or {}
    out = agent_brief(a, stats)
    out.update({
        "prompt": a.prompt,
        "requirement": st.get("spec"),
        "questions": [q for q in st.get("questions", []) if q.get("blocking")],
        "fields": st.get("fields", []),
        "conversation": a.conversation,
        "workflow": workflow_out(w),
        "tested_version": a.last_test_passed_version,
        "can_deploy": bool(w and a.last_test_passed_version == w.version and a.status in ("tested", "paused")),
        "can_run_live": bool(w and a.last_test_passed_version == w.version),
        "knowledge_ids": a.knowledge_ids,
    })
    return out


def log_out(l: ExecutionLog) -> dict[str, Any]:
    return {"step_id": l.step_id, "index": l.step_index, "tool": l.tool, "label": l.label, "status": l.status,
            "message": l.message, "output": l.output, "attempts": l.attempts,
            "started_at": iso(l.started_at), "finished_at": iso(l.finished_at), "duration_ms": l.duration_ms}


def execution_out(e: Execution, agent_name: str | None = None, logs: list[ExecutionLog] | None = None,
                  approval_id: str | None = None) -> dict[str, Any]:
    out = {"id": e.id, "agent_id": e.agent_id, "agent_name": agent_name, "mode": e.mode, "status": e.status,
           "triggered_by": e.triggered_by, "workflow_version": e.workflow_version, "current_step": e.current_step,
           "summary": e.summary, "error": e.error, "started_at": iso(e.started_at), "finished_at": iso(e.finished_at),
           "approval_id": approval_id}
    if logs is not None:
        out["logs"] = [log_out(l) for l in sorted(logs, key=lambda x: x.step_index)]
    return out


def approval_out(ap: Approval, agent_name: str | None = None, with_items: bool = True,
                 decided_by_name: str | None = None) -> dict[str, Any]:
    items = ap.items
    out = {"id": ap.id, "execution_id": ap.execution_id, "agent_id": ap.agent_id, "agent_name": agent_name,
           "action": ap.action, "title": ap.title, "reason": ap.reason, "status": ap.status,
           "decided_by": decided_by_name, "decided_at": iso(ap.decided_at), "created_at": iso(ap.created_at),
           "counts": {"total": len(items), "approved": sum(1 for i in items if i.status == "approved"),
                      "rejected": sum(1 for i in items if i.status == "rejected"),
                      "pending": sum(1 for i in items if i.status == "pending"),
                      "flagged": sum(1 for i in items if i.flags)}}
    if with_items:
        out["items"] = [{"id": i.id, "idx": i.idx, "ref_key": i.ref_key, "payload": i.payload, "flags": i.flags,
                         "status": i.status, "edited": i.edited, "note": i.note} for i in items]
    return out


def file_out(f: DataFile) -> dict[str, Any]:
    return {"id": f.id, "name": f.name, "kind": f.kind, "columns": f.columns, "row_count": f.row_count,
            "version": f.version or 1, "created_at": iso(f.created_at), "updated_at": iso(f.updated_at)}


def knowledge_out(k: KnowledgeSource) -> dict[str, Any]:
    return {"id": k.id, "title": k.title, "file_name": k.file_name, "source_type": k.source_type,
            "chunk_count": k.chunk_count, "char_count": k.char_count, "status": k.status, "created_at": iso(k.created_at)}


def outbox_out(m: OutboxMessage, agent_name: str | None = None) -> dict[str, Any]:
    return {"id": m.id, "agent_id": m.agent_id, "agent_name": agent_name, "execution_id": m.execution_id,
            "to": m.to, "to_name": m.to_name, "subject": m.subject, "body": m.body, "transport": m.transport,
            "status": m.status, "sent_at": iso(m.sent_at), "touch": m.touch, "replied_at": iso(m.replied_at),
            "reply_category": m.reply_category}
