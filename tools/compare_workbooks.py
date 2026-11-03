"""Compare a PowerShell-generated report workbook with its Python port, cell by cell, sheet by sheet.

Usage: python tools/compare_workbooks.py <powershell.xlsx> <python.xlsx> ["<key column>"]

Rows are matched on the key column when a sheet has it; otherwise rows are compared in order.
Values in columns whose name contains "secret" are never printed.
"""

import sys
from datetime import datetime

from openpyxl import load_workbook

MAX_EXAMPLES = 3


def read_sheets(path: str) -> dict[str, list[tuple]]:
    wb = load_workbook(path, read_only=True)
    return {ws.title: list(ws.iter_rows(values_only=True)) for ws in wb.worksheets}


def normalize(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="milliseconds")
    return str(value).replace("\r\n", "\n").strip()


def keyed(rows: list[tuple], header: list, key: str | None) -> dict:
    if key in header:
        return {r[header.index(key)]: dict(zip(header, r)) for r in rows}
    return {i: dict(zip(header, r)) for i, r in enumerate(rows, start=2)}


def show(col: str, value):
    return "<hidden>" if "secret" in col.lower() and value is not None else repr(value)


def compare_sheet(name: str, ps_rows: list[tuple], py_rows: list[tuple], key: str | None, verbose: bool) -> int:
    ps_header, py_header = list(ps_rows[0]), list(py_rows[0])
    ps, py = keyed(ps_rows[1:], ps_header, key), keyed(py_rows[1:], py_header, key)
    problems = 0
    if ps_header != py_header:
        problems += 1
        print(f"[{name}] columns differ")
        print(f"  Only in PowerShell: {[c for c in ps_header if c not in py_header]}")
        print(f"  Only in Python:     {[c for c in py_header if c not in ps_header]}")
        if set(ps_header) == set(py_header):
            print("  (same columns, different order)")
    if set(ps) != set(py):
        problems += 1
        print(f"[{name}] rows: PowerShell {len(ps)}, Python {len(py)}; "
              f"missing in Python {len(set(ps) - set(py))}, extra in Python {len(set(py) - set(ps))}")

    diffs: dict[str, list] = {}
    for row_key, ps_row in ps.items():
        for col in ps_header:
            a, b = normalize(ps_row.get(col)), normalize(py.get(row_key, {}).get(col))
            if a != b:
                diffs.setdefault(col, []).append((row_key, a, b))
    cells = len(ps) * len(ps_header)
    differing = sum(len(v) for v in diffs.values())
    if verbose or differing:
        print(f"[{name}] {len(ps)} rows, cells compared {cells}, differing {differing}")
    for col, items in diffs.items():
        print(f"  [{col}] differs in {len(items)} row(s)")
        for row_key, a, b in items[:MAX_EXAMPLES]:
            print(f"    {row_key}:\n      PowerShell: {show(col, a)}\n      Python:     {show(col, b)}")
    return problems + differing


def main(ps_path: str, py_path: str, key: str | None = None) -> int:
    ps_sheets, py_sheets = read_sheets(ps_path), read_sheets(py_path)
    print(f"Sheets: PowerShell {len(ps_sheets)}, Python {len(py_sheets)}")
    missing = [s for s in ps_sheets if s not in py_sheets]
    extra = [s for s in py_sheets if s not in ps_sheets]
    if missing or extra:
        print(f"  Only in PowerShell: {missing}\n  Only in Python:     {extra}")
    verbose = len(ps_sheets) <= 3
    total = 0
    for name, rows in ps_sheets.items():
        if name in py_sheets and rows and py_sheets[name]:
            total += compare_sheet(name, rows, py_sheets[name], key, verbose)
    print(f"Result: {'IDENTICAL' if not total and not missing and not extra else f'{total} difference(s)'}")
    return 1 if total or missing or extra else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
