"""Team management: members, roles, password change."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Agent, Approval, User
from ..security import audit, current_user, hash_password, require_admin, verify_password
from ..tools.spreadsheet import EMAIL_RE
from . import serialize as S

router = APIRouter(prefix="/api")


@router.get("/team")
def team(user: User = Depends(current_user), db: Session = Depends(get_db)):
    members = db.scalars(select(User).where(User.org_id == user.org_id).order_by(User.created_at)).all()
    agents = db.scalars(select(Agent).where(Agent.org_id == user.org_id)).all()
    out = []
    for m in members:
        decided = db.scalar(select(func.count()).select_from(Approval).where(Approval.decided_by == m.id)) or 0
        pending = db.scalar(select(func.count()).select_from(Approval)
                            .where(Approval.assigned_to == m.id, Approval.status == "pending")) or 0
        out.append(S.user_out(m) | {
            "agents_built": sum(1 for a in agents if a.user_id == m.id),
            "approves_for": [a.name for a in agents if (a.approver_id or a.user_id) == m.id],
            "approvals_decided": decided, "approvals_pending": pending,
            "joined_at": S.iso(m.created_at), "is_me": m.id == user.id})
    return out


class MemberIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    title: str = ""
    role: str = Field(default="member", pattern="^(admin|member)$")


@router.post("/team")
def team_add(body: MemberIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if db.scalars(select(User).where(func.lower(User.email) == email)).first():
        raise HTTPException(409, "Someone with that email already has an account.")
    temp = secrets.token_urlsafe(7)
    m = User(org_id=user.org_id, name=body.name.strip(), email=email, title=body.title.strip(), role=body.role,
             password_hash=hash_password(temp))
    db.add(m)
    db.flush()
    audit(db, user.org_id, user.name, "team.added", "user", m.id, f"Added {m.name} as {m.role}")
    db.commit()
    return S.user_out(m) | {"temporary_password": temp}


class RoleIn(BaseModel):
    role: str = Field(pattern="^(admin|member)$")


@router.patch("/team/{member_id}")
def team_role(member_id: str, body: RoleIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.get(User, member_id)
    if not m or m.org_id != user.org_id:
        raise HTTPException(404, "Not found.")
    if m.role == "admin" and body.role != "admin":
        admins = db.scalar(select(func.count()).select_from(User)
                           .where(User.org_id == user.org_id, User.role == "admin")) or 0
        if admins <= 1:
            raise HTTPException(409, "This is the only admin. Make someone else an admin first.")
    m.role = body.role
    audit(db, user.org_id, user.name, "team.role", "user", m.id, f"{m.name} is now {m.role}")
    db.commit()
    return S.user_out(m)


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=200)


@router.post("/auth/password")
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current, user.password_hash):
        raise HTTPException(403, "Your current password is incorrect.")
    user.password_hash = hash_password(body.new)
    audit(db, user.org_id, user.name, "auth.password", "user", user.id, "Changed password")
    db.commit()
    return {"ok": True}
