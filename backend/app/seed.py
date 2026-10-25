"""Demo workspace seed: a fictional company (Brightpath Software), two users,
realistic spreadsheets, a knowledge base, and one live finance agent with real
run history produced by the actual engine (nothing is faked)."""
from __future__ import annotations

import csv
import logging
import shutil
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select

from . import config
from .db import Base, engine, session_scope
from .models import Agent, DataFile, KnowledgeSource, Organization, User
from .runtime.knowledge import ingest
from .security import hash_password
from .tools.spreadsheet import read_table

log = logging.getLogger("agentjerry.seed")

DEMO_EMAIL = "priya@brightpath.example"
DEMO_PASSWORD = "demo1234"


def _make_invoices(path: Path) -> None:
    t = date.today()
    rows = [
        ("INV-2041", "FreshMart Stores", "Priya Nair", "accounts@freshmart.example", 84000, t - timedelta(days=21), "Unpaid"),
        ("INV-2042", "MediSure Clinics", "Arjun Mehta", "finance@medisure.example", 126500, t - timedelta(days=9), "Unpaid"),
        ("INV-2043", "SwiftCargo Logistics", "Kavya Reddy", "ap@swiftcargo.example", 58000, t + timedelta(days=6), "Unpaid"),
        ("INV-2044", "UrbanBrew Cafes", "Rohan Kapoor", "rohan@urbanbrew.example", 32000, t - timedelta(days=30), "Paid"),
        ("INV-2045", "LearnLoop Academy", "Ananya Iyer", "billing@learnloop.example", 45000, t - timedelta(days=4), "Unpaid"),
        ("INV-2046", "SteelCore Industries", "Vikram Singh", "payables@steelcore.example", 210000, t - timedelta(days=37), "Unpaid"),
        ("INV-2047", "StyleStreet Fashion", "Meera Joshi", "meera@stylestreet.example", 39500, t + timedelta(days=12), "Unpaid"),
        ("INV-2048", "CarePoint Diagnostics", "Karthik Raman", "accounts@carepoint.example", 97000, t - timedelta(days=15), "Paid"),
        ("INV-2049", "GreenFork Restaurants", "Aditya Rao", "aditya@greenfork.example", 27500, t - timedelta(days=2), "Unpaid"),
        ("INV-2050", "Lifeline Hospitals", "Siddharth Menon", "ap@lifeline.example", 340000, t + timedelta(days=20), "Unpaid"),
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Invoice No", "Client", "Contact Name", "Email", "Amount", "Due Date", "Payment Status"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], r[3], r[4], r[5].isoformat(), r[6]])


def _make_pipeline(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Pipeline"
    ws.append(["Deal", "Company", "Owner", "Stage", "Deal Value", "Expected Close"])
    data = [
        ("Store analytics rollout", "FreshMart Stores", "Rahul", "Proposal", 450000, "2026-11-15"),
        ("Clinic stock tracking", "MediSure Clinics", "Sneha", "Negotiation", 620000, "2026-11-05"),
        ("Warehouse dashboards", "SwiftCargo Logistics", "Rahul", "Discovery", 780000, "2026-12-10"),
        ("Outlet reporting", "UrbanBrew Cafes", "Sneha", "Won", 210000, "2026-10-12"),
        ("Enrolment analytics", "LearnLoop Academy", "Divya", "Proposal", 180000, "2026-11-20"),
        ("Line analytics pilot", "SteelCore Industries", "Rahul", "Negotiation", 950000, "2026-11-01"),
        ("Lab turnaround", "CarePoint Diagnostics", "Sneha", "Won", 540000, "2026-10-08"),
        ("Fee dashboards", "BrightMinds School", "Divya", "Lost", 150000, "2026-10-03"),
        ("Bed occupancy", "Lifeline Hospitals", "Sneha", "Discovery", 1200000, "2026-12-20"),
        ("Inventory audits", "PackRight Warehousing", "Rahul", "Proposal", 490000, "2026-11-25"),
    ]
    for r in data:
        ws.append(list(r))
    wb.save(path)


def _make_pdf(md_path: Path, pdf_path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    styles = getSampleStyleSheet()
    story = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            story.append(Spacer(1, 8))
            story.append(Paragraph(line[2:], styles["Heading2"]))
        elif line.strip():
            story.append(Paragraph(line, styles["BodyText"]))
    SimpleDocTemplate(str(pdf_path), pagesize=A4, title="Brightpath product brief").build(story)


def _add_file(db, org_id: str, user_id: str, src: Path, name: str) -> DataFile:
    dest = config.UPLOAD_DIR / f"seed_{name}"
    if src != dest:
        shutil.copy(src, dest)
    cols, rows = read_table(dest)
    f = DataFile(org_id=org_id, uploaded_by=user_id, name=name, kind=dest.suffix.lstrip("."), path=str(dest),
                 columns=cols, row_count=len(rows))
    db.add(f)
    return f


def _add_knowledge(db, org_id: str, path: Path, title: str) -> None:
    dest = config.UPLOAD_DIR / f"seed_{path.name}"
    if path != dest:
        shutil.copy(path, dest)
    k = KnowledgeSource(org_id=org_id, file_name=path.name, source_type=path.suffix.lstrip("."), title=title)
    db.add(k)
    db.flush()
    ingest(db, k, dest)


def seed(with_history: bool = True) -> None:
    with session_scope() as db:
        if db.scalars(select(Organization)).first():
            return
        org = Organization(name="Brightpath Software", plan="team",
                           settings={"policy": {"require_approval_external": True, "require_approval_internal": False,
                                                "max_emails_per_run": 50}})
        db.add(org)
        db.flush()
        priya = User(org_id=org.id, name="Priya Raman", email=DEMO_EMAIL, title="Sales Lead", role="admin",
                     password_hash=hash_password(DEMO_PASSWORD))
        arun = User(org_id=org.id, name="Arun Prakash", email="arun@brightpath.example", title="Finance Executive",
                    role="member", password_hash=hash_password(DEMO_PASSWORD))
        db.add_all([priya, arun])
        db.flush()

        s = config.SAMPLES_DIR
        _add_file(db, org.id, priya.id, s / "sales_leads.csv", "sales_leads.csv")
        _add_file(db, org.id, priya.id, s / "candidates.csv", "candidates.csv")
        inv = config.UPLOAD_DIR / "seed_invoices.csv"
        _make_invoices(inv)
        _add_file(db, org.id, arun.id, inv, "invoices.csv")
        pipe = config.UPLOAD_DIR / "seed_sales_pipeline_q3.xlsx"
        _make_pipeline(pipe)
        _add_file(db, org.id, priya.id, pipe, "sales_pipeline_q3.xlsx")

        pdf = config.UPLOAD_DIR / "Brightpath product brief.pdf"
        _make_pdf(s / "Brightpath product brief.md", pdf)
        _add_knowledge(db, org.id, pdf, "Brightpath product brief")
        _add_knowledge(db, org.id, s / "Payment terms policy.md", "Payment terms policy")
        _add_knowledge(db, org.id, s / "Hiring process.md", "Hiring process")
        arun_id = arun.id

    if with_history:
        _seed_history(arun_id)


def _seed_history(user_id: str) -> None:
    """Create a live finance agent and run it through the real engine."""
    from .engine import service
    from .runtime import executor
    prev = executor.SYNC
    executor.SYNC = True
    try:
        with session_scope() as db:
            user = db.get(User, user_id)
            a = service.start(db, user, "Every weekday at 10am, check the invoices sheet for overdue invoices and send a "
                                        "polite payment reminder to each client after I approve.")
            agent_id = a.id
        with session_scope() as db:
            a = db.get(Agent, agent_id)
            if a.status != "ready":
                log.warning("seed finance agent not ready: %s", a.requirement.get("questions"))
                return
            executor.start_execution(db, a, "test", "manual", db.get(User, user_id))
        with session_scope() as db:
            a = db.get(Agent, agent_id)
            a.status = "deployed"
            from datetime import datetime, timezone
            a.deployed_at = datetime.now(timezone.utc)
        with session_scope() as db:
            a = db.get(Agent, agent_id)
            executor.start_execution(db, a, "live", "schedule", None)
    finally:
        executor.SYNC = prev


def reset_demo() -> None:
    from .runtime import scheduler
    scheduler.shutdown()
    Base.metadata.drop_all(engine)
    for p in config.UPLOAD_DIR.glob("*"):
        p.unlink(missing_ok=True)
    Base.metadata.create_all(engine)
    seed()
    if config.SCHEDULER_ENABLED:
        scheduler.start()
