"""Runtime configuration. Everything is overridable through environment variables
so the same build runs on a laptop demo (SQLite, sandbox email) and in production
(PostgreSQL, SMTP, Claude API)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("AGENTJERRY_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
SAMPLES_DIR = BASE_DIR / "samples"
STATIC_DIR = Path(os.getenv("AGENTJERRY_STATIC_DIR", BASE_DIR / "static"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("AGENTJERRY_DATABASE_URL", f"sqlite:///{DATA_DIR / 'agentjerry.db'}")

JWT_SECRET = os.getenv("AGENTJERRY_JWT_SECRET", "change-me-in-production-agentjerry")
JWT_TTL_HOURS = int(os.getenv("AGENTJERRY_JWT_TTL_HOURS", "72"))

# LLM — when a key is present the hybrid engine uses Claude for understanding
# and drafting; otherwise the deterministic offline engine is used.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("AGENTJERRY_MODEL", "claude-sonnet-5-5")
LLM_TIMEOUT_S = float(os.getenv("AGENTJERRY_LLM_TIMEOUT", "40"))

# Minimum visible duration of a workflow step (ms). Purely a UX pacing aid so
# people can follow a live run; set to 0 for tests/production.
STEP_PACING_MS = int(os.getenv("AGENTJERRY_STEP_PACING_MS", "550"))

# Estimated manual minutes saved per processed item (used for the dashboard
# "time saved" estimate; shown in the UI as an estimate).
MINUTES_SAVED_PER_ITEM = float(os.getenv("AGENTJERRY_MINUTES_PER_ITEM", "6"))

SCHEDULER_ENABLED = os.getenv("AGENTJERRY_SCHEDULER", "1") == "1"
SEED_DEMO = os.getenv("AGENTJERRY_SEED", "1") == "1"
