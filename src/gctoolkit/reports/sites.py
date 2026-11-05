from ..client import GenesysClient
from ..export import Sheet
from ..fields import EMPTY, _blank, joined, to_datetime, us_date, us_time
from . import Log, ReportResult, register

STYLE = "TableStyleLight11"


def _date(value, default=EMPTY):
    return us_date(to_datetime(value), default)


def _time(value, default=EMPTY):
    return us_time(to_datetime(value), default)


def _ids(items) -> list:
    return [i.get("id") for i in items or [] if isinstance(i, dict)]


def _site_row(site: dict) -> dict:
    edges = _ids(site.get("edges"))
    return {
        "Site GUID": site.get("id"),
        "Description": site["description"] if len(site.get("description") or "") > 3 else EMPTY,
        "Site Name": site.get("name"),
        "Version": site.get("version"),
        "Caller ID": site.get("callerId") or EMPTY,
        "Caller Name": site.get("callerName") or EMPTY,
        "Created By": site.get("createdBy"),
        "Created Date": _date(site.get("dateCreated")),
        "Created Time": _time(site.get("dateCreated")),
        "Modified By GUID": site.get("modifiedBy") or "N/A",
        "Modified Date": _date(site.get("dateModified"), "N/A"),
        "Modified Time": _time(site.get("dateModified"), "N/A"),
        "state": site.get("state"),
        "Primary Sites": joined(_ids(site.get("primarySites"))),
        "Secondary Sites": joined(_ids(site.get("secondarySites"))),
        "Primary Edges": joined(_ids(site.get("primaryEdges"))),
        "Secondary Edges": joined(_ids(site.get("secondaryEdges"))),
        "edges": joined(edges, "N/A"),
        "Location ID": (site.get("location") or {}).get("id"),
        "Location Name": (site.get("location") or {}).get("name"),
        "Managed": site.get("managed"),
        "Time Zone": (site.get("edgeAutoUpdateConfig") or {}).get("timeZone") or EMPTY,
        "mediaModel": site.get("mediaModel"),
        "coreSite": site.get("coreSite"),
        "siteConnections": joined([c.get("name") for c in site.get("siteConnections") or []], "N/A"),
        "mediaRegions": joined(site.get("mediaRegions") or [], "N/A"),
        "cloudProxyForceTurn": site.get("cloudProxyForceTurn"),
    }


def _number_plan_row(site: dict, plan: dict) -> dict:
    return {
        "Site ID": site.get("id"),
        "Site Name": site.get("name"),
        "NumberPlans ID": plan.get("id") or EMPTY,
        "NumberPlans Name": plan.get("name") or EMPTY,
        "NumberPlans Date Created": _date(plan.get("dateCreated")),
        "NumberPlans Time Created": _time(plan.get("dateCreated")),
        "NumberPlans Date Modified": _date(plan.get("dateModified")),
        "NumberPlans Time Modified": _time(plan.get("dateModified")),
        "NumberPlans State": plan.get("state") or EMPTY,
        "NumberPlans Priority": plan.get("priority") or 0,
        "NumberPlans Numbers": joined([n.get("start") for n in plan.get("numbers") or []]),
        "NumberPlans Classification": plan.get("classification") or EMPTY,
        "NumberPlans Match Type": plan.get("matchType") or EMPTY,
    }


def _route_row(site: dict, route: dict) -> dict:
    return {
        "Site ID": site.get("id"),
        "Site Name": site.get("name"),
        "Outbound Route ID": route.get("id"),
        "Outbound Route Name": route.get("name"),
        "Outbound Route Version": route.get("version"),
        "Outbound Route Date Created": _date(route.get("dateCreated")),
        "Outbound Route Time Created": _time(route.get("dateCreated")),
        "Outbound Route Date Modified": _date(route.get("dateModified")),
        "Outbound Route Time Modified": _time(route.get("dateModified")),
        "Outbound Route State": route.get("state"),
        "Outbound Route Classification Types": joined(route.get("classificationTypes") or []),
        "Outbound Route Enabled": route.get("enabled"),
        "Outbound Route Distribution": route.get("distribution"),
        "Outbound Route External Trunk Bases": joined([t.get("name") for t in route.get("externalTrunkBases") or []]),
    }


@register(
    key="get-sites",
    title="Get Sites",
    category="Telephony",
    context="Sites",
    sub_context="Digital and Telephony\\Telephony",
    description="Telephony sites, plus Number Plans and Outbound Routes sheets for every site.",
    source_script="GC CLI Get Sites v4.0.ps1",
    name_separator="_",
    table_style=STYLE,
)
def get_sites(client: GenesysClient, log: Log) -> ReportResult:
    log("Getting sites...")
    sites = client.get_all("/api/v2/telephony/providers/edges/sites")
    log(f"  {len(sites)} sites; getting number plans and outbound routes...")
    plans, routes = [], []
    for site in sites:
        base = f"/api/v2/telephony/providers/edges/sites/{site['id']}"
        plans += [_number_plan_row(site, p) for p in client.get(f"{base}/numberplans") or []]
        routes += [_route_row(site, r) for r in client.get_all(f"{base}/outboundroutes")]
    return ReportResult(
        rows=[_site_row(s) for s in sites],
        raw=sites,
        extra_sheets=[
            Sheet("Number Plans", plans, table_name="Number_Plans", style=STYLE),
            Sheet("Outbound Routes", routes, table_name="Outbound_Routes", style=STYLE),
        ],
    )
