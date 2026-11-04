import json
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

from ..client import ApiError, GenesysClient
from . import Log, ReportResult, register

EXPORT_WORKERS = 4
POLL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 600
STAMP = "%Y_%m_%dT%H.%M.%S"

Exporter = Callable[[GenesysClient, dict, Path, Log], tuple[str, "int | None"]]


def safe_name(name: str, fallback: str) -> str:
    """A table name usable as a Windows/macOS folder or file name."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip(" .")
    return cleaned or fallback


def _table_file(folder: Path, table: dict, suffix: str) -> Path:
    name = safe_name(table.get("name"), table["id"])
    table_folder = folder / name
    table_folder.mkdir(parents=True, exist_ok=True)
    return table_folder / f"{name}-{datetime.now():{STAMP}}{suffix}"


def _export_rows(client: GenesysClient, table: dict, folder: Path, log: Log) -> tuple[str, int | None]:
    """Export one table's rows to CSV. Returns (saved path or failure reason, rows exported)."""
    tid, name = table["id"], table.get("name") or table["id"]
    try:
        job = client.request("POST", f"/api/v2/flows/datatables/{tid}/export/jobs")
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        status = job
        while status.get("status") == "Processing":
            if time.monotonic() > deadline:
                log(f"  {name}: export job did not finish within {POLL_TIMEOUT_SECONDS // 60} minutes.")
                return "Export timed out", None
            time.sleep(POLL_SECONDS)
            status = client.get(f"/api/v2/flows/datatables/{tid}/export/jobs/{job['id']}") or {}
        if status.get("status") != "Succeeded":
            log(f"  {name}: export job {status.get('status')}.")
            return f"Export {status.get('status') or 'failed'}", None

        download_id = status["downloadURI"].rstrip("/").split("/")[-1]
        url = (client.get(f"/api/v2/downloads/{download_id}", issueRedirect="false") or {})["url"]
        path = _table_file(folder, table, ".csv")
        client.download(url, path)
    except (ApiError, requests.RequestException, KeyError, OSError) as err:
        log(f"  {name}: failed to download: {err}")
        return "Download failed", None
    rows = status.get("countRecordsProcessed")
    log(f"  {name}: saved {rows if rows is not None else '?'} rows")
    return str(path), rows


def _export_schema(client: GenesysClient, table: dict, folder: Path, log: Log) -> tuple[str, int | None]:
    """Save one table's definition with its JSON schema. Returns (saved path or failure reason, column count)."""
    tid, name = table["id"], table.get("name") or table["id"]
    try:
        definition = client.get(f"/api/v2/flows/datatables/{tid}", expand="schema")
        if not definition:
            log(f"  {name}: no schema returned.")
            return "Schema not found", None
        path = _table_file(folder, table, ".json")
        path.write_text(json.dumps(definition, indent=2, ensure_ascii=False), encoding="utf-8")
    except (ApiError, requests.RequestException, OSError) as err:
        log(f"  {name}: failed to save schema: {err}")
        return "Download failed", None
    columns = len(((definition.get("schema") or {}).get("properties")) or {})
    log(f"  {name}: saved schema ({columns} columns)")
    return str(path), columns


def _run_exports(
    client: GenesysClient, log: Log, folder: Path, exporter: Exporter, *, what: str, count_column: str, log_name: str
) -> ReportResult:
    started = datetime.now()
    job_log: list[str] = []
    lock = threading.Lock()

    def record(message: str) -> None:
        with lock:
            job_log.append(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}")
        log(message)

    record("Getting data tables...")
    tables = client.get_all("/api/v2/flows/datatables")
    record(f"  {len(tables)} data tables; exporting their {what} to {folder}")
    with ThreadPoolExecutor(max_workers=EXPORT_WORKERS) as pool:
        exports = list(pool.map(lambda t: exporter(client, t, folder, record), tables))

    saved = sum(1 for path, _ in exports if Path(path).is_file())
    record(f"Exported {saved} of {len(tables)} data tables.")
    rows = [
        {
            "Data Table GUID": t.get("id"),
            "Date Table Name": t.get("name"),
            "Division GUID": (t.get("division") or {}).get("id"),
            "Division Name": (t.get("division") or {}).get("name"),
            "Save Directory": path,
            count_column: count,
        }
        for t, (path, count) in zip(tables, exports)
    ]

    log_folder = folder / "JobLogs"
    log_folder.mkdir(parents=True, exist_ok=True)
    log_file = log_folder / f"{client.profile.org_label}_{log_name}_{started:{STAMP}}.log"
    log_file.write_text("\n".join(job_log) + "\n", encoding="utf-8")
    return ReportResult(rows=rows, raw=tables)


@register(
    key="export-data-tables",
    title="Export Data Tables",
    category="Architect",
    context="CSV Exports",
    sub_context="Orchestration\\Assets\\Data Tables",
    description="Backs up every Architect data table's rows to its own CSV (one folder per table), "
    "with a summary workbook and a job log.",
    source_script="Export Data Tables from Org v9.4.ps1",
    file_context="DataTables",
    name_separator="_",
    sheet_name="Data Tables",
    writes_files=True,
    workbook_folder="Reports",
)
def export_data_tables(client: GenesysClient, log: Log, folder: Path) -> ReportResult:
    return _run_exports(
        client, log, folder, _export_rows, what="rows", count_column="Rows Exported", log_name="DataTableBackup"
    )


@register(
    key="export-data-table-schemas",
    title="Export Data Table Schemas",
    category="Architect",
    context="CSV Exports",
    sub_context="Orchestration\\Assets\\Data Tables",
    description="Saves every Architect data table's definition and JSON schema to its own folder, "
    "next to the CSV exports, with a summary workbook and a job log.",
    source_script="GC CLI Export Data Tables SCHEMAS from Org v8.1.ps1",
    file_context="DataTableSchemas",
    name_separator="_",
    sheet_name="Data Table Schemas",
    writes_files=True,
    workbook_folder="Reports",
)
def export_data_table_schemas(client: GenesysClient, log: Log, folder: Path) -> ReportResult:
    return _run_exports(
        client, log, folder, _export_schema, what="schemas", count_column="Columns", log_name="DataTableSchemaBackup"
    )
