"""Parsing and stepping helpers for the mirror-battle auto-battle dialog.

Layout observed 2026-09-26 (简体 client, 1920x1080 reference): the dialog
shows "N倍 ⚙" (per-battle cocktail multiplier, 1~40, set in a sub-dialog with
MIN / -5 / +5 / MAX and -/+), the 仅使用免费鲜血鸡尾酒 switch, and the battle
count "自动战斗N次" with MIN / -10 / +10 / MAX and -/+.  The start button
reads "战斗开始 🍹C" where C is the per-battle cost (equal to the multiplier,
live 2026-09-26; ``PVPTask._verify_free_cost`` relies on it); the top bar
shows the free cocktails as "36/40" followed by the paid pool.
"""

from __future__ import annotations

import re

MULTIPLIER_RANGE = (1, 40)

_MULTIPLIER = re.compile(r"(\d{1,2})\s*倍")
_BATTLE_COUNT = re.compile(r"自动战斗\s*(\d{1,3})\s*次")
_FREE_POOL = re.compile(r"(?<![\d,.])(\d{1,2})\s*[/／]\s*(\d{1,2})(?!\d)")


def parse_multiplier(text: object) -> int | None:
    match = _MULTIPLIER.search(str(text))
    return int(match.group(1)) if match else None


def parse_battle_count(text: object) -> int | None:
    match = _BATTLE_COUNT.search(str(text).replace(" ", ""))
    return int(match.group(1)) if match else None


def parse_start_cost(text: object) -> int | None:
    """Cost C from the start button text '战斗开始🍹C' (icon may OCR as noise)."""
    raw = str(text)
    index = raw.find("战斗开始")
    if index < 0:
        return None
    digits = re.findall(r"\d+", raw[index + len("战斗开始") :])
    return int(digits[-1]) if digits else None


def parse_free_cocktails(text: object) -> int | None:
    """Free cocktails a from 'a/40' in the top bar; the paid pool follows it."""
    match = _FREE_POOL.search(str(text))
    if not match or int(match.group(2)) <= 0:
        return None
    return int(match.group(1))


def adjust_step(current: int, target: int, big_step: int) -> str | None:
    """Button to press next: big_plus / big_minus / plus / minus (None: done)."""
    difference = target - current
    if difference == 0:
        return None
    if difference >= big_step:
        return "big_plus"
    if difference <= -big_step:
        return "big_minus"
    return "plus" if difference > 0 else "minus"
