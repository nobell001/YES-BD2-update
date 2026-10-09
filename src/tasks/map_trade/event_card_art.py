"""Event cartridges (活动游戏卡) told apart by their cover art on the quick bar.

The 活动游戏卡 tab lists the owned event cards left to right, 180 px apart
(1080p), numbered 1..n by position only: which card sits in which slot
depends on which time-limited cards the player owns, so the slot number
cannot name a card.  The art can (live 4K 2026-10-09): a card's own art
scores 1.00 at its slot, 0.87-0.88 when it is the card being played (dimmed,
"游戏中" over it), and any other card's art at most 0.45 there.

Templates are cut at 1080p from the middle of the art (between the "III"
mark and the pin, which players toggle), so they are matched on the bar
resized to 1080 rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from src.utils.image_utils import template_match_response

ART_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[3]
    / "recognition-assets"
    / "template-assets"
    / "quick_switch_cartridges"
)
ART_FILE = "event_cartridge_art_{:02d}.png"
# Shop numbering (data.py E1/E2/E3/E5/E7): the permanent event cards.
ART_NUMBERS = (1, 2, 3, 5, 7)
ART_SCALE_STEPS = (0.97, 1.0, 1.03)
# Rows of the 1080p client that hold the cartridges (art 925-1010).
ART_BAND_TOP_1080 = 895
ART_BAND_BOTTOM_1080 = 1050
# The template starts 30 px right of the cartridge's left edge (1080p).
ART_FROM_CARD_LEFT_1080 = 30.0
# The point handed on as the card's "badge": on the card's art, left of
# centre, at the height the story badges use, so the completion icons
# (card_status, offsets from the badge) fall on the ✦ / 💀 badges below.
BADGE_FROM_CARD_LEFT_1080 = 40.0
BADGE_Y_1080 = 936.0
BADGE_SIZE_1080 = 29
CARD_SPACING_1080 = 180.0
ART_MIN_SCORE = 0.70
ART_MIN_LEAD = 0.15


@dataclass(frozen=True)
class ArtMatch:
    number: int
    score: float
    # Template top-left in 1080p client pixels.
    left: float
    top: float

    @property
    def card_left(self) -> float:
        return self.left - ART_FROM_CARD_LEFT_1080

    @property
    def badge_center(self) -> tuple[float, float]:
        """The click / completion-icon anchor in 1080p client pixels."""
        return self.card_left + BADGE_FROM_CARD_LEFT_1080, BADGE_Y_1080


@dataclass(frozen=True)
class SlotCheck:
    ok: bool
    reason: str
    target: ArtMatch | None = None
    other: ArtMatch | None = None


@lru_cache(maxsize=None)
def _template(number: int) -> np.ndarray | None:
    path = ART_TEMPLATE_DIR / ART_FILE.format(number)
    if not path.is_file():
        return None
    return cv2.imread(str(path), cv2.IMREAD_COLOR)


@lru_cache(maxsize=64)
def _scaled_template(number: int, scale: float) -> np.ndarray | None:
    template = _template(number)
    if template is None:
        return None
    if scale == 1.0:
        return template
    return cv2.resize(
        template,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )


def _band_1080(frame: np.ndarray) -> np.ndarray:
    """The cartridge rows, resized so the client is 1080 pixels high."""

    height, width = frame.shape[:2]
    factor = 1080.0 / height
    top = int(ART_BAND_TOP_1080 / factor)
    bottom = int(np.ceil(ART_BAND_BOTTOM_1080 / factor))
    band = frame[top:bottom, :, :3]
    if factor != 1.0:
        band = cv2.resize(
            band,
            (round(width * factor), round((bottom - top) * factor)),
            interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC,
        )
    return band


def _best(
    band: np.ndarray,
    number: int,
    x_range: tuple[float, float] | None = None,
) -> ArtMatch | None:
    best: ArtMatch | None = None
    for step in ART_SCALE_STEPS:
        template = _scaled_template(number, step)
        if template is None:
            return None
        th, tw = template.shape[:2]
        left = 0
        right = band.shape[1]
        if x_range is not None:
            left = max(0, int(x_range[0]))
            right = min(band.shape[1], int(np.ceil(x_range[1])) + tw)
        region = band[:, left:right]
        if region.shape[0] < th or region.shape[1] < tw:
            continue
        response = template_match_response(region, template)
        _, score, _, location = cv2.minMaxLoc(response)
        if best is None or score > best.score:
            best = ArtMatch(
                number,
                float(score),
                float(left + location[0]),
                float(ART_BAND_TOP_1080 + location[1]),
            )
    return best


def find_card(frame: np.ndarray, target: int) -> SlotCheck:
    """The target's art anywhere on the bar, clearly ahead of every other
    event card's art at that spot."""

    if _template(target) is None:
        return SlotCheck(False, f"没有活动卡带{target}的图片")
    band = _band_1080(frame)
    target_match = _best(band, target)
    if target_match is None:
        return SlotCheck(False, f"活动卡带{target}的图片超出画面")
    if target_match.score < ART_MIN_SCORE:
        return SlotCheck(
            False,
            f"活动卡带{target}图片相似度{target_match.score:.3f}<{ART_MIN_SCORE:.2f}",
            target_match,
        )
    window = 0.3 * CARD_SPACING_1080
    x_range = (target_match.left - window, target_match.left + window)
    other: ArtMatch | None = None
    for number in ART_NUMBERS:
        if number == target:
            continue
        match = _best(band, number, x_range)
        if match is not None and (other is None or match.score > other.score):
            other = match
    if other is not None and target_match.score - other.score < ART_MIN_LEAD:
        return SlotCheck(
            False,
            (
                f"活动卡带{target}图片{target_match.score:.3f}没有明显赢过"
                f"活动卡带{other.number}的{other.score:.3f}"
            ),
            target_match,
            other,
        )
    return SlotCheck(True, "", target_match, other)
