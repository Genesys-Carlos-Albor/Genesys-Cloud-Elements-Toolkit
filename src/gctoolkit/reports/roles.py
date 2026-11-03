from ..client import GenesysClient
from ..export import Sheet
from ..fields import EMPTY, joined
from . import Log, ReportResult, register


def _all_or_list(value) -> str:
    values = value if isinstance(value, list) else [value]
    if "*" in values:
        return "All"
    return joined(values)


def _policy_row(role: dict, policy: dict) -> dict:
    return {
        "Id": role.get("id"),
        "Name": role.get("name"),
        "Description": role.get("description"),
        "Default Role Id": role.get("defaultRoleId"),
        "Permission": joined(role.get("permissions") or []),
        "Permission Domain": policy.get("domain"),
        "Permission Entity Name": _all_or_list(policy.get("entityName")),
        "Permission Action Set": _all_or_list(policy.get("actionSet")),
        "Permission Allow Condition": policy.get("allowConditions"),
        "User Count": role.get("userCount"),
        "Base": role.get("base"),
        "Default": role.get("default"),
    }


def _sheet_name(role: dict) -> str:
    name = role.get("name") or role.get("id")
    # PowerShell drops every underscore when the name starts with one.
    return name.replace("_", "") if name.startswith("_") else name


@register(
    key="get-roles",
    title="Get Roles and Permissions",
    category="Users",
    context="Roles and Permissions",
    sub_context="User Management",
    description="Roles summary sheet plus one sheet per role listing its permission policies.",
    source_script="GC CLI Get all roles and permissions v3.2.ps1",
    file_context="RolesandPermissions",
    name_separator="_",
    sheet_name="Roles Summary",
    table_style="TableStyleDark10",
    freeze_panes="A2",
)
def get_roles(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting roles...")
    roles = client.get_all("/api/v2/authorization/roles")
    log(f"  {len(roles)} roles")
    summary = []
    sheets = []
    for role in roles:
        policies = role.get("permissionPolicies") or []
        action_count = sum(len(p.get("actionSet") or []) if isinstance(p.get("actionSet"), list) else 1 for p in policies)
        summary.append({
            "name": role.get("name"),
            "id": role.get("id"),
            "userCount": role.get("userCount"),
            "default": role.get("default"),
            "Permission Count": action_count,
        })
        rows = sorted(
            (_policy_row(role, p) for p in policies or [{}]),
            key=lambda r: tuple(str(r[c]).lower() for c in ("Permission Domain", "Permission Entity Name", "Permission Action Set")),
        )
        sheets.append(Sheet(_sheet_name(role), rows, freeze_panes="A2"))
    return ReportResult(rows=summary, raw=roles, extra_sheets=sheets)
