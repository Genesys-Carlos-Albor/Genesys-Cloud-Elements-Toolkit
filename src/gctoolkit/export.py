"""Versioned Excel and JSON report output."""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .profiles import Profile
from .settings import region_code

EXCEL_CELL_LIMIT = 32767
MAX_COLUMN_WIDTH = 60


def base_file_name(profile: Profile, context: str, on: date | None = None, separator: str = ".") -> str:
    """REGION.ORG.Context.MM.dd.yy (or REGION_ORG_Context_MM.dd.yy), matching the PowerShell report names."""
    on = on or date.today()
    region = region_code(profile.environment).upper().replace("-", ".")
    org = profile.org_label.upper().replace("/", ".")
    return separator.join([region, org, context.replace(" ", "_"), f"{on:%m.%d.%y}"])


def versioned_path(folder: Path, base_name: str, extension: str = "xlsx") -> Path:
    """Next free `_vN.0` file name: one major version above the highest existing one, starting at v1.0."""
    pattern = re.compile(rf"^{re.escape(base_name)}_v(\d+)\.(\d+)\.{re.escape(extension)}$", re.IGNORECASE)
    majors = [int(m.group(1)) for f in folder.glob(f"{base_name}_v*.{extension}") if (m := pattern.match(f.name))]
    next_major = max(majors) + 1 if majors else 1
    return folder / f"{base_name}_v{next_major}.0.{extension}"


def _cell_value(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        # A stored "\r\n" shows as an extra blank line in Excel.
        value = ILLEGAL_CHARACTERS_RE.sub("", value.replace("\r\n", "\n"))[:EXCEL_CELL_LIMIT]
    return value


@dataclass
class Sheet:
    name: str
    rows: list[dict]
    table_name: str | None = None
    style: str = "TableStyleLight16"
    freeze_panes: str = "B2"


def _safe_table_name(name: str) -> str:
    cleaned = re.sub(r"\W", "_", name)[:250]
    # Excel rejects table names that start with a non-letter or look like a cell reference (e.g. "ABC12").
    if not cleaned[:1].isalpha() or re.fullmatch(r"[A-Za-z]{1,3}\d+|[Rr]\d*[Cc]\d*", cleaned):
        cleaned = f"T_{cleaned}"
    return cleaned


def _unique(name: str, used: set[str], limit: int) -> str:
    candidate, n = name[:limit], 2
    while candidate.lower() in used:
        suffix = f"_{n}"
        candidate, n = name[: limit - len(suffix)] + suffix, n + 1
    used.add(candidate.lower())
    return candidate


def _fill_sheet(ws, sheet: Sheet, table_name: str) -> None:
    rows = sheet.rows
    columns = list(dict.fromkeys(key for row in rows for key in row))
    ws.append(columns)
    for row in rows:
        ws.append([_cell_value(row.get(col)) for col in columns])

    last_cell = f"{get_column_letter(len(columns))}{len(rows) + 1}"
    table = Table(displayName=table_name, ref=f"A1:{last_cell}")
    table.tableStyleInfo = TableStyleInfo(name=sheet.style, showRowStripes=True)
    ws.add_table(table)
    ws.freeze_panes = sheet.freeze_panes
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for index, col in enumerate(columns, start=1):
        longest = max(
            [len(col)] + [max((len(line) for line in str(r.get(col, "")).splitlines()), default=0) for r in rows[:500]]
        )
        ws.column_dimensions[get_column_letter(index)].width = min(longest + 2, MAX_COLUMN_WIDTH)


def write_workbook(sheets: list[Sheet], path: Path) -> None:
    """One table per sheet; sheets without rows are skipped."""
    wb = Workbook()
    wb.remove(wb.active)
    used_sheets: set[str] = set()
    used_tables: set[str] = set()
    for sheet in sheets:
        if not sheet.rows:
            continue
        title = _unique(re.sub(r"[\[\]:*?/\\]", "_", sheet.name) or "Sheet", used_sheets, 31)
        table_name = _unique(_safe_table_name(sheet.table_name or sheet.name), used_tables, 255)
        _fill_sheet(wb.create_sheet(title), sheet, table_name)
    if not wb.sheetnames:
        wb.create_sheet("Empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_excel(rows: list[dict], path: Path, sheet_name: str, freeze_panes: str = "B2") -> None:
    write_workbook([Sheet(sheet_name, rows, freeze_panes=freeze_panes)], path)


def write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def open_file(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def reveal_in_folder(path: Path) -> None:
    """Open the containing folder with the file selected (Linux file managers can only open the folder)."""
    if sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{path}"')
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path.parent)], check=False)
