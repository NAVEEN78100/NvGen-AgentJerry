# AgentJerry: product plan, modules and roadmap

Status key: **✅ Built & verified** (covered by automated tests and/or a browser walkthrough) · **🟡 Built, not fully verified** · **⬜ Planned**

---

## 1. What the design document got right, and what was changed

The core idea is strong: *natural language → validated agent → safe execution*, with "the LLM proposes, a deterministic executor performs." That principle is kept everywhere.

Weak points in the original design, and the decision taken for each:

| Original design | Problem | Decision |
|---|---|---|
| LLM does understanding, clarification **and** planning | Non-deterministic plans are hard to validate and demo; they break without internet | **Hybrid engine.** Claude (optional) only *understands* and *writes*. Clarification, planning, validation and execution are deterministic. An offline engine makes the whole product work without an API key |
| Pipeline order: Test → RAG → Tool → Safety | Safety should be checked *before* a person sees drafts, and approval must precede the action | Draft → **safety.check** → **approval.request** → send. The validator enforces this order |
| Approval as a yes/no gate | Real users approve *some* drafts, edit others and reject a few | **Per-item decisions** with inline edits, keyboard review, and blocked items (invalid address or placeholder) that can't be approved until fixed |
| Memory as a generic key-value store | "Already processed" is the real need, and it differs per purpose | **Purpose-aware memory.** Follow-ups never repeat; payment reminders have a 7-day cool-down. Only *sent* items are remembered; rejected ones return next run |
| Deploy straight after building | A changed agent could go live untested | **Lifecycle gate:** draft → ready → **tested** → live. Editing a live agent takes it offline until a new test passes. Live runs require a passing test of the *current version* |
| Vector DB + embeddings for MVP | Heavy dependencies, slow cold start, overkill for a few documents | **BM25 retriever** behind a small interface, swappable for ChromaDB/pgvector later |
| Celery + Redis for scheduling | Extra infrastructure for one process | **APScheduler** in-process; Celery beat later when scaled out |
| PostgreSQL required | Demo machines don't have it | **SQLite by default**, Postgres via one env var (SQLAlchemy 2) |
| Emails sent through real SMTP | Risky in demos and pilots | **Sandbox outbox** by default (fully visible); SMTP is opt-in in Settings |

## 2. The end-to-end flow (each module's place)

```
Describe ─▶ Understand ─▶ Clarify ─▶ Plan ─▶ Validate ─▶ Test (sandbox) ─▶ Go live ─▶ Scheduled/manual run
                                                                                         │
     Audit log ◀─ Notify ◀─ Remember ◀─ Send (once) ◀─ Approve/Edit/Reject ◀─ Safety check ◀─ Draft (+ knowledge)
```

## 3. Module plan

### M1. Authentication & workspace ✅
JWT sign-in, organisations (multi-tenant `org_id` on every query), roles (admin/member), PBKDF2 password hashing. Admin-only settings.
*Next:* invitations, SSO (Google/Microsoft), approver role. ⬜

### M2. Agent Studio: requirement understanding ✅
- Parses an instruction into: purpose, entity, trigger (day/time/frequency), data source, filter word, approval intent, tone, recipient, sign-off, "mention X" requests.
- **Records the exact words behind each field** (spans), which the UI shows as the colour-coded sentence.
- Claude path (optional) returns the same schema as strict JSON, validated before use.

### M3. Clarification engine ✅
A completeness checklist asks **only** for what's missing or ambiguous:
- which file (several match, or none uploaded, with inline upload)
- which column has the emails
- what "new" or "overdue" means when the status column has no such value (options built from the real values)
- when to run, which weekday, who receives a report

Assumptions it made on its own are shown ("Signs emails as Priya"). **Refinement in plain words** ("make it formal", "run on Fridays at 5pm", "mention our free pilot") rebuilds a new version.

### M4. Workflow planner + tool grounding ✅
Turns the completed requirement into an ordered step graph. Every step has a registered tool, concrete parameters, a plain-language description and a **"why this step"** reason (auditability). Two patterns: per-person outreach (10 steps) and summary report (6 steps).

### M5. Workflow validator ✅
Nine deterministic checks:
1. tools registered
2. required parameters present
3. graph is acyclic
4. data dependencies satisfied
5. nothing is sent before it's written and checked
6. sensitive actions are gated by approval
7. memory key for dedupe
8. every email has a recipient
9. volume cap

A failing workflow cannot be tested or run.

### M6. Execution controller ✅
Thread-pool runner; state is persisted after every step (resumable).
- **Test mode:** real data and real drafts, with sending and memory writes simulated.
- **Live mode:** pauses at the approval gate and resumes after the decision.
- **Safeguards:**
  - retries with backoff for transient errors
  - one live run per agent at a time
  - cancel at any point
  - idempotency keys so a retry never re-sends
  - `email.send` re-checks approvals in the database (defence in depth)

### M7. Human approval ✅
An inbox of pending batches. Review screen:
- per-draft approve/reject
- edit the recipient, subject and body
- see the source spreadsheet row and the knowledge citation
- safety flags; blocked items
- keyboard shortcuts: J/K to move, A to approve, R to reject
- "approve the rest"

Submission is refused until every draft has a decision.

### M8. Memory ✅
A per-agent memory of who was handled, with purpose-aware cool-downs. A memory tab lets you **forget** a person (they're included next run) or clear everything (with a warning).

### M9. Knowledge base (RAG) ✅
Upload PDF/TXT/MD. Documents are split into section-aware, overlapping chunks and searched with BM25.
- Each agent attaches only the documents relevant to its department (sales → product brief, finance → payment terms, HR → hiring process).
- Drafts carry **citations**.
- "Mention X" requests pull the exact fact from your documents.
- A search tester is built into the UI.

*Next:* embeddings + re-ranker (pgvector), per-document permissions. ⬜

### M10. Data files ✅
CSV/XLSX upload with encoding and delimiter sniffing, duplicate-header handling, and semantic column-role inference (email, name, status, amount, due date, company, industry, notes…). Includes a preview, usage tracking, and delete protection while a file is in use.
*Next:* Google Sheets / Excel Online connectors and write-back ("mark as Contacted"). ⬜

### M11. Content generation ✅
- **Offline writer:** grounded templates built from the row's own fields plus the best-matching knowledge sentence (follow-up, payment reminder, interview invite, welcome, thank-you, report).
- **Claude writer:** batched JSON drafting with the same inputs, falling back per draft on failure.

### M12. Safety layer ✅
- **Workspace policy:** approval required for external email (on by default); internal approval optional; emails-per-run cap.
- **Content checks:** invalid addresses, duplicate recipients, unfilled placeholders, generic greetings, risky wording ("guaranteed", "wire money", "password").

### M13. Scheduler ✅ (🟡 real-time firing not observed in tests)
Weekly, weekday, daily and monthly cron triggers in the workspace timezone. Jobs are synced on go-live, pause, edit and restart. The next run time is shown in the UI. A scheduled run is skipped (with a notification) while the previous one awaits approval.

### M14. Delivery: outbox & SMTP ✅ / 🟡
The sandbox outbox is verified. SMTP code is written but not exercised against a real mail server in this build.

### M15. Notifications & audit ✅
In-app notifications (approval needed, run finished/failed) and a full audit log of who built, tested, approved and sent what.

### M16. Dashboard ✅
Live agents, live runs this week, emails sent, estimated hours saved (labelled as an estimate); a 7-day runs chart (with a table view); a pending-approval strip; recent runs; activity.

### M17. Settings ✅
Safety policy, email delivery, AI engine status, tool catalogue, reset demo workspace.

## 4. New modules proposed (beyond the document)

| Module | Why it matters | Priority |
|---|---|---|
| **Agent templates gallery** (6 examples, including a sequence and an event trigger) ✅ | Users start from a working example rather than a blank page | Done |
| **Version history** ✅ | Each rebuild is a new version; only tested versions go live | Done |
| **Spreadsheet write-back + file versions** ✅ | "Mark them as contacted" keeps the sheet the source of truth; every change is a downloadable version | Done |
| **Replies inbox + intent sorting + suggested responses** ✅ | Replies stop sequences, unsubscribes go to the do-not-contact list, interested leads get a grounded draft answer | Done (sandbox replies + inbound webhook) |
| **Follow-up sequences** ✅ | "If no reply in 3 days, follow up again, up to 3 times" with "Re:" threading and a stop-on-reply rule | Done |
| **Do-not-contact list** ✅ | Compliance: checked before drafting *and* at send time | Done |
| **Event trigger: when the spreadsheet is updated** ✅ | Runs on each new upload (never on the agent's own write-back, so no loops) | Done |
| **Team + approver routing + four-eyes rule** ✅ | Separation of duties for finance and HR | Done |
| **Insights + suggestions** ✅ | Approval, edit and reply rates, funnel, weekly trend; one-click fixes | Done |
| **Health guard** ✅ | Auto-pause after 3 failed live runs in a row | Done |
| **Recipes: duplicate / export / import** ✅ | Share a working agent with a colleague or another workspace | Done |
| **Evaluation harness** ✅ | Tuning set (40) + held-out set (20); 97% field accuracy on unseen phrasing | Done |
| **Command palette + onboarding checklist** ✅ | Faster navigation; first-time users see the next step | Done |
| **Real inbox connectors** (Gmail/Outlook OAuth) | Replace sandbox replies with live mailbox reading | Next |
| **Proactive suggestions** ("You send this every Monday, want an agent?") | From the document's future scope; needs email/calendar connectors | Medium |
| **Slack/WhatsApp notifications and approvals** | Approving from a phone | Medium |
| **Multi-agent handoff** (report agent triggers follow-up agent) | Future scope | Later |

## 5. Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1. Core loop | Studio, clarify, plan, validate, test, approve, send, memory, audit | ✅ |
| 2. Knowledge + safety | RAG with citations, content checks, policy, version gate | ✅ |
| 3. Product polish | Dashboard, notifications, mobile layout, keyboard review, empty/error states | ✅ |
| 3b. Closing the loop | Replies, sequences, do-not-contact, write-back, file versions, event trigger | ✅ |
| 3c. Team & quality | Team, approver routing, four-eyes, insights, health guard, recipes, evaluation | ✅ |
| 4. Real integrations | Gmail/Outlook OAuth send + inbox, Google Sheets read/write | ⬜ next |
| 5. Team features | Email invites, SSO, granular roles | ⬜ |
| 6. Scale | PostgreSQL + pgvector, Celery workers, rate limits, observability | ⬜ |
| 7. Intelligence | Evaluation set, proactive suggestions, analytics-driven tuning | ⬜ |

## 6. Known limitations (be upfront in reviews)
- The offline engine understands the common patterns (follow-ups, reminders, invitations, reports, sequences, write-back, event triggers). It scores 97% field accuracy on the held-out set; the known misses are listed on the Engine quality page. Open-ended requests need the Claude engine.
- Replies are recorded in the sandbox ("Simulate a reply") or through the inbound-email webhook. A live Gmail/Outlook mailbox connector isn't built yet.
- SMTP delivery and real-time schedule firing are implemented but were not observed end to end in this build.
- Secrets (SMTP password) are stored in the database for the demo. Production should use a secret manager.
- No dark mode yet.
