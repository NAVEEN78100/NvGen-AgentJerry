"""Relational schema. Mirrors section 6.1 of the design document and adds the
tables a working product needs: data files, knowledge chunks, approval items,
outbox, notifications and an audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("org"))
    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(40), default="team")
    # Safety policy and other org-wide settings
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("usr"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="member")  # admin | member
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DataFile(Base):
    """Spreadsheets (CSV/XLSX) agents read as structured input."""
    __tablename__ = "data_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("fil"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(10))  # csv | xlsx
    path: Mapped[str] = mapped_column(String(500))
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FileVersion(Base):
    """Every change to a spreadsheet (re-upload or agent write-back) is kept."""
    __tablename__ = "file_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("data_files.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(500))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="upload")  # upload | agent
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("kno"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(20))  # pdf | txt | md
    title: Mapped[str] = mapped_column(String(255))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(cascade="all, delete-orphan", back_populates="source")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[KnowledgeSource] = relationship(back_populates="chunks")


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("agt"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200), default="Untitled agent")
    goal: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    department: Mapped[str] = mapped_column(String(40), default="general")
    # draft -> ready -> tested -> deployed (<-> paused)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    requirement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    conversation: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    knowledge_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    engine: Mapped[str] = mapped_column(String(20), default="offline")
    last_test_passed_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    failure_streak: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Workflow(Base):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("wfl"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("agent_id", "version"),)


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("run"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10))  # test | live
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")  # manual | schedule
    triggered_user: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # queued | running | awaiting_approval | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(40))
    step_index: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(200))
    # pending | running | passed | failed | skipped | waiting
    status: Mapped[str] = mapped_column(String(16), default="pending")
    message: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class MemoryEntry(Base):
    __tablename__ = "memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    namespace: Mapped[str] = mapped_column(String(60), default="processed")
    key: Mapped[str] = mapped_column(String(300))
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("agent_id", "namespace", "key"),)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("apr"))
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    step_id: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60))  # e.g. email.send
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | decided | expired
    assigned_to: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    items: Mapped[list["ApprovalItem"]] = relationship(cascade="all, delete-orphan", order_by="ApprovalItem.idx")


class ApprovalItem(Base):
    __tablename__ = "approval_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    ref_key: Mapped[str] = mapped_column(String(300))  # e.g. recipient email (dedupe key)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # draft (to, subject, body, ...)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | rejected
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")


class OutboxMessage(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("msg"))
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    execution_id: Mapped[str] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(300), unique=True)
    to: Mapped[str] = mapped_column(String(254))
    to_name: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(String(16), default="sandbox")  # sandbox | smtp
    status: Mapped[str] = mapped_column(String(16), default="sent")  # sent | failed
    approved_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    touch: Mapped[int] = mapped_column(Integer, default=1)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reply(Base):
    """An inbound reply to an email an agent sent."""
    __tablename__ = "replies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uid("rep"))
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    outbox_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    from_email: Mapped[str] = mapped_column(String(254), index=True)
    from_name: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text)
    # interested | question | not_now | not_interested | unsubscribe | out_of_office | other
    category: Mapped[str] = mapped_column(String(20), default="other")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | handled
    suggested_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Suppression(Base):
    """Workspace do-not-contact list. Enforced before drafting and again at send time."""
    __tablename__ = "suppressions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    email: Mapped[str] = mapped_column(String(254))
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | reply | import
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("org_id", "email"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # approval | run_completed | run_failed | info
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(300), default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(200))  # user name or "AgentJerry" / "Scheduler"
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Metric(Base):
    """Lightweight counters for the dashboard (items processed etc.)."""
    __tablename__ = "metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
