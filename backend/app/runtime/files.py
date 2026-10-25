"""Spreadsheet versioning. Re-uploads and agent write-backs never overwrite a
file in place: each change becomes a new version that can be downloaded."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from sqlalchemy import select

from .. import config
from ..models import DataFile, FileVersion, uid
from ..tools.spreadsheet import write_csv


def _write(path: Path, kind: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    if kind == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.append(columns)
        for r in rows:
            ws.append([r.get(c, "") for c in columns])
        wb.save(path)
    else:
        write_csv(path, columns, rows)


def ensure_initial_version(db, f: DataFile, created_by: str = "") -> None:
    if not db.scalars(select(FileVersion).where(FileVersion.file_id == f.id)).first():
        db.add(FileVersion(file_id=f.id, version=f.version or 1, path=f.path, row_count=f.row_count,
                           source="upload", note="Original upload", created_by=created_by))


def write_new_version(db, f: DataFile, columns: list[str], rows: list[dict[str, Any]], source: str,
                      created_by: str, note: str) -> int:
    ensure_initial_version(db, f)
    clean = [{k: v for k, v in r.items() if not str(k).startswith("_")} for r in rows]
    new_v = (f.version or 1) + 1
    stem = Path(f.name).stem
    path = config.UPLOAD_DIR / f"{uid('v')}_{stem}_v{new_v}.{f.kind}"
    _write(path, f.kind, columns, clean)
    db.add(FileVersion(file_id=f.id, version=new_v, path=str(path), row_count=len(clean), source=source,
                       note=note, created_by=created_by))
    f.path = str(path)
    f.version = new_v
    f.columns = columns
    f.row_count = len(clean)
    f.updated_at = datetime.now(timezone.utc)
    return new_v
