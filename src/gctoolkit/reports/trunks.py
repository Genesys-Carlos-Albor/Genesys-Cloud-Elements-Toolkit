import json
import re

from ..client import GenesysClient
from ..export import Sheet
from ..fields import EMPTY, _blank, iso_part, names_by_id
from . import Log, ReportResult, register

GENERAL_SHEET = "Trunk Base Settings"
# Checked in order; a property that matches none of these stays on the Trunk Base Settings sheet.
DOMAINS = [
    ("Media", r"^trunk_media_"),
    ("Outbound Identity", r"^trunk_outbound(Identity)?_"),
    ("Protocol", r"^trunk_(protocol$|sip_)"),
    ("Recording", r"^trunk_recording_"),
    ("Transport", r"^trunk_transport_"),
    ("Provisioning", r"^trunk_provisioning_"),
]
SECRET = re.compile("password|secret", re.IGNORECASE)
MASK = "********"


def property_domain(name: str) -> str:
    return next((sheet for sheet, pattern in DOMAINS if re.search(pattern, name)), GENERAL_SHEET)


def _cell(value):
    """One cell per property: lists one item per line, objects as compact JSON."""
    if _blank(value):
        return EMPTY
    if isinstance(value, list):
        items = [json.dumps(v, separators=(",", ":")) if isinstance(v, dict) else str(v) for v in value]
        return "\n".join(items)
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"))
    return value


def property_value(prop: dict | None, name: str):
    """The trunk base's own `instance` value when it has one, otherwise the `default`."""
    if not prop:
        return EMPTY
    value = prop.get("value") or {}
    result = _cell(value["instance"] if value.get("instance") is not None else value.get("default"))
    return MASK if SECRET.search(name) and result != EMPTY else result


def _or_empty(value):
    return EMPTY if _blank(value) else value


def _date_time(value) -> tuple:
    """("yyyy-MM-dd", "HH:mm:ss") halves of an ISO timestamp, or Empty for both."""
    date, time = iso_part(value, 0), iso_part(value, 1)
    return (date, time[:8]) if date and time else (EMPTY, EMPTY)


def unique_by_id(items: list[dict]) -> list[dict]:
    """The trunks API repeats some entries across pages; keep the first of each id."""
    seen, unique = set(), []
    for item in items:
        if item.get("id") and item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique


def _trunk_row(trunk: dict) -> dict:
    created, modified = _date_time(trunk.get("dateCreated")), _date_time(trunk.get("dateModified"))
    connected = _date_time((trunk.get("connectedStatus") or {}).get("connectedStateTime"))
    ref = lambda key, field: (trunk.get(key) or {}).get(field)  # noqa: E731
    return {
        "name": trunk.get("name"),
        "id": trunk.get("id"),
        "version": trunk.get("version"),
        "dateCreated": created[0],
        "timeCreated": created[1],
        "dateModified": modified[0],
        "timeModified": modified[1],
        "state": trunk.get("state"),
        "modifiedByApp": _or_empty(trunk.get("modifiedByApp")),
        "createdByApp": _or_empty(trunk.get("createdByApp")),
        "trunkType": trunk.get("trunkType"),
        "edgeId": ref("edge", "id"),
        "edgeName": ref("edge", "name"),
        "trunkBaseId": ref("trunkBase", "id"),
        "trunkBaseName": ref("trunkBase", "name"),
        "trunkMetabaseid": ref("trunkMetabase", "id"),
        "trunkMetabaseName": ref("trunkMetabase", "name"),
        "edgeGroupid": ref("edgeGroup", "id"),
        "edgeGroupName": ref("edgeGroup", "name"),
        "inService": trunk.get("inService"),
        "enabled": trunk.get("enabled"),
        "logicalInterfaceId": ref("logicalInterface", "id"),
        "logicalInterfaceName": ref("logicalInterface", "name"),
        "connectedStatusconnected": ref("connectedStatus", "connected"),
        "connectedStateDate": connected[0],
        "connectedStateTime": connected[1],
        "optionsStatus": _cell(trunk.get("optionsStatus")),
        "registersStatus": _cell(trunk.get("registersStatus")),
        "ipStatus": _or_empty(ref("ipStatus", "address")),
        "optionsEnabledStatus": trunk.get("optionsEnabledStatus"),
        "registersEnabledStatus": trunk.get("registersEnabledStatus"),
        "family": trunk.get("family"),
        "proxyAddressList": _cell(trunk.get("proxyAddressList")),
    }


def _base_rows(base: dict, property_names: list[str], user_names: dict) -> dict[str, dict]:
    created, modified = _date_time(base.get("dateCreated")), _date_time(base.get("dateModified"))
    ref = lambda key, field: _or_empty((base.get(key) or {}).get(field))  # noqa: E731
    rows = {GENERAL_SHEET: {
        "name": base.get("name"),
        "id": base.get("id"),
        "version": base.get("version"),
        "dateCreated": created[0],
        "timeCreated": created[1],
        "dateModified": modified[0],
        "timeModified": modified[1],
        "modifiedById": _or_empty(base.get("modifiedBy")),
        "modifiedByName": user_names.get(base.get("modifiedBy")) or EMPTY,
        "createdById": _or_empty(base.get("createdBy")),
        "createdByName": user_names.get(base.get("createdBy")) or EMPTY,
        "state": base.get("state"),
        "modifiedByApp": _or_empty(base.get("modifiedByApp")),
        "createdByApp": _or_empty(base.get("createdByApp")),
        "trunkMetabaseId": (base.get("trunkMetabase") or {}).get("id"),
        "trunkMetabaseName": (base.get("trunkMetabase") or {}).get("name"),
        "trunkType": base.get("trunkType"),
        "managed": base.get("managed"),
        "siteId": ref("site", "id"),
        "siteName": ref("site", "name"),
        "inboundSiteId": ref("inboundSite", "id"),
        "inboundSiteName": ref("inboundSite", "name"),
    }}
    for sheet, _ in DOMAINS:
        rows[sheet] = {"trunkBaseName": base.get("name"), "trunkBaseId": base.get("id"), "trunkType": base.get("trunkType")}
    properties = base.get("properties") or {}
    for name in property_names:
        rows[property_domain(name)][name] = property_value(properties.get(name), name)
    return rows


@register(
    key="get-trunks",
    title="Get Trunk Details",
    category="Telephony",
    context="Trunks",
    sub_context="Digital and Telephony\\Telephony",
    description="Trunks, plus every trunk base's settings split into worksheets by domain "
    "(general, media, outbound identity, protocol, recording, transport, provisioning). Passwords are masked.",
    source_script="GC CLI Get Org Trunk Details v3.1.ps1",
    freeze_panes="B2",
)
def get_trunks(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting users...")
    user_names = names_by_id(client.get_all("/api/v2/users", state="any"))
    log("Getting trunks...")
    trunks = unique_by_id(client.get_all("/api/v2/telephony/providers/edges/trunks"))
    log(f"  {len(trunks)} trunks")
    log("Getting trunk base settings...")
    # The list leaves out some properties (e.g. SIP credentials), so each trunk base is fetched on its own.
    listed = unique_by_id(client.get_all("/api/v2/telephony/providers/edges/trunkbasesettings", ignoreHidden="false"))
    bases = [
        client.get(f"/api/v2/telephony/providers/edges/trunkbasesettings/{b['id']}", ignoreHidden="false") or b
        for b in listed
    ]
    log(f"  {len(bases)} trunk base settings")

    property_names = sorted({name for b in bases for name in (b.get("properties") or {})}, key=str.lower)
    sheets: dict[str, list[dict]] = {GENERAL_SHEET: [], **{sheet: [] for sheet, _ in DOMAINS}}
    for base in sorted(bases, key=lambda b: (b.get("name") or "").lower()):
        for sheet, row in _base_rows(base, property_names, user_names).items():
            sheets[sheet].append(row)

    return ReportResult(
        rows=[_trunk_row(t) for t in trunks],
        raw={"trunks": trunks, "trunkBaseSettings": bases},
        extra_sheets=[Sheet(name, rows) for name, rows in sheets.items()],
    )
