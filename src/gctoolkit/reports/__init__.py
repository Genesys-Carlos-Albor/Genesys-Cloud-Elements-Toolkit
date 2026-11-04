"""Report catalog. Each report fetches and maps data; the CLI (or a future launcher) handles login and export."""

from dataclasses import dataclass, field
from typing import Callable

from ..client import GenesysClient
from ..export import Sheet

Log = Callable[[str], None]


@dataclass
class ReportResult:
    rows: list[dict]
    raw: object = None
    sort_by: str | None = None
    extra_sheets: list[Sheet] = field(default_factory=list)
    # Additional raw JSON files: {file-name context: data}, saved next to the workbook.
    extra_json: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Report:
    key: str
    title: str
    category: str
    context: str
    sub_context: str
    description: str
    source_script: str
    run: Callable[[GenesysClient, Log], ReportResult] = field(compare=False)
    modifies_org: bool = False
    folder_includes_context: bool = True
    freeze_panes: str = "B2"
    file_context: str | None = None
    name_separator: str = "."
    sheet_name: str | None = None
    table_name: str | None = None
    table_style: str = "TableStyleLight16"
    # Reports that need input before running (e.g. "audit-query") receive it as `run(..., options=...)`.
    options_form: str | None = None
    # Reports that save their own files (e.g. CSV exports) receive the report folder as `run(..., folder=...)`.
    writes_files: bool = False
    # Subfolder of the report folder for the workbook and JSON.
    workbook_folder: str | None = None

    @property
    def file_label(self) -> str:
        return self.file_context or self.context.replace(" ", "_")

    def catalog_entry(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "modifies_org": self.modifies_org,
            "source_script": self.source_script,
        }


REGISTRY: dict[str, Report] = {}


def register(**meta):
    def decorator(func):
        REGISTRY[meta["key"]] = Report(run=func, **meta)
        return func

    return decorator


def load_all() -> dict[str, Report]:
    from . import (  # noqa: F401
        audit_logs,
        authorized_apps,
        data_tables,
        divisions,
        groups,
        oauth_clients,
        permissions,
        queues,
        roles,
        skill_groups,
        skills,
        user_phones,
        users,
        wrapup_codes,
    )

    return REGISTRY
