import argparse
import getpass
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import __version__, profiles, settings, updates, use_system_certificates
from .client import ApiError, GenesysClient
from .reports import audit_logs, flow_exports, load_all
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


def choose(title: str, options: list[str], allow_all: bool = False) -> str | None:
    """Numbered menu; returns the chosen option, or None for 'All' when allowed."""
    if not sys.stdin.isatty():
        raise SystemExit(f"Pass the {title.lower()} as an option when not running interactively.")
    print(f"\n{title}:")
    if allow_all:
        print("  0. All")
    for i, option in enumerate(options, start=1):
        print(f"{i:>3}. {option}")
    while True:
        choice = input(f"Choose a {title.lower()} number: ").strip()
        if allow_all and choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]


def _pick(value: str | None, title: str, options: list[str], allow_all: bool) -> str | None:
    if value is None:
        return choose(title, options, allow_all)
    if allow_all and value.lower() == "all":
        return None
    match = next((o for o in options if o.lower() == value.lower()), None)
    if not match:
        raise SystemExit(f"Unknown {title.lower()} '{value}'. Choices: {', '.join(options)}")
    return match


def audit_query_from_args(args, profile: profiles.Profile) -> audit_logs.AuditQuery:
    services = audit_logs.service_mapping(GenesysClient(profile))
    service_name = _pick(args.service, "Service", [s["name"] for s in services], allow_all=False)
    service = next(s for s in services if s["name"] == service_name)
    entity_type = _pick(args.entity, "Entity type", [e["name"] for e in service["entities"]], allow_all=True)
    actions = sorted({a for e in service["entities"] if entity_type in (None, e["name"]) for a in e.get("actions") or []})
    action = _pick(args.action, "Action", actions, allow_all=True)

    today = date.today()
    start = date.fromisoformat(args.date_from) if args.date_from else today - timedelta(days=6)
    end = date.fromisoformat(args.date_to) if args.date_to else today
    if start > end:
        raise SystemExit("--from must be on or before --to.")
    if start < audit_logs.earliest_start(today):
        raise SystemExit(f"Audit logs only go back to {audit_logs.earliest_start(today)} (365 days).")
    return audit_logs.AuditQuery(service_name, entity_type, action, start, end)


def flows_from_args(args, profile: profiles.Profile) -> list[dict]:
    flows = flow_exports.list_flows(GenesysClient(profile))
    if args.flow_type:
        wanted = {t.upper() for t in args.flow_type}
        flows = [f for f in flows if (f.get("type") or "").upper() in wanted]
    if args.flow:
        wanted = {name.lower() for name in args.flow}
        chosen = [f for f in flows if f["id"].lower() in wanted or (f.get("name") or "").lower() in wanted]
        missing = wanted - {f["id"].lower() for f in chosen} - {(f.get("name") or "").lower() for f in chosen}
        if missing:
            raise SystemExit(f"No flow named {', '.join(sorted(missing))}. Check the name or pass its ID.")
        return chosen
    if args.flow_type:
        return flows
    if not sys.stdin.isatty():
        raise SystemExit("Pass --flow (name or ID, repeatable) or --flow-type when not running interactively.")
    print("\nFlows:")
    for i, f in enumerate(flows, start=1):
        print(f"{i:>4}. {f.get('name')}  ({f.get('type')})")
    while True:
        try:
            choice = input("Flow numbers to export (e.g. 1,4,7), or 'all': ").strip().lower()
        except EOFError:
            raise SystemExit("Cancelled.") from None
        if choice == "all":
            return flows
        numbers = [part.strip() for part in choice.split(",") if part.strip()]
        if numbers and all(n.isdigit() and 1 <= int(n) <= len(flows) for n in numbers):
            return [flows[int(n) - 1] for n in dict.fromkeys(numbers)]


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
    options = None
    if report.options_form == "audit-query":
        options = audit_query_from_args(args, profile)
    elif report.options_form == "flow-picker":
        options = flows_from_args(args, profile)
    run_report(report, profile, log, output_dir=args.output_dir, open_after=False if args.no_open else None, options=options)


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
    audit = p.add_argument_group("get-audit-logs options (prompted for when missing)")
    audit.add_argument("--service", help="Audit service, e.g. Routing")
    audit.add_argument("--entity", help="Entity type, or 'all'")
    audit.add_argument("--action", help="Action, or 'all'")
    audit.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="First day (default: 6 days ago)")
    audit.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="Last day (default: today)")
    flows = p.add_argument_group("export-flows options (prompted for when missing)")
    flows.add_argument("--flow", action="append", help="Flow name or ID to export (repeatable)")
    flows.add_argument("--flow-type", action="append", help="Flow type, e.g. INBOUNDCALL (repeatable); without --flow, exports every flow of these types")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("settings", help="Show or change settings")
    p.add_argument("--save-location")
    p.add_argument("--open-after-export", choices=["on", "off"])
    p.set_defaults(func=cmd_settings)

    p = sub.add_parser("version", help="Show the version and check GitHub for a newer one")
    p.set_defaults(func=cmd_version)
    return parser


def main(argv: list[str] | None = None) -> None:
    use_system_certificates()
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (profiles.ProfileError, ApiError) as err:
        raise SystemExit(f"Error: {err}")
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
