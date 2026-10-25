"""Claude API client used by the hybrid engine. Every call must return strict
JSON validated by the caller; on any failure the caller falls back to the
deterministic offline engine, so the product never breaks because the LLM is
unavailable."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .. import config

log = logging.getLogger("agentjerry.llm")


class LLMUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def status() -> dict[str, Any]:
    return {"provider": "anthropic" if enabled() else "offline", "model": config.ANTHROPIC_MODEL if enabled() else None,
            "enabled": enabled()}


def _extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found")
    return json.loads(text[start:])


def call_json(system: str, user: str, max_tokens: int = 2000) -> Any:
    if not enabled():
        raise LLMUnavailable("No ANTHROPIC_API_KEY configured")
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=config.LLM_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return _extract_json(text)
    except Exception as exc:  # network, HTTP, JSON — all fall back
        log.warning("LLM call failed, falling back to offline engine: %s", exc)
        raise LLMUnavailable(str(exc)) from exc


UNDERSTAND_SYSTEM = """You convert a business user's plain-language automation request into JSON.
Return ONLY a JSON object with these keys (use null when the user did not say):
{
 "purpose": one of "follow_up","payment_reminder","interview_invite","welcome","thank_you","custom","report" or null,
 "entity": {"singular": str, "plural": str} or null,       // who the agent targets, e.g. lead/leads
 "department": one of "sales","hr","finance","support","general",
 "trigger": {"type": "schedule"|"manual"|null, "frequency": "daily"|"weekdays"|"weekly"|"monthly"|null,
             "day_of_week": lowercase weekday or null, "day_of_month": int or null, "time": "HH:MM" 24h or null},
 "source_hint": the words naming the data source (e.g. "my sales spreadsheet") or null,
 "filter_word": the single adjective that selects rows (e.g. "new", "overdue", "shortlisted") or null,
 "approval_explicit": true if they want to review/approve first, false if they explicitly want auto-send, else null,
 "tone": "friendly"|"formal"|"concise" or null,
 "fixed_email": an email address mentioned for receiving a report, or null,
 "report_to_role": e.g. "manager" or null,
 "sender": a sign-off name if stated, or null,
 "instructions": any extra writing instructions in the user's words, or ""
}
Never invent facts that are not in the request."""


def understand(text: str) -> dict[str, Any]:
    out = call_json(UNDERSTAND_SYSTEM, text, max_tokens=800)
    if not isinstance(out, dict):
        raise LLMUnavailable("understanding did not return an object")
    allowed_p = {"follow_up", "payment_reminder", "interview_invite", "welcome", "thank_you", "custom", "report", None}
    if out.get("purpose") not in allowed_p:
        out["purpose"] = None
    tr = out.get("trigger") or {}
    if tr.get("time") and not re.fullmatch(r"\d{2}:\d{2}", str(tr["time"])):
        tr["time"] = None
    out["trigger"] = tr
    return out


DRAFT_SYSTEM = """You write short, specific business emails for a company, one per recipient.
Rules: use only facts given in the recipient record and the knowledge passages; never invent prices,
dates or promises; no placeholders like [Name]; 70-140 words; sign off with the sender name and company.
Return ONLY JSON: [{"index": int, "subject": str, "body": str, "used_passage": int|null}]"""


def draft_batch(spec: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = {"purpose": spec.get("purpose"), "tone": spec.get("tone"), "sender": spec.get("sender"),
               "company": spec.get("company"), "extra_instructions": spec.get("instructions", ""),
               "recipients": items}
    out = call_json(DRAFT_SYSTEM, json.dumps(payload, ensure_ascii=False), max_tokens=min(8000, 400 * len(items) + 500))
    if not isinstance(out, list):
        raise LLMUnavailable("draft did not return a list")
    return out
