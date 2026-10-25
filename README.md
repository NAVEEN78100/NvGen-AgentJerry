# AgentJerry

**A no-code AI agent builder for business automation.** A non-technical employee describes a repetitive task in plain words. AgentJerry turns it into a structured, validated, testable agent that runs on a schedule and never sends anything without a person's approval.

> "Every Monday at 9am, read my sales spreadsheet, identify new leads, generate personalized follow-up emails, and show them to me for approval."

From that one sentence, AgentJerry:

1. **Understands** it, and highlights which words became which setting (when, data, who, action, safety).
2. **Asks** only for what's genuinely missing (which file? which day? whose email?).
3. **Builds** a 10-step workflow, with every step bound to a registered tool and a reason for existing.
4. **Validates** it with 9 deterministic checks (order, data flow, safety gate, memory key, volume cap, and so on).
5. **Tests** it on real data in a sandbox. It writes real drafts but sends and remembers nothing.
6. **Pauses for approval.** You approve, edit or reject each draft, with keyboard shortcuts.
7. **Sends** exactly once per person (idempotent), **remembers** who was emailed, and skips them next week.
8. **Logs** every decision in an audit trail.

It also covers the work around the core loop:

- **Replies inbox.** Replies are sorted by intent (interested, question, not now, not interested, unsubscribe, out of office), and each comes with a suggested response grounded in your documents.
- **Follow-up sequences.** Asking for "If they don't reply in 3 days, follow up again" gives you a polite second and third email that stop the moment someone replies.
- **Do-not-contact list.** It's checked before drafting and again at send time. Unsubscribe replies are added automatically.
- **Spreadsheet write-back.** "Mark them as contacted" updates the sheet as a new, downloadable version; nothing is overwritten.
- **Event trigger.** "Whenever the sheet is updated" runs the agent when you upload a new version.
- **Team & approver routing.** A builder and an approver can be different people, with an optional four-eyes rule.
- **Insights.** A funnel, a weekly trend and per-agent rates, plus suggestions you can apply in one click.
- **Health guard.** An agent is auto-paused after 3 failed live runs in a row.
- **Recipes.** Duplicate an agent, or export/import it as a portable recipe.
- **Engine quality.** A labelled tuning set and a held-out set, with field-level accuracy shown in the app and enforced as a test.
- **Command palette** (Ctrl+K) and a getting-started checklist.

## Quick start

**Windows:** double-click `run.bat`. **macOS/Linux:** `./run.sh`.
Then open http://localhost:8000 and sign in as `priya@brightpath.example` / `demo1234`.

Only Python 3.10+ is required. The built UI ships in `backend/static`.

```bash
# manual
pip install -r backend/requirements.txt
cd backend && python -m uvicorn app.main:app --port 8000
```

UI development with hot reload: `cd frontend && npm install && npm run dev` (proxies `/api` to :8000).
After UI changes, run `./build_frontend.sh`.

Docker: `docker compose up --build`.

### Using Claude (optional)

The engine is **hybrid**. Without a key it uses a deterministic offline engine (no internet needed, ideal for demos). With a key, Claude handles understanding and drafting, and falls back to the offline engine automatically on any error:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Windows: set ANTHROPIC_API_KEY=...
export AGENTJERRY_MODEL=claude-sonnet-5-5  # optional
```

Either way, the LLM only *proposes*. Validation, the safety gate and execution are deterministic code.

## Architecture

```
React + TypeScript UI (Vite, Tailwind, Framer Motion, React Flow)
        │  REST /api (JWT)
FastAPI backend ── Auth · Agents · Studio · Runs · Approvals · Files · Knowledge · Outbox · Audit
        │
AI Engine:  Understand → Clarify (checklist) → Plan (tool grounding) → Validate
        │
Execution Controller (thread pool): test/live modes · approval pause/resume · retries · idempotency
        │
Tools: spreadsheet.read · data.filter · memory.exclude/record · knowledge.retrieve · ai.draft
       data.summarize · ai.draft_report · safety.check · approval.request · email.send · notify
        │
SQLite (default) / PostgreSQL · BM25 knowledge index · APScheduler · Sandbox outbox / SMTP
```

| Folder | What's inside |
|---|---|
| `backend/app/engine` | `understand.py` (parser + spans), `clarify.py` (requirement + checklist), `planner.py`, `validator.py`, `writer.py`, `llm.py`, `service.py` |
| `backend/app/runtime` | `executor.py` (execution controller), `knowledge.py` (chunking + BM25), `scheduler.py` |
| `backend/app/tools` | Tool registry, spreadsheet reader, email transport |
| `backend/app/api` | REST routes + serializers |
| `backend/tests` | End-to-end tests, including the design document's Section 11 scenario |
| `frontend/src` | Pages, components, design tokens |
| `docs/` | `PLAN.md` (modules, roadmap, status) and `DEMO.md` (demo script) |

## Tests

```bash
cd backend && python -m pytest -q
```

15 end-to-end tests run through the real API, covering:

- the full Section 11 scenario (20 leads → 15 new → approve 12 / reject 3 → 12 sent → the next run skips those 12)
- an attempted approval-gate bypass, which is blocked even when the stored workflow is tampered with
- clarification and refinement
- HR and finance flows
- the safety check
- file uploads
- PDF knowledge retrieval
- auth
- replies and the follow-up sequence (reply stops it, unsubscribe blocks it, a follow-up goes out 4 days later as "Re:")
- spreadsheet write-back and versions
- the file-updated trigger
- approver routing and the four-eyes rule
- insights, recipes and auto-pause
- the engine-quality regression (≥ 97% field accuracy)

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Enables the Claude engine |
| `AGENTJERRY_DATABASE_URL` | SQLite in `backend/data` | e.g. a PostgreSQL URL |
| `AGENTJERRY_JWT_SECRET` | dev value | **Change in production** |
| `AGENTJERRY_STEP_PACING_MS` | 550 | Minimum visible step time in the UI; set to 0 in production |
| `AGENTJERRY_TZ` | Asia/Kolkata | Scheduler timezone |
| `AGENTJERRY_SEED` | 1 | Seeds the demo workspace on first start |
