"""Classify freshly pulled equipment as junk (enhance to +7 and dismantle).

User rule (2026-09-26): keep only UR exclusive gear of 5★ characters; every
R and SR item, and UR exclusive gear of 3★/4★ characters, is junk.  Owner
stars come from assets/gear/exclusive_gear.json (built from the community
database browndust2-db.souseha.com: exclusive item -> character -> star).

Only gear carrying the new-item badge is considered.  Anything uncertain is
kept: rarity OCR and label colour must agree, a UR not found in the table is
kept, and equipped, locked or enhanced items are never touched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

EXCLUSIVE_TABLE = Path(__file__).resolve().parents[2] / "assets" / "gear" / "exclusive_gear.json"

# OCR sometimes reads the gradient "U" of UR as J/I/L (seen live: "JR").
_UR_TOKENS = {"UR", "JR", "IR", "LR", "UF"}


@dataclass(frozen=True)
class GearItem:
    name: str
    rarity: str | None
    equipped: bool
    locked: bool
    enhanced: bool


def load_exclusive_stars(path: Path = EXCLUSIVE_TABLE) -> dict[str, int]:
    """Map exclusive item names (Simplified and Traditional) to owner stars."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    stars: dict[str, int] = {}
    for row in data["items"]:
        for key in ("zh_cn", "zh_tw"):
            if row.get(key):
                stars[normalize_name(row[key])] = int(row["star"])
    return stars


def normalize_name(name: str) -> str:
    return re.sub(r"[\s·•.。…]", "", str(name))


def ocr_rarity(token: str) -> str | None:
    text = re.sub(r"[^A-Za-z0-9]", "", str(token)).upper()
    if text in _UR_TOKENS:
        return "UR"
    if text in {"SR", "5R"}:
        return "SR"
    if text == "R":
        return "R"
    if text == "N":
        return "N"
    return None


def colour_rarity(label_bgr: np.ndarray) -> str | None:
    """Rarity from the label colour: R blue, SR purple, UR rainbow gradient.

    Live 2026-09-26: R labels had one hue (median 106, spread ~5); UR labels
    spanned the spectrum (spread ~35).
    """
    if label_bgr is None or label_bgr.size == 0:
        return None
    hsv = cv2.cvtColor(label_bgr[:, :, :3], cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    hues = hue[(saturation > 90) & (value > 120)]
    if hues.size < 80:
        return None
    if float(hues.std()) > 20.0:
        return "UR"
    median = float(np.median(hues))
    if 90 <= median < 120:
        return "R"
    if 120 <= median <= 165:
        return "SR"
    return None


def label_hues(label_bgr: np.ndarray) -> np.ndarray:
    """Hues (OpenCV 0-179) of a rarity label's saturated, bright pixels.

    New items carry a yellow "!" badge right beside the label (60% of the
    coloured pixels of a live R label, 2026-09-27) and gold item art bleeds
    in too; no rarity letter is yellow, so yellow is left out.
    """
    if label_bgr is None or label_bgr.size == 0:
        return np.empty(0, np.uint8)
    hsv = cv2.cvtColor(label_bgr[:, :, :3], cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    hues = hue[(saturation > 90) & (value > 120)]
    return hues[(hues < 10) | (hues > 34)]


def hue_share(hues: np.ndarray, low: int, high: int) -> float:
    return float(((hues >= low) & (hues <= high)).mean()) if hues.size else 0.0


def only_blue(hues: np.ndarray, trace: float) -> bool:
    """The R label's cyan-to-blue alone: at most a trace of green (N and UR
    labels), purple (SR, UR) or red (UR).

    Live 2K 2026-09-30 (珍藏集 labels): R letters spanned hue 90-109, so the
    cyan end fell in the old 35-95 "green" band and every R was left unsure
    (full-res crops even looked UR); UR labels there were 20-23% green
    (35-84) and 40% purple, N labels are green.
    """
    return (
        hues.size > 0
        and hue_share(hues, 35, 84) <= trace
        and hue_share(hues, 125, 165) <= trace
        and float(((hues < 10) | (hues > 165)).mean()) <= trace
    )


def grid_label_rarity(label_bgr: np.ndarray) -> str | None:
    """R / SR / UR from a bag grid cell's rarity label, or None when unsure.

    The grid crop also catches the item art (a golden gauntlet made an SR
    label look like a rainbow UR to ``colour_rarity``).  UR letters always
    carry green-cyan (hue 35-95: 25-34% of the coloured pixels, live 4K
    2026-09-27); SR letters have none and are purple (72%); R letters are
    cyan to blue only.  Anything in between is left unsure so the detail
    gets opened.
    """

    hues = label_hues(label_bgr)
    if hues.size < 60:
        return None
    if only_blue(hues, GRID_R_TRACE_MAX):
        return "R"
    green = hue_share(hues, 35, 95)
    if green >= GRID_UR_GREEN_MIN:
        return "UR"
    if green > GRID_NO_GREEN_MAX:
        return None
    if hue_share(hues, 125, 165) >= GRID_MAIN_HUE_MIN:
        return "SR"
    if hue_share(hues, 96, 124) >= GRID_MAIN_HUE_MIN:
        return "R"
    return None


GRID_UR_GREEN_MIN = 0.15
GRID_NO_GREEN_MAX = 0.03
GRID_MAIN_HUE_MIN = 0.5
GRID_R_TRACE_MAX = 0.05
# "Certain" colour: enough to skip the label OCR when that cannot read the tiny
# italic letters (2K, 2026-09-30).  Every UR label had 20-45 % green.
GRID_CERTAIN_GREEN_MAX = 0.02
GRID_CERTAIN_MAIN_MIN = 0.85
GRID_CERTAIN_MIN_PIXELS = 80


def grid_label_colour_certain(label_bgr: np.ndarray, rarity: str) -> bool:
    """True when the label is unmistakably R (cyan-blue alone) or SR (purple,
    no green at all): every UR label carries green and purple."""

    if rarity not in ("R", "SR"):
        return False
    hues = label_hues(label_bgr)
    if hues.size < GRID_CERTAIN_MIN_PIXELS:
        return False
    if rarity == "R":
        return only_blue(hues, GRID_CERTAIN_GREEN_MAX)
    if hue_share(hues, 35, 95) > GRID_CERTAIN_GREEN_MAX:
        return False
    return hue_share(hues, 125, 165) >= GRID_CERTAIN_MAIN_MIN


def label_text_looks_ur(text: str) -> bool:
    """The label OCR shows a U (or its usual misreads before an R)."""
    letters = re.sub(r"[^A-Za-z]", "", str(text)).upper()
    return "U" in letters or letters.startswith(("JR", "IR", "LR"))


def agreed_rarity(token: str, label_bgr: np.ndarray) -> str | None:
    by_text = ocr_rarity(token)
    by_colour = colour_rarity(label_bgr)
    return by_text if by_text is not None and by_text == by_colour else None


def classify(
    item: GearItem,
    exclusive_stars: dict[str, int],
    *,
    dismantle_r_sr: bool = True,
    dismantle_low_star_ur: bool = True,
) -> tuple[bool, str]:
    """Return (is_junk, reason)."""
    if item.equipped:
        return False, "穿戴中"
    if item.locked:
        return False, "已上锁"
    if item.enhanced:
        return False, "已强化"
    if item.rarity is None:
        return False, "品质无法确认"
    if item.rarity in {"R", "SR"}:
        return (True, f"{item.rarity}") if dismantle_r_sr else (False, "未开启分解R/SR")
    if item.rarity == "UR":
        star = exclusive_stars.get(normalize_name(item.name))
        if star is None:
            return False, "UR 不在专用装备表中"
        if star >= 5:
            return False, "5★角色UR专用"
        if not dismantle_low_star_ur:
            return False, "未开启分解3★/4★专用UR"
        return True, f"{star}★角色UR专用"
    return False, f"{item.rarity} 不在规则内"


# The yellow "!" badge at a cell's top-right marks gear acquired since the bag
# was last opened (user, 2026-09-26): every freshly pulled item carries it
# when the daily automation opens the bag.  Offsets from the cell centre in
# 1920x1080 reference; live: 29% orange in the marked cell, 0% elsewhere.
NEW_MARKER_BOX = (42, -68, 28, 26)
NEW_MARKER_MIN_RATIO = 0.12


def new_marker_ratio(frame_1080: np.ndarray, centre: tuple[int, int]) -> float:
    dx, dy, w, h = NEW_MARKER_BOX
    x, y = centre[0] + dx, centre[1] + dy
    patch = frame_1080[max(0, y) : y + h, max(0, x) : x + w]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch[:, :, :3], cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    orange = (hue >= 10) & (hue <= 25) & (saturation >= 170) & (value >= 200)
    return float(orange.mean())


def leading_new_cells(
    frame_1080: np.ndarray,
    columns: tuple[int, ...],
    rows: tuple[int, ...],
    cap: int,
) -> list[tuple[int, int]]:
    """Cells marked new, read from the top-left in acquisition order.

    With the bag sorted newest first the new items are contiguous at the
    top; stop at the first unmarked cell so nothing older is ever included.
    """
    cells: list[tuple[int, int]] = []
    for row, cy in enumerate(rows):
        for column, cx in enumerate(columns):
            if len(cells) >= cap:
                return cells
            if new_marker_ratio(frame_1080, (cx, cy)) < NEW_MARKER_MIN_RATIO:
                return cells
            cells.append((row, column))
    return cells
