from ..client import GenesysClient
from . import Log, ReportResult, register


@register(
    key="get-divisions",
    title="Get Divisions",
    category="Users",
    context="Divisions",
    sub_context="User Management",
    description="All divisions with home-division flag and self URI.",
    source_script="GC Get Divisions v1.1.ps1",
    name_separator="_",
)
def get_divisions(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting divisions...")
    divisions = client.get_all("/api/v2/authorization/divisions")
    log(f"  {len(divisions)} divisions")
    rows = [
        {
            "ID": d.get("id"),
            "Name": d.get("name"),
            "Division Home": d.get("homeDivision"),
            "Self URI": d.get("selfUri"),
        }
        for d in divisions
    ]
    return ReportResult(rows=rows, raw=divisions)
