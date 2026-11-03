from ..client import GenesysClient
from ..fields import to_datetime, us_date, us_time
from . import Log, ReportResult, register


@register(
    key="get-skills",
    title="Get Skills",
    category="Routing",
    context="Skills",
    sub_context="User Management",
    description="All ACD skills with state, version and last-modified date and time (UTC).",
    source_script="GC CLI Get Skills v4.2.ps1",
)
def get_skills(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting skills...")
    skills = client.get_all("/api/v2/routing/skills")
    log(f"  {len(skills)} skills")
    rows = []
    for s in skills:
        modified = to_datetime(s.get("dateModified"))
        rows.append({
            "Skill UUID": s.get("id"),
            "Skill Name": s.get("name"),
            "Date Modified": us_date(modified),
            "Time Modified": us_time(modified),
            "State": s.get("state"),
            "Version": s.get("version"),
            "Skill Type": "ACD Routing",
        })
    return ReportResult(rows=rows, raw=skills)
