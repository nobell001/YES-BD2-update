"""Match an OCR'd unit name against the names the fight can contain.

The name a selected unit shows top-left is the unit's identity, so a
misread must never become a different unit.  The OCR text is snapped to
the closest known name (the saved fight's units, or a character list)
only when that choice is clear; otherwise the answer is None and the
caller stops instead of guessing.

Replay only ever snaps to the saved fight's own names.  Recording also
has to take names no list has yet: new costumes and characters come out
often and are often the ones used for the current 魔獸, so the character
database may lack them (Leo, 2026-09-30).  ``settle_name`` then takes the
name as the game shows it, once repeated reads agree.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

from src.utils.chinese import to_simplified

_NOISE = str.maketrans("", "", " \t\r\n·•.。:：,，'\"“”‘’-_|")

MIN_RATIO = 0.75
MIN_MARGIN = 0.1
READS_TO_AGREE = 2

_LOOKS_LIKE_A_NAME = re.compile(r"[\u4e00-\u9fff]{1,12}")  # 鲁 is a whole name


def normalize_name(text: object) -> str:
    return to_simplified(str(text)).translate(_NOISE)


def snap_name(
    text: object,
    known: Iterable[str],
    *,
    min_ratio: float = MIN_RATIO,
    min_margin: float = MIN_MARGIN,
    inside: bool = True,
) -> str | None:
    """The known name ``text`` stands for, or None when unsure.

    Exact matches win.  Otherwise, with ``inside``, a known name found
    inside the text (OCR may pick up a costume title next to the name) is
    taken when only one fits, the longest if one contains another.  Last,
    the most similar name is taken if it is similar enough and clearly
    ahead of the next.
    """
    read = normalize_name(text)
    if not read:
        return None
    names = {normalize_name(name): name for name in known}
    names.pop("", None)
    if read in names:
        return names[read]

    found = [name for name in names if name in read] if inside else []
    if found:
        longest = max(len(name) for name in found)
        best = [name for name in found if len(name) == longest]
        return names[best[0]] if len(best) == 1 else None

    scored = sorted(
        ((SequenceMatcher(None, read, name).ratio(), name) for name in names), reverse=True
    )
    if not scored or scored[0][0] < min_ratio:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < min_margin:
        return None
    return names[scored[0][1]]


def settle_name(
    reads: Iterable[object], known: Iterable[str], *, agree: int = READS_TO_AGREE
) -> str | None:
    """The unit's name from successive OCR reads of its name line.

    ``reads`` may be lazy (each item a fresh capture); it is consumed only
    until the name is settled.  A read that snaps to a known name settles
    it at once, but not by being found inside the text: with a whole
    character list, a new name like 鲁卡斯 would become 鲁.  A name no
    list has is taken as the game shows it when ``agree`` reads in a row
    give the same Chinese text, so a flicker or a half-drawn frame can't
    invent a unit.  The reads must hold the name line only: a costume title
    next to it changes with the costume every turn and would make one unit
    look like several.  None when unsure.
    """
    known = list(known)
    previous, streak = "", 0
    for text in reads:
        snapped = snap_name(text, known, inside=False)
        if snapped is not None:
            return snapped
        name = normalize_name(text)
        if not _LOOKS_LIKE_A_NAME.fullmatch(name):
            previous, streak = "", 0
            continue
        streak = streak + 1 if name == previous else 1
        previous = name
        if streak >= agree:
            return name
    return None
