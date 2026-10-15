"""Plausible ranges for numbers read by OCR (Leo 2026-10-14: 「不要再有這種讀5位數的了
你應該給每個數值設合理的範圍」).

A value outside its range is refused, never guessed: the caller reads it
again or stops without spending anything.
"""

from __future__ import annotations


def pool_amount(amount: int, top: int, *, top_range: tuple[int, int] = (1, 999)) -> int | None:
    """``amount`` of an "amount/top" pool, or None when it cannot be real.

    Nothing is guessed (Leo 2026-10-14: a safe range, no repairs that could
    misjudge): an amount above its top ("124/90") is refused, and the caller
    reads again or stops without spending."""
    if not top_range[0] <= top <= top_range[1] or not 0 <= amount <= top:
        return None
    return amount


def within(value: int | None, low: int, high: int) -> int | None:
    """``value`` when it lies in [low, high], else None."""
    if value is None or not low <= value <= high:
        return None
    return value
