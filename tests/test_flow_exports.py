from pathlib import Path

from gctoolkit.reports import flow_exports, load_all

from test_core import FakeResponse, make_client


class Download:
    status_code = 200
    content = b"flow-archive"

    def raise_for_status(self):
        pass


def test_extension_comes_from_download_url_then_flow_type():
    url = "https://api-downloads.example.com/jobs/j1/flows/Main_IVR.i3InboundFlow?Signature=abc"
    assert flow_exports._extension(url, "BOT") == ".i3InboundFlow"
    assert flow_exports._extension("https://x.example.com/download", "BOT") == ".i3BotFlow"
    assert flow_exports._extension("https://x.example.com/download", "WORKFLOW") == ".i3Flow"


def test_export_flows_downloads_each_flow_into_its_own_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_exports, "POLL_SECONDS", 0)
    client = make_client({
        "/api/v2/flows/export/jobs": [
            FakeResponse(body={"id": "j1", "status": "Started"}),
        ],
        "/api/v2/flows/export/jobs/j1": [
            FakeResponse(body={"id": "j1", "status": "Success",
                               "downloadUrl": "https://dl.example.com/flows/Main_IVR.i3InboundFlow?sig=1"}),
        ],
    })
    client.session.get = lambda url, **kwargs: Download()
    flows = [{"id": "f1", "name": "Main IVR", "type": "INBOUNDCALL",
              "division": {"name": "Home"}, "publishedVersion": {"name": "12.0"}}]

    result = load_all()["export-flows"].run(client, lambda _: None, options=flows, folder=tmp_path)

    (row,) = result.rows
    saved = Path(row["Save Directory"])
    assert saved.parent == tmp_path / "Main IVR"
    assert saved.name.startswith("Main IVR_") and saved.suffix == ".i3InboundFlow"
    assert saved.read_bytes() == Download.content
    assert (row["Flow Type"], row["Division Name"], row["Published Version"]) == ("INBOUNDCALL", "Home", "12.0")
    method, path, _ = client.session.calls[0]
    assert (method, path) == ("POST", "/api/v2/flows/export/jobs")


def test_api_file_name_only_uses_characters_the_export_api_accepts(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_exports, "POLL_SECONDS", 0)
    client = make_client({"/api/v2/flows/export/jobs": [FakeResponse(body={"id": "j1", "status": "Failure"})]})
    bodies = []
    request = client.session.request
    client.session.request = lambda method, url, json=None, **kw: bodies.append(json) or request(method, url, json=json, **kw)

    flow_exports._export_flow(client, {"id": "f1", "name": "Disfruta – Voice Bot”", "type": "BOT"}, tmp_path, lambda _: None)

    assert bodies[0]["flows"][0]["fileName"] == "Disfruta___Voice_Bot"


def test_failed_export_job_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_exports, "POLL_SECONDS", 0)
    client = make_client({
        "/api/v2/flows/export/jobs": [FakeResponse(body={"id": "j1", "status": "Failure"})],
    })

    result = load_all()["export-flows"].run(
        client, lambda _: None, options=[{"id": "f1", "name": "Broken", "type": "BOT"}], folder=tmp_path,
    )

    assert result.rows[0]["Save Directory"] == "Export Failure"
    assert not any(tmp_path.iterdir())
