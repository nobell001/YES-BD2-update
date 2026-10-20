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

# Leo 2026-10-15 「我說的10秒是卡死 或者辨識不到」「一定會超過10秒甚至15秒」:
# a loading screen or a picture that keeps moving is the game working and
# does not count towards STUCK_SECONDS; it is still not waited for past this.
# Leo 2026-10-20 「改成45秒」 (was 30 s: a 1080p player's 「MIRROR WARS」
# loading screen was still at 94% when the wait gave up).
LOADING_MAX_SECONDS = 45.0

# Leo 2026-10-19 「可以20秒」 (after the 2K clone's bright 「FANTASIA SQUARE」
# splash was cut at 10 s): the 10 s is for 判断不出来 / 按了没反应 / 不知道要做
# 什么, not for loading.  A screen that a press changed and that then stands
# still is loading, whatever it looks like: waited for up to this long.  Only a
# screen the press left as it was counts as stuck after STUCK_SECONDS.
CHANGED_LOAD_SECONDS = 20.0

# 95th-percentile brightness under which a frame is the black loading screen
# (2K 10-15: 22 while loading story cartridge 1).
LOADING_DARK_P95 = 40


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


def scene(frame):
    """A small picture of ``frame`` for ``scene_moved`` (None when empty)."""
    return _thumb(frame)


def scene_moved(before, picture, min_diff: float = SCENE_MOVE_MIN_DIFF) -> bool:
    """``picture`` differs from ``before`` as much as a moving scene does."""
    if before is None or picture is None:
        return False
    if before.shape != picture.shape:
        return True
    return float(abs(picture.astype("float32") - before.astype("float32")).mean()) >= min_diff


def scene_at_press(task):
    """The screen the task saw right before its last press (None if unknown)."""
    return getattr(task, "_scene_at_press", None)


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


def is_loading_dark(frame) -> bool:
    """The black loading screen; an all-zero frame is a blank test frame."""
    try:
        if frame is None or not frame.any():
            return False
        import numpy as np

        return float(np.percentile(frame[..., :3], 95)) < LOADING_DARK_P95
    except (AttributeError, TypeError, IndexError, ValueError):
        return False


# Reads a frame and says what marks it as a loading screen ("94%", "加载"),
# "" when nothing does.  The running task sets it (BaseBD2Task.capture_frame)
# so every wait asks it before giving up, without an OCR on every look.
_loading_reader = None


def set_loading_reader(reader) -> None:
    global _loading_reader
    _loading_reader = reader


def read_loading_sign(frame) -> str:
    reader = _loading_reader
    if reader is None or frame is None:
        return ""
    try:
        return str(reader(frame) or "")
    except Exception as exc:
        # The task being stopped must still stop the wait.
        if type(exc).__name__ in ("TaskDisabledException", "FinishedException"):
            raise
        return ""


class ProgressWait:
    """A wait that ends after STUCK_SECONDS without progress, or after
    LOADING_MAX_SECONDS in all.  A loading screen or a moving picture is
    progress; a still screen that is not the target is not (卡死／辨識不到).

    With ``before`` (the screen right before the press, ``scene_at_press``),
    a still screen that the press changed is loading and stops only after
    CHANGED_LOAD_SECONDS; one the press left as it was (按了没反应) after
    ``stuck``."""

    def __init__(
        self,
        now: float,
        stuck: float = STUCK_SECONDS,
        cap: float = LOADING_MAX_SECONDS,
        before=None,
    ):
        self.still = StillTimer()
        self.stuck = stuck
        self.cap_at = now + cap
        self.before = before

    def over(self, frame, now: float, loading: bool = False) -> bool:
        if now >= self.cap_at:
            return True
        if loading:
            self.still.reset()
            return False
        limit = self.stuck
        if self.before is not None and scene_moved(self.before, _thumb(frame)):
            limit = max(limit, CHANGED_LOAD_SECONDS)
        if self.still.still_for(frame, now) < limit:
            return False
        # Leo 2026-10-20 「10秒限制 不該在這種時候」: a still screen that shows
        # the loading ring's percent or a loading word is loading, not stuck.
        if read_loading_sign(frame):
            self.still.reset()
            return False
        return True


def load_wait(now: float, seconds, before=None) -> ProgressWait:
    """A wait for a page that comes after a loading screen (Leo 2026-10-15
    「你單純等載入怎麼可以改成只等10秒」): ``seconds`` (a saved setting) or
    LOADING_MAX_SECONDS in all, whichever is longer; it gives up sooner only
    on a screen that stands still, not loading, for STUCK_SECONDS (or the
    shorter ``seconds``), or CHANGED_LOAD_SECONDS when ``before`` shows the
    press changed the screen."""
    seconds = max(0.0, float(seconds))
    return ProgressWait(
        now,
        stuck=min(seconds, STUCK_SECONDS),
        cap=max(seconds, LOADING_MAX_SECONDS),
        before=before,
    )
