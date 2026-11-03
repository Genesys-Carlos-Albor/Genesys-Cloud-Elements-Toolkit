import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from ..client import GenesysClient
from ..export import Sheet
from ..fields import EMPTY, joined, to_datetime
from . import Log, ReportResult, register

MAX_DAYS_PER_QUERY = 30
RETENTION_DAYS = 365
POLL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 600
AUDIT_STYLE = "TableStyleLight1"


@dataclass(frozen=True)
class AuditQuery:
    service: str
    entity_type: str | None  # None = every entity type in the service
    action: str | None  # None = every action
    start: date  # first day, local time
    end: date  # last day (inclusive), local time

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def earliest_start(today: date | None = None) -> date:
    """Oldest day the audit service still holds (it keeps a rolling 365 days)."""
    return (today or date.today()) - timedelta(days=RETENTION_DAYS - 1)


def service_mapping(client: GenesysClient) -> list[dict]:
    """Audit services with their entity types and actions, sorted by name."""
    services = (client.get("/api/v2/audits/query/servicemapping") or {}).get("services") or []
    for service in services:
        service["entities"] = sorted(service.get("entities") or [], key=lambda e: e.get("name", "").lower())
    return sorted(services, key=lambda s: s.get("name", "").lower())


def _utc(day: date) -> datetime:
    """Local midnight at the start of `day`, in UTC."""
    return datetime.combine(day, datetime.min.time()).astimezone().astimezone(timezone.utc)


def intervals(start: date, end: date, now: datetime | None = None) -> list[str]:
    """ISO-8601 intervals of at most 30 days covering start..end (local days), ending no later than now."""
    now = now or datetime.now(timezone.utc)
    stop = min(_utc(end + timedelta(days=1)), now)
    current = _utc(start)
    result = []
    while current < stop:
        nxt = min(current + timedelta(days=MAX_DAYS_PER_QUERY), stop)
        result.append(f"{current:%Y-%m-%dT%H:%M:%SZ}/{nxt:%Y-%m-%dT%H:%M:%SZ}")
        current = nxt
    return result


def _run_query(client: GenesysClient, body: dict, log: Log) -> list[dict]:
    job = client.request("POST", "/api/v2/audits/query", json=body)
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    state = job.get("state")
    while state in ("Queued", "Running", None):
        if time.monotonic() > deadline:
            raise TimeoutError(f"Audit query {job['id']} did not finish within {POLL_TIMEOUT_SECONDS // 60} minutes.")
        time.sleep(POLL_SECONDS)
        state = (client.get(f"/api/v2/audits/query/{job['id']}") or {}).get("state")
    if state != "Succeeded":
        log(f"  Audit query {job['id']} ended as {state}; no results for {body['interval']}.")
        return []

    results, cursor = [], None
    while True:
        params = {"expand": "user", "pageSize": 500}
        if cursor:
            params["cursor"] = cursor
        page = client.get(f"/api/v2/audits/query/{job['id']}/results", **params) or {}
        results.extend(page.get("entities") or [])
        cursor = page.get("cursor")
        if not cursor or not page.get("entities"):
            return results


def _context(entry: dict) -> tuple:
    context = entry.get("context") or {}
    return joined(list(context.keys())), joined([str(v) for v in context.values()])


def _event(entry: dict) -> dict:
    when = to_datetime(entry.get("eventDate"))
    return {
        "Event Date": f"{when:%Y-%m-%d}" if when else EMPTY,
        "Event Time": f"{when:%I:%M:%S %p}".lstrip("0") if when else EMPTY,
    }


def _audit_row(entry: dict, oauth_names: dict) -> dict:
    user = entry.get("user") or {}
    initiating = entry.get("initiatingAction") or {}
    user_name = user.get("name") or oauth_names.get((entry.get("client") or {}).get("id")) or oauth_names.get(user.get("id"))
    context_names, context_values = _context(entry)
    return {
        "Audit Id": entry.get("id"),
        "User HomeOrg Id": entry.get("userHomeOrgId"),
        "User Id": user.get("id"),
        "User Name": user_name or EMPTY,
        "Remote IP": joined(entry.get("remoteIp") or [], ""),
        "Service Name": entry.get("serviceName"),
        "Level": entry.get("level"),
        **_event(entry),
        "Action": entry.get("action"),
        "Entity Id": (entry.get("entity") or {}).get("id"),
        "Entity Name": (entry.get("entity") or {}).get("name"),
        "Entity Type": entry.get("entityType"),
        "Status": entry.get("status"),
        "Application": entry.get("application") or EMPTY,
        "InitiatingAction Transaction Id": initiating.get("transactionId") or EMPTY,
        "InitiatingAction Action Context": initiating.get("actionContext") or EMPTY,
        "Transaction Initiator": entry.get("transactionInitiator"),
        "Context Property": context_names,
        "Context Value": context_values,
    }


def _change_rows(entry: dict) -> tuple[list[dict], list[dict]]:
    user_name = (entry.get("user") or {}).get("name") or EMPTY
    common = {
        "Audit Id": entry.get("id"),
        "User Name": user_name,
        "Service Name": entry.get("serviceName"),
        **_event(entry),
        "Action": entry.get("action"),
    }
    context_names, context_values = _context(entry)
    properties = [
        {
            **common,
            "Property Changed": change.get("property") or EMPTY,
            "Old Values": joined(change.get("oldValues") or []),
            "New Values": joined(change.get("newValues") or []),
            "Context Property": context_names,
            "Context Value": context_values,
        }
        for change in entry.get("propertyChanges") or []
    ]
    entities = [
        {
            **common,
            "entityId": change.get("entityId"),
            "entityName": change.get("entityName"),
            "entityType": change.get("entityType"),
            "oldValues": joined(change.get("oldValues") or []),
            "newValues": joined(change.get("newValues") or []),
        }
        for change in entry.get("entityChanges") or []
    ]
    return properties, entities


def _summary(services: list[dict], query: AuditQuery) -> list[dict]:
    service = next((s for s in services if s.get("name") == query.service), {"entities": []})
    entities = [e for e in service["entities"] if query.entity_type in (None, e.get("name"))]
    return [{
        "name": query.service,
        "EntityName": joined([e.get("name") for e in entities]),
        "EntityActions": joined([a for e in entities for a in e.get("actions") or [] if query.action in (None, a)]),
        "From": query.start.isoformat(),
        "To": query.end.isoformat(),
    }]


@register(
    key="get-audit-logs",
    title="Get Audit Logs by Scope",
    category="IT and Integrations",
    context="AuditLogs",
    sub_context="IT and Integrations",
    description="Audit trail for one service, optionally narrowed to an entity type and action, over a date range you pick "
    "(up to the last 365 days). Includes property and entity change sheets.",
    source_script="GC CLI Get Audit Logs by Scope_v3.2.ps1",
    options_form="audit-query",
    sheet_name="Services Summary",
    table_style="TableStyleDark10",
    freeze_panes="A2",
)
def get_audit_logs(client: GenesysClient, log: Log, query: AuditQuery) -> ReportResult:
    log(f"Service {query.service}, entity type {query.entity_type or 'all'}, action {query.action or 'all'}, "
        f"{query.start:%m/%d/%Y} to {query.end:%m/%d/%Y}")
    services = service_mapping(client)
    oauth_names = {c["id"]: c.get("name") for c in client.get_all("/api/v2/oauth/clients")}

    filters = []
    if query.entity_type:
        filters.append({"property": "EntityType", "value": query.entity_type})
    if query.action:
        filters.append({"property": "Action", "value": query.action})

    entries: list[dict] = []
    chunks = intervals(query.start, query.end)
    for number, interval in enumerate(chunks, start=1):
        log(f"Querying {interval.replace('/', ' to ')} ({number} of {len(chunks)})...")
        body = {"interval": interval, "serviceName": query.service, "filters": filters,
                "sort": [{"name": "Timestamp", "sortOrder": "ascending"}]}
        found = _run_query(client, body, log)
        log(f"  {len(found)} audit records")
        entries.extend(found)

    audit_rows, property_rows, entity_rows = [], [], []
    for entry in entries:
        audit_rows.append(_audit_row(entry, oauth_names))
        properties, entities = _change_rows(entry)
        property_rows.extend(properties)
        entity_rows.extend(entities)
    log(f"{len(audit_rows)} audit records, {len(property_rows)} property changes, {len(entity_rows)} entity changes")

    sheet_name = f"{query.service}_{query.entity_type or 'All'}"
    sheets = [
        Sheet(sheet_name, audit_rows, style=AUDIT_STYLE, freeze_panes="A2"),
        Sheet("Property_Changes", property_rows, style=AUDIT_STYLE, freeze_panes="A2"),
        Sheet("Entity_Changes", entity_rows, style=AUDIT_STYLE, freeze_panes="A2"),
    ]
    return ReportResult(rows=_summary(services, query), raw=entries, extra_sheets=sheets)
