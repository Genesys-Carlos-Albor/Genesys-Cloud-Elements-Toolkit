import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("GCTK_CONFIG_DIR", Path.home() / ".gctoolkit"))
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "save_location": str(Path.home() / "Element Reports"),
    "open_after_export": True,
    "check_for_updates": True,
}

# Genesys Cloud environment -> region code used as the report file name prefix (from GCAuthRegions.xlsx).
REGIONS = {
    "mypurecloud.com": "USE1",
    "use2.us-gov-pure.cloud": "USE2FED",
    "usw2.pure.cloud": "USW2",
    "cac1.pure.cloud": "CAN1",
    "sae1.pure.cloud": "SAE1",
    "mypurecloud.de": "EUC1",
    "mypurecloud.ie": "EUW1",
    "euw2.pure.cloud": "EUW2",
    "aps1.pure.cloud": "APS2",
    "apne2.pure.cloud": "APNE2",
    "mypurecloud.com.au": "APSE2",
    "mypurecloud.jp": "APNE1",
    "inindca.com": "ININDCA",
}


def region_code(environment: str) -> str:
    return REGIONS.get(environment, environment.split(".")[0].upper())


def load() -> dict:
    settings = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        settings.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    return settings


def save(settings: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
