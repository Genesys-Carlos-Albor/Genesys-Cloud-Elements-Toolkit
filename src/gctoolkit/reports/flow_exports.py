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
EXPORT_TYPES = ("Architect", "YAML")
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


def _export_flow(client: GenesysClient, flow: dict, folder: Path, log: Log, export_type: str, stamp: str) -> str:
    """Export one flow in one format ("Architect" or "YAML") and download the file.

    Returns the saved path or a failure reason."""
    name, flow_type = flow.get("name") or flow["id"], flow.get("type") or ""
    file_base = safe_name(name, flow["id"])
    body = {"flows": [{
        "flow": {"id": flow["id"], "type": flow_type},
        "fileName": re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_") or flow["id"],
        "exportType": export_type,
    }]}
    try:
        job = client.request("POST", "/api/v2/flows/export/jobs", json=body)
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        status = job
        while status.get("status") in RUNNING:
            if time.monotonic() > deadline:
                log(f"  {name} ({export_type}): export job did not finish within {POLL_TIMEOUT_SECONDS // 60} minutes.")
                return "Export timed out"
            time.sleep(POLL_SECONDS)
            status = client.get(f"/api/v2/flows/export/jobs/{job['id']}") or {}
        if status.get("status") != "Success" or not status.get("downloadUrl"):
            log(f"  {name} ({export_type}): export job {status.get('status') or 'failed'}.")
            return f"Export {status.get('status') or 'failed'}"

        flow_folder = folder / file_base
        flow_folder.mkdir(parents=True, exist_ok=True)
        extension = ".yaml" if export_type == "YAML" else _extension(status["downloadUrl"], flow_type)
        path = flow_folder / f"{file_base}_{stamp}{extension}"
        client.download(status["downloadUrl"], path)
    except (ApiError, requests.RequestException, KeyError, OSError) as err:
        log(f"  {name} ({export_type}): failed to export: {err}")
        return "Download failed"
    log(f"  {name}: saved {path.name}")
    return str(path)


@register(
    key="export-flows",
    title="Export and Download Flows",
    category="Architect",
    context="Flow Exports",
    sub_context="Architect",
    description="Pick one or more Architect flows; each is exported as an Architect .i3 flow file and a .yaml copy, "
    "both saved to the flow's own folder, with a summary workbook.",
    source_script="GC CLI Export and Download flows v1.1.ps1",
    options_form="flow-picker",
    writes_files=True,
)
def export_flows(client: GenesysClient, log: Log, options: list[dict], folder: Path) -> ReportResult:
    flows = options or []
    log(f"Exporting {len(flows)} flow{'s' * (len(flows) != 1)} to {folder}")
    stamp = f"{datetime.now():%Y-%m-%d_%H.%M.%S}"
    jobs = [(f, export_type) for f in flows for export_type in EXPORT_TYPES]
    with ThreadPoolExecutor(max_workers=EXPORT_WORKERS) as pool:
        saved = list(pool.map(lambda job: _export_flow(client, job[0], folder, log, job[1], stamp), jobs))
    files = {(job[0]["id"], job[1]): path for job, path in zip(jobs, saved)}
    complete = sum(1 for f in flows if all(Path(files[f["id"], t]).is_file() for t in EXPORT_TYPES))
    log(f"Exported {complete} of {len(flows)} flows in both formats.")
    rows = [
        {
            "Flow GUID": f.get("id"),
            "Flow Name": f.get("name"),
            "Flow Type": f.get("type"),
            "Division Name": (f.get("division") or {}).get("name"),
            "Published Version": (f.get("publishedVersion") or {}).get("name"),
            "Architect File": files[f["id"], "Architect"],
            "YAML File": files[f["id"], "YAML"],
        }
        for f in flows
    ]
    return ReportResult(rows=rows, raw=flows)
