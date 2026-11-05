from gctoolkit import fields
from gctoolkit.reports import language_skills, load_all, locations, org_settings, sites, speech_analytics

from test_core import FakeResponse, make_client


def page(*entities):
    return [FakeResponse(body={"entities": list(entities), "pageCount": 1})]


def log(_):
    pass


def test_flatten_and_iso_date_time():
    assert fields.flatten({"a": {"b": 1, "selfUri": "/x"}, "c": [], "d": [{"e": 1}, {"e": 2}], "f": ["x", "y"]}) == {
        "a.b": 1, "c": "Empty", "d.e": "1\n2", "f": "x\ny",
    }
    assert fields.iso_date_time("2026-01-02T03:04:05.123Z") == ("2026-01-02", "03:04:05")
    assert fields.iso_date_time(None, None) == (None, None)


def test_locations_split_top_level_and_sub_locations():
    hq = {"id": "hq", "name": "HQ", "address": {"street1": "1 Main", "zipcode": "02150"}, "addressStored": True}
    floor = {"id": "f2", "name": "Floor 2", "path": ["hq"], "state": "active"}
    client = make_client({"/api/v2/locations": page(hq, floor)})
    result = locations.get_locations(client, log)
    assert [r["Location Name"] for r in result.rows] == ["HQ"]
    row = result.rows[0]
    assert (row["Zip Code"], row["Address Street 2"], row["Sub-Locations"], row["Address Stored"]) == ("02150", "Empty", "Floor 2", True)
    assert result.extra_sheets[0].rows == [
        {"ID": "f2", "Name": "Floor 2", "State": "active", "Path": "hq", "addressVerified": None, "Parent Name": "HQ"}
    ]


def test_sites_include_number_plans_and_outbound_routes():
    site = {"id": "s1", "name": "Site 1", "callerId": "+15551234", "dateCreated": "2026-01-02T15:04:05Z",
            "edges": [{"id": "e1"}, {"id": "e2"}], "mediaRegions": ["us-east-1"]}
    base = "/api/v2/telephony/providers/edges/sites"
    client = make_client({
        base: page(site),
        f"{base}/s1/numberplans": [FakeResponse(body=[{"id": "np", "name": "Emergency", "numbers": [{"start": "911"}, {"start": "933"}]}])],
        f"{base}/s1/outboundroutes": page({"id": "r1", "name": "Default", "classificationTypes": ["National"],
                                           "externalTrunkBases": [{"name": "Trunk A"}]}),
    })
    result = sites.get_sites(client, log)
    row = result.rows[0]
    assert (row["Caller ID"], row["Created Date"], row["Created Time"]) == ("+15551234", "1/2/2026", "03:04:05 PM")
    assert (row["Modified Date"], row["edges"], row["Primary Edges"]) == ("N/A", "e1\ne2", "Empty")
    plans, routes = (s.rows for s in result.extra_sheets)
    assert (plans[0]["NumberPlans Numbers"], plans[0]["NumberPlans Priority"]) == ("911\n933", 0)
    assert routes[0]["Outbound Route External Trunk Bases"] == "Trunk A"


def test_language_skills():
    client = make_client({"/api/v2/routing/languages": page({"id": "l1", "name": "Spanish", "dateModified": "2026-03-04T05:06:07Z"})})
    row = language_skills.get_language_skills(client, log).rows[0]
    assert (row["Language Name"], row["Date Modified"], row["Time Modified"], row["Skill Type"]) == ("Spanish", "3/4/2026", "05:06:07 AM", "Language")


def test_sta_topics_resolve_modified_by_name():
    topic = {"id": "t1", "name": "Billing", "dateModified": "2026-03-04T05:06:07.890Z", "modifiedBy": {"id": "u1"},
             "tags": ["a", "b"], "published": True}
    client = make_client({
        "/api/v2/speechandtextanalytics/topics": page(topic, {"id": "t2", "name": "Other", "modifiedBy": {"id": "gone"}}),
        "/api/v2/users": page({"id": "u1", "name": "Ann"}),
    })
    rows = speech_analytics.get_sta_topics(client, log).rows
    assert (rows[0]["dateModified"], rows[0]["timeModified"], rows[0]["modifiedByName"], rows[0]["tags"]) == ("2026-03-04", "05:06:07", "Ann", "a\nb")
    assert (rows[1]["modifiedByName"], rows[1]["tags"]) == ("gone", None)


def test_org_settings_one_sheet_per_section_and_skips_failures():
    routes = {path: [FakeResponse(status=403, body={"message": "no"})] for _, path, _, _ in org_settings.SECTIONS}
    routes["/api/v2/fax/settings"] = [FakeResponse(body={"sendEmailNotifications": True, "disableEmailPii": False})]
    routes["/api/v2/routing/utilization"] = [FakeResponse(body={"utilization": {"call": {"maximumCapacity": 1, "interruptableMediaTypes": ["email", "chat"]}}})]
    result = org_settings.get_org_settings(make_client(routes), log)
    sheets = {s.name: s.rows for s in result.extra_sheets}
    assert set(sheets) == {"Fax Settings", "Routing Utilization"}
    assert sheets["Fax Settings"] == [{"sendEmailNotifications": True, "disableEmailPii": False}]
    utilization = sheets["Routing Utilization"][0]
    assert utilization["utilization\ncall\nmaximumCapacity"] == 1
    assert utilization["utilization\ncall\ninterruptableMediaTypes"] == "email\nchat"


def test_new_reports_are_registered():
    assert {"get-locations", "get-sites", "get-language-skills", "get-sta-categories", "get-sta-programs",
            "get-sta-topics", "get-org-settings"} <= set(load_all())
