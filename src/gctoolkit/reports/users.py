from concurrent.futures import ThreadPoolExecutor

from ..client import ApiError, GenesysClient
from ..fields import EMPTY, get, joined, to_datetime, values_at
from . import Log, ReportResult, register

PER_USER_WORKERS = 4
USER_EXPAND = ["authorization", "dateLastLogin", "profileSkills", "locations", "skills", "groups", "station", "lasttokenissued"]
NEVER_LOGGED_IN = "0000-12-30T00:00:00Z"


def _user_details(client: GenesysClient, user: dict, log: Log) -> tuple[list[dict], list[dict]]:
    try:
        queues = client.get_all(f"/api/v2/users/{user['id']}/queues")
    except ApiError as err:
        log(f"  Queues for user '{user.get('name')}' failed: {err}")
        queues = []
    languages = []
    if user.get("state") == "active":
        try:
            languages = client.get_all(f"/api/v2/users/{user['id']}/routinglanguages")
        except ApiError as err:
            log(f"  Language skills for user '{user.get('name')}' failed: {err}")
    return queues, languages


def _trim(value: str | None):
    return value.strip("( )") if value else None


def _phones_for(user: dict, phones: list[dict]) -> list[dict]:
    """Phones whose WebRTC user is this user, or named '<NameWithoutSpaces>-WebRtc'."""
    webrtc_name = (user.get("name") or "").replace(" ", "").replace("(Admin)", "").lower() + "-webrtc"
    return [
        p for p in phones
        if (user["id"] in (get(p, "webRtcUser.id", "") or "")) or (p.get("name") or "").lower() == webrtc_name
    ]


def contact_columns(user: dict) -> dict:
    """Work Phone, Work Phone 2 and Extension from the first two addresses, as the PowerShell reports read them."""
    addresses = user.get("addresses") or []
    first = addresses[0] if len(addresses) > 0 else {}
    second = addresses[1] if len(addresses) > 1 else {}

    if first.get("extension"):
        extension = first["extension"]
    elif 0 < len(first.get("display") or "") < 10:
        extension = _trim(first["display"])
    elif second.get("extension"):
        extension = second["extension"]
    elif 0 < len(second.get("display") or "") < 10:
        extension = _trim(second["display"])
    else:
        extension = EMPTY

    return {
        "Work Phone": _trim(first.get("display")) if first.get("mediaType") == "PHONE" else EMPTY,
        "Work Phone 2": _trim(second.get("display"))
        if second.get("mediaType") == "PHONE" and len(second.get("display") or "") >= 10 else EMPTY,
        "Extension": extension,
    }


def _row(user: dict, queues: list[dict], languages: list[dict], lookups: dict) -> dict:
    addresses = user.get("addresses") or []
    sms = [a for a in addresses if a.get("mediaType") == "SMS"]
    contact = contact_columns(user)

    manager_id = get(user, "manager.id", None)
    manager = lookups["users"].get(manager_id, {}) if manager_id else {}
    location_ids = values_at(user, "locations.locationDefinition.id")
    group_ids = values_at(user, "groups.id")
    phones = _phones_for(user, lookups["phones"])
    last_login = user.get("dateLastLogin")

    return {
        "UUID": user.get("id"),
        "Name": user.get("name"),
        "Email": user.get("email"),
        "Work Phone": contact["Work Phone"],
        "Work Phone 2": contact["Work Phone 2"],
        "Cell Phone SMS": joined([_trim(a.get("address")) for a in sms]) if sms else EMPTY,
        "Extension": contact["Extension"],
        "Title": user["title"] if "title" in user else EMPTY,
        "Department": user["department"] if "department" in user else EMPTY,
        "Manager Email": manager.get("email") if "manager" in user else EMPTY,
        "location": joined([lookups["locations"].get(i) for i in location_ids], None) if user.get("locations") else EMPTY,
        "Roles": joined(sorted(values_at(user, "authorization.roles.name"), key=str.lower), "")
        if "authorization" in user else EMPTY,
        "Queues": get(queues, "name"),
        "ACD Skill Names": get(user, "skills.name"),
        "ACD Skill GUIDs": get(user, "skills.id"),
        "Language Skill Names": get(languages, "name"),
        "Language Skill GUIDs": get(languages, "id"),
        "Auto Answer": "" if user.get("acdAutoAnswer") is None else str(user["acdAutoAnswer"]),
        "Division": get(user, "division.name", None),
        "Division Id": get(user, "division.id", None),
        "LastLogon": to_datetime(last_login) if last_login and last_login != NEVER_LOGGED_IN else "Never Logged In",
        "Phone Base": joined([lookups["phone_bases"].get(i) for i in values_at(phones, "phoneBaseSettings.id")], None)
        if phones else "No phone, no base",
        "Site": joined([lookups["sites"].get(i) for i in values_at(phones, "site.id")], None) if phones else "No phone, no site",
        "Manager": manager.get("name") if manager_id else EMPTY,
        "Routing Status": get(user, "routingStatus.status", "Offline"),
        "AcctState": user.get("state"),
        "Assigned License": joined(lookups["licenses"].get(user.get("id"), []), ""),
        "Phone UUID": get(phones, "id") if phones else "No phone assigned",
        "Phone Name": get(phones, "name") if phones else "No phone assigned",
        "Phone Line GUID": get(phones, "lines.id", "") if phones else "No phone lines assigned",
        "Groups": joined([lookups["groups"].get(i) for i in group_ids]),
    }


@register(
    key="get-users",
    title="Get Users",
    category="Users",
    context="UsersReport",
    sub_context="User Management\\Users",
    description="All users with contact details, roles, queues, ACD and language skills, licenses, phone, site and groups.",
    source_script="GC CLI Get Users_v4.8.ps1",
    folder_includes_context=False,
)
def get_users(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting users...")
    users = client.get_all("/api/v2/users", state="any", expand=USER_EXPAND)
    log(f"  {len(users)} users")
    log("Getting locations, phones, licenses, phone base settings, groups and sites...")
    locations = client.get_all("/api/v2/locations")
    phones = client.get_all("/api/v2/telephony/providers/edges/phones")
    licenses = client.get_all("/api/v2/license/users")
    phone_bases = client.get_all("/api/v2/telephony/providers/edges/phonebasesettings")
    groups = client.get_all("/api/v2/groups")
    sites = client.get_all("/api/v2/telephony/providers/edges/sites")

    lookups = {
        "users": {u["id"]: u for u in users},
        "locations": {loc["id"]: loc.get("name") for loc in locations},
        "phones": phones,
        "licenses": {entry["id"]: entry.get("licenses") or [] for entry in licenses},
        "phone_bases": {b["id"]: b.get("name") for b in phone_bases},
        "groups": {g["id"]: g.get("name") for g in groups},
        "sites": {s["id"]: s.get("name") for s in sites},
    }

    log("Getting queues and language skills for each user...")
    with ThreadPoolExecutor(max_workers=PER_USER_WORKERS) as pool:
        details = list(pool.map(lambda u: _user_details(client, u, log), users))

    rows = [_row(u, queues, languages, lookups) for u, (queues, languages) in zip(users, details)]
    return ReportResult(rows=rows, raw=users)
