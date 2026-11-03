"""Org profiles: name, environment and client ID in a JSON file; client secrets in the OS keychain."""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import keyring
from keyring.errors import PasswordDeleteError

from .settings import CONFIG_DIR

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

KEYRING_SERVICE = "gc-toolkit"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
GC_CLI_CONFIG = Path.home() / ".gc" / "config.toml"


class ProfileError(Exception):
    pass


@dataclass
class Profile:
    name: str
    environment: str
    client_id: str

    @property
    def client_secret(self) -> str:
        secret = keyring.get_password(KEYRING_SERVICE, self.name)
        if not secret:
            raise ProfileError(f"No client secret stored for profile '{self.name}'. Re-add the profile.")
        return secret

    @property
    def org_label(self) -> str:
        """Org label used in folder and file names, title-cased like the PowerShell scripts."""
        return self.name if self.name[:1].isupper() else self.name.title()


def _read() -> dict:
    if not PROFILES_FILE.exists():
        return {}
    return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def list_profiles() -> list[Profile]:
    return [Profile(**p) for _, p in sorted(_read().items(), key=lambda kv: kv[0].lower())]


def get_profile(name: str) -> Profile:
    data = _read()
    if name not in data:
        raise ProfileError(f"Profile '{name}' not found. Run 'gctk profiles list'.")
    return Profile(**data[name])


def add_profile(name: str, environment: str, client_id: str, client_secret: str) -> Profile:
    profile = Profile(name=name, environment=environment, client_id=client_id)
    keyring.set_password(KEYRING_SERVICE, name, client_secret)
    data = _read()
    data[name] = asdict(profile)
    _write(data)
    return profile


def remove_profile(name: str) -> None:
    data = _read()
    if data.pop(name, None) is None:
        raise ProfileError(f"Profile '{name}' not found.")
    _write(data)
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
    except PasswordDeleteError:
        pass


def import_gc_cli_profiles(path: Path = GC_CLI_CONFIG, overwrite: bool = False) -> tuple[list[str], list[str]]:
    """Copy client-credential profiles from the Genesys Cloud CLI config. Returns (imported, skipped)."""
    if not path.exists():
        raise ProfileError(f"Genesys Cloud CLI config not found at {path}")
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    existing = _read()
    imported, skipped = [], []
    for name, section in sorted(config.items()):
        if not isinstance(section, dict):
            continue
        client_id = section.get("client_credentials")
        secret = section.get("client_secret")
        environment = section.get("environment")
        if not (client_id and secret and environment) or (name in existing and not overwrite):
            skipped.append(name)
            continue
        add_profile(name, environment, client_id, secret)
        imported.append(name)
    return imported, skipped
