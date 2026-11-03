from datetime import date, datetime, timezone

from gctoolkit.reports import audit_logs, load_all

from test_core import FakeResponse, make_client


def test_intervals_split_into_30_day_chunks_and_stop_at_now(monkeypatch):
    monkeypatch.setattr(audit_logs, "_utc", lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc))
    now = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
    chunks = audit_logs.intervals(date(2026, 9, 1), date(2026, 11, 3), now=now)
    assert chunks == [
        "2026-09-01T00:00:00Z/2026-10-01T00:00:00Z",
        "2026-10-01T00:00:00Z/2026-10-31T00:00:00Z",
        "2026-10-31T00:00:00Z/2026-11-03T18:00:00Z",
    ]
    assert audit_logs.intervals(date(2026, 11, 2), date(2026, 11, 2), now=now) == ["2026-11-02T00:00:00Z/2026-11-03T00:00:00Z"]


def test_earliest_start_keeps_365_days():
    assert audit_logs.earliest_start(date(2026, 11, 3)) == date(2025, 11, 4)


def test_audit_report_runs_query_and_builds_sheets(monkeypatch):
    monkeypatch.setattr(audit_logs, "POLL_SECONDS", 0)
    entry = {
        "id": "a1", "user": {"id": "u1", "name": "Pat Admin"}, "remoteIp": ["10.0.0.1"], "serviceName": "Routing",
        "level": "USER", "eventDate": "2026-11-02T15:04:05Z", "action": "Update", "entity": {"id": "q1", "name": "Sales"},
        "entityType": "Queue", "status": "SUCCESS", "application": "", "initiatingAction": {"transactionId": "t1"},
        "context": {"queueId": "q1"},
        "propertyChanges": [{"property": "name", "oldValues": ["Sale"], "newValues": ["Sales"]}],
        "entityChanges": [],
    }
    client_entry = {**entry, "id": "a2", "user": {"id": "x"}, "client": {"id": "app1"}, "propertyChanges": []}
    client = make_client({
        "/api/v2/audits/query/servicemapping": [FakeResponse(body={"services": [
            {"name": "Routing", "entities": [{"name": "Queue", "actions": ["Create", "Update"]}, {"name": "Skill", "actions": ["Delete"]}]},
        ]})],
        "/api/v2/oauth/clients": [FakeResponse(body={"entities": [{"id": "app1", "name": "Provisioning App"}]})],
        "/api/v2/audits/query": [FakeResponse(body={"id": "job1", "state": "Queued"})],
        "/api/v2/audits/query/job1": [FakeResponse(body={"state": "Running"}), FakeResponse(body={"state": "Succeeded"})],
        "/api/v2/audits/query/job1/results": [
            FakeResponse(body={"entities": [entry], "cursor": "next"}),
            FakeResponse(body={"entities": [client_entry]}),
        ],
    })
    query = audit_logs.AuditQuery("Routing", "Queue", None, date.today(), date.today())
    result = load_all()["get-audit-logs"].run(client, lambda _: None, query)

    assert result.rows == [{"name": "Routing", "EntityName": "Queue", "EntityActions": "Create\nUpdate",
                            "From": query.start.isoformat(), "To": query.end.isoformat()}]
    audits, properties, entities = result.extra_sheets
    assert audits.name == "Routing_Queue"
    assert [r["Audit Id"] for r in audits.rows] == ["a1", "a2"]
    first = audits.rows[0]
    assert (first["Event Date"], first["Event Time"]) == ("2026-11-02", "3:04:05 PM")
    assert first["InitiatingAction Transaction Id"] == "t1"
    assert first["Application"] == "Empty"
    assert first["Context Property"] == "queueId"
    assert audits.rows[1]["User Name"] == "Provisioning App"
    assert properties.rows[0]["Old Values"] == "Sale"
    assert entities.rows == []

    posted = [call for call in client.session.calls if call[0] == "POST"]
    assert len(posted) == 1
