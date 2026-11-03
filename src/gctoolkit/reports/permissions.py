from ..client import GenesysClient
from . import Log, ReportResult, register


@register(
    key="get-permissions",
    title="Get All Permissions",
    category="Users",
    context="PermissionsExport",
    sub_context="User Management\\Roles and Permissions",
    description="Every permission (domain, entity, action) the org offers, with conditions and division awareness.",
    source_script="Get All Permissions from an org v1.2.ps1",
)
def get_permissions(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting permissions...")
    domains = client.get_all("/api/v2/authorization/permissions", page_size=500)
    rows = []
    seen = set()
    for domain in domains:
        permission_map = domain.get("permissionMap") or {}
        for entity in sorted(permission_map, key=str.lower):
            for perm in permission_map[entity] or []:
                # The API repeats some domains across pages.
                identity = (perm.get("domain"), perm.get("entityType"), perm.get("action"))
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append({
                    "Domain": perm.get("domain"),
                    "Entity Type": perm.get("entityType"),
                    "Action": perm.get("action"),
                    "Label": perm.get("label"),
                    "Allows Conditions": perm.get("allowsConditions"),
                    "Division Aware": perm.get("divisionAware"),
                })
    log(f"  {len(rows)} permissions across {len({r['Domain'] for r in rows})} domains")
    return ReportResult(rows=rows)
