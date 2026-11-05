from ..client import GenesysClient
from ..export import Sheet
from ..fields import EMPTY, _blank, joined
from . import Log, ReportResult, register


def _or_empty(value):
    return EMPTY if _blank(value) else value


@register(
    key="get-locations",
    title="Get Locations",
    category="Telephony",
    context="Locations",
    sub_context="User Management",
    description="Locations with address and emergency number, plus a Sub-Locations sheet with each one's parent.",
    source_script="GC CLI Get Locations v2.0.ps1",
    name_separator="_",
    table_style="TableStyleLight10",
)
def get_locations(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting locations...")
    locations = client.get_all("/api/v2/locations")
    log(f"  {len(locations)} locations")
    top_level = [loc for loc in locations if not loc.get("path")]
    nested = [loc for loc in locations if loc.get("path")]

    rows = []
    for loc in top_level:
        address = loc.get("address") or {}
        rows.append({
            "Location GUID": loc.get("id"),
            "Location Name": loc.get("name"),
            "Emergency Number": (loc.get("emergencyNumber") or {}).get("number"),
            "Address Street 1": address.get("street1"),
            "Address Street 2": _or_empty(address.get("street2")),
            "Address City": address.get("city"),
            "Address State": _or_empty(address.get("state")),
            "Zip Code": _or_empty(address.get("zipcode")),
            "State": _or_empty(loc.get("state")),
            "Country": _or_empty(address.get("country")),
            "Country Name": _or_empty(address.get("countryName")),
            "Notes": loc.get("notes"),
            "Version": loc.get("version"),
            "Address Verified": loc.get("addressVerified"),
            "Address Stored": bool(loc.get("addressStored")),
            "Sub-Locations": joined([s.get("name") for s in nested if loc.get("id") in s["path"]]),
        })

    sub_rows = []
    for sub in nested:
        parent = next((loc for loc in top_level if loc.get("id") in sub["path"]), {})
        sub_rows.append({
            "ID": sub.get("id"),
            "Name": sub.get("name"),
            "State": sub.get("state"),
            "Path": joined(sub["path"]),
            "addressVerified": sub.get("addressVerified"),
            "Parent Name": parent.get("name"),
        })
    sub_rows.sort(key=lambda r: str(r["Parent Name"] or "").lower())
    return ReportResult(
        rows=rows,
        raw=locations,
        extra_sheets=[Sheet("Sub-Locations", sub_rows, table_name="Sub-Locations", style="TableStyleLight10")],
    )
