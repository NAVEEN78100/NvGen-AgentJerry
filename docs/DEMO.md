# Demo script (8–10 minutes)

**Before you start:** run `run.bat` (or `./run.sh`), open http://localhost:8000. If you rehearsed earlier, go to **Settings → Reset workspace** for a clean slate. Keep the browser at 100% zoom, full screen.

## 1. The problem (30 s, on the sign-in page)
The left panel cycles through example sentences, with each phrase highlighting itself.
> "Employees know *what* to automate but not *how*. AgentJerry lets them say it in their own words."

Sign in with the pre-filled demo account (Priya, Sales Lead).

## 2. Home (30 s)
Point out the red strip: **a finance agent already ran overnight and is waiting for approval**. Nothing is sent until a person decides. Mention the KPIs and the 7-day chart.

## 3. Build an agent from one sentence (2 min): the core moment
**Create agent** → click the example **Weekly lead follow-ups** (or type it) → **Build my agent**.
- Watch the four stages: reading, checking for gaps, planning, safety checks.
- The sentence lights up: *amber* = when, *blue* = data, *violet* = who, *green* = action, *rose* = safety. Hover a row in "Here's what I understood" and the matching words highlight.
- Read the assumptions line: it picked `sales_leads.csv` and signs as Priya.
- Right side: the 10-step workflow, coloured the same way. Click **Skip leads already contacted** to show the "why this step" reason.
- Open **Validation**: 9 checks, including "Nothing is sent before it's written and checked."

*Optional (shows clarification):* Start over, type `Weekly, summarize the sales pipeline and email it to my manager`. Jerry asks **which day** and **your manager's email**. Answer both, then type `make it run every Friday at 5pm` in the bottom box and it rebuilds as version 2.

## 4. Safe test (1 min)
**Run a safe test**. Steps tick through live:
- 20 leads loaded
- 15 are "New"
- knowledge found
- 15 drafts written
- all checks passed
- "would pause for approval"
- "test mode — 15 emails were not sent"

Click **Preview the drafts**. Show that each email is personal: the event they met at, their question, and a fact from the product brief with a "Grounded in" citation.

## 5. Go live + approval (2 min)
**Go live · Every Monday at 9:00 AM**, then **Run now**.
- The run stops at **Waiting for you**. Nothing has been sent.
- **Review drafts**: press **A** twelve times, then **R** three times (or click). Edit one subject line to show editing.
- **Send 12 approved**. The run finishes: 12 sent, 3 rejected.
- **Open outbox**: the 12 emails, exactly as approved (sandbox: nothing left the machine).

## 6. Memory: the "next Monday" moment (1 min)
Go back to the agent → **Run now** again. Open **Skip leads already contacted**: 12 names are struck through. Only the 3 you rejected come back.
> "It never emails the same person twice, and rejected drafts get a second chance."

Show the **Memory** tab with **Forget**.

## 7. Trust & audit (1 min)
- **Approvals**: open the finance batch and show a payment reminder grounded in the late-fee policy.
- **Activity log**: who built, tested, approved and sent what, and when.
- **Settings**: safety policy toggles, sandbox vs SMTP, tool catalogue (sensitive tools marked with a lock), AI engine (offline now, Claude with one env var).

## Likely questions
- **"Is it just templates?"** The understanding, checklist, planner and validator are generic. With an API key, Claude writes the drafts; the offline engine covers the demo without internet. Either way, the AI only proposes and deterministic code validates and executes.
- **"What stops it sending something bad?"** Three layers: validator (no send step without an approval gate), content safety check, and `email.send` refusing anything not approved in the database. A test tampers with a workflow to bypass approval, and it is blocked.
- **"Retries / duplicates?"** Every email has an idempotency key, and memory records only what was actually sent.
- **"How is it tested?"** `pytest` runs the design document's Section 11 scenario end to end (9 tests).
