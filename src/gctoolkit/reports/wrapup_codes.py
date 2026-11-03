from ..client import GenesysClient
from ..fields import EMPTY, names_by_id, to_datetime
from . import Log, ReportResult, register


def _field(obj: dict, key: str, convert=lambda v: v):
    """The value when the API returned the field (even if null), otherwise 'Empty'."""
    return convert(obj[key]) if key in obj else EMPTY


@register(
    key="get-wrapup-codes",
    title="Get WrapUpCodes",
    category="Routing",
    context="WrapUpCodes",
    sub_context="Interaction Assets",
    description="All wrap-up codes with division, created/modified dates (UTC) and who created or modified them.",
    source_script="GC CLI Get WrapUpCodes v1.3.ps1",
)
def get_wrapup_codes(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting wrap-up codes...")
    codes = client.get_all("/api/v2/routing/wrapupcodes")
    log(f"  {len(codes)} wrap-up codes")
    log("Getting users...")
    users = client.get_all("/api/v2/users", page_size=500, state="any")
    log("Getting OAuth clients...")
    oauth_clients = (client.get("/api/v2/oauth/clients") or {}).get("entities", [])
    who = names_by_id(users, oauth_clients)

    rows = []
    for w in codes:
        division = w.get("division") or {}
        rows.append({
            "WrapUpCode UUID": w.get("id"),
            "WrapUpCode Name": w.get("name"),
            "Division GUID": division.get("id"),
            "Division Name": "Home" if division.get("id") == "*" else division.get("name"),
            "Date Created": _field(w, "dateCreated", to_datetime),
            "Date Modified": _field(w, "dateModified", to_datetime),
            "Created By GUID": _field(w, "createdBy"),
            "Created By Name": who.get(w.get("createdBy")) or EMPTY,
            "Modified By GUID": _field(w, "modifiedBy"),
            "Modified By Name": who.get(w.get("modifiedBy")) or EMPTY,
        })
    return ReportResult(rows=rows, raw=codes)
