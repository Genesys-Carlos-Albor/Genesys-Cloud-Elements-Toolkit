from concurrent.futures import ThreadPoolExecutor

from ..client import ApiError, GenesysClient
from ..export import Sheet
from ..fields import EMPTY, get, joined, to_datetime, us_date, us_time, values_at
from . import Log, ReportResult, register

PER_GROUP_WORKERS = 4


def _details(client: GenesysClient, group: dict, log: Log) -> dict:
    try:
        return client.get(f"/api/v2/routing/skillgroups/{group['id']}") or {}
    except ApiError as err:
        log(f"  Details for skill group '{group.get('name')}' failed: {err}")
        return {}


def _summary_row(group: dict, divisions: dict) -> dict:
    modified = to_datetime(group.get("dateModified"))
    created = to_datetime(group.get("dateCreated"))
    division_id = get(group, "division.id", None)
    return {
        "Group ID": group.get("id"),
        "Group Name": group.get("name"),
        "Description": group.get("description") or EMPTY,
        "Division ID": division_id,
        "Division Name": divisions.get(division_id),
        "Member Count": group.get("memberCount") or "0",
        "Modified Date": us_date(modified, EMPTY),
        "Modified Time": us_time(modified, EMPTY),
        "Created Date": us_date(created, EMPTY),
        "Created Time": us_time(created, EMPTY),
    }


def _value(values: list, default=EMPTY):
    return values[0] if len(values) == 1 else joined(values, default)


def _condition_rows(group: dict, condition: dict) -> list[dict]:
    def pick(field: str):
        routing = values_at(condition, f"routingSkillConditions.{field}")
        language = values_at(condition, f"languageSkillConditions.{field}")
        return routing, language

    routing_skill, language_skill = pick("routingSkill")
    routing_cmp, language_cmp = pick("comparator")
    routing_prof, language_prof = pick("proficiency")
    if routing_prof and any(p > 0 for p in routing_prof):
        proficiency = _value(routing_prof)
    elif language_prof:
        proficiency = _value(language_prof)
    else:
        proficiency = "0"

    rows = [{
        "Expression Group ID": group.get("id"),
        "Expression Group Name": group.get("name"),
        "Skill Type": "routingSkill" if routing_skill else "languageSkill" if language_skill else EMPTY,
        "Routing Skill Condition Routing Skill": _value(routing_skill or language_skill),
        "Routing Skill Condition Comparator": _value(routing_cmp or language_cmp),
        "Routing Skill Condition Proficiency": proficiency,
        "Operation": condition.get("operation"),
    }]
    for child in values_at(condition, "routingSkillConditions.childConditions"):
        child_routing = values_at(child, "routingSkillConditions.routingSkill")
        child_language = values_at(child, "languageSkillConditions.languageSkill")
        rows.append({
            "Expression Group ID": group.get("id"),
            "Expression Group Name": group.get("name"),
            "Skill Type": "Child.routingSkill" if child_routing else "Child.languageSkill" if child_language else EMPTY,
            "Routing Skill Condition Routing Skill": _value(child_routing, None),
            "Routing Skill Condition Comparator": get(child, "routingSkillConditions.comparator", None),
            "Routing Skill Condition Proficiency": get(child, "routingSkillConditions.proficiency", None),
            "Operation": child.get("operation"),
        })
    return rows


@register(
    key="get-skill-groups",
    title="Get Skill Expression Groups",
    category="Routing",
    context="Skill Expression Groups",
    sub_context="User Management",
    description="Skill expression groups (summary sheet) and their routing and language skill conditions (details sheet).",
    source_script="GC CLI Get Skill Expression Groups v1.6.ps1",
    file_context="SkillExpressionGroups",
    name_separator="_",
    sheet_name="SkillExpressionGroups",
    freeze_panes="A2",
)
def get_skill_groups(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting divisions and skill expression groups...")
    divisions = {d["id"]: d.get("name") for d in client.get_all("/api/v2/authorization/divisions")}
    groups = client.get_all("/api/v2/routing/skillgroups")
    log(f"  {len(groups)} skill expression groups")
    with ThreadPoolExecutor(max_workers=PER_GROUP_WORKERS) as pool:
        details = list(pool.map(lambda g: _details(client, g, log), groups))

    summary = [_summary_row(g, divisions) for g in groups]
    detail_rows = [
        row
        for g, d in zip(groups, details)
        for condition in d.get("skillConditions") or []
        for row in _condition_rows(g, condition)
    ]
    sheet = Sheet("ExpGrp Details", detail_rows, table_name="ExpGrp_Details", style="TableStyleLight11", freeze_panes="A2")
    return ReportResult(rows=summary, raw=groups, extra_sheets=[sheet])
