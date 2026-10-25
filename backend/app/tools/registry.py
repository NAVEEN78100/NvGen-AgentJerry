"""Tool registry: the only actions an agent can take. The planner may only
reference tools registered here, and the validator enforces each tool's
contract (required params, inputs it consumes, whether it is sensitive)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolSpec:
    name: str
    label: str
    category: str              # data | audience | memory | knowledge | ai | safety | approval | action | output
    description: str
    required_params: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    sensitive: bool = False    # external / irreversible effect -> needs approval
    side_effect: bool = False  # mocked in test mode
    integration: str = "built-in"


TOOLS: dict[str, ToolSpec] = {t.name: t for t in [
    ToolSpec("spreadsheet.read", "Read spreadsheet", "data",
             "Loads every row from a CSV or Excel file.", ("file_id",), (), ("rows",), integration="Spreadsheet"),
    ToolSpec("data.filter", "Filter rows", "audience",
             "Keeps only the rows that match a condition.", ("column", "op"), ("rows",), ("rows",)),
    ToolSpec("compliance.suppress", "Respect do-not-contact list", "safety",
             "Removes anyone who unsubscribed or is on your workspace’s do-not-contact list.", (), ("rows",), ("rows",)),
    ToolSpec("memory.exclude", "Skip already handled", "memory",
             "Removes anyone this agent has already handled in earlier runs.", ("namespace", "key_column"), ("rows",), ("rows",)),
    ToolSpec("knowledge.retrieve", "Look up company knowledge", "knowledge",
             "Finds the most relevant passages in your documents for each person.", (), ("rows",), ("passages",),
             integration="Knowledge base"),
    ToolSpec("ai.draft", "Draft personalised emails", "ai",
             "Writes one email per row using that row’s details and your knowledge base.", ("purpose", "tone"),
             ("rows",), ("drafts",)),
    ToolSpec("data.summarize", "Summarise data", "ai",
             "Counts, totals and highlights across the rows.", (), ("rows",), ("summary",)),
    ToolSpec("ai.draft_report", "Write the report email", "ai",
             "Turns the summary into a clear report email.", ("to",), ("summary",), ("drafts",)),
    ToolSpec("safety.check", "Check drafts for problems", "safety",
             "Flags missing names, invalid addresses, leftover placeholders and risky wording.", (), ("drafts",), ("drafts",)),
    ToolSpec("approval.request", "Ask for your approval", "approval",
             "Pauses the run and shows you every draft. Nothing is sent until you decide.", ("action",),
             ("drafts",), ("approved",)),
    ToolSpec("email.send", "Send approved emails", "action",
             "Sends each approved email once — never twice, even if the run is retried.", (),
             ("drafts",), ("sent",), sensitive=True, side_effect=True, integration="Email"),
    ToolSpec("memory.record", "Remember who was handled", "memory",
             "Saves who received an email so the next run skips them.", ("namespace", "key_column"),
             ("sent",), (), side_effect=True),
    ToolSpec("spreadsheet.update", "Update the spreadsheet", "data",
             "Writes the new status and date back to the sheet as a new version you can download.", ("file_id", "column", "value"),
             ("sent",), (), side_effect=True, integration="Spreadsheet"),
    ToolSpec("notify.summary", "Send you a summary", "output",
             "Posts a run summary to your notifications.", (), (), ()),
]}


def spec(name: str) -> ToolSpec | None:
    return TOOLS.get(name)


def catalog() -> list[dict]:
    return [{
        "name": t.name, "label": t.label, "category": t.category, "description": t.description,
        "sensitive": t.sensitive, "side_effect": t.side_effect, "integration": t.integration,
        "consumes": list(t.consumes), "produces": list(t.produces),
    } for t in TOOLS.values()]
