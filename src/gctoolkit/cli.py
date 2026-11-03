import argparse
import getpass
import json
import sys
from pathlib import Path

from . import __version__, profiles, settings, updates
from .client import ApiError, GenesysClient
from .reports import load_all
from .runner import run_report


def log(message: str) -> None:
    print(message, flush=True)


def choose_profile(name: str | None) -> profiles.Profile:
    if name:
        return profiles.get_profile(name)
    available = profiles.list_profiles()
    if not available:
        raise profiles.ProfileError("No profiles yet. Run 'gctk profiles import-gc' or 'gctk profiles add'.")
    if not sys.stdin.isatty():
        raise profiles.ProfileError("Pass --profile when not running interactively.")
    for i, p in enumerate(available, start=1):
        print(f"{i:>3}. {p.name}  ({p.environment})")
    while True:
        choice = input("Choose a profile number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available):
            return available[int(choice) - 1]


def cmd_profiles_list(args) -> None:
    for p in profiles.list_profiles():
        print(f"{p.name:<30} {p.environment:<25} {p.client_id}")


def cmd_profiles_add(args) -> None:
    secret = getpass.getpass("Client secret: ")
    profiles.add_profile(args.name, args.environment, args.client_id, secret)
    print(f"Saved profile '{args.name}'. The secret is stored in the OS credential store.")


def cmd_profiles_remove(args) -> None:
    profiles.remove_profile(args.name)
    print(f"Removed profile '{args.name}'.")


def cmd_profiles_import(args) -> None:
    path = Path(args.path) if args.path else profiles.GC_CLI_CONFIG
    imported, skipped = profiles.import_gc_cli_profiles(path, overwrite=args.overwrite)
    print(f"Imported {len(imported)} profile(s): {', '.join(imported) or '-'}")
    if skipped:
        print(f"Skipped {len(skipped)} (already present or not client-credentials): {', '.join(skipped)}")


def cmd_profiles_test(args) -> None:
    profile = choose_profile(args.profile)
    org = GenesysClient(profile).get("/api/v2/organizations/me")
    print(f"OK: profile '{profile.name}' is connected to org '{org.get('name')}' ({org.get('thirdPartyOrgName')})")


def cmd_reports(args) -> None:
    reports = load_all()
    if args.json:
        print(json.dumps([r.catalog_entry() for r in reports.values()], indent=2))
        return
    for r in sorted(reports.values(), key=lambda r: (r.category, r.title)):
        flag = "CHANGES ORG" if r.modifies_org else "read-only"
        print(f"{r.key:<20} {r.category:<12} {flag:<12} {r.title}  [from {r.source_script}]")


def cmd_run(args) -> None:
    reports = load_all()
    if args.report not in reports:
        raise SystemExit(f"Unknown report '{args.report}'. Run 'gctk reports' to see the list.")
    report = reports[args.report]
    profile = choose_profile(args.profile)
    if report.modifies_org:
        answer = input(f"'{report.title}' CHANGES data in org '{profile.name}'. Type the org name to continue: ")
        if answer.strip() != profile.name:
            raise SystemExit("Cancelled.")
    run_report(report, profile, log, output_dir=args.output_dir, open_after=False if args.no_open else None)


def cmd_settings(args) -> None:
    config = settings.load()
    if args.save_location:
        config["save_location"] = args.save_location
    if args.open_after_export is not None:
        config["open_after_export"] = args.open_after_export == "on"
    if args.save_location or args.open_after_export is not None:
        settings.save(config)
    print(json.dumps(config, indent=2))


def cmd_version(args) -> None:
    print(f"Genesys Cloud Elements Toolkit {__version__}")
    release = updates.latest_release()
    if release is None:
        print("Couldn't check GitHub for a newer version.")
    elif updates.parse_version(release.version) > updates.parse_version(__version__):
        print(f"Version {release.version} is available: {release.page_url}\nTo update, run: {updates.PIP_UPGRADE}")
    else:
        print("You have the latest version.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gctk", description="Genesys Cloud admin reports and tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_profiles = sub.add_parser("profiles", help="Manage org login profiles").add_subparsers(dest="action", required=True)
    p = p_profiles.add_parser("list", help="List saved profiles")
    p.set_defaults(func=cmd_profiles_list)
    p = p_profiles.add_parser("add", help="Add a profile (prompts for the client secret)")
    p.add_argument("name")
    p.add_argument("--environment", required=True, help="e.g. mypurecloud.com or usw2.pure.cloud")
    p.add_argument("--client-id", required=True)
    p.set_defaults(func=cmd_profiles_add)
    p = p_profiles.add_parser("remove", help="Remove a profile and its stored secret")
    p.add_argument("name")
    p.set_defaults(func=cmd_profiles_remove)
    p = p_profiles.add_parser("import-gc", help="Import profiles from the Genesys Cloud CLI (~/.gc/config.toml)")
    p.add_argument("--path")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_profiles_import)
    p = p_profiles.add_parser("test", help="Check that a profile can log in")
    p.add_argument("--profile")
    p.set_defaults(func=cmd_profiles_test)

    p = sub.add_parser("reports", help="List available reports")
    p.add_argument("--json", action="store_true", help="Machine-readable catalog (for a launcher UI)")
    p.set_defaults(func=cmd_reports)

    p = sub.add_parser("run", help="Run a report")
    p.add_argument("report")
    p.add_argument("--profile")
    p.add_argument("--output-dir")
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("settings", help="Show or change settings")
    p.add_argument("--save-location")
    p.add_argument("--open-after-export", choices=["on", "off"])
    p.set_defaults(func=cmd_settings)

    p = sub.add_parser("version", help="Show the version and check GitHub for a newer one")
    p.set_defaults(func=cmd_version)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (profiles.ProfileError, ApiError) as err:
        raise SystemExit(f"Error: {err}")
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
