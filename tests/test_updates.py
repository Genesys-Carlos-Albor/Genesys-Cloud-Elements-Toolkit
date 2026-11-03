import requests

from gctoolkit import updates


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error

    def get(self, url, headers=None, timeout=None):
        if self.error:
            raise self.error
        return self.response


RELEASE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/x/y/releases/tag/v0.2.0",
    "body": "New Architect reports",
    "assets": [
        {"name": "notes.txt", "browser_download_url": "https://example/notes.txt"},
        {"name": "Genesys Cloud Elements Toolkit.exe", "browser_download_url": "https://example/app.exe"},
    ],
}


def test_parse_version():
    assert updates.parse_version("v1.2.3") == (1, 2, 3)
    assert updates.parse_version("0.10") == (0, 10, 0)
    assert updates.parse_version("2.0.0-beta") == (2, 0, 0)
    assert updates.parse_version("0.10.0") > updates.parse_version("0.9.9")
    assert updates.parse_version("latest") == ()


def test_newer_release_found_with_exe_asset():
    release = updates.newer_release("0.1.0", session=FakeSession(FakeResponse(body=RELEASE)))
    assert release.version == "0.2.0"
    assert release.exe_url == "https://example/app.exe"
    assert release.notes == "New Architect reports"


def test_no_update_when_current_or_unreachable():
    assert updates.newer_release("0.2.0", session=FakeSession(FakeResponse(body=RELEASE))) is None
    assert updates.newer_release("0.1.0", session=FakeSession(FakeResponse(404))) is None
    assert updates.newer_release("0.1.0", session=FakeSession(error=requests.ConnectionError())) is None
