"""Dismiss the characters that crowd around the player in a field after login.

Every day after login a group of characters with "!" balloons follows the
player around the field (箱庭).  They stand on the 镜中之战 stage and in the way
of the 女神像 walk.  While they are there the field's F button shows the same
"!" speech-bubble icon; one press of that button sends them all away (Leo,
2026-10-03, 4K screenshot in the PVP hub).

The icon is the existing ``image/green/tanhaoGE.png`` template.  On Leo's
frame it scores 0.99 (pixel 0.94) at 1080p, 2K and 4K inside the F-slot box
below.  The PVP hub used the same template before, but its box was written in
1080p numbers and then converted as if it were 1440p, so it searched the wrong
place and never pressed the button.

Rule 「认不准就不按」: press only after two frames in a row show the icon at
the same place, then confirm on two frames that it is gone.

The crowd shows up once a game day, in whichever cartridge comes first (Leo,
2026-10-03), so after one successful press the rest of the day skips the look.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic
from typing import Callable

import numpy as np

from src.utils.game_day import DAILY_REFRESH_HOUR, GAME_TZ
from src.utils.vision_models import TemplateSpec

# F slot of the field HUD, 1080p reference (x, y, width, height).  The button
# icon sits at about (1385-1436, 869-897) at 1080p.
FIELD_TALK_ICON_ROI = (1376, 862, 66, 51)
FIELD_TALK_ICON_TEMPLATE = TemplateSpec(
    name="field_talk_icon",
    file_name="image/green/tanhaoGE.png",
    threshold_key="跟随角色按钮阈值",
    default_threshold=0.80,
    roi=FIELD_TALK_ICON_ROI,
    green_mask=True,
    scale_ratios=(0.90, 0.925, 0.95, 0.975, 1.0),
    min_pixel_score=0.75,
)
FOLLOWERS_ABSENT = "absent"
FOLLOWERS_DISMISSED = "dismissed"
FOLLOWERS_STILL_VISIBLE = "still_visible"
FOLLOWERS_DONE_TODAY = "done_today"

# Game day of the last successful press; kept for the life of the tool.
_dismissed_game_day: str | None = None


def _game_day(now: datetime | None = None) -> str:
    local = (now or datetime.now(GAME_TZ)).astimezone(GAME_TZ)
    return (local - timedelta(hours=DAILY_REFRESH_HOUR)).date().isoformat()


def dismissed_today(now: datetime | None = None) -> bool:
    return _dismissed_game_day == _game_day(now)


def mark_dismissed(now: datetime | None = None) -> None:
    global _dismissed_game_day
    _dismissed_game_day = _game_day(now)


def reset_dismissed() -> None:
    global _dismissed_game_day
    _dismissed_game_day = None


def dismiss_once_per_run(navigator) -> None:
    """Map/trade navigators: look once per run, right after a cartridge loads."""
    if getattr(navigator, "_field_followers_checked", False):
        return
    navigator._field_followers_checked = True
    dismiss = getattr(navigator.task, "dismiss_field_followers", None)
    if callable(dismiss):
        dismiss()


def is_exclamation_glyph(box: np.ndarray) -> bool:
    """True when the bubble in ``box`` (the matched template area, BGR) holds
    the "!" and not another F-button glyph.

    The template's green mask keeps only the bubble outline, so the talk
    "…" (beside 艾琳) and the teleport-circle hand also passed (cp3 at 4K,
    2026-10-04: 0.974/0.907 and 0.948/0.851) and the press opened the talk or
    the 移动魔法阵.  The "!" is a narrow upright bar (6x18 of the 53x43
    template); the dots are wide and the hand is a square blob.
    """

    if box is None or box.size == 0 or box.ndim != 3:
        return False
    height, width = box.shape[:2]
    inner = box[int(height * 0.2) : int(height * 0.8), int(width * 0.35) : int(width * 0.65)]
    if inner.size == 0:
        return False
    gray = inner.astype(np.float32).mean(axis=2)
    dark = gray < np.percentile(gray, 90) * 0.45
    ys, xs = np.nonzero(dark)
    if len(xs) < 4:
        return False
    glyph_width = xs.max() - xs.min() + 1
    glyph_height = ys.max() - ys.min() + 1
    return glyph_height >= height * 0.25 and glyph_width / glyph_height <= 0.6


@dataclass(frozen=True)
class TalkIconSighting:
    """One frame's look at the F slot; ``center`` is relative (0-1)."""

    passed: bool
    score: float = -1.0
    center: tuple[float, float] | None = None


def same_place(first: TalkIconSighting, second: TalkIconSighting, tolerance=0.01) -> bool:
    """Both sightings passed at (almost) the same point."""
    if not (first.passed and second.passed and first.center and second.center):
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(first.center, second.center))


def dismiss_field_followers(
    observe: Callable[[], TalkIconSighting],
    click: Callable[[float, float], None],
    sleep: Callable[[float], None],
    *,
    appear_seconds: float = 3.0,
    interval: float = 0.35,
    settle_seconds: float = 1.5,
    max_clicks: int = 2,
    clock: Callable[[], float] = monotonic,
) -> str:
    """Press the F "!" button until the followers are gone.

    Waits up to ``appear_seconds`` for the icon (the crowd can arrive a moment
    after the field loads).  Returns ``FOLLOWERS_ABSENT`` when the icon never
    showed on two frames in a row, ``FOLLOWERS_DISMISSED`` when a press made it
    go away, or ``FOLLOWERS_STILL_VISIBLE`` after ``max_clicks`` presses.
    """
    clicks = 0
    deadline = clock() + max(0.0, appear_seconds)
    previous = None
    while True:
        sighting = observe()
        if previous is not None and same_place(previous, sighting):
            click(*sighting.center)
            clicks += 1
            sleep(settle_seconds)
            if _gone_on_two_frames(observe, sleep, interval):
                return FOLLOWERS_DISMISSED
            if clicks >= max_clicks:
                return FOLLOWERS_STILL_VISIBLE
            previous = None
            deadline = clock() + max(0.0, appear_seconds)
            continue
        previous = sighting if sighting.passed else None
        if clock() >= deadline:
            # After a press, an icon that stays away counts as gone.
            return FOLLOWERS_DISMISSED if clicks else FOLLOWERS_ABSENT
        sleep(interval)


def _gone_on_two_frames(observe, sleep, interval: float) -> bool:
    if observe().passed:
        return False
    sleep(interval)
    return not observe().passed
