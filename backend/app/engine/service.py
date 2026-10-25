"""Orchestrates the Studio flow:
   instruction -> understand -> complete/clarify -> (answers) -> plan -> validate -> save version.
State lives on the Agent row so a half-finished conversation survives reloads."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Agent, DataFile, KnowledgeSource, Organization, User, Workflow
from . import llm
from .clarify import Context, build_requirement, checklist, trigger_label
from .planner import plan
from .understand import understand
from .validator import validate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_policy(org: Organization) -> dict[str, Any]:
    p = {"require_approval_external": True, "require_approval_internal": False, "max_emails_per_run": 50}
    p.update((org.settings or {}).get("policy", {}))
    return p


def build_context(db: Session, user: User) -> Context:
    org = db.get(Organization, user.org_id)
    files = db.scalars(select(DataFile).where(DataFile.org_id == user.org_id).order_by(DataFile.created_at.desc())).all()
    kn = db.scalars(select(KnowledgeSource).where(KnowledgeSource.org_id == user.org_id,
                                                  KnowledgeSource.status == "ready")).all()
    domain = user.email.split("@")[-1]
    return Context(
        user_name=user.name.split(" ")[0] if user.name else "",
        user_email=user.email,
        org_name=org.name,
        org_domain=domain,
        files=[{"id": f.id, "name": f.name, "path": f.path, "kind": f.kind, "columns": f.columns,
                "row_count": f.row_count} for f in files],
        knowledge=[{"id": k.id, "title": k.title} for k in kn],
        policy=default_policy(org),
    )


def _parse(text: str, user_name: str) -> tuple[dict[str, Any], str]:
    parsed = understand(text, user_name)
    engine = "offline"
    if llm.enabled():
        try:
            out = llm.understand(text)
            # LLM fields override; offline spans are kept for the annotation UI
            for k in ("purpose", "department", "filter_word", "approval_explicit", "tone", "fixed_email",
                      "report_to_role", "sender"):
                if out.get(k) is not None:
                    parsed[k] = out[k]
            if out.get("entity"):
                parsed["entity"] = out["entity"]
            tr = out.get("trigger") or {}
            if tr.get("type"):
                parsed["trigger"] = {**parsed["trigger"], **{k: v for k, v in tr.items() if v is not None}}
            if out.get("source_hint"):
                parsed["source"] = {"kind": "spreadsheet", "hint": out["source_hint"]}
            parsed["instructions"] = out.get("instructions") or ""
            engine = "claude"
        except llm.LLMUnavailable:
            engine = "offline"
    return parsed, engine


def _merge_refinement(base: dict[str, Any], delta: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    if delta.get("purpose") and delta["purpose"] != "custom":
        merged["purpose"] = delta["purpose"]
        merged["entity"] = delta.get("entity") or merged.get("entity")
    tr = delta.get("trigger") or {}
    if tr.get("type"):
        merged["trigger"] = tr
        answers.pop("trigger", None)
        answers.pop("trigger_day", None)
    for k in ("tone", "sender", "fixed_email", "filter_word"):
        if delta.get(k):
            merged[k] = delta[k]
            answers.pop({"tone": "tone", "sender": "sender", "fixed_email": "report_to", "filter_word": "filter"}[k], None)
    if delta.get("approval_explicit") is not None:
        merged["approval_explicit"] = delta["approval_explicit"]
        answers.pop("approval", None)
    for k, ak in (("sequence", "sequence"), ("writeback", "writeback")):
        if delta.get(k):
            merged[k] = delta[k]
            answers.pop(ak, None)
    if delta.get("mentions"):
        merged["mentions"] = list(dict.fromkeys((merged.get("mentions") or []) + delta["mentions"]))
    if (delta.get("source") or {}).get("hint"):
        merged["source"] = delta["source"]
        answers.pop("source_file", None)
    return merged


def _summary_fields(req: dict[str, Any]) -> list[dict[str, Any]]:
    """Human-readable 'what I understood' card."""
    fields = []
    if req.get("purpose"):
        fields.append({"field": "action", "label": "What it does",
                       "value": f"Drafts {req['message']['noun']}" if req["pattern"] == "outreach" else "Emails a summary report"})
    fields.append({"field": "trigger", "label": "When it runs", "value": trigger_label(req.get("trigger")) if req.get("trigger") else None})
    fields.append({"field": "data", "label": "Where the data is",
                   "value": req["source"].get("file_name") or (req["source"].get("hint") and f"“{req['source']['hint']}” — file not chosen yet")})
    if req["pattern"] == "outreach":
        f = req.get("filter")
        fields.append({"field": "audience", "label": "Who it targets",
                       "value": (f"{req['filter_word'].capitalize()} {req['entity']['plural']} · {f['label']}" if f else
                                 f"{req['filter_word'].capitalize()} {req['entity']['plural']} — rule not set" if req.get("filter_word") else
                                 f"All {req['entity']['plural']}")})
        fields.append({"field": "memory", "label": "What it remembers", "value": req["memory"]["description"]})
        if (req.get("writeback") or {}).get("enabled"):
            wb = req["writeback"]
            fields.append({"field": "data", "label": "Updates the sheet", "value": f"Sets {wb['column']} to “{wb['value']}” and records the date"})
    else:
        fields.append({"field": "output", "label": "Who receives it", "value": req["recipient"].get("email")})
    if req["knowledge"]["enabled"]:
        fields.append({"field": "knowledge", "label": "Knowledge it uses", "value": ", ".join(req["knowledge"]["titles"])})
    fields.append({"field": "approval", "label": "Safety check",
                   "value": "Waits for your approval before sending" if req["approval"]["required"] else "Sends without approval"})
    return fields


def evaluate(db: Session, agent: Agent, user: User) -> dict[str, Any]:
    """Recompute requirement + questions from stored parse/answers."""
    ctx = build_context(db, user)
    state = dict(agent.requirement or {})
    req = build_requirement(state.get("parsed", {}), state.get("answers", {}), ctx, state.get("spec"))
    questions = checklist(req, ctx)
    state["spec"] = {k: v for k, v in req.items() if not k.startswith("_")}
    state["questions"] = questions
    state["fields"] = _summary_fields(req) if req.get("purpose") else []
    agent.requirement = state
    agent.name = req["name"] if req.get("purpose") else agent.name
    agent.goal = req["goal"] if req.get("purpose") else ""
    agent.department = req.get("department") or "general"
    agent.trigger = req.get("trigger") or {"type": "manual"}
    agent.knowledge_ids = req["knowledge"]["source_ids"] if req["knowledge"]["enabled"] else []
    return {"requirement": state["spec"], "questions": questions, "fields": state["fields"], "policy": ctx.policy}


def start(db: Session, user: User, prompt: str) -> Agent:
    parsed, engine = _parse(prompt, user.name)
    agent = Agent(org_id=user.org_id, user_id=user.id, prompt=prompt, engine=engine, status="draft",
                  requirement={"parsed": parsed, "answers": {}})
    agent.conversation = [{"role": "user", "kind": "prompt", "text": prompt, "spans": parsed["spans"], "at": _now()}]
    db.add(agent)
    db.flush()
    result = evaluate(db, agent, user)
    _after_evaluate(db, agent, user, result)
    return agent


def answer(db: Session, agent: Agent, user: User, answers: dict[str, Any]) -> Agent:
    state = dict(agent.requirement or {})
    merged = dict(state.get("answers", {}))
    labels = []
    qmap = {q["id"]: q for q in state.get("questions", [])}
    for k, v in answers.items():
        if v is None or v == "":
            continue
        merged[k] = v
        q = qmap.get(k)
        if q:
            opt = next((o for o in q.get("options", []) if o["value"] == v), None)
            labels.append(opt["label"] if opt else str(v))
    state["answers"] = merged
    agent.requirement = state
    agent.conversation = list(agent.conversation) + [
        {"role": "user", "kind": "answer", "text": " · ".join(labels) or "Answered", "at": _now()}]
    result = evaluate(db, agent, user)
    _after_evaluate(db, agent, user, result)
    return agent


def refine(db: Session, agent: Agent, user: User, text: str) -> Agent:
    state = dict(agent.requirement or {})
    delta, _ = _parse(text, user.name)
    answers = dict(state.get("answers", {}))
    state["parsed"] = _merge_refinement(state.get("parsed", {}), delta, answers)
    if not delta.get("understood") and not any(delta.get(k) for k in ("tone", "sender", "approval_explicit", "fixed_email", "mentions", "sequence", "writeback")) \
            and not (delta.get("trigger") or {}).get("type"):
        # free-form writing guidance, e.g. "mention our Diwali offer"
        answers["instructions"] = (answers.get("instructions", "") + " " + text).strip()
    state["answers"] = answers
    agent.requirement = state
    agent.conversation = list(agent.conversation) + [
        {"role": "user", "kind": "refine", "text": text, "spans": delta["spans"], "at": _now()}]
    result = evaluate(db, agent, user)
    _after_evaluate(db, agent, user, result)
    return agent


def _after_evaluate(db: Session, agent: Agent, user: User, result: dict[str, Any]) -> None:
    blocking = [q for q in result["questions"] if q.get("blocking")]
    conv = list(agent.conversation)
    if not result["requirement"].get("purpose"):
        conv.append({"role": "jerry", "kind": "questions",
                     "text": "I couldn’t work out the main job from that. Pick the closest one below, or describe it differently.",
                     "questions": result["questions"], "at": _now()})
        agent.conversation = conv
        agent.status = "draft"
        return
    conv.append({"role": "jerry", "kind": "understanding", "text": "Here’s what I understood.",
                 "fields": result["fields"], "assumptions": result["requirement"].get("assumptions", []), "at": _now()})
    if blocking:
        conv.append({"role": "jerry", "kind": "questions",
                     "text": "I need a little more before I can build it." if len(blocking) > 1 else "One thing before I build it.",
                     "questions": blocking, "at": _now()})
        agent.conversation = conv
        agent.status = "draft"
        return
    agent.conversation = conv
    build(db, agent, user)


def build(db: Session, agent: Agent, user: User) -> Workflow:
    ctx = build_context(db, user)
    req = agent.requirement["spec"]
    steps = plan(req)
    report = validate(steps, req, ctx.policy)
    latest = db.scalar(select(func.max(Workflow.version)).where(Workflow.agent_id == agent.id)) or 0
    wf = Workflow(agent_id=agent.id, version=latest + 1, steps=steps, validation=report)
    db.add(wf)
    was_live = agent.status in ("deployed", "paused")
    agent.status = "ready" if report["valid"] else "draft"
    agent.last_test_passed_version = None
    conv = list(agent.conversation)
    conv.append({"role": "jerry", "kind": "blueprint",
                 "text": (f"Your agent is built — {len(steps)} steps, all checks passed. Run a test next; nothing real happens in a test."
                          if report["status"] == "pass" else
                          f"Your agent is built — {len(steps)} steps. Review the warnings, then run a test."
                          if report["valid"] else "I built the workflow but it failed validation. See the checks below."),
                 "version": wf.version, "validation": report, "was_live": was_live, "at": _now()})
    agent.conversation = conv
    db.flush()
    return wf


def latest_workflow(db: Session, agent_id: str) -> Workflow | None:
    return db.scalars(select(Workflow).where(Workflow.agent_id == agent_id).order_by(Workflow.version.desc())).first()
