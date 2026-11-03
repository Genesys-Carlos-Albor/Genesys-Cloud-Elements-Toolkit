from concurrent.futures import ThreadPoolExecutor

from ..client import ApiError, GenesysClient
from ..fields import EMPTY, get, iso_part, names_by_id, percent
from . import Log, ReportResult, register

PER_QUEUE_WORKERS = 4


def _queue_details(client: GenesysClient, queue: dict, log: Log) -> tuple[list[dict], list[dict]]:
    try:
        wrapup_codes = client.get_all(f"/api/v2/routing/queues/{queue['id']}/wrapupcodes")
    except ApiError as err:
        log(f"  Wrap-up codes for queue '{queue['name']}' failed: {err}")
        wrapup_codes = []
    try:
        members = client.get_all(f"/api/v2/routing/queues/{queue['id']}/members")
    except ApiError as err:
        log(f"  Members for queue '{queue['name']}' failed: {err}")
        members = []
    return wrapup_codes, members


def _row(q: dict, wrapup_codes: list[dict], members: list[dict], who: dict, script_names: dict) -> dict:
    def person(user_id):
        return who.get(user_id) if user_id else EMPTY

    script_id = get(q, "defaultScripts.CALL.id", None)
    media = q.get("mediaSettings") or {}
    return {
        "Queue GUID": q.get("id"),
        "Queue Name": q.get("name"),
        "Division GUID": get(q, "division.id", None),
        "Division Name": get(q, "division.name", None),
        "Created by GUID": q.get("createdBy"),
        "Created by Name": person(q.get("createdBy")),
        "Created Date": iso_part(q.get("dateCreated"), 0),
        "Created Time": iso_part(q.get("dateCreated"), 1),
        "Modified by GUID": get(q, "modifiedBy", "N/A"),
        "Modified by Name": person(q.get("modifiedBy")),
        "Modified Date": iso_part(q.get("dateModified"), 0, "N/A"),
        "Modified Time": iso_part(q.get("dateModified"), 1, "N/A"),
        "enableAgentOwnedCallbacks": get(q, "agentOwnedRouting.enableAgentOwnedCallbacks"),
        "maxOwnedCallbackDelayHours": get(q, "agentOwnedRouting.maxOwnedCallbackDelayHours"),
        "maxOwnedCallbackHours": get(q, "agentOwnedRouting.maxOwnedCallbackHours"),
        "removeOwnershipOnExpiry": get(q, "agentOwnedRouting.removeOwnershipOnExpiry"),
        "defaultMediaLanguage": get(q, "defaultMediaLanguage"),
        "lastAgentRoutingMode": get(q, "lastAgentRoutingMode"),
        "scoringMethod": get(q, "scoringMethod"),
        "call.alertingTimeoutSeconds": get(media, "call.alertingTimeoutSeconds", None),
        "call.serviceLevel.percentage": percent(get(media, "call.serviceLevel.percentage", None)),
        "call.serviceLevel.durationMs": get(media, "call.serviceLevel.durationMs", None),
        "callback.alertingTimeoutSeconds": get(media, "callback.alertingTimeoutSeconds", None),
        "callback.serviceLevel.percentage": percent(get(media, "callback.serviceLevel.percentage", None)),
        "callback.serviceLevel.durationMs": get(media, "callback.serviceLevel.durationMs", None),
        "callback.autoDialDelaySeconds": get(media, "callback.autoDialDelaySeconds"),
        "callback.autoEndDelaySeconds": get(media, "callback.autoEndDelaySeconds"),
        "callback.enableAutoAnswer": get(media, "callback.enableAutoAnswer"),
        "callback.enableAutoDialAndEnd": get(media, "callback.enableAutoDialAndEnd"),
        "callback.mode": get(media, "callback.mode"),
        "chat.alertingTimeoutSeconds": get(media, "chat.alertingTimeoutSeconds"),
        "chat.serviceLevel.durationMs": get(media, "chat.serviceLevel.durationMs"),
        "chat.serviceLevel.percentage": get(media, "chat.serviceLevel.percentage"),
        "email.alertingTimeoutSeconds": get(media, "email.alertingTimeoutSeconds"),
        "email.serviceLevel.durationMs": get(media, "email.serviceLevel.durationMs"),
        "email.serviceLevel.percentage": get(media, "email.serviceLevel.percentage"),
        "message.alertingTimeoutSeconds": get(media, "message.alertingTimeoutSeconds"),
        "message.serviceLevel.durationMs": get(media, "message.serviceLevel.durationMs"),
        "message.serviceLevel.percentage": get(media, "message.serviceLevel.percentage"),
        "Scoring Method": q.get("scoringMethod"),
        "acwSettings.timeoutMs": get(q, "acwSettings.timeoutMs", None),
        "acwSettings.wrapupPrompt": get(q, "acwSettings.wrapupPrompt", None),
        "skillEvaluationMethod": get(q, "skillEvaluationMethod"),
        "WhisperPrompt": get(q, "whisperPrompt.name"),
        "autoAnswerOnly": get(q, "autoAnswerOnly"),
        "enableTranscription": get(q, "enableTranscription", False),
        "callingPartyName": get(q, "callingPartyName"),
        "callingPartyNumber": get(q, "callingPartyNumber"),
        "Routing Rule Operator": get(q, "routingRules.operator"),
        "Routing Rule Threshold": get(q, "routingRules.threshold"),
        "Routing Rule WaitSeconds": get(q, "routingRules.waitSeconds", 0),
        "DefaultScriptGUID": script_id or EMPTY,
        "DefaultScriptName": script_names.get(script_id) if script_id else EMPTY,
        "suppressInQueueCallRecording": q.get("suppressInQueueCallRecording"),
        "WrapUpCodes": get(wrapup_codes, "name"),
        "memberCount": q.get("memberCount"),
        "joinedMemberCount": get(q, "joinedMemberCount"),
        "memberGroups.name": get(q, "memberGroups.name"),
        "memberGroups.id": get(q, "memberGroups.id"),
        "memberGroups.division.name": get(q, "memberGroups.division.name"),
        "memberGroups.division.id": get(q, "memberGroups.division.id"),
        "memberGroups.memberCount": get(q, "memberGroups.memberCount"),
        "memberGroups.type": get(q, "memberGroups.type"),
        "userMemberCount": get(q, "userMemberCount"),
        "Members": get(members, "name"),
        "CGA PilotRule Condition Metric": get(q, "conditionalGroupActivation.pilotRule.conditions.simpleMetric.metric"),
        "CGA PilotRule Condition Operator": get(q, "conditionalGroupActivation.pilotRule.conditions.operator"),
        "CGA PilotRule Condition Value": get(q, "conditionalGroupActivation.pilotRule.conditions.value"),
        "CGA PilotRule Condition Expression": get(q, "conditionalGroupActivation.pilotRule.conditionExpression"),
        "CGA Rule Condition Metric": get(q, "conditionalGroupActivation.rules.conditions.simpleMetric.metric"),
        "CGA Rule Condition Queue Name": get(q, "conditionalGroupActivation.rules.conditions.simpleMetric.queue.name"),
        "CGA Rule Condition Value": get(q, "conditionalGroupActivation.rules.conditions.value"),
        "CGA Rule Condition Expression": get(q, "conditionalGroupActivation.rules.conditionExpression"),
        "CGA Rule SkillGroup": get(q, "conditionalGroupActivation.rules.groups.name"),
    }


@register(
    key="get-queues",
    title="Get Queues",
    category="Routing",
    context="Queues",
    sub_context="User Management",
    description="All queues with settings, wrap-up codes, members, default script and conditional group activation rules.",
    source_script="GC CLI Get Queues v6.3.ps1",
    freeze_panes="A2",
)
def get_queues(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting users...")
    users = client.get_all("/api/v2/users", page_size=500, state="any")
    log(f"  {len(users)} users")
    log("Getting OAuth clients...")
    oauth_clients = (client.get("/api/v2/oauth/clients") or {}).get("entities", [])
    log("Getting scripts...")
    scripts = client.get_all("/api/v2/scripts")
    log("Getting queues...")
    queues = client.get_all("/api/v2/routing/queues", page_size=500)
    log(f"  {len(queues)} queues")

    who = names_by_id(users, oauth_clients)
    script_names = names_by_id(scripts)

    log("Getting wrap-up codes and members for each queue...")
    with ThreadPoolExecutor(max_workers=PER_QUEUE_WORKERS) as pool:
        details = list(pool.map(lambda q: _queue_details(client, q, log), queues))

    rows = [_row(q, codes, members, who, script_names) for q, (codes, members) in zip(queues, details)]
    return ReportResult(rows=rows, raw=queues, sort_by="Queue Name")
