"""Execution Controller.

Runs a validated workflow step by step with a deterministic executor (the LLM
only ever proposes; this code performs). Supports:
  * test mode  – side-effect tools are dry-run, approvals are simulated
  * live mode  – approval gates pause the run; it resumes after a decision
  * resumable  – step outputs are persisted after every step
  * idempotent – every email has an idempotency key, so a retry never re-sends
  * defence in depth – email.send re-verifies approvals in the database"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import config
from ..db import session_scope
from ..engine import writer
from ..models import (Agent, Approval, ApprovalItem, DataFile, Execution, ExecutionLog, MemoryEntry, Metric,
                      Organization, OutboxMessage, User, Workflow)
from ..security import audit, notify
from ..tools.email_transport import DeliveryError, deliver
from ..tools.registry import TOOLS
from ..tools.spreadsheet import EMAIL_RE, parse_date, parse_number, read_table
from .knowledge import BM25Retriever

log = logging.getLogger("agentjerry.executor")

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agentjerry-run")
_locks: dict[str, threading.Lock] = {}
SYNC = os.getenv("AGENTJERRY_SYNC_EXECUTION", "0") == "1"


class StepFailed(Exception):
    pass


class SafetyViolation(StepFailed):
    pass


class WaitForApproval(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class RunError(ValueError):
    """Raised when a run cannot start (shown to the user)."""


def start_execution(db, agent: Agent, mode: str, triggered_by: str = "manual", user: User | None = None) -> Execution:
    wf = db.scalars(select(Workflow).where(Workflow.agent_id == agent.id).order_by(Workflow.version.desc())).first()
    if wf is None:
        raise RunError("This agent has no workflow yet. Finish setting it up in the Studio.")
    if not (wf.validation or {}).get("valid"):
        raise RunError("The workflow failed validation, so it can’t run. Fix the failed checks first.")
    if mode == "live":
        if agent.last_test_passed_version != wf.version:
            raise RunError("Run a successful test of the latest version before running it for real.")
        busy = db.scalars(select(Execution).where(Execution.agent_id == agent.id, Execution.mode == "live",
                                                  Execution.status.in_(["queued", "running", "awaiting_approval"]))).first()
        if busy:
            raise RunError("A live run is already in progress or waiting for your approval. Finish that one first."
                           if busy.status != "awaiting_approval" else
                           "The last run is still waiting for your approval. Review it before starting another.")
    ex = Execution(agent_id=agent.id, org_id=agent.org_id, workflow_version=wf.version, mode=mode,
                   triggered_by=triggered_by, triggered_user=user.id if user else None, status="queued",
                   context={"data": {}, "step_index": 0})
    db.add(ex)
    db.flush()
    for i, s in enumerate(wf.steps):
        db.add(ExecutionLog(execution_id=ex.id, step_id=s["id"], step_index=i, tool=s["tool"], label=s["label"]))
    audit(db, agent.org_id, user.name if user else "Scheduler", "run.started", "execution", ex.id,
          f"{'Test' if mode == 'test' else 'Live'} run of “{agent.name}”", mode=mode, agent_id=agent.id)
    db.commit()
    submit(ex.id, 0)
    return ex


def submit(execution_id: str, start_index: int) -> None:
    if SYNC:
        _run(execution_id, start_index)
    else:
        _pool.submit(_run, execution_id, start_index)


def resume(execution_id: str) -> None:
    with session_scope() as db:
        ex = db.get(Execution, execution_id)
        if not ex or ex.status != "awaiting_approval":
            return
        idx = int(ex.context.get("step_index", 0)) + 1
        ex.status = "queued"
    submit(execution_id, idx)


def _lock(execution_id: str) -> threading.Lock:
    return _locks.setdefault(execution_id, threading.Lock())


def _run(execution_id: str, start_index: int) -> None:
    with _lock(execution_id):
        try:
            _run_inner(execution_id, start_index)
        except Exception:  # last-resort guard: never leave a run "running"
            log.error("run crashed: %s", traceback.format_exc())
            with session_scope() as db:
                ex = db.get(Execution, execution_id)
                if ex and ex.status in ("queued", "running"):
                    ex.status = "failed"
                    ex.error = "Unexpected error while running. The team has the details in the server log."
                    ex.finished_at = _now()


def _run_inner(execution_id: str, start_index: int) -> None:
    with session_scope() as db:
        ex = db.get(Execution, execution_id)
        if ex is None or ex.status in ("cancelled", "completed", "failed"):
            return
        agent = db.get(Agent, ex.agent_id)
        wf = db.scalars(select(Workflow).where(Workflow.agent_id == ex.agent_id,
                                               Workflow.version == ex.workflow_version)).one()
        steps = wf.steps
        req = (agent.requirement or {}).get("spec", {})
        org = db.get(Organization, ex.org_id)
        ex.status = "running"
        db.commit()

    data_box: dict[str, Any] = {}
    for i in range(start_index, len(steps)):
        step = steps[i]
        t0 = time.monotonic()
        with session_scope() as db:
            ex = db.get(Execution, execution_id)
            if ex.status == "cancelled":
                return
            data_box = dict(ex.context.get("data", {}))
            lg = _log(db, execution_id, step["id"])
            lg.status = "running"
            lg.started_at = _now()
            lg.attempts += 1
            ex.current_step = step["id"]
            ex.context = {**ex.context, "step_index": i}
        try:
            handler = HANDLERS[step["tool"]]
            result = _with_retry(lambda: handler(StepCtx(execution_id, ex.mode, step, steps, data_box, req, agent, org)))
            status, message, output = "passed", result.get("message", ""), result.get("output", {})
            for k, v in result.get("data", {}).items():
                data_box[k] = v
        except WaitForApproval as w:
            _pace(t0)
            with session_scope() as db:
                ex = db.get(Execution, execution_id)
                lg = _log(db, execution_id, step["id"])
                lg.status = "waiting"
                lg.message = str(w)
                ex.status = "awaiting_approval"
                ex.context = {**ex.context, "data": data_box, "step_index": i}
            return
        except Exception as exc:
            _pace(t0)
            msg = str(exc) if isinstance(exc, (StepFailed, DeliveryError)) else f"Unexpected error: {exc}"
            if not isinstance(exc, StepFailed):
                log.error("step crashed: %s", traceback.format_exc())
            _finish_failed(execution_id, step, i, steps, msg)
            return
        _pace(t0)
        with session_scope() as db:
            ex = db.get(Execution, execution_id)
            lg = _log(db, execution_id, step["id"])
            lg.status = status
            lg.message = message
            lg.output = output
            lg.finished_at = _now()
            lg.duration_ms = int((time.monotonic() - t0) * 1000)
            ex.context = {**ex.context, "data": data_box, "step_index": i}
            if ex.status == "cancelled":
                return

    _finish_completed(execution_id, data_box)


def _with_retry(fn: Callable[[], dict], attempts: int = 3) -> dict:
    delay = 0.4
    for n in range(attempts):
        try:
            return fn()
        except (StepFailed, WaitForApproval):
            raise
        except (ConnectionError, TimeoutError, DeliveryError):
            if n == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise StepFailed("retries exhausted")


def _pace(t0: float) -> None:
    if config.STEP_PACING_MS and not SYNC:
        remaining = config.STEP_PACING_MS / 1000 - (time.monotonic() - t0)
        if remaining > 0:
            time.sleep(remaining)


def _log(db, execution_id: str, step_id: str) -> ExecutionLog:
    return db.scalars(select(ExecutionLog).where(ExecutionLog.execution_id == execution_id,
                                                 ExecutionLog.step_id == step_id)).one()


def _finish_failed(execution_id: str, step: dict, index: int, steps: list[dict], msg: str) -> None:
    with session_scope() as db:
        ex = db.get(Execution, execution_id)
        agent = db.get(Agent, ex.agent_id)
        lg = _log(db, execution_id, step["id"])
        lg.status = "failed"
        lg.message = msg
        lg.finished_at = _now()
        for s in steps[index + 1:]:
            l2 = _log(db, execution_id, s["id"])
            l2.status = "skipped"
            l2.message = "Skipped because an earlier step failed."
        ex.status = "failed"
        ex.error = f"{step['label']}: {msg}"
        ex.finished_at = _now()
        ex.summary = {**(ex.summary or {}), "headline": f"Stopped at “{step['label']}”", "test": ex.mode == "test"}
        notify(db, ex.org_id, "run_failed", f"{agent.name} stopped", f"{step['label']}: {msg}",
               f"/agents/{agent.id}/runs/{ex.id}")
        audit(db, ex.org_id, "AgentJerry", "run.failed", "execution", ex.id, ex.error, agent_id=agent.id)


def _finish_completed(execution_id: str, data: dict) -> None:
    with session_scope() as db:
        ex = db.get(Execution, execution_id)
        agent = db.get(Agent, ex.agent_id)
        s = _summarize(data, ex.mode, agent)
        ex.summary = s
        ex.status = "completed"
        ex.finished_at = _now()
        ex.current_step = None
        if ex.mode == "test":
            wf_latest = db.scalars(select(Workflow).where(Workflow.agent_id == agent.id)
                                   .order_by(Workflow.version.desc())).first()
            if wf_latest and wf_latest.version == ex.workflow_version:
                agent.last_test_passed_version = ex.workflow_version
                if agent.status in ("ready", "draft"):
                    agent.status = "tested"
        else:
            if s.get("sent"):
                db.add(Metric(org_id=ex.org_id, agent_id=agent.id, name="items_processed", value=s["sent"]))
        notify(db, ex.org_id, "run_completed", f"{agent.name}: {'test passed' if ex.mode == 'test' else 'run finished'}",
               s["headline"], f"/agents/{agent.id}/runs/{ex.id}")
        audit(db, ex.org_id, "AgentJerry", "run.completed", "execution", ex.id, s["headline"], agent_id=agent.id)


def _summarize(data: dict, mode: str, agent: Agent) -> dict[str, Any]:
    ent = ((agent.requirement or {}).get("spec") or {}).get("entity") or {"plural": "records", "singular": "record"}
    s = {
        "test": mode == "test",
        "loaded": data.get("_loaded"),
        "matched": data.get("_matched"),
        "skipped_memory": data.get("_skipped_memory", 0),
        "drafted": len(data.get("drafts", []) or []),
        "flagged": data.get("_flagged", 0),
        "approved": data.get("_approved"),
        "rejected": data.get("_rejected"),
        "sent": data.get("_sent", 0),
        "simulated": data.get("_simulated", 0),
        "deferred": data.get("_deferred", 0),
        "followups": data.get("_followups", 0),
        "suppressed": data.get("_suppressed", 0),
    }
    if mode == "test":
        s["headline"] = (f"Test passed — {s['drafted']} drafts would be sent for your approval. Nothing real happened."
                         if s["drafted"] else f"Test passed — no {ent['plural']} need emails right now.")
    else:
        if not s["drafted"]:
            s["headline"] = f"Nothing to do — no new {ent['plural']} this time."
        else:
            parts = [f"Sent {s['sent']} email{'s' if s['sent'] != 1 else ''}"]
            if s.get("rejected"):
                parts.append(f"{s['rejected']} rejected")
            if s.get("skipped_memory"):
                parts.append(f"{s['skipped_memory']} skipped as already handled")
            s["headline"] = ", ".join(parts) + "."
    return s


# ------------------------------------------------------------------ handlers

class StepCtx:
    def __init__(self, execution_id, mode, step, steps, data, req, agent, org):
        self.execution_id = execution_id
        self.mode = mode
        self.step = step
        self.steps = steps
        self.data = data
        self.req = req
        self.agent = agent
        self.org = org
        self.params = step.get("params", {})

    @property
    def ent(self) -> dict:
        return self.req.get("entity") or {"singular": "record", "plural": "records"}

    def row_name(self, row: dict) -> str:
        roles = self.req.get("roles", {})
        for r in ("name", "first_name", "company", "email", "invoice"):
            c = roles.get(r)
            if c and row.get(c):
                return row[c]
        return f"Row {row.get('_row', '?')}"


def h_read(c: StepCtx) -> dict:
    with session_scope() as db:
        f = db.get(DataFile, c.params["file_id"])
        if f is None:
            raise StepFailed("The spreadsheet was deleted. Choose another file in the Studio.")
        path, kind, name = f.path, f.kind, f.name
    try:
        columns, rows = read_table(path, kind)
    except Exception as exc:
        raise StepFailed(f"Couldn’t read {name}: {exc}")
    for i, r in enumerate(rows):
        r["_row"] = i + 2  # spreadsheet row number (header is row 1)
    missing = [col for col in (c.req.get("roles") or {}).values() if col and col not in columns]
    if missing:
        raise StepFailed(f"{name} no longer has the column(s) {', '.join(missing)}. Re-upload or rebuild the agent.")
    return {"message": f"Loaded {len(rows)} {c.ent['plural']} from {name}.",
            "output": {"count": len(rows), "columns": columns, "preview": [_clean(r) for r in rows[:6]]},
            "data": {"rows": rows, "_loaded": len(rows)}}


def _clean(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def h_filter(c: StepCtx) -> dict:
    rows = c.data.get("rows", [])
    col, op, val = c.params.get("column"), c.params.get("op"), c.params.get("value")
    and_not = c.params.get("and_not")
    today = date.today()

    def keep(r: dict) -> bool:
        v = (r.get(col) or "").strip()
        ok = True
        if op == "equals":
            ok = v.lower() == str(val).strip().lower()
            if not ok and v.lower() in [str(x).strip().lower() for x in c.params.get("or_values") or []]:
                r["_needs_memory"] = True  # only a follow-up candidate if *this agent* emailed them
                ok = True
        elif op == "not_equals":
            ok = v.lower() != str(val).strip().lower()
        elif op == "contains":
            ok = str(val).lower() in v.lower()
        elif op == "before_today":
            d = parse_date(v)
            ok = bool(d and d < today)
        elif op == "not_empty":
            ok = bool(v)
        if ok and and_not and and_not.get("column"):
            ok = (r.get(and_not["column"]) or "").strip().lower() not in [x.lower() for x in and_not.get("values", [])]
        return ok

    kept = [r for r in rows if keep(r)]
    removed = len(rows) - len(kept)
    return {"message": f"{len(kept)} of {len(rows)} {c.ent['plural']} match ({c.params.get('label')}).",
            "output": {"kept": len(kept), "removed": removed, "rule": c.params.get("label"),
                       "sample": [c.row_name(r) for r in kept[:8]]},
            "data": {"rows": kept, "_matched": len(kept)}}


def h_mem_exclude(c: StepCtx) -> dict:
    rows = c.data.get("rows", [])
    key_col, ns, cooldown = c.params["key_column"], c.params["namespace"], c.params.get("cooldown_days")
    with session_scope() as db:
        entries = {e.key: (e.value, _aware(e.updated_at)) for e in db.scalars(
            select(MemoryEntry).where(MemoryEntry.agent_id == c.agent.id, MemoryEntry.namespace == ns))}
    seq = c.params.get("sequence") or None
    kept, skipped, followups = [], [], 0
    cutoff = _now() - timedelta(days=cooldown) if cooldown else None
    for r in rows:
        k = (r.get(key_col) or "").strip().lower()
        hit = entries.get(k) if k else None
        if not hit:
            if r.get("_needs_memory"):
                skipped.append({"name": c.row_name(r), "key": k, "when": None, "reason": "marked by someone else"})
                continue
            r["_touch"] = 1
            kept.append(r)
            continue
        val, when = hit
        base = {"name": c.row_name(r), "key": k, "when": when.isoformat() if when else None}
        if val.get("replied"):
            skipped.append(base | {"reason": "replied"})
        elif seq:
            touches = int(val.get("touches") or 1)
            due = when is None or when <= _now() - timedelta(days=int(seq["after_days"]))
            if touches >= int(seq["max_touches"]):
                skipped.append(base | {"reason": "sequence finished"})
            elif not due:
                skipped.append(base | {"reason": f"waiting {seq['after_days']} days for a reply"})
            else:
                r["_touch"] = touches + 1
                r["_prev_subject"] = val.get("first_subject") or val.get("subject") or ""
                kept.append(r)
                followups += 1
        elif cutoff is None or (when and when >= cutoff):
            skipped.append(base | {"reason": f"already {ns}"})
        else:
            r["_touch"] = int(val.get("touches") or 1) + 1
            kept.append(r)
    if c.data.get("_matched") is None:
        c.data["_matched"] = len(rows)
    new = len(kept) - followups
    if seq:
        msg = f"{new} new, {followups} due a follow-up, {len(skipped)} skipped (replied or not due yet)."
    else:
        msg = (f"Skipped {len(skipped)} already {ns} — {len(kept)} {c.ent['plural']} to go." if skipped else
               f"None of these {c.ent['plural']} were {ns} before — {len(kept)} to go.")
    return {"message": msg, "output": {"kept": len(kept), "followups": followups, "skipped": skipped[:50],
                                       "memory_size": len(entries)},
            "data": {"rows": kept, "_skipped_memory": len(skipped), "_followups": followups,
                     "_matched": c.data.get("_matched")}}


def _suppressed(org_id: str) -> dict[str, str]:
    from ..models import Suppression
    with session_scope() as db:
        return {s.email.lower(): s.reason for s in db.scalars(select(Suppression).where(Suppression.org_id == org_id))}


def h_suppress(c: StepCtx) -> dict:
    rows = c.data.get("rows", [])
    col = c.params.get("email_column") or (c.req.get("roles") or {}).get("email")
    sup = _suppressed(c.agent.org_id)
    kept, removed = [], []
    for r in rows:
        e = (r.get(col) or "").strip().lower()
        if e and e in sup:
            removed.append({"name": c.row_name(r), "email": e, "reason": sup[e]})
        else:
            kept.append(r)
    msg = (f"Removed {len(removed)} on the do-not-contact list — {len(kept)} remain." if removed else
           f"Nobody here is on the do-not-contact list ({len(sup)} people listed).")
    return {"message": msg, "output": {"removed": removed, "list_size": len(sup)},
            "data": {"rows": kept, "_suppressed": len(removed)}}


def h_sheet_update(c: StepCtx) -> dict:
    sent = c.data.get("sent", []) if c.mode == "live" else (c.data.get("approved") or c.data.get("drafts") or [])
    keys = {(d.get("key") or d.get("to") or "").lower() for d in sent if (d.get("key") or d.get("to"))}
    col, value, date_col = c.params["column"], c.params["value"], c.params.get("date_column") or "Last contacted"
    if c.mode == "test":
        return {"message": f"Test mode — would mark {len(keys)} rows “{value}” in {c.params.get('file_name')}.",
                "output": {"would_update": len(keys)}}
    if not keys:
        return {"message": "Nobody was emailed, so the sheet was left unchanged.", "output": {"updated": 0}}
    from ..runtime.files import write_new_version
    with session_scope() as db:
        f = db.get(DataFile, c.params["file_id"])
        if f is None:
            raise StepFailed("The spreadsheet was deleted, so it couldn’t be updated.")
        columns, rows = read_table(f.path, f.kind)
        key_col = c.params.get("key_column")
        if col not in columns:
            columns.append(col)
        if date_col not in columns:
            columns.append(date_col)
        today = date.today().isoformat()
        n = 0
        for r in rows:
            if (r.get(key_col) or "").strip().lower() in keys:
                r[col] = value
                r[date_col] = today
                n += 1
        v = write_new_version(db, f, columns, rows, source="agent", created_by=c.agent.name,
                              note=f"Marked {n} rows “{value}”")
        name = f.name
    return {"message": f"Marked {n} rows “{value}” in {name} (version {v}).",
            "output": {"updated": n, "version": v, "file_id": c.params["file_id"]}}


def h_retrieve(c: StepCtx) -> dict:
    rows = c.data.get("rows", [])
    if not rows:
        return {"message": "Nothing to look up.", "output": {"hits": 0}, "data": {"passages": []}}
    purpose_terms = {"follow_up": "benefits results customers", "payment_reminder": "payment terms late fee invoice",
                     "interview_invite": "interview process candidates", "welcome": "onboarding getting started",
                     "thank_you": "customers"}.get(c.params.get("purpose"), "")
    with session_scope() as db:
        retr = BM25Retriever(db, c.agent.org_id, c.params.get("source_ids") or None)
        per_row, sources, hits = [], {}, 0
        for r in rows:
            q = " ".join(r.get(col, "") for col in c.params.get("query_columns", [])) + " " + purpose_terms
            ps = [p.as_dict() for p in retr.search(q, k=2)]
            if ps:
                hits += 1
                sources[ps[0]["source_title"]] = sources.get(ps[0]["source_title"], 0) + 1
            per_row.append(ps)
    return {"message": f"Found relevant knowledge for {hits} of {len(rows)} {c.ent['plural']}.",
            "output": {"hits": hits, "sources": sources,
                       "example": per_row[0][0] if per_row and per_row[0] else None},
            "data": {"passages": per_row}}


def h_draft(c: StepCtx) -> dict:
    rows = c.data.get("rows", [])
    cap = int((c.org.settings or {}).get("policy", {}).get("max_emails_per_run", 50))
    deferred = max(0, len(rows) - cap)
    rows = rows[:cap]
    passages = (c.data.get("passages") or [[] for _ in rows])[:len(rows)]
    roles = c.params.get("roles", {})
    spec = dict(c.params)
    lines = []
    if c.params.get("mentions"):
        from .knowledge import best_sentence
        with session_scope() as db:
            retr = BM25Retriever(db, c.agent.org_id)
            for topic in c.params["mentions"]:
                hits = retr.search(topic, k=1, min_score=1.0)
                lines.append({"topic": topic, "line": best_sentence(hits[0].text, topic) if hits else None,
                              "source": hits[0].source_title if hits else None})
    spec["mention_lines"] = lines
    drafts_raw, engine = writer.draft_all(rows, roles, spec, passages)
    email_col = roles.get("email")
    key_col = (c.req.get("memory") or {}).get("key_column") or email_col
    drafts = []
    for i, (r, d) in enumerate(zip(rows, drafts_raw)):
        cites = []
        up = d.get("used_passage")
        if isinstance(up, int) and 0 <= up < len(passages[i]):
            p = passages[i][up]
            cites.append({"source_title": p["source_title"], "section": p["section"], "text": p["text"][:400]})
        drafts.append({"key": (r.get(key_col) or "").strip().lower(), "to": (r.get(email_col) or "").strip(),
                       "to_name": c.row_name(r), "subject": d["subject"], "body": d["body"],
                       "row": _clean(r), "row_number": r.get("_row"), "citations": cites, "engine": d.get("engine"),
                       "touch": r.get("_touch", 1)})
    msg = f"Wrote {len(drafts)} personalised drafts" + (" with Claude." if engine == "claude" else ".")
    if deferred:
        msg += f" {deferred} more will be handled next run (limit {cap} per run)."
    return {"message": msg, "output": {"count": len(drafts), "engine": engine, "deferred": deferred,
                                       "samples": drafts[:3]},
            "data": {"drafts": drafts, "_deferred": deferred, "passages": None, "rows": None}}


def h_summarize(c: StepCtx) -> dict:
    rows = c.data.get("rows", [])
    gb, sm, owner = c.params.get("group_by"), c.params.get("sum"), c.params.get("owner")
    groups: dict[str, dict] = {}
    total = 0.0 if sm else None
    for r in rows:
        v = (r.get(gb) or "—") if gb else "All"
        g = groups.setdefault(v, {"value": v, "count": 0, "total": 0.0 if sm else None})
        g["count"] += 1
        if sm:
            n = parse_number(r.get(sm, "")) or 0
            g["total"] += n
            total += n
    owners: dict[str, int] = {}
    if owner and owner != gb:
        for r in rows:
            owners[r.get(owner) or "Unassigned"] = owners.get(r.get(owner) or "Unassigned", 0) + 1
    top = []
    if sm:
        name_col = c.params.get("company_column") or c.params.get("name_column")
        ranked = sorted(rows, key=lambda r: -(parse_number(r.get(sm, "")) or 0))[:3]
        top = [{"label": r.get(name_col) or c.row_name(r), "value": parse_number(r.get(sm, "")) or 0} for r in ranked]
    summary = {"count": len(rows), "group_by": gb, "groups": sorted(groups.values(), key=lambda g: -g["count"]),
               "total": total, "owners": [{"value": k, "count": v} for k, v in sorted(owners.items(), key=lambda kv: -kv[1])],
               "top": top}
    return {"message": f"Summarised {len(rows)} {c.ent['plural']} into {len(groups)} groups.",
            "output": summary, "data": {"summary": summary, "rows": None, "_matched": len(rows)}}


def h_draft_report(c: StepCtx) -> dict:
    d = writer.report_draft(c.data.get("summary", {}), c.params)
    to = c.params["to"]
    draft = {"key": f"{to.lower()}|{date.today().isoformat()}", "to": to, "to_name": to.split("@")[0].title(),
             "subject": d["subject"], "body": d["body"], "row": {}, "citations": [], "engine": d["engine"]}
    return {"message": f"Wrote the report email for {to}.", "output": {"samples": [draft]}, "data": {"drafts": [draft]}}


RISKY = [r"\bguarantee(d)?\b", r"\b100%\b", r"\brisk[- ]free\b", r"\bact now\b", r"\bwire (the )?money\b",
         r"\burgent(ly)? transfer\b", r"\bpassword\b", r"\bbank account (number|details)\b"]


def h_safety(c: StepCtx) -> dict:
    drafts = c.data.get("drafts", [])
    seen: set[str] = set()
    flagged = 0
    for d in drafts:
        flags = []
        if not d.get("to") or not EMAIL_RE.match(d["to"]):
            flags.append({"level": "error", "text": f"“{d.get('to') or 'empty'}” is not a valid email address."})
        if d.get("to", "").lower() in seen:
            flags.append({"level": "error", "text": "Duplicate recipient in this run."})
        seen.add(d.get("to", "").lower())
        if re.search(r"\[[A-Za-z ]+\]|\{\{.*?\}\}|<[A-Z_]+>", d.get("body", "") + d.get("subject", "")):
            flags.append({"level": "error", "text": "Contains an unfilled placeholder."})
        if re.search(r"^(Hi|Dear) there,", d.get("body", "")):
            flags.append({"level": "warn", "text": "No name found — the greeting is generic."})
        for pat in RISKY:
            m = re.search(pat, d.get("body", ""), re.I)
            if m:
                flags.append({"level": "warn", "text": f"Risky wording: “{m.group(0)}”."})
        if len(d.get("body", "")) > 2500:
            flags.append({"level": "warn", "text": "Very long email."})
        d["flags"] = flags
        if flags:
            flagged += 1
    errors = sum(1 for d in drafts if any(f["level"] == "error" for f in d.get("flags", [])))
    msg = (f"Checked {len(drafts)} drafts — all clear." if not flagged else
           f"Checked {len(drafts)} drafts — {flagged} need attention" + (f" ({errors} can’t be sent as-is)." if errors else "."))
    return {"message": msg, "output": {"checked": len(drafts), "flagged": flagged, "errors": errors,
                                       "issues": [{"to": d["to_name"], "flags": d["flags"]} for d in drafts if d.get("flags")][:20]},
            "data": {"drafts": drafts, "_flagged": flagged}}


def h_approval(c: StepCtx) -> dict:
    drafts = c.data.get("drafts", [])
    if c.data.get("_approval_done"):
        return {"message": c.data.get("_approval_msg", "Approved."), "output": {}}
    if not drafts:
        return {"message": "Nothing to approve.", "output": {"count": 0}, "data": {"approved": []}}
    if c.mode == "test":
        return {"message": f"Would pause here and ask you to approve {len(drafts)} drafts.",
                "output": {"count": len(drafts), "simulated": True, "drafts": drafts},
                "data": {"approved": drafts}}
    with session_scope() as db:
        existing = db.scalars(select(Approval).where(Approval.execution_id == c.execution_id,
                                                     Approval.step_id == c.step["id"])).first()
        if existing is None:
            ap = Approval(execution_id=c.execution_id, agent_id=c.agent.id, org_id=c.agent.org_id,
                          step_id=c.step["id"], action=c.params.get("action", "email.send"),
                          title=f"{len(drafts)} {c.req.get('message', {}).get('noun', 'emails')} from “{c.agent.name}”",
                          reason=c.req.get("approval", {}).get("reason", ""))
            for i, d in enumerate(drafts):
                blocked = any(f["level"] == "error" for f in d.get("flags", []))
                ap.items.append(ApprovalItem(idx=i, ref_key=d["key"] or d["to"], payload=d, flags=d.get("flags", []),
                                             status="rejected" if blocked else "pending",
                                             note="Blocked by safety check — edit to fix, then approve." if blocked else ""))
            db.add(ap)
            db.flush()
            notify(db, c.agent.org_id, "approval", f"{len(drafts)} drafts need your approval",
                   f"“{c.agent.name}” is waiting for you.", f"/approvals/{ap.id}")
            audit(db, c.agent.org_id, "AgentJerry", "approval.requested", "approval", ap.id,
                  f"{len(drafts)} drafts awaiting approval", agent_id=c.agent.id)
    raise WaitForApproval(f"Waiting for your approval of {len(drafts)} drafts.")


def _approved_from_db(c: StepCtx) -> tuple[list[dict], int, int, str | None]:
    with session_scope() as db:
        ap = db.scalars(select(Approval).where(Approval.execution_id == c.execution_id)).first()
        if ap is None:
            return [], 0, 0, None
        if ap.status != "decided":
            raise SafetyViolation("Approval has not been decided — nothing can be sent.")
        approved = [dict(it.payload, _approval_item=it.id) for it in ap.items if it.status == "approved"]
        rejected = sum(1 for it in ap.items if it.status == "rejected")
        return approved, len(approved), rejected, ap.decided_by


def h_send(c: StepCtx) -> dict:
    gated = any(s["tool"] == "approval.request" for s in c.steps[:c.steps.index(c.step)])
    if c.mode == "test":
        n = len(c.data.get("approved", c.data.get("drafts", [])) or [])
        return {"message": f"Test mode — {n} emails were not sent.", "output": {"simulated": n},
                "data": {"_simulated": n}}
    policy = (c.org.settings or {}).get("policy", {})
    if not gated and (c.req.get("approval", {}).get("required") or
                      (policy.get("require_approval_external", True) and c.req.get("approval", {}).get("external", True))):
        raise SafetyViolation("Blocked: this action needs approval and the workflow has no approval step.")
    approved_by = None
    if gated:
        items, n_ok, n_rej, approved_by = _approved_from_db(c)
        c.data["_approved"], c.data["_rejected"] = n_ok, n_rej
    else:
        items = c.data.get("drafts", [])
    sent, failed, blocked = [], [], []
    sup = _suppressed(c.agent.org_id)
    with session_scope() as db:
        org = db.get(Organization, c.agent.org_id)
        for d in items:
            if not EMAIL_RE.match(d.get("to", "")):
                failed.append({"to": d.get("to"), "error": "invalid address"})
                continue
            if d.get("to", "").lower() in sup:
                blocked.append(d.get("to_name") or d.get("to"))  # opted out while waiting for approval
                continue
            key = f"{c.agent.id}:{c.execution_id}:{d['key'] or d['to'].lower()}"
            if db.scalars(select(OutboxMessage).where(OutboxMessage.idempotency_key == key)).first():
                sent.append(d)  # already delivered on a previous attempt — never re-send
                continue
            try:
                transport = deliver(org.settings or {}, d["to"], d.get("to_name", ""), d["subject"], d["body"])
                db.add(OutboxMessage(org_id=org.id, agent_id=c.agent.id, execution_id=c.execution_id,
                                     idempotency_key=key, to=d["to"], to_name=d.get("to_name", ""),
                                     subject=d["subject"], body=d["body"], transport=transport, approved_by=approved_by,
                                     touch=int(d.get("touch") or 1)))
                db.flush()
                sent.append(d)
            except DeliveryError as exc:
                failed.append({"to": d["to"], "error": str(exc)})
            except IntegrityError:
                db.rollback()
                sent.append(d)
        audit(db, org.id, "AgentJerry", "email.sent", "execution", c.execution_id,
              f"Sent {len(sent)} emails", failed=len(failed), agent_id=c.agent.id)
    if items and not sent and failed:
        raise StepFailed(f"No emails could be sent: {failed[0]['error']}")
    msg = f"Sent {len(sent)} email{'s' if len(sent) != 1 else ''}."
    if gated and c.data.get("_rejected"):
        msg += f" {c.data['_rejected']} rejected — not sent."
    if failed:
        msg += f" {len(failed)} failed."
    if blocked:
        msg += f" {len(blocked)} held back — they opted out after drafting."
    return {"message": msg, "output": {"sent": len(sent), "failed": failed,
                                       "recipients": [d["to_name"] for d in sent][:50]},
            "data": {"sent": [{"key": d["key"], "to": d["to"], "to_name": d["to_name"], "subject": d["subject"],
                               "touch": d.get("touch", 1)} for d in sent],
                     "_sent": len(sent), "_approved": c.data.get("_approved"), "_rejected": c.data.get("_rejected")}}


def h_mem_record(c: StepCtx) -> dict:
    sent = c.data.get("sent", []) if c.mode == "live" else c.data.get("approved", c.data.get("drafts", [])) or []
    ns = c.params["namespace"]
    if c.mode == "test":
        return {"message": f"Test mode — would remember {len(sent)} {c.ent['plural']}.", "output": {"would_record": len(sent)}}
    n = 0
    with session_scope() as db:
        for d in sent:
            k = (d.get("key") or d.get("to", "")).lower()
            if not k:
                continue
            e = db.scalars(select(MemoryEntry).where(MemoryEntry.agent_id == c.agent.id, MemoryEntry.namespace == ns,
                                                     MemoryEntry.key == k)).first()
            prev = dict(e.value or {}) if e else {}
            val = {"name": d.get("to_name"), "email": d.get("to"), "subject": d.get("subject"),
                   "first_subject": prev.get("first_subject") or d.get("subject"),
                   "touches": int(d.get("touch") or (int(prev.get("touches") or 0) + 1)),
                   "replied": bool(prev.get("replied")), "at": _now().isoformat()}
            if e:
                e.value = val
                e.execution_id = c.execution_id
                e.updated_at = _now()
            else:
                db.add(MemoryEntry(agent_id=c.agent.id, namespace=ns, key=k, value=val, execution_id=c.execution_id))
            n += 1
    return {"message": f"Remembered {n} {c.ent['plural'] if n != 1 else c.ent['singular']} for next time.",
            "output": {"recorded": n}}


def h_notify(c: StepCtx) -> dict:
    s = _summarize(c.data, c.mode, c.agent)
    return {"message": s["headline"], "output": s}


HANDLERS: dict[str, Callable[[StepCtx], dict]] = {
    "spreadsheet.read": h_read, "data.filter": h_filter, "memory.exclude": h_mem_exclude,
    "knowledge.retrieve": h_retrieve, "ai.draft": h_draft, "data.summarize": h_summarize,
    "ai.draft_report": h_draft_report, "safety.check": h_safety, "approval.request": h_approval,
    "email.send": h_send, "memory.record": h_mem_record, "notify.summary": h_notify,
    "compliance.suppress": h_suppress, "spreadsheet.update": h_sheet_update,
}
assert set(HANDLERS) == set(TOOLS), "every registered tool needs a handler"


def decide(approval_id: str, user: User, decisions: list[dict[str, Any]], org_id: str) -> Approval:
    """Record per-item decisions (with optional edits) and resume the run."""
    with session_scope() as db:
        ap = db.get(Approval, approval_id)
        if ap is None or ap.org_id != org_id:
            raise RunError("Approval not found.")
        if ap.status != "pending":
            raise RunError("This approval was already decided.")
        by_id = {it.id: it for it in ap.items}
        for d in decisions:
            it = by_id.get(int(d["id"]))
            if it is None:
                raise RunError(f"Unknown item {d['id']}.")
            if d.get("status") not in ("approved", "rejected"):
                raise RunError("Each item must be approved or rejected.")
            payload = dict(it.payload)
            if d.get("subject") is not None and d["subject"] != payload.get("subject"):
                payload["subject"] = d["subject"].strip()
                it.edited = True
            if d.get("body") is not None and d["body"] != payload.get("body"):
                payload["body"] = d["body"]
                it.edited = True
            if d.get("to") is not None and d["to"] != payload.get("to"):
                payload["to"] = d["to"].strip()
                it.edited = True
            if d["status"] == "approved" and not EMAIL_RE.match(payload.get("to", "")):
                raise RunError(f"“{payload.get('to')}” isn’t a valid address — fix it or reject that email.")
            if d["status"] == "approved" and re.search(r"\[[A-Za-z ]+\]|\{\{.*?\}\}", payload.get("body", "")):
                raise RunError(f"The email to {payload.get('to_name')} still has a placeholder — edit it or reject it.")
            it.payload = payload
            it.status = d["status"]
        undecided = [it for it in ap.items if it.status == "pending"]
        if undecided:
            raise RunError(f"{len(undecided)} drafts still need a decision.")
        ap.status = "decided"
        ap.decided_by = user.id
        ap.decided_at = _now()
        n_ok = sum(1 for it in ap.items if it.status == "approved")
        n_rej = len(ap.items) - n_ok
        ex = db.get(Execution, ap.execution_id)
        data = dict(ex.context.get("data", {}))
        data["_approval_done"] = True
        data["_approval_msg"] = f"{user.name} approved {n_ok} and rejected {n_rej}."
        ex.context = {**ex.context, "data": data}
        lg = _log(db, ex.id, ap.step_id)
        lg.status = "passed"
        lg.message = data["_approval_msg"]
        lg.output = {"approved": n_ok, "rejected": n_rej, "decided_by": user.name,
                     "edited": sum(1 for it in ap.items if it.edited)}
        lg.finished_at = _now()
        audit(db, org_id, user.name, "approval.decided", "approval", ap.id,
              f"Approved {n_ok}, rejected {n_rej}", agent_id=ap.agent_id)
        execution_id = ex.id
    resume(execution_id)
    with session_scope() as db:
        return db.get(Approval, approval_id)


def cancel(execution_id: str, user: User) -> None:
    with session_scope() as db:
        ex = db.get(Execution, execution_id)
        if ex is None or ex.status in ("completed", "failed", "cancelled"):
            raise RunError("This run has already finished.")
        ex.status = "cancelled"
        ex.finished_at = _now()
        ex.summary = {**(ex.summary or {}), "headline": f"Cancelled by {user.name}.", "test": ex.mode == "test"}
        for lg in db.scalars(select(ExecutionLog).where(ExecutionLog.execution_id == execution_id,
                                                        ExecutionLog.status.in_(["pending", "running", "waiting"]))):
            lg.status = "skipped"
            lg.message = "Run cancelled."
        for ap in db.scalars(select(Approval).where(Approval.execution_id == execution_id, Approval.status == "pending")):
            ap.status = "expired"
        audit(db, ex.org_id, user.name, "run.cancelled", "execution", ex.id, "Run cancelled")
