"""Game sizes the tool is built and tested for, and a notice on others.

A player on 2026-10-09 ran the game in a smaller window: the tool started
anyway (ok-script accepts any 16:9 size from 1280x720 up), the shrunken
cartridge numbers and buttons were never recognised, and 跑图 slid the
cartridge bar and clicked the map's back button for minutes on end.  Leo
(2026-10-09) chose 「提醒但照跑」: say so and how to fix it, then run anyway.
"""

from __future__ import annotations

import time

SUPPORTED_SIZES = ((1920, 1080), (2560, 1440), (3840, 2160))
# A window sized by hand can be a pixel or two off.
TOLERANCE = 2
# One notice is enough while the batch's children and the scheduler's
# retries each start on the same window.
NOTIFY_GAP_SECONDS = 600.0

_last_notified = {"at": 0.0}


def supported(width: int, height: int) -> bool:
    return any(
        abs(int(width) - w) <= TOLERANCE and abs(int(height) - h) <= TOLERANCE
        for w, h in SUPPORTED_SIZES
    )


def current_size(executor) -> tuple[int, int] | None:
    """The game's client size, None while no game window is known."""
    manager = getattr(executor, "device_manager", None)
    # The captured picture's size first: what every recognition works on
    # (ok's own 16:9 check reads the same).
    method = getattr(manager, "capture_method", None)
    try:
        connected = method is not None and (
            not hasattr(method, "connected") or method.connected()
        )
    except Exception:
        connected = False
    if connected:
        width = int(getattr(method, "width", 0) or 0)
        height = int(getattr(method, "height", 0) or 0)
        if width > 0 and height > 0:
            return width, height
    window = getattr(manager, "hwnd_window", None)
    if window is None or not getattr(window, "exists", False):
        return None
    width = int(getattr(window, "width", 0) or 0)
    height = int(getattr(window, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    return width, height


def unsupported_size(executor) -> tuple[int, int] | None:
    """The game's size when it is one the tool does not support, else None."""
    size = current_size(executor)
    if size is None or supported(*size):
        return None
    return size


def message(size: tuple[int, int]) -> str:
    return (
        f"游戏画面是 {size[0]}×{size[1]}，工具只在 1920×1080、2560×1440、3840×2160 测过，"
        "其他大小可能认不准、卡住。建议在首页「游戏视窗大小」按「调整」，"
        "或在游戏设置里改分辨率。这次照常执行。"
    )


def should_notify(now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    if _last_notified["at"] and now - _last_notified["at"] < NOTIFY_GAP_SECONDS:
        return False
    _last_notified["at"] = now
    return True


NOTICE_KEY = "画面大小提醒"


def warn_if_unsupported(task) -> bool:
    """Tell the user when the game is at a size the tool was not tested on.

    True when it is; the run goes on either way.
    """
    size = unsupported_size(getattr(task, "executor", None))
    if size is None:
        return False
    text = message(size)
    task.info_set(NOTICE_KEY, text)
    task.log_warning(text, notify=should_notify())
    return True
