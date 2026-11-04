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


def test_export_flows_saves_architect_and_yaml_files_in_the_flow_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_exports, "POLL_SECONDS", 0)
    monkeypatch.setattr(flow_exports, "EXPORT_WORKERS", 1)
    client = make_client({
        "/api/v2/flows/export/jobs": [
            FakeResponse(body={"id": "j1", "status": "Started"}),
            FakeResponse(body={"id": "j2", "status": "Started"}),
        ],
        "/api/v2/flows/export/jobs/j1": [
            FakeResponse(body={"id": "j1", "status": "Success",
                               "downloadUrl": "https://dl.example.com/flows/Main_IVR.i3InboundFlow?sig=1"}),
        ],
        "/api/v2/flows/export/jobs/j2": [
            FakeResponse(body={"id": "j2", "status": "Success",
                               "downloadUrl": "https://dl.example.com/flows/Main_IVR.yaml?sig=2"}),
        ],
    })
    client.session.get = lambda url, **kwargs: Download()
    bodies = []
    request = client.session.request
    client.session.request = lambda method, url, json=None, **kw: bodies.append(json) or request(method, url, json=json, **kw)
    flows = [{"id": "f1", "name": "Main IVR", "type": "INBOUNDCALL",
              "division": {"name": "Home"}, "publishedVersion": {"name": "12.0"}}]

    result = load_all()["export-flows"].run(client, lambda _: None, options=flows, folder=tmp_path)

    (row,) = result.rows
    architect, yaml = Path(row["Architect File"]), Path(row["YAML File"])
    assert architect.parent == yaml.parent == tmp_path / "Main IVR"
    assert architect.name.startswith("Main IVR_") and architect.suffix == ".i3InboundFlow"
    assert yaml.stem == architect.stem and yaml.suffix == ".yaml"
    assert architect.read_bytes() == yaml.read_bytes() == Download.content
    assert (row["Flow Type"], row["Division Name"], row["Published Version"]) == ("INBOUNDCALL", "Home", "12.0")
    assert [b["flows"][0]["exportType"] for b in bodies if b] == ["Architect", "YAML"]


def test_api_file_name_only_uses_characters_the_export_api_accepts(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_exports, "POLL_SECONDS", 0)
    client = make_client({"/api/v2/flows/export/jobs": [FakeResponse(body={"id": "j1", "status": "Failure"})]})
    bodies = []
    request = client.session.request
    client.session.request = lambda method, url, json=None, **kw: bodies.append(json) or request(method, url, json=json, **kw)

    flow_exports._export_flow(
        client, {"id": "f1", "name": "Disfruta – Voice Bot”", "type": "BOT"}, tmp_path, lambda _: None, "YAML", "stamp",
    )

    assert bodies[0]["flows"][0]["fileName"] == "Disfruta___Voice_Bot"


def test_failed_export_job_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_exports, "POLL_SECONDS", 0)
    client = make_client({
        "/api/v2/flows/export/jobs": [FakeResponse(body={"id": "j1", "status": "Failure"})],
    })

    result = load_all()["export-flows"].run(
        client, lambda _: None, options=[{"id": "f1", "name": "Broken", "type": "BOT"}], folder=tmp_path,
    )

    assert (result.rows[0]["Architect File"], result.rows[0]["YAML File"]) == ("Export Failure", "Export Failure")
    assert not any(tmp_path.iterdir())
