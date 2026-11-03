"""Check GitHub Releases for a newer version of the toolkit."""

import re
import sys
from dataclasses import dataclass

import requests

from . import __version__

REPO = "Genesys-Carlos-Albor/Genesys-Cloud-Elements-Toolkit"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
PIP_UPGRADE = f"pip install --upgrade git+https://github.com/{REPO}.git"


@dataclass
class Release:
    version: str
    page_url: str
    exe_url: str | None
    notes: str


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' or '1.2' -> (1, 2, 3) / (1, 2, 0); anything after the numbers (e.g. '-beta') is ignored."""
    match = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    if not match:
        return ()
    parts = tuple(int(p) for p in match.group(1).split("."))
    return parts + (0,) * (3 - len(parts))


def is_frozen_exe() -> bool:
    return getattr(sys, "frozen", False)


def latest_release(session=None, timeout: float = 5) -> Release | None:
    """The newest published release, or None when there is none or GitHub can't be reached."""
    try:
        response = (session or requests).get(
            LATEST_RELEASE_API, headers={"Accept": "application/vnd.github+json"}, timeout=timeout,
        )
        if response.status_code != 200:
            return None
        data = response.json()
    except (requests.RequestException, ValueError):
        return None
    exe = next((a for a in data.get("assets") or [] if a.get("name", "").lower().endswith(".exe")), None)
    return Release(
        version=(data.get("tag_name") or "").lstrip("v"),
        page_url=data.get("html_url") or RELEASES_PAGE,
        exe_url=exe.get("browser_download_url") if exe else None,
        notes=(data.get("body") or "").strip(),
    )


def newer_release(current: str = __version__, session=None) -> Release | None:
    release = latest_release(session)
    if release and parse_version(release.version) > parse_version(current):
        return release
    return None
