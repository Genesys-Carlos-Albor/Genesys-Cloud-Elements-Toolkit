import re
from concurrent.futures import ThreadPoolExecutor

from ..client import ApiError, GenesysClient
from ..fields import EMPTY, get, joined, values_at
from . import Log, ReportResult, register
from .users import NEVER_LOGGED_IN, contact_columns

PER_USER_WORKERS = 4
USER_EXPAND = ["lasttokenissued", "authorization", "dateLastLogin", "profileSkills", "locations", "skills"]
PHONE_FIELDS = "webRtcUser,properties.*,lines.loggedInUser,lines.defaultForUser"


def _queues(client: GenesysClient, user: dict, log: Log) -> list[dict]:
    try:
        return client.get_all(f"/api/v2/users/{user['id']}/queues")
    except ApiError as err:
        log(f"  Queues for user '{user.get('name')}' failed: {err}")
        return []


def _name_matches(phone_name: str, user_name: str) -> bool:
    """PowerShell `-match`: the user's name without spaces, as a case-insensitive regex, found in the phone name."""
    pattern = user_name.replace(" ", "")
    try:
        return re.search(pattern, phone_name, re.IGNORECASE) is not None
    except re.error:
        return pattern.lower() in phone_name.lower()


def _phones_for(user: dict, phones: list[dict], base_id: str | None) -> list[dict]:
    return [
        p for p in phones
        if base_id and get(p, "phoneBaseSettings.id", None) == base_id
        and _name_matches((p.get("name") or "").replace("-WebRtc", ""), user.get("name") or "")
    ]


def _row(user: dict, queues: list[dict], phones: list[dict], lookups: dict) -> dict:
    manager_id = get(user, "manager.id", None)
    manager = lookups["users"].get(manager_id, {}) if manager_id else {}
    last_login = user.get("dateLastLogin")
    return {
        "Name": user.get("name"),
        "Email": user.get("email"),
        **contact_columns(user),
        "Title": user["title"] if "title" in user else EMPTY,
        "Department": user["department"] if "department" in user else EMPTY,
        "Manager Email": manager.get("email") if "manager" in user else EMPTY,
        "location": joined([lookups["locations"].get(i) for i in values_at(user, "locations.locationDefinition.id")], None)
        if user.get("locations") else EMPTY,
        "Roles": joined(sorted(values_at(user, "authorization.roles.name"), key=str.lower), ""),
        "Queues": get(queues, "name"),
        "Skills": get(user, "skills.name"),
        "Auto Answer": "" if user.get("acdAutoAnswer") is None else str(user["acdAutoAnswer"]),
        "Division": get(user, "division.name", None),
        "Division Id": get(user, "division.id", None),
        "LastLogon": last_login if last_login and last_login != NEVER_LOGGED_IN else "Never Logged In",
        "UUID": user.get("id"),
        "Phone Base": get(phones, "lineBaseSettings.name", None) if phones else "No phone, no base",
        "Site": get(phones, "site.id", None) if phones else "No phone, no site",
        "Manager": manager.get("name") if manager_id else EMPTY,
        "Routing Status": get(user, "routingStatus.status", "Offline"),
        "AcctState": user.get("state"),
        "Assigned License": joined(lookups["licenses"].get(user.get("id"), []), ""),
        "Phone UUID": get(phones, "id") if phones else "No phone assigned",
        "Phone Name": get(phones, "name") if phones else "No phone assigned",
    }


@register(
    key="get-user-phones",
    title="Get Users Remote Phones",
    category="Users",
    context="User Phones",
    sub_context="User Management",
    description="Active users with contact details, roles, queues, skills, licenses and the WebRTC phone on the org's first phone base.",
    source_script="GC CLI Get Users_v4.5 Remote phones.ps1",
    file_context="UserPhones",
    table_name="User_Phones",
)
def get_user_phones(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting active users...")
    users = client.get_all("/api/v2/users", page_size=500, state="active", expand=USER_EXPAND)
    log(f"  {len(users)} users")
    log("Getting locations, phones, licenses and phone base settings...")
    locations = client.get_all("/api/v2/locations")
    phones = client.get_all("/api/v2/telephony/providers/edges/phones", fields=PHONE_FIELDS)
    licenses = client.get_all("/api/v2/license/users")
    phone_bases = client.get_all("/api/v2/telephony/providers/edges/phonebasesettings")
    base_id = phone_bases[0]["id"] if phone_bases else None

    lookups = {
        "users": {u["id"]: u for u in users},
        "locations": {loc["id"]: loc.get("name") for loc in locations},
        "licenses": {entry["id"]: entry.get("licenses") or [] for entry in licenses},
    }

    log("Getting queues for each user...")
    with ThreadPoolExecutor(max_workers=PER_USER_WORKERS) as pool:
        queues = list(pool.map(lambda u: _queues(client, u, log), users))

    rows = [_row(u, q, _phones_for(u, phones, base_id), lookups) for u, q in zip(users, queues)]
    return ReportResult(
        rows=rows,
        extra_json={
            "Phones": phones, "Users": users, "Locations": locations,
            "LicensePool": licenses, "PhoneBase": phone_bases,
        },
    )
