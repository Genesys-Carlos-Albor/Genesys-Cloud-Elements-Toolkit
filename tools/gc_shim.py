"""Stand-in for gc.exe so the original PowerShell scripts can run against an org through a toolkit profile.

Usage: python tools/gc_shim.py <gc command words> [id] [flags]   (GC_SHIM_PROFILE picks the profile)

Command words before `list`/`get` become the API path; an id after the verb goes before the last word
(`sites numberplans list <id>` -> /sites/<id>/numberplans). -a/--autopaginate returns every entity as an array.
Credentials and output flags meant for gc.exe are ignored.
"""

import json
import os
import sys

from gctoolkit import use_system_certificates
from gctoolkit.client import GenesysClient
from gctoolkit.profiles import get_profile

IGNORED = {"--clientid", "--clientsecret", "--environment", "--outputformat", "--profile", "--pageSize"}
PASSED = {"--state": "state", "--expand": "expand"}


def parse(args: list[str]) -> tuple[str, bool, dict]:
    words, ids, params, paginate, i = [], [], {}, False, 0
    while i < len(args):
        arg = args[i]
        if arg in IGNORED:
            # Unset PowerShell variables are dropped from the command line, leaving the flag without a value.
            i += 1 if i + 1 < len(args) and args[i + 1].startswith("-") else 2
            continue
        if arg in PASSED:
            params[PASSED[arg]] = args[i + 1]
            i += 2
            continue
        if arg in ("-a", "--autopaginate"):
            paginate = True
        elif arg in ("list", "get"):
            ids = args[i + 1:i + 2] if i + 1 < len(args) and not args[i + 1].startswith("-") else []
            i += 1 + len(ids)
            continue
        else:
            words.append(arg)
        i += 1
    if ids:
        words.insert(len(words) - 1, ids[0]) if len(words) > 1 else words.append(ids[0])
    return "/api/v2/" + "/".join(words), paginate, params


def main() -> None:
    use_system_certificates()
    path, paginate, params = parse(sys.argv[1:])
    client = GenesysClient(get_profile(os.environ["GC_SHIM_PROFILE"]))
    data = client.get_all(path, **params) if paginate else client.get(path, **params)
    print(json.dumps(data))


if __name__ == "__main__":
    main()
