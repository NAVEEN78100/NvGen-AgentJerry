"""Scores the requirement-understanding engine against the labelled set."""
from __future__ import annotations

import time
from typing import Any

from .eval_set import CASES, HELD_OUT
from .understand import understand


def _trigger_sig(tr: dict) -> str | None:
    if not tr or not tr.get("type"):
        return None
    if tr["type"] in ("manual", "file_updated"):
        return tr["type"]
    sig = tr.get("frequency") or ""
    if tr.get("frequency") == "weekly" and tr.get("day_of_week"):
        sig += f"/{tr['day_of_week']}"
    if tr.get("time"):
        sig += f"@{tr['time']}"
    return sig


def _matches(field: str, want: Any, p: dict) -> tuple[bool, Any]:
    if field == "purpose":
        got = p.get("purpose")
        return got == want, got
    if field == "trigger":
        got = _trigger_sig(p.get("trigger") or {})
        if want is None:
            return got is None, got
        # "weekly/monday" also accepts a detected time; "@" part only scored when expected
        if "@" not in want and got and "@" in got:
            got_cmp = got.split("@")[0]
        else:
            got_cmp = got
        # an implied time ("morning" -> 09:00) is accepted when no exact time was expected
        return got_cmp == want, got
    if field == "filter_word":
        got = p.get("filter_word")
        return got == want, got
    if field == "approval":
        got = p.get("approval_explicit")
        return got == want, got
    if field == "tone":
        got = p.get("tone")
        return got == want, got
    if field == "sender":
        got = p.get("sender")
        return got == want, got
    if field == "source":
        got = bool((p.get("source") or {}).get("kind"))
        return got == want, got
    if field == "sequence":
        s = p.get("sequence")
        got = f"{s['after_days']}/{s['max_touches']}" if s else None
        return got == want, got
    if field == "writeback":
        w = p.get("writeback")
        got = (w or {}).get("value") if w else None
        return got == want, got
    if field == "mention":
        got = bool(p.get("mentions"))
        return got == want, got
    if field == "report_to":
        got = p.get("report_to_role")
        return got == want, got
    if field == "email":
        got = p.get("fixed_email")
        return got == want, got
    return False, None


FIELD_LABEL = {
    "purpose": "What it does", "trigger": "When it runs", "filter_word": "Who it targets", "approval": "Approval intent",
    "tone": "Writing style", "sender": "Signed by", "source": "Data source", "sequence": "Follow-up sequence",
    "writeback": "Sheet update", "mention": "Things to mention", "report_to": "Report recipient", "email": "Email address",
}


def run() -> dict[str, Any]:
    main = _score(CASES)
    held = _score(HELD_OUT)
    main["held_out"] = {k: held[k] for k in ("cases", "cases_fully_correct", "field_accuracy", "checks", "per_field", "results")}
    return main


def _score(cases_in: list[dict]) -> dict[str, Any]:
    t0 = time.perf_counter()
    per_field: dict[str, dict[str, int]] = {}
    cases_out = []
    for i, case in enumerate(cases_in):
        p = understand(case["text"])
        results = []
        for field, want in case["expect"].items():
            ok, got = _matches(field, want, p)
            f = per_field.setdefault(field, {"correct": 0, "total": 0})
            f["total"] += 1
            f["correct"] += int(ok)
            results.append({"field": field, "label": FIELD_LABEL.get(field, field), "expected": want, "got": got, "ok": ok})
        cases_out.append({"id": i + 1, "text": case["text"], "spans": p["spans"], "ok": all(r["ok"] for r in results),
                          "results": results})
    total = sum(f["total"] for f in per_field.values())
    correct = sum(f["correct"] for f in per_field.values())
    return {
        "engine": "offline",
        "cases": len(cases_in),
        "cases_fully_correct": sum(1 for c in cases_out if c["ok"]),
        "field_accuracy": round(correct / total, 4) if total else 0,
        "checks": total,
        "per_field": [{"field": k, "label": FIELD_LABEL.get(k, k), **v, "accuracy": round(v["correct"] / v["total"], 4)}
                      for k, v in sorted(per_field.items(), key=lambda kv: -kv[1]["total"])],
        "results": cases_out,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }
