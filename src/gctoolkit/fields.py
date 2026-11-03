"""Helpers for flattening API objects into report columns."""

from datetime import datetime

EMPTY = "Empty"


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == []


def values_at(obj, path: str) -> list:
    """Follow a dotted path, stepping into lists along the way (like PowerShell member enumeration)."""
    current = [obj]
    for key in path.split("."):
        found = []
        for item in current:
            for element in item if isinstance(item, list) else [item]:
                if isinstance(element, dict) and key in element:
                    value = element[key]
                    found.extend(value if isinstance(value, list) else [value])
        current = found
    return [v for v in current if not _blank(v)]


def get(obj, path: str, default=EMPTY):
    """Value at a dotted path; multiple values are joined one per line, missing or blank values give `default`."""
    values = values_at(obj, path)
    if not values:
        return default
    if len(values) == 1:
        return values[0]
    return "\n".join(str(v) for v in values)


def iso_part(value: str | None, index: int, default=None):
    """Date (index 0) or time (index 1) half of an ISO-8601 timestamp."""
    if _blank(value) or "T" not in value:
        return default
    return value.split("T")[index]


def to_datetime(value: str | None, default=None):
    """ISO-8601 UTC timestamp as a naive datetime, which Excel stores as a real date value."""
    if _blank(value):
        return default
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def us_date(value: datetime | None, default=None):
    return default if value is None else f"{value.month}/{value.day}/{value.year}"


def us_time(value: datetime | None, default=None):
    return default if value is None else value.strftime("%I:%M:%S %p")


def joined(values: list, default=EMPTY):
    values = [v for v in values if not _blank(v)]
    return "\n".join(str(v) for v in values) if values else default


def percent(value, default=EMPTY):
    return default if _blank(value) else f"{value:.0%}"


def names_by_id(*sources: list[dict]) -> dict:
    """id -> name map; earlier sources win when the same id appears more than once."""
    lookup = {}
    for source in reversed(sources):
        for item in source:
            if item.get("id"):
                lookup[item["id"]] = item.get("name")
    return lookup
