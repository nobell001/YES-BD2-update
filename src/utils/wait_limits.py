"""No step waits longer than STUCK_SECONDS for a screen that does not come.

Leo 2026-10-14: 「還有沒有任何地方萬一卡住或者等待的地方要等很久例如20 30秒的
都把它改掉改成頂多等8秒到10秒」「卡住了按按鈕也返回不回去或者說一直沒有識別到
那就按esc 而且要跟用戶說明是哪裡卡住觸發了這個」.

Every wait for a page, a dialog, a loading screen to end or a result to show
gives up after at most STUCK_SECONDS.  Only waits whose screen keeps moving
on its own because the game is working (a battle being fought, an auto-walk)
may run longer, and those still stop once nothing changes for STUCK_SECONDS.
Waits read from the saved settings go through ``capped`` too: an older
config may still hold the old 20-35 s values.
"""

from __future__ import annotations

STUCK_SECONDS = 10.0


def capped(seconds, limit: float = STUCK_SECONDS) -> float:
    """``seconds`` as a float, never above ``limit``."""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return limit
    return min(value, limit)


# Mean grey change (0-255, on a 1/8 thumbnail) between two looks that counts
# as the scene moving: a walk pans the whole field, idle sparkles and a
# blinking character stay well under it.
SCENE_MOVE_MIN_DIFF = 3.0


def _thumb(frame):
    if frame is None or getattr(frame, "size", 0) == 0 or getattr(frame, "ndim", 0) < 2:
        return None
    small = frame[::8, ::8]
    if small.ndim == 3:
        small = small[..., :3].mean(axis=2)
    return small.astype("float32")


class StillTimer:
    """How long the scene has stood still: a walk or a battle that keeps the
    screen moving is the game working; one that stopped moving is stuck."""

    def __init__(self, min_diff: float = SCENE_MOVE_MIN_DIFF):
        self.min_diff = min_diff
        self.picture = None
        self.since = None

    def reset(self) -> None:
        self.picture = None
        self.since = None

    def still_for(self, frame, now: float) -> float:
        """Seconds since the scene last moved, counting this look."""
        picture = _thumb(frame)
        if picture is None:  # nothing to compare: no sign of movement
            if self.since is None:
                self.since = now
            return now - self.since
        if (
            self.picture is None
            or self.picture.shape != picture.shape
            or float(abs(picture - self.picture).mean()) >= self.min_diff
        ):
            self.picture, self.since = picture, now
        return now - self.since
