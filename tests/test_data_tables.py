from pathlib import Path

from gctoolkit.reports import data_tables, load_all

from test_core import FakeResponse, make_client


class Download:
    status_code = 200
    content = b"key,value\nA,1\n"

    def raise_for_status(self):
        pass


def test_safe_name_replaces_characters_windows_rejects():
    assert data_tables.safe_name('IVR: Routes / "Main"?', "id1") == "IVR_ Routes _ _Main__"
    assert data_tables.safe_name(" . ", "id1") == "id1"


def test_export_writes_csv_per_table_and_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(data_tables, "POLL_SECONDS", 0)
    client = make_client({
        "/api/v2/flows/datatables": [FakeResponse(body={"entities": [
            {"id": "t1", "name": "DNIS / Lookup", "division": {"id": "d1", "name": "Home"}},
            {"id": "t2", "name": "Broken"},
        ], "pageCount": 1})],
        "/api/v2/flows/datatables/t1/export/jobs": [FakeResponse(body={"id": "j1", "status": "Processing"})],
        "/api/v2/flows/datatables/t1/export/jobs/j1": [FakeResponse(body={
            "status": "Succeeded", "countRecordsProcessed": 1, "downloadURI": "https://api.example.com/api/v2/downloads/dl1",
        })],
        "/api/v2/downloads/dl1": [FakeResponse(body={"url": "https://downloads.example.com/signed"})],
        "/api/v2/flows/datatables/t2/export/jobs": [FakeResponse(body={"id": "j2", "status": "Failed"})],
    })
    client.session.get = lambda url, **kwargs: Download()

    result = load_all()["export-data-tables"].run(client, lambda _: None, folder=tmp_path)

    ok, failed = result.rows
    csv = Path(ok["Save Directory"])
    assert csv.parent == tmp_path / "DNIS _ Lookup"
    assert csv.read_bytes() == Download.content
    assert csv.name.startswith("DNIS _ Lookup-")
    assert (ok["Division Name"], ok["Rows Exported"]) == ("Home", 1)
    assert (failed["Save Directory"], failed["Rows Exported"]) == ("Export Failed", None)
    logs = list((tmp_path / "JobLogs").glob("Acme-Dev_DataTableBackup_*.log"))
    assert len(logs) == 1 and "Exported 1 of 2 data tables." in logs[0].read_text()
