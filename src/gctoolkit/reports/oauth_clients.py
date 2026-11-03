from ..client import GenesysClient
from ..fields import EMPTY, get, joined, to_datetime
from . import Log, ReportResult, register


@register(
    key="get-oauth-clients",
    title="Get OAuth Accounts",
    category="IT and Integrations",
    context="OAuth Accounts",
    sub_context="IT and Integrations",
    description="All OAuth clients with grant type, creator, modifier, token lifetime, redirect URIs and roles.",
    source_script="GC CLI Get OAuth Accounts from an org v2.1.ps1",
    file_context="OAuthAccounts",
    name_separator="_",
    sheet_name="OAuthAccounts",
    freeze_panes="A2",
)
def get_oauth_clients(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting users, OAuth clients and roles...")
    users = {u["id"]: u.get("name") for u in client.get_all("/api/v2/users", state="any")}
    oauth_clients = client.get_all("/api/v2/oauth/clients")
    roles = {r["id"]: r.get("name") for r in client.get_all("/api/v2/authorization/roles")}
    log(f"  {len(oauth_clients)} OAuth clients")

    rows = []
    for c in oauth_clients:
        created_by = get(c, "createdBy.id", None)
        modified_by = get(c, "modifiedBy.id", None)
        role_ids = [rd.get("roleId") for rd in c.get("roleDivisions") or [] if rd.get("roleId")]
        rows.append({
            "OAuth GUID": c.get("id"),
            "OAuth Name": c.get("name"),
            "description": c.get("description") or EMPTY,
            "Authorized Grant Type": c.get("authorizedGrantType"),
            "Created By GUID": created_by or EMPTY,
            "Created By Name": users.get(created_by) or EMPTY,
            "Date Created": to_datetime(c.get("dateCreated")),
            "Date Modified": to_datetime(c.get("dateModified")),
            "Access Token Validity Seconds": c.get("accessTokenValiditySeconds"),
            "Modified By GUID": modified_by or EMPTY,
            "Modified By Name": users.get(modified_by) or EMPTY,
            "Registered Redirect Uri": joined(c.get("registeredRedirectUri") or []),
            "Role Divisions GUID": joined(role_ids),
            "Role Divisions Name": joined([roles.get(i) for i in role_ids]),
            "Role Ids": joined(c.get("roleIds") or [], ""),
            "Secret": c.get("secret"),
            "State": c.get("state"),
        })
    return ReportResult(rows=rows, raw=oauth_clients)
