from ..client import ApiError, GenesysClient
from ..export import Sheet
from ..fields import flatten, get, iso_date_time
from . import Log, ReportResult, register

MEDIA_TYPES = ("call", "callback", "chat", "email", "message", "workitem")


def _columns(*paths: str, headers: dict | None = None):
    """Row builder that copies dotted paths into columns (header defaults to the path)."""
    headers = headers or {}
    return lambda obj: {headers.get(p, p): get(obj, p, None) for p in paths}


def _content_row(item: dict) -> dict:
    created, modified = iso_date_time(item.get("dateCreated"), None), iso_date_time(item.get("dateModified"), None)
    allow = (item.get("mediaTypes") or {}).get("allow") or {}
    return {
        "name": item.get("name"),
        "id": item.get("id"),
        "createdBy": (item.get("createdBy") or {}).get("id"),
        "dateCreated": created[0],
        "timeCreated": created[1],
        "dateModified": modified[0],
        "timeModified": modified[1],
        "modifiedBy": (item.get("modifiedBy") or {}).get("id"),
        "inboundMediaTypes": get(allow, "inbound.type", None),
        "outboundMediaTypes": get(allow, "outbound.type", None),
        "version": item.get("version"),
    }


_WINDOWS = "automaticTimeZoneMapping.callableWindows"
_utilization = [f"utilization.{m}.{f}" for m in MEDIA_TYPES for f in ("includeNonAcd", "interruptableMediaTypes", "maximumCapacity")]

# (sheet, API path, list of entities?, row builder)
SECTIONS = [
    ("Reporting Settings", "/api/v2/analytics/reporting/settings", False,
     _columns("piiMaskingEnabled", "queueAgentAccessObfuscation", "myInteractionsPiiMaskingEnabled")),
    ("Messaging Settings", "/api/v2/conversations/messaging/settings", True, flatten),
    ("Messaging Supported Content", "/api/v2/conversations/messaging/supportedcontent", True, _content_row),
    ("Fax Settings", "/api/v2/fax/settings", False, _columns("sendEmailNotifications", "disableEmailPii")),
    ("External Metrics Definitions", "/api/v2/employeeperformance/externalmetrics/definitions", True, flatten),
    ("Geolocation Settings", "/api/v2/geolocations/settings", False, _columns("enabled")),
    ("Authentication Settings", "/api/v2/organizations/authentication/settings", False, _columns(
        "domainAllowlist", "domainAllowlistEnabled", "inactivityTimeoutExclusions", "ipAddressAllowlist",
        "multifactorAuthenticationRequired",
        *[f"passwordRequirements.{f}" for f in ("expirationDays", "minimumAgeSeconds", "minimumDigits", "minimumLength",
                                                 "minimumLetters", "minimumLower", "minimumSpecials", "minimumUpper")],
        "universalLogout",
        headers={p: p.replace(".", "") for p in [f"passwordRequirements.{f}" for f in (
            "expirationDays", "minimumAgeSeconds", "minimumDigits", "minimumLength",
            "minimumLetters", "minimumLower", "minimumSpecials", "minimumUpper")]},
    )),
    ("Outbound Settings", "/api/v2/outbound/settings", False, _columns(
        "abandonSeconds",
        *[f"{_WINDOWS}.{k}" for k in ("mapped.earliestCallableTime", "mapped.latestCallableTime",
                                       "unmapped.earliestCallableTime", "unmapped.latestCallableTime", "unmapped.timeZoneId")],
        "complianceAbandonRateDenominator", "maxCallsPerAgent", "maxCallsPerAgentDecimal",
        "maxConfigurableCallsPerAgent", "maxLineUtilization", "name", "rescheduleTimeZoneSkippedContacts",
        headers={f"{_WINDOWS}.{k}": f"{_WINDOWS}.{k}".replace(".", "\n") for k in (
            "mapped.earliestCallableTime", "mapped.latestCallableTime", "unmapped.earliestCallableTime",
            "unmapped.latestCallableTime", "unmapped.timeZoneId")},
    )),
    ("Recording Settings", "/api/v2/recording/settings", False, _columns(
        "maxConfigurableScreenRecordingStreams", "maxSimultaneousStreams", "recordingBatchDownloadUrlTtl",
        "recordingPlaybackUrlTtl", "regionalRecordingStorageEnabled", "stopRecordingWhenOnlyExternalParticipants")),
    ("Routing Utilization", "/api/v2/routing/utilization", False,
     _columns(*_utilization, headers={p: p.replace(".", "\n") for p in _utilization})),
]


@register(
    key="get-org-settings",
    title="Get Organization Settings",
    category="Organization",
    context="Organization Settings",
    sub_context="Organizational",
    description="Org-wide settings in one workbook, one sheet each: reporting, messaging, supported content, fax, "
    "external metrics, geolocation, authentication, outbound, recording and routing utilization.",
    source_script="GC CLI Get Organization Settings v1.0.ps1",
    freeze_panes="A2",
)
def get_org_settings(client: GenesysClient, log: Log) -> ReportResult:
    sheets, raw = [], {}
    for name, path, is_list, build in SECTIONS:
        log(f"Getting {name.lower()}...")
        try:
            data = client.get_all(path) if is_list else client.get(path)
        except ApiError as exc:
            log(f"  Skipped: {exc}")
            continue
        raw[name] = data
        items = data if is_list else [data] if data else []
        sheets.append(Sheet(name, [build(item) for item in items], freeze_panes="A2"))
    return ReportResult(rows=[], raw=raw, extra_sheets=sheets)
