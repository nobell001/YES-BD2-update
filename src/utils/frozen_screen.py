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
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

import cv2
import numpy as np

# Two slow-PC re-looks (SLOW_PC_GRACE_SECONDS, 5 s each) with their reads
# must fit, or a slow PC reading an empty page twice would count as stuck.
FROZEN_SCREEN_SECONDS = 15.0
FROZEN_GAP_SECONDS = 5.0
THUMB_SIZE = (192, 108)
# A pixel this much brighter or darker counts as changed; this many changed
# pixels of the thumbnail make a changed screen (a small spinner is enough).
PIXEL_DIFF = 6
CHANGED_PIXELS = 4


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

    def pressed(self) -> None:
        """The tool pressed or typed something: count from the next look."""
        self.picture = None

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
        if (
            self.picture is None
            or now - self.seen > FROZEN_GAP_SECONDS
            or changed(picture, self.picture)
        ):
            self.picture, self.since = picture, now
        self.seen = now
        if now - self.since >= self.seconds:
            self.fired = True
            raise FrozenScreen()
