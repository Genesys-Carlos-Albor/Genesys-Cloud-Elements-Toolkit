from ..client import GenesysClient
from ..fields import to_datetime, us_date, us_time
from . import Log, ReportResult, register


@register(
    key="get-language-skills",
    title="Get Language Skills",
    category="Routing",
    context="Language Skills",
    sub_context="Contact Center",
    description="All language skills with state, version and last-modified date and time (UTC).",
    source_script="GC CLI Get Language Skills v1.2.ps1",
)
def get_language_skills(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting language skills...")
    languages = client.get_all("/api/v2/routing/languages")
    log(f"  {len(languages)} language skills")
    rows = []
    for language in languages:
        modified = to_datetime(language.get("dateModified"))
        rows.append({
            "Language UUID": language.get("id"),
            "Language Name": language.get("name"),
            "Date Modified": us_date(modified),
            "Time Modified": us_time(modified),
            "State": language.get("state"),
            "Version": language.get("version"),
            "Skill Type": "Language",
        })
    return ReportResult(rows=rows, raw=languages)
