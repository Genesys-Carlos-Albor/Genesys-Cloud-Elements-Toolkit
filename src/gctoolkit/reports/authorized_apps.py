from ..client import GenesysClient
from ..fields import EMPTY, get, joined, names_by_id, values_at
from . import Log, ReportResult, register


@register(
    key="get-authorized-apps",
    title="Get Authorized Apps",
    category="IT and Integrations",
    context="Authorized Apps",
    sub_context="IT and Integrations",
    description="OAuth apps authorized in the org, with scopes, allowed IPs, resource owner and who created or changed them.",
    source_script="GC CLI Get Authorized Apps v1.0.ps1",
    file_context="AuthorizedApps",
    table_name="AuthorizedApps",
)
def get_authorized_apps(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting users, authorized apps, OAuth clients and organization...")
    users = client.get_all("/api/v2/users", state="any")
    data = client.get("/api/v2/oauth/authorizations") or {}
    authorizations = data.get("entities") or []
    oauth_clients = client.get_all("/api/v2/oauth/clients")
    org = client.get("/api/v2/organizations/me") or {}
    log(f"  {len(authorizations)} authorized apps")
    names = names_by_id(users, oauth_clients, [org])

    def owner(entry: dict, path: str) -> tuple:
        oid = get(entry, path, None)
        return (names.get(oid) or EMPTY, oid) if oid else (EMPTY, EMPTY)

    rows = []
    for a in authorizations:
        resource_name, resource_id = owner(a, "resourceOwner.id")
        created_name, created_id = owner(a, "createdBy.id")
        modified_name, modified_id = owner(a, "modifiedBy.id")
        rows.append({
            "Client Name": get(a, "client.name", None),
            "Client Id": get(a, "client.id", None),
            "Client Description": get(a, "client.description", None),
            "Client Scope": joined(values_at(a, "client.scope"), ""),
            "Client Allowed IPs": joined(values_at(a, "client.allowedIPAddresses")),
            "Scope": joined(values_at(a, "scope"), ""),
            "Resource Name": resource_name,
            "Resource Id": resource_id,
            "Created By Name": created_name,
            "Created By Id": created_id,
            "Modified By Name": modified_name,
            "Modified By Id": modified_id,
            "Pending": a.get("pending"),
            "State": a.get("state"),
        })
    return ReportResult(rows=rows, raw=authorizations)
