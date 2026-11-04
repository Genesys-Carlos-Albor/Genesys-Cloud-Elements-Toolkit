"""Run a report end to end: fetch, sort, save versioned Excel + JSON, then open and reveal the file."""

from pathlib import Path

from . import export, settings
from .client import GenesysClient
from .profiles import Profile
from .reports import Log, Report


def report_folder(report: Report, profile: Profile, save_root: Path) -> Path:
    folder = save_root / profile.org_label / Path(*report.sub_context.split("\\"))
    return folder / report.context if report.folder_includes_context else folder


def run_report(
    report: Report,
    profile: Profile,
    log: Log,
    output_dir: str | None = None,
    open_after: bool | None = None,
    options=None,
) -> Path | None:
    """Returns the saved workbook path, or None when the report returned no rows."""
    config = settings.load()
    log(f"Running '{report.title}' against {profile.name} ({profile.environment})")
    client = GenesysClient(profile)
    folder = report_folder(report, profile, Path(output_dir or config["save_location"]))
    extra_args = {}
    if report.options_form:
        extra_args["options"] = options
    if report.writes_files:
        extra_args["folder"] = folder
    result = report.run(client, log, **extra_args)
    if not result.rows:
        log("No data was returned; nothing to save.")
        return None
    rows = result.rows
    if result.sort_by:
        rows = sorted(rows, key=lambda r: str(r.get(result.sort_by) or "").lower())

    if report.workbook_folder:
        folder = folder / report.workbook_folder
    folder.mkdir(parents=True, exist_ok=True)
    base = export.base_file_name(profile, report.file_label, separator=report.name_separator)
    xlsx_path = export.versioned_path(folder, base)
    sheet_name = report.sheet_name or report.context
    main = export.Sheet(
        sheet_name, rows, table_name=report.table_name or sheet_name,
        style=report.table_style, freeze_panes=report.freeze_panes,
    )
    export.write_workbook([main, *result.extra_sheets], xlsx_path)
    if result.raw is not None:
        export.write_json(result.raw, xlsx_path.with_suffix(".json"))
    for label, data in result.extra_json.items():
        extra = export.base_file_name(profile, label, separator=report.name_separator)
        export.write_json(data, folder / f"{extra}.json")
    extra_rows = sum(len(s.rows) for s in result.extra_sheets)
    log(f"Saved {len(rows)} rows{f' (plus {extra_rows} on other sheets)' if extra_rows else ''} to {xlsx_path}")

    if config.get("open_after_export") if open_after is None else open_after:
        export.reveal_in_folder(xlsx_path)
        export.open_file(xlsx_path)
    return xlsx_path
