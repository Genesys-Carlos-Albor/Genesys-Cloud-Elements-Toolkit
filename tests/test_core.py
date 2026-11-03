from datetime import date

import pytest
from openpyxl import load_workbook

from gctoolkit import export, fields
from gctoolkit.client import ApiError, GenesysClient
from gctoolkit.profiles import Profile
from gctoolkit.reports import load_all


class FakeProfile(Profile):
    client_secret = "secret"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.content = b"x"
        self.text = str(self._body)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


class FakeSession:
    """Serves queued responses per path and records requests."""

    def __init__(self, routes):
        self.routes = {path: list(responses) for path, responses in routes.items()}
        self.calls = []

    def post(self, url, **kwargs):
        return FakeResponse(body={"access_token": "token", "expires_in": 3600})

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split(".com", 1)[1]
        self.calls.append((method, path, params))
        responses = self.routes[path]
        return responses.pop(0) if len(responses) > 1 else responses[0]


def make_client(routes):
    profile = FakeProfile(name="acme-dev", environment="mypurecloud.com", client_id="id")
    return GenesysClient(profile, session=FakeSession(routes))


def test_get_walks_lists_and_defaults():
    queue = {"memberGroups": [{"name": "A", "division": {"name": "Home"}}, {"name": "B"}], "blank": "  ", "flag": False}
    assert fields.get(queue, "memberGroups.name") == "A\nB"
    assert fields.get(queue, "memberGroups.division.name") == "Home"
    assert fields.get(queue, "missing.path") == "Empty"
    assert fields.get(queue, "blank", "N/A") == "N/A"
    assert fields.get(queue, "flag") is False


def test_iso_percent_and_lookup():
    assert fields.iso_part("2026-01-02T03:04:05.000Z", 0) == "2026-01-02"
    assert fields.iso_part("2026-01-02T03:04:05.000Z", 1) == "03:04:05.000Z"
    assert fields.iso_part(None, 0, "N/A") == "N/A"
    assert fields.percent(0.8) == "80%"
    assert fields.names_by_id([{"id": "1", "name": "User"}], [{"id": "1", "name": "OAuth"}]) == {"1": "User"}


def test_file_name_and_versioning(tmp_path):
    profile = FakeProfile(name="acme-dev", environment="usw2.pure.cloud", client_id="id")
    base = export.base_file_name(profile, "Get Queues", on=date(2026, 11, 2))
    assert base == "USW2.ACME-DEV.Get_Queues.11.02.26"
    assert export.versioned_path(tmp_path, base).name == f"{base}_v1.0.xlsx"
    (tmp_path / f"{base}_v1.0.xlsx").touch()
    (tmp_path / f"{base}_v3.0.xlsx").touch()
    assert export.versioned_path(tmp_path, base).name == f"{base}_v4.0.xlsx"


def test_get_all_pages_until_page_count():
    client = make_client({
        "/api/v2/routing/queues": [
            FakeResponse(body={"entities": [{"id": "1"}], "pageCount": 2}),
            FakeResponse(body={"entities": [{"id": "2"}], "pageCount": 2}),
        ]
    })
    assert [q["id"] for q in client.get_all("/api/v2/routing/queues")] == ["1", "2"]


def test_get_all_follows_cursor_next_uri():
    client = make_client({
        "/api/v2/routing/skillgroups": [FakeResponse(body={"entities": [{"id": "1"}], "nextUri": "/api/v2/routing/skillgroups?after=abc"})],
        "/api/v2/routing/skillgroups?after=abc": [FakeResponse(body={"entities": [{"id": "2"}]})],
    })
    assert [g["id"] for g in client.get_all("/api/v2/routing/skillgroups")] == ["1", "2"]


def test_underscore_file_name():
    profile = FakeProfile(name="acme-dev", environment="usw2.pure.cloud", client_id="id")
    base = export.base_file_name(profile, "OAuthAccounts", on=date(2026, 11, 2), separator="_")
    assert base == "USW2_ACME-DEV_OAuthAccounts_11.02.26"


def test_write_workbook_multiple_sheets(tmp_path):
    path = tmp_path / "roles.xlsx"
    long_name = "A role name that is longer than thirty-one characters"
    export.write_workbook([
        export.Sheet("Roles Summary", [{"name": "admin"}], style="TableStyleDark10", freeze_panes="A2"),
        export.Sheet(long_name, [{"Id": "1"}]),
        export.Sheet(long_name, [{"Id": "2"}]),
        export.Sheet("No rows", []),
    ], path)
    wb = load_workbook(path)
    assert wb.sheetnames == ["Roles Summary", long_name[:31], long_name[:29] + "_2"]
    summary = wb["Roles Summary"]
    assert summary.freeze_panes == "A2"
    assert summary.tables["Roles_Summary"].tableStyleInfo.name == "TableStyleDark10"


def test_retries_on_rate_limit_then_raises_on_client_error():
    client = make_client({
        "/api/v2/ok": [FakeResponse(429, headers={"Retry-After": "0"}), FakeResponse(body={"done": True})],
        "/api/v2/bad": [FakeResponse(400, body={"message": "bad request"})],
    })
    assert client.get("/api/v2/ok") == {"done": True}
    with pytest.raises(ApiError, match="HTTP 400: bad request"):
        client.get("/api/v2/bad")


def test_get_queues_report_maps_columns():
    queue = {
        "id": "q1", "name": "Sales", "division": {"id": "d1", "name": "Home"},
        "createdBy": "u1", "dateCreated": "2026-01-02T03:04:05.000Z",
        "mediaSettings": {"call": {"alertingTimeoutSeconds": 8, "serviceLevel": {"percentage": 0.8, "durationMs": 20000}}},
        "defaultScripts": {"CALL": {"id": "s1"}},
        "memberGroups": [{"name": "G1", "type": "GROUP"}, {"name": "G2", "type": "TEAM"}],
    }
    client = make_client({
        "/api/v2/users": [FakeResponse(body={"entities": [{"id": "u1", "name": "Pat Admin"}], "pageCount": 1})],
        "/api/v2/oauth/clients": [FakeResponse(body={"entities": []})],
        "/api/v2/scripts": [FakeResponse(body={"entities": [{"id": "s1", "name": "Default Script"}], "pageCount": 1})],
        "/api/v2/routing/queues": [FakeResponse(body={"entities": [queue], "pageCount": 1})],
        "/api/v2/routing/queues/q1/wrapupcodes": [FakeResponse(body={"entities": [{"name": "Sold"}, {"name": "No Sale"}], "pageCount": 1})],
        "/api/v2/routing/queues/q1/members": [FakeResponse(body={"entities": [{"name": "Agent One"}], "pageCount": 1})],
    })
    result = load_all()["get-queues"].run(client, lambda _: None)
    row = result.rows[0]
    assert row["Queue Name"] == "Sales"
    assert row["Created by Name"] == "Pat Admin"
    assert row["Created Date"] == "2026-01-02"
    assert row["Modified Date"] == "N/A"
    assert row["call.serviceLevel.percentage"] == "80%"
    assert row["DefaultScriptName"] == "Default Script"
    assert row["WrapUpCodes"] == "Sold\nNo Sale"
    assert row["Members"] == "Agent One"
    assert row["memberGroups.type"] == "GROUP\nTEAM"
    assert row["enableTranscription"] is False
    assert len(row) == 74


def test_write_excel_creates_table(tmp_path):
    path = tmp_path / "out.xlsx"
    export.write_excel([{"Name": "A", "Notes": "line1\nline2\x01"}, {"Name": "B", "Extra": [1, 2]}], path, "Queues")
    ws = load_workbook(path)["Queues"]
    assert [c.value for c in ws[1]] == ["Name", "Notes", "Extra"]
    assert ws["B2"].value == "line1\nline2"
    assert ws["C3"].value == "[1, 2]"
    assert "Queues" in ws.tables
