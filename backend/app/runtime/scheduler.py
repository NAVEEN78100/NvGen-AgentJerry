"""Scheduled triggers (APScheduler, in-process). Deployed agents with a
schedule get a cron job; pausing or editing removes it. Swappable for
Celery beat / RQ scheduler when the app is scaled out."""
from __future__ import annotations

import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from ..db import session_scope
from ..models import Agent, User
from ..security import notify

log = logging.getLogger("agentjerry.scheduler")
TZ = os.getenv("AGENTJERRY_TZ", "Asia/Kolkata")
_scheduler: BackgroundScheduler | None = None
DOW = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri",
       "saturday": "sat", "sunday": "sun"}


def cron_for(trigger: dict) -> CronTrigger | None:
    if not trigger or trigger.get("type") != "schedule":
        return None
    h, m = map(int, (trigger.get("time") or "09:00").split(":"))
    f = trigger.get("frequency")
    if f == "weekly":
        return CronTrigger(day_of_week=DOW.get(trigger.get("day_of_week") or "monday", "mon"), hour=h, minute=m, timezone=TZ)
    if f == "weekdays":
        return CronTrigger(day_of_week="mon-fri", hour=h, minute=m, timezone=TZ)
    if f == "daily":
        return CronTrigger(hour=h, minute=m, timezone=TZ)
    if f == "monthly":
        return CronTrigger(day=int(trigger.get("day_of_month") or 1), hour=h, minute=m, timezone=TZ)
    return None


def next_run(trigger: dict) -> str | None:
    ct = cron_for(trigger)
    if ct is None:
        return None
    from zoneinfo import ZoneInfo
    nxt = ct.get_next_fire_time(None, datetime.now(ZoneInfo(TZ)))
    return nxt.isoformat() if nxt else None


def _fire(agent_id: str) -> None:
    from .executor import RunError, start_execution
    with session_scope() as db:
        agent = db.get(Agent, agent_id)
        if agent is None or agent.status != "deployed":
            return
        user = db.get(User, agent.user_id)
        try:
            start_execution(db, agent, "live", "schedule", None)
        except RunError as exc:
            notify(db, agent.org_id, "info", f"Skipped scheduled run of {agent.name}", str(exc), f"/agents/{agent.id}")
            log.info("scheduled run skipped for %s: %s", agent_id, exc)


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=TZ)
    _scheduler.start()
    with session_scope() as db:
        for a in db.scalars(select(Agent).where(Agent.status == "deployed")):
            sync(a)


def shutdown() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def sync(agent: Agent) -> None:
    if _scheduler is None:
        return
    job_id = f"agent:{agent.id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    ct = cron_for(agent.trigger) if agent.status == "deployed" else None
    if ct:
        _scheduler.add_job(_fire, ct, args=[agent.id], id=job_id, replace_existing=True, misfire_grace_time=3600)
