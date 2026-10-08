"""Per-day sale checklist on the trade settings page (user choice, 2026-09-26).

Every date of the bundled price table becomes one multi-selection setting
("出售19号") listing that day's items, all ticked by default.  Unticking an
item keeps it from being sold on that date; items that are not in the
bundled table (online or custom tables) cannot be unticked and are sold.

The setting stores the ticked items, so an item later added to a date the
user already saved starts unticked (not sold, and logged as such); a new
date gets its own checklist with everything ticked.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.tasks.map_trade.calendar import parse_calendar_payload
from src.tasks.map_trade.models import CalendarEntry
from src.tasks.map_trade.trader_constants import CALENDAR_DIR

BUNDLED_CALENDAR_FILE = CALENDAR_DIR / "price_calendar.v1.json"


def sale_day_key(day: int) -> str:
    return f"出售{day}号"


def bundled_sale_days() -> dict[int, tuple[CalendarEntry, ...]]:
    """Dates of the bundled price table that have something to sell."""

    try:
        calendar = parse_calendar_payload(BUNDLED_CALENDAR_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {day: entries for day, entries in calendar.days.items() if entries}


def day_items(entries: Iterable[CalendarEntry]) -> list[str]:
    return list(dict.fromkeys(entry.item for entry in entries))


def describe_entry(entry: CalendarEntry) -> str:
    text = f"{entry.item}→{entry.shop}"
    return f"{text}（保留{entry.reserve}）" if entry.reserve else text


def apply_sale_checklist(
    config: Mapping,
    day: int,
    entries: Iterable[CalendarEntry],
    bundled_entries: Iterable[CalendarEntry],
) -> tuple[list[CalendarEntry], list[CalendarEntry]]:
    """Split today's entries into (to sell, unticked by the user)."""

    entries = list(entries)
    options = set(day_items(bundled_entries))
    key = sale_day_key(day)
    if key not in config:
        return entries, []
    selected = set(config.get(key) or [])
    unticked = options - selected
    keep = [entry for entry in entries if entry.item not in unticked]
    dropped = [entry for entry in entries if entry.item in unticked]
    return keep, dropped
