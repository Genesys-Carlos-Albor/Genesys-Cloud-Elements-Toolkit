from ..client import GenesysClient
from ..fields import iso_date_time, joined, names_by_id
from . import Log, ReportResult, register

SUB_CONTEXT = "Conversation Intelligence\\Speech and Text Analytics"


def _common(item: dict, user_names: dict) -> dict:
    date, time = iso_date_time(item.get("dateModified"), None)
    modified_by = (item.get("modifiedBy") or {}).get("id")
    return {
        "name": item.get("name"),
        "id": item.get("id"),
        "dateModified": date,
        "timeModified": time,
        "description": item.get("description"),
        "modifiedById": modified_by,
        "modifiedByName": user_names.get(modified_by) or modified_by,
    }


def _fetch(client: GenesysClient, log: Log, kind: str) -> tuple[list[dict], dict]:
    log(f"Getting speech and text analytics {kind}...")
    items = client.get_all(f"/api/v2/speechandtextanalytics/{kind}")
    log(f"  {len(items)} {kind}")
    user_names = names_by_id(client.get_all("/api/v2/users", state="any")) if items else {}
    return items, user_names


@register(
    key="get-sta-categories",
    title="Get Speech and Text Analytics Categories",
    category="Speech and Text Analytics",
    context="Categories",
    sub_context=SUB_CONTEXT,
    description="Interaction categories with interaction type, criteria and who last modified them.",
    source_script="GC CLI Get Speech and Text Analytics Interaction Categories v1.0.ps1",
)
def get_sta_categories(client: GenesysClient, log: Log) -> ReportResult:
    items, user_names = _fetch(client, log, "categories")
    rows = []
    for item in items:
        common, criteria = _common(item, user_names), item.get("criteria") or {}
        rows.append({
            "name": common["name"],
            "id": common["id"],
            "interactionType": item.get("interactionType"),
            **{k: common[k] for k in ("dateModified", "timeModified", "description", "modifiedById", "modifiedByName")},
            "criteriaType": criteria.get("type"),
            "criteriaOccurrence": criteria.get("occurrence"),
            "criteriaInverted": criteria.get("inverted"),
        })
    return ReportResult(rows=rows, raw=items)


@register(
    key="get-sta-programs",
    title="Get Speech and Text Analytics Programs",
    category="Speech and Text Analytics",
    context="Programs",
    sub_context=SUB_CONTEXT,
    description="Programs with publish state, tags and who last modified them.",
    source_script="GC CLI Get Speech and Text Analytics Programs v1.0.ps1",
)
def get_sta_programs(client: GenesysClient, log: Log) -> ReportResult:
    items, user_names = _fetch(client, log, "programs")
    rows = [
        {**_common(item, user_names), "published": item.get("published"), "tags": joined(item.get("tags") or [], None)}
        for item in items
    ]
    return ReportResult(rows=rows, raw=items)


@register(
    key="get-sta-topics",
    title="Get Speech and Text Analytics Topics",
    category="Speech and Text Analytics",
    context="Topics",
    sub_context=SUB_CONTEXT,
    description="Topics with dialect, matching, strictness, phrase and program counts.",
    source_script="GC CLI Get Speech and Text Analytics Topics v1.0.ps1",
)
def get_sta_topics(client: GenesysClient, log: Log) -> ReportResult:
    items, user_names = _fetch(client, log, "topics")
    rows = []
    for item in items:
        common = _common(item, user_names)
        rows.append({
            **{k: common[k] for k in ("name", "id", "dateModified", "timeModified", "description")},
            "dialect": item.get("dialect"),
            "matchingType": item.get("matchingType"),
            "modifiedById": common["modifiedById"],
            "modifiedByName": common["modifiedByName"],
            "participants": item.get("participants"),
            "phrasesCount": item.get("phrasesCount"),
            "programsCount": item.get("programsCount"),
            "published": item.get("published"),
            "strictness": item.get("strictness"),
            "tags": joined(item.get("tags") or [], None),
        })
    return ReportResult(rows=rows, raw=items)
