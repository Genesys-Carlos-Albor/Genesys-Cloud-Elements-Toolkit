from datetime import datetime
from pathlib import Path

from gctoolkit import export
from gctoolkit.reports import load_all

from test_core import FakeResponse, make_client


def page(*entities):
    return [FakeResponse(body={"entities": list(entities), "pageCount": 1})]


def run_result(key, routes):
    return load_all()[key].run(make_client(routes), lambda _: None)


def run(key, routes):
    return run_result(key, routes).rows


def test_get_roles_builds_summary_and_one_sheet_per_role():
    result = run_result("get-roles", {
        "/api/v2/authorization/roles": page(
            {"id": "r1", "name": "_Supervisor_Business", "userCount": 2, "permissions": ["a", "b"], "permissionPolicies": [
                {"domain": "routing", "entityName": "queue", "actionSet": ["view", "edit"], "allowConditions": False},
                {"domain": "analytics", "entityName": "*", "actionSet": ["*"]},
            ]},
            {"id": "r2", "name": "Empty Role", "permissionPolicies": []},
        ),
    })
    assert [r["Permission Count"] for r in result.rows] == [3, 0]
    supervisor, empty = result.extra_sheets
    assert supervisor.name == "SupervisorBusiness"
    assert [r["Permission Domain"] for r in supervisor.rows] == ["analytics", "routing"]
    assert supervisor.rows[0]["Permission Entity Name"] == "All"
    assert supervisor.rows[0]["Permission Action Set"] == "All"
    assert supervisor.rows[1]["Permission Action Set"] == "view\nedit"
    assert supervisor.rows[1]["Permission"] == "a\nb"
    assert empty.rows[0]["Permission Domain"] is None
    assert empty.rows[0]["Permission Action Set"] == "Empty"


def test_get_permissions_drops_domains_repeated_across_pages():
    domain = {"domain": "routing", "permissionMap": {"queue": [{"domain": "routing", "entityType": "queue", "action": "view"}]}}
    rows = run("get-permissions", {"/api/v2/authorization/permissions": page(domain, domain)})
    assert len(rows) == 1


def test_get_skill_groups_details_include_child_conditions():
    group = {"id": "g1", "name": "Spanish Sales", "division": {"id": "d1"}, "memberCount": 0, "dateModified": "2025-06-23T15:01:16Z"}
    detail = {"skillConditions": [{
        "operation": "And",
        "routingSkillConditions": [{"routingSkill": "Sales", "comparator": "GreaterThan", "proficiency": 2, "childConditions": [
            {"operation": "Or", "routingSkillConditions": [{"routingSkill": "Billing", "comparator": "EqualTo", "proficiency": 1}]},
        ]}],
    }]}
    result = run_result("get-skill-groups", {
        "/api/v2/authorization/divisions": page({"id": "d1", "name": "Home"}),
        "/api/v2/routing/skillgroups": [FakeResponse(body={"entities": [group]})],
        "/api/v2/routing/skillgroups/g1": [FakeResponse(body=detail)],
    })
    summary = result.rows[0]
    assert summary["Division Name"] == "Home"
    assert summary["Member Count"] == "0"
    assert summary["Modified Time"] == "03:01:16 PM"
    assert summary["Created Date"] == "Empty"
    parent, child = result.extra_sheets[0].rows
    assert (parent["Skill Type"], parent["Routing Skill Condition Routing Skill"], parent["Routing Skill Condition Proficiency"]) == ("routingSkill", "Sales", 2)
    assert (child["Skill Type"], child["Routing Skill Condition Routing Skill"], child["Operation"]) == ("Child.routingSkill", "Billing", "Or")


def test_get_authorized_apps_reads_entities_and_resolves_owner():
    app = {"client": {"id": "c1", "name": "CRM", "scope": ["users", "routing"]}, "scope": ["users"],
           "resourceOwner": {"id": "org1"}, "createdBy": {"id": "u1"}, "pending": False, "state": "Active"}
    rows = run("get-authorized-apps", {
        "/api/v2/users": page({"id": "u1", "name": "Pat Admin"}),
        "/api/v2/oauth/authorizations": [FakeResponse(body={"total": 1, "entities": [app]})],
        "/api/v2/oauth/clients": page(),
        "/api/v2/organizations/me": [FakeResponse(body={"id": "org1", "name": "Acme"})],
    })
    assert rows[0]["Client Scope"] == "users\nrouting"
    assert rows[0]["Client Allowed IPs"] == "Empty"
    assert rows[0]["Resource Name"] == "Acme"
    assert rows[0]["Created By Name"] == "Pat Admin"
    assert rows[0]["Modified By Id"] == "Empty"


def test_get_skills_formats_modified_date_and_time():
    rows = run("get-skills", {
        "/api/v2/routing/skills": page({"id": "s1", "name": "Billing", "dateModified": "2025-06-23T15:01:16Z", "state": "active", "version": 2}),
    })
    assert rows == [{
        "Skill UUID": "s1", "Skill Name": "Billing", "Date Modified": "6/23/2025", "Time Modified": "03:01:16 PM",
        "State": "active", "Version": 2, "Skill Type": "ACD Routing",
    }]


def test_get_wrapup_codes_resolves_division_and_people():
    rows = run("get-wrapup-codes", {
        "/api/v2/routing/wrapupcodes": page(
            {"id": "w1", "name": "Sold", "division": {"id": "*"}, "dateCreated": "2025-05-13T13:48:36.565Z", "createdBy": "app1"},
        ),
        "/api/v2/users": page({"id": "u1", "name": "Pat Admin"}),
        "/api/v2/oauth/clients": [FakeResponse(body={"entities": [{"id": "app1", "name": "Provisioning App"}]})],
    })
    row = rows[0]
    assert row["Division Name"] == "Home"
    assert row["Date Created"] == datetime(2025, 5, 13, 13, 48, 36, 565000)
    assert row["Date Modified"] == "Empty"
    assert row["Created By Name"] == "Provisioning App"
    assert row["Modified By GUID"] == "Empty"


def test_get_users_maps_contacts_phone_groups_and_roles():
    pat = {
        "id": "u1", "name": "Pat Admin", "state": "active", "email": "pat@example.com", "title": "Lead",
        "addresses": [{"mediaType": "PHONE", "display": "(317) 555-0100"}, {"mediaType": "PHONE", "display": "1234"}],
        "authorization": {"roles": [{"name": "employee"}, {"name": "Admin"}]},
        "groups": [{"id": "g1"}, {"id": "g2"}], "manager": {"id": "u2"},
        "dateLastLogin": "2026-10-28T15:36:20.689Z", "acdAutoAnswer": True,
    }
    sam = {"id": "u2", "name": "Sam Boss", "state": "inactive", "email": "sam@example.com", "dateLastLogin": "0000-12-30T00:00:00Z"}
    rows = run("get-users", {
        "/api/v2/users": page(pat, sam),
        "/api/v2/locations": page(),
        "/api/v2/telephony/providers/edges/phones": page(
            {"id": "p1", "name": "PatAdmin-WebRtc", "site": {"id": "site1"}, "phoneBaseSettings": {"id": "b1"}, "lines": [{"id": "l1"}]},
        ),
        "/api/v2/license/users": page({"id": "u1", "licenses": ["cloudCX3"]}),
        "/api/v2/telephony/providers/edges/phonebasesettings": page({"id": "b1", "name": "WebRTC Base"}),
        "/api/v2/groups": page({"id": "g1", "name": "Tier 1"}, {"id": "g2", "name": "Tier 2"}),
        "/api/v2/telephony/providers/edges/sites": page({"id": "site1", "name": "Austin"}),
        "/api/v2/users/u1/queues": page({"name": "Sales"}),
        "/api/v2/users/u1/routinglanguages": page({"id": "lang1", "name": "English"}),
        "/api/v2/users/u2/queues": page(),
    })
    pat_row, sam_row = rows
    assert pat_row["Work Phone"] == "317) 555-0100"
    assert pat_row["Work Phone 2"] == "Empty"
    assert pat_row["Extension"] == "1234"
    assert pat_row["Manager"] == "Sam Boss"
    assert pat_row["Manager Email"] == "sam@example.com"
    assert pat_row["Roles"] == "Admin\nemployee"
    assert pat_row["Groups"] == "Tier 1\nTier 2"
    assert pat_row["Queues"] == "Sales"
    assert pat_row["Language Skill Names"] == "English"
    assert pat_row["Phone Name"] == "PatAdmin-WebRtc"
    assert pat_row["Site"] == "Austin"
    assert pat_row["Phone Base"] == "WebRTC Base"
    assert pat_row["Assigned License"] == "cloudCX3"
    assert pat_row["Auto Answer"] == "True"
    assert pat_row["LastLogon"] == datetime(2026, 10, 28, 15, 36, 20, 689000)
    assert sam_row["LastLogon"] == "Never Logged In"
    assert sam_row["Language Skill Names"] == "Empty"
    assert sam_row["Phone UUID"] == "No phone assigned"
    assert sam_row["Title"] == "Empty"


def test_reveal_in_folder_selects_file_in_explorer(monkeypatch):
    launched = []
    monkeypatch.setattr(export.sys, "platform", "win32")
    monkeypatch.setattr(export.subprocess, "Popen", lambda cmd: launched.append(cmd))
    export.reveal_in_folder(Path(r"C:\Element Reports\Org\Queues\report_v1.0.xlsx"))
    assert launched == [r'explorer /select,"C:\Element Reports\Org\Queues\report_v1.0.xlsx"']
