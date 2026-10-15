"""A run whose screen stops changing while the tool presses nothing is stuck.

Leo 2026-10-13, after a player's 活动每日战斗 stayed on the event page until
it was stopped: 「卡住卡個10秒就很怪了」「點擊沒反應 或者辨識不到卡住 那就回主頁
可以的話就重試沒辦法就下一步」「不要整個卡死」.  A daily task's frames are
watched: the same picture for FROZEN_SCREEN_SECONDS with no press or key from
the tool in between raises FrozenScreen; the run then goes home, tries once
more where that is safe, else ends as failed and 一键日常 goes on.

Game screens move (idle animation, particles, loading spinners), so a picture
that stays the same while the tool waits means nothing is coming.  Captures
further apart than FROZEN_GAP_SECONDS (a pause, a long sleep) start the count
over: only time spent looking counts.

Leo 2026-10-15 「我說的10秒是卡死 或者辨識不到」「注意其他等載入的地方不要只有
10秒」: a black loading screen is the game working, not stuck; it is watched
up to LOADING_MAX_SECONDS instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

import cv2
import numpy as np

from src.utils.wait_limits import LOADING_MAX_SECONDS, STUCK_SECONDS, is_loading_dark

# Leo 2026-10-14 「頂多等8秒到10秒」: was 15 s.  A slow-PC re-look
# (SLOW_PC_GRACE_SECONDS, 5 s) still fits.
FROZEN_SCREEN_SECONDS = STUCK_SECONDS
FROZEN_GAP_SECONDS = 5.0
THUMB_SIZE = (192, 108)
# A pixel this much brighter or darker counts as changed; this many changed
# pixels of the thumbnail make a changed screen (a small spinner is enough).
PIXEL_DIFF = 6
CHANGED_PIXELS = 4
# Presses in a row that left the screen exactly as it was (Leo 2026-10-14:
# the login's clear spot was pressed 29 times under a 恭喜晋级 page that only
# its 确认 closes).  From this many on, a known popup is looked for first.
INEFFECTIVE_PRESSES = 3


class FrozenScreen(Exception):
    """The screen did not change for FROZEN_SCREEN_SECONDS without a press.

    A task's own stuck check raises it too, with the reason as its message.
    """


def thumbnail(frame) -> np.ndarray | None:
    if frame is None or getattr(frame, "size", 0) == 0 or frame.ndim not in (2, 3):
        return None
    image = frame if frame.ndim == 2 else cv2.cvtColor(
        np.ascontiguousarray(frame[..., :3]), cv2.COLOR_BGR2GRAY
    )
    return cv2.resize(image, THUMB_SIZE, interpolation=cv2.INTER_AREA)


def changed(a: np.ndarray, b: np.ndarray) -> bool:
    if a.shape != b.shape:
        return True
    diff = cv2.absdiff(a, b)
    return int(np.count_nonzero(diff > PIXEL_DIFF)) >= CHANGED_PIXELS


@dataclass
class FrozenWatch:
    """The picture the still time started from, when, and the last look."""

    seconds: float = FROZEN_SCREEN_SECONDS
    picture: np.ndarray | None = None
    since: float = 0.0
    seen: float = 0.0
    paused: int = 0
    fired: bool = False
    last: np.ndarray | None = None
    at_last_press: np.ndarray | None = None
    last_point: tuple | None = None
    ineffective: int = 0

    def pressed(self, point: tuple | None = None) -> None:
        """The tool pressed or typed something: count from the next look.

        Also counts clicks in a row on the same spot whose screen before was
        the same as at the click before (nothing they did changed it)."""
        self.picture = None
        if (
            point is not None
            and point == self.last_point
            and self.last is not None
            and self.at_last_press is not None
            and not changed(self.last, self.at_last_press)
        ):
            self.ineffective += 1
        else:
            self.ineffective = 0
        self.at_last_press = self.last
        self.last_point = point

    def look(self, frame, now: float | None = None) -> None:
        """Raise FrozenScreen once the screen has been still long enough."""
        if self.paused:
            return
        if self.fired:
            raise FrozenScreen()
        now = monotonic() if now is None else now
        picture = thumbnail(frame)
        if picture is None:
            return
        self.last = picture
        if (
            self.picture is None
            or now - self.seen > FROZEN_GAP_SECONDS
            or changed(picture, self.picture)
        ):
            self.picture, self.since = picture, now
        self.seen = now
        # The black loading screen (a faint logo at most) may stand still
        # for longer than a stuck page (Leo 2026-10-15 「一定會超過10秒甚至15秒」).
        loading = is_loading_dark(picture[..., None])
        limit = max(self.seconds, LOADING_MAX_SECONDS) if loading else self.seconds
        if now - self.since >= limit:
            self.fired = True
            if loading:
                raise FrozenScreen(f"加载画面 {limit:.0f} 秒没有结束")
            raise FrozenScreen()
