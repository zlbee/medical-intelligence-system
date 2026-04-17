from __future__ import annotations

import re
from datetime import date
from html import unescape
from typing import Any, Iterable

from app.domain import DatePrecision, NormalizedDate

MONTH_LOOKUP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

NCT_PATTERN = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)


def get_nested(mapping: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = " ".join(unescape(value).split())
        return normalized or None
    return clean_text(str(value))


def unique_strings(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    normalized_values: list[str] = []
    for value in values:
        normalized = clean_text(value)
        if normalized is None:
            continue
        marker = normalized.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        normalized_values.append(normalized)
    return normalized_values


def normalize_enum_label(value: str | None) -> str | None:
    normalized = clean_text(value)
    if normalized is None:
        return None
    return normalized.replace("-", "_").replace(" ", "_").upper()


def parse_partial_date(raw_value: str | None) -> NormalizedDate | None:
    normalized = clean_text(raw_value)
    if normalized is None:
        return None

    parts = normalized.split("-")
    try:
        if len(parts) == 3:
            return NormalizedDate(
                raw_text=normalized,
                value=date(int(parts[0]), int(parts[1]), int(parts[2])),
                precision=DatePrecision.DAY,
            )
        if len(parts) == 2:
            return NormalizedDate(
                raw_text=normalized,
                value=date(int(parts[0]), int(parts[1]), 1),
                precision=DatePrecision.MONTH,
            )
        if len(parts) == 1 and len(parts[0]) == 4:
            return NormalizedDate(
                raw_text=normalized,
                value=date(int(parts[0]), 1, 1),
                precision=DatePrecision.YEAR,
            )
    except ValueError:
        return NormalizedDate(raw_text=normalized)
    return NormalizedDate(raw_text=normalized)


def build_structured_date(
    *,
    year: str | None = None,
    month: str | None = None,
    day: str | None = None,
    raw_text: str | None = None,
) -> NormalizedDate | None:
    normalized_year = clean_text(year)
    normalized_month = clean_text(month)
    normalized_day = clean_text(day)
    fallback_text = clean_text(raw_text)

    if normalized_year is None and fallback_text is None:
        return None

    if normalized_year is None:
        return parse_partial_date(fallback_text)

    try:
        year_value = int(normalized_year)
    except ValueError:
        return NormalizedDate(raw_text=fallback_text or normalized_year)

    if normalized_month is None:
        return NormalizedDate(
            raw_text=fallback_text or normalized_year,
            value=date(year_value, 1, 1),
            precision=DatePrecision.YEAR,
        )

    month_value = parse_month(normalized_month)
    if month_value is None:
        return NormalizedDate(raw_text=fallback_text or f"{normalized_year}-{normalized_month}")

    if normalized_day is None:
        return NormalizedDate(
            raw_text=fallback_text or f"{normalized_year}-{month_value:02d}",
            value=date(year_value, month_value, 1),
            precision=DatePrecision.MONTH,
        )

    try:
        day_value = int(normalized_day)
        return NormalizedDate(
            raw_text=fallback_text or f"{normalized_year}-{month_value:02d}-{day_value:02d}",
            value=date(year_value, month_value, day_value),
            precision=DatePrecision.DAY,
        )
    except ValueError:
        return NormalizedDate(
            raw_text=fallback_text or f"{normalized_year}-{month_value:02d}-{normalized_day}"
        )


def parse_month(value: str) -> int | None:
    normalized = clean_text(value)
    if normalized is None:
        return None
    if normalized.isdigit():
        month_value = int(normalized)
        if 1 <= month_value <= 12:
            return month_value
        return None
    return MONTH_LOOKUP.get(normalized.casefold())


def extract_nct_ids(values: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for value in values:
        matches.extend(match.upper() for match in NCT_PATTERN.findall(value))
    return unique_strings(matches)

