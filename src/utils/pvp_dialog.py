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

from src.utils.ocr_numbers import pool_amount, within

MULTIPLIER_RANGE = (1, 40)

_MULTIPLIER = re.compile(r"(\d{1,2})\s*倍")
_BATTLE_COUNT = re.compile(r"自动战斗\s*(\d{1,3})\s*次")
_FREE_POOL = re.compile(r"(?<![\d,.])(\d{1,2})\s*[/／]\s*(\d{1,2})(?!\d)")


def parse_multiplier(text: object) -> int | None:
    match = _MULTIPLIER.search(str(text))
    return within(int(match.group(1)), *MULTIPLIER_RANGE) if match else None


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
    """Free cocktails a from 'a/40' in the top bar; the paid pool follows it.

    a may be above 40 ("50/40", player 2026-10-18: rewards pile free
    cocktails past the daily refill); 倍数 x 场数 stays capped at 40 anyway."""
    match = _FREE_POOL.search(str(text))
    if not match:
        return None
    return pool_amount(
        int(match.group(1)), int(match.group(2)), top_range=(1, 99), amount_max=99
    )


def free_cocktails_problem(text: object) -> str:
    """Why parse_free_cocktails gave nothing for ``text``, in the player's words."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return "右上角一个字都没读到"
    match = re.search(r"(\d+)\s*[/／]\s*(\d+)", raw)
    if not match:
        return f"右上角读到「{raw[:30]}」，里面没有「数字/40」"
    amount, top = match.group(1), match.group(2)
    if len(amount) > 2:
        # 273/40 (player v0.2.11 2026-10-24): left as is by Leo, said plainly.
        return (
            f"右上角读到 {amount}/{top}，免费鸡尾酒超过 99 个，"
            "工具只认得 99 个以内，为免读错不开打"
        )
    return f"右上角读到 {amount}/{top}，后面的上限不是正常的数字"


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


def step_moves(step: str, big_step: int) -> int:
    """How far one press of ``step`` moves the value."""
    return {"big_plus": big_step, "big_minus": -big_step, "plus": 1, "minus": -1}[step]


def steps_between(start: int, target: int, big_step: int) -> list[str]:
    """The presses that take the value from ``start`` to ``target``."""
    presses = []
    current = start
    while (step := adjust_step(current, target, big_step)) is not None:
        presses.append(step)
        current += step_moves(step, big_step)
    return presses
