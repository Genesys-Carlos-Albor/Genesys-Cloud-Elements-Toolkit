from concurrent.futures import ThreadPoolExecutor

from ..client import ApiError, GenesysClient
from ..fields import EMPTY, get, joined, to_datetime, values_at
from . import Log, ReportResult, register

PER_GROUP_WORKERS = 4


def _group_details(client: GenesysClient, group: dict, log: Log) -> tuple[list, list, dict]:
    gid = group["id"]
    try:
        individuals = client.get_all(f"/api/v2/groups/{gid}/individuals")
        members = client.get_all(f"/api/v2/groups/{gid}/members")
        profile = client.get(f"/api/v2/groups/{gid}/profile") or {}
    except ApiError as err:
        log(f"  Details for group '{group.get('name')}' failed: {err}")
        return [], [], {}
    return individuals, members, profile


def _first(*values):
    return next((v for v in values if v not in (None, "") and str(v).strip()), EMPTY)


def _row(group: dict, individuals: list, members: list, profile: dict, user_names: dict) -> dict:
    modified = to_datetime(group.get("dateModified"))
    owner_ids = values_at(group, "owners.id")
    return {
        "Group ID": group.get("id"),
        "Group Name": group.get("name"),
        "Description": group.get("description") or EMPTY,
        "Modified Date": f"{modified:%Y-%m-%d}" if modified else EMPTY,
        "Modified Time": f"{modified:%H:%M:%S}" if modified else EMPTY,
        "Members&Owners Count": group.get("memberCount"),
        "Members&Owners": joined([user_names.get(m.get("id")) for m in members]) if members else EMPTY,
        "Members Only Count": len(individuals),
        "State": group.get("state"),
        "Version": group.get("version"),
        "Type": group.get("type"),
        "Rule Visibile": group.get("rulesVisible"),
        "Visibility": group.get("visibility"),
        "Roles Enabled": bool(group.get("rolesEnabled")),
        "Include Owners": group.get("includeOwners"),
        "Owner Name": joined([user_names.get(i) for i in owner_ids]) if owner_ids else EMPTY,
        "Owner GUID's": joined(owner_ids),
        "Extension": get(group, "addresses.display"),
        "Chat": _first(get(profile, "contactInfo.chat.value.jid", None), get(group, "chat.jabberId", None)),
        "Email": _first(get(profile, "contactInfo.email.value", None), get(group, "email.address", None)),
    }


@register(
    key="get-groups",
    title="Get Groups",
    category="Users",
    context="Groups",
    sub_context="User Management",
    description="All groups with members, owners, visibility, roles flag, extension, chat and email.",
    source_script="GC CLI Get Groups v3.2.ps1",
)
def get_groups(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting users and groups...")
    users = client.get_all("/api/v2/users", state="any")
    groups = client.get_all("/api/v2/groups")
    log(f"  {len(groups)} groups")
    user_names = {u["id"]: u.get("name") for u in users}

    log("Getting members, individuals and profile for each group...")
    with ThreadPoolExecutor(max_workers=PER_GROUP_WORKERS) as pool:
        details = list(pool.map(lambda g: _group_details(client, g, log), groups))

    rows = [_row(g, *d, user_names) for g, d in zip(groups, details)]
    return ReportResult(rows=rows, raw=groups)
