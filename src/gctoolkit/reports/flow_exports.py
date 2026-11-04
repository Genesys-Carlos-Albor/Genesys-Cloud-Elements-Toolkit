import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import requests

from ..client import ApiError, GenesysClient
from . import Log, ReportResult, register
from .data_tables import safe_name

EXPORT_WORKERS = 4
POLL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 600
RUNNING = {"Registered", "Started", "Running", "Processing"}
EXTENSIONS = {
    "INBOUNDCALL": ".i3InboundFlow",
    "COMMONMODULE": ".i3CommonModuleFlow",
    "INQUEUECALL": ".i3InQueueFlow",
    "VOICEMAIL": ".i3VoicemailFlow",
    "VOICESURVEY": ".i3VoiceSurveyFlow",
    "BOT": ".i3BotFlow",
}


def list_flows(client: GenesysClient) -> list[dict]:
    flows = client.get_all("/api/v2/flows")
    return sorted(flows, key=lambda f: ((f.get("type") or "").lower(), (f.get("name") or "").lower()))


def _extension(download_url: str, flow_type: str) -> str:
    suffix = PurePosixPath(urlparse(download_url).path).suffix
    return suffix or EXTENSIONS.get(flow_type, ".i3Flow")


def _export_flow(client: GenesysClient, flow: dict, folder: Path, log: Log) -> str:
    """Export one flow and download the file. Returns the saved path or a failure reason."""
    name, flow_type = flow.get("name") or flow["id"], flow.get("type") or ""
    file_base = safe_name(name, flow["id"])
    body = {"flows": [{
        "flow": {"id": flow["id"], "type": flow_type},
        "fileName": re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_") or flow["id"],
        "exportType": "Architect",
    }]}
    try:
        job = client.request("POST", "/api/v2/flows/export/jobs", json=body)
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        status = job
        while status.get("status") in RUNNING:
            if time.monotonic() > deadline:
                log(f"  {name}: export job did not finish within {POLL_TIMEOUT_SECONDS // 60} minutes.")
                return "Export timed out"
            time.sleep(POLL_SECONDS)
            status = client.get(f"/api/v2/flows/export/jobs/{job['id']}") or {}
        if status.get("status") != "Success" or not status.get("downloadUrl"):
            log(f"  {name}: export job {status.get('status') or 'failed'}.")
            return f"Export {status.get('status') or 'failed'}"

        flow_folder = folder / file_base
        flow_folder.mkdir(parents=True, exist_ok=True)
        path = flow_folder / f"{file_base}_{datetime.now():%Y-%m-%d_%H.%M.%S}{_extension(status['downloadUrl'], flow_type)}"
        client.download(status["downloadUrl"], path)
    except (ApiError, requests.RequestException, KeyError, OSError) as err:
        log(f"  {name}: failed to export: {err}")
        return "Download failed"
    log(f"  {name}: saved {path.name}")
    return str(path)


@register(
    key="export-flows",
    title="Export and Download Flows",
    category="Architect",
    context="Flow Exports",
    sub_context="Architect",
    description="Pick one or more Architect flows; each is exported and its .i3 flow file downloaded "
    "to its own folder, with a summary workbook.",
    source_script="GC CLI Export and Download flows v1.1.ps1",
    options_form="flow-picker",
    writes_files=True,
)
def export_flows(client: GenesysClient, log: Log, options: list[dict], folder: Path) -> ReportResult:
    flows = options or []
    log(f"Exporting {len(flows)} flow{'s' * (len(flows) != 1)} to {folder}")
    with ThreadPoolExecutor(max_workers=EXPORT_WORKERS) as pool:
        saved = list(pool.map(lambda f: _export_flow(client, f, folder, log), flows))
    log(f"Exported {sum(1 for path in saved if Path(path).is_file())} of {len(flows)} flows.")
    rows = [
        {
            "Flow GUID": f.get("id"),
            "Flow Name": f.get("name"),
            "Flow Type": f.get("type"),
            "Division Name": (f.get("division") or {}).get("name"),
            "Published Version": (f.get("publishedVersion") or {}).get("name"),
            "Save Directory": path,
        }
        for f, path in zip(flows, saved)
    ]
    return ReportResult(rows=rows, raw=flows)
