"""Email delivery. Default transport is the sandbox outbox (messages are stored
and visible in the Outbox screen, nothing leaves the machine). When an admin
configures SMTP in Settings, real email is sent."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any


class DeliveryError(RuntimeError):
    pass


def smtp_config(org_settings: dict[str, Any]) -> dict[str, Any] | None:
    cfg = (org_settings or {}).get("smtp") or {}
    if cfg.get("enabled") and cfg.get("host") and cfg.get("from_email"):
        return cfg
    return None


def deliver(org_settings: dict[str, Any], to: str, to_name: str, subject: str, body: str) -> str:
    cfg = smtp_config(org_settings)
    if not cfg:
        return "sandbox"
    msg = EmailMessage()
    msg["From"] = f"{cfg.get('from_name') or ''} <{cfg['from_email']}>".strip()
    msg["To"] = f"{to_name} <{to}>" if to_name else to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        port = int(cfg.get("port") or 587)
        if port == 465:
            with smtplib.SMTP_SSL(cfg["host"], port, context=ssl.create_default_context(), timeout=20) as s:
                if cfg.get("username"):
                    s.login(cfg["username"], cfg.get("password", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], port, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                if cfg.get("username"):
                    s.login(cfg["username"], cfg.get("password", ""))
                s.send_message(msg)
    except Exception as exc:
        raise DeliveryError(str(exc)) from exc
    return "smtp"
