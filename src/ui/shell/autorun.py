"""打开工具就自动跑一键日常：玩家在首页自己勾（默认不勾）。

Leo 2026-10-09（玩家建议 YES-BD2 issue #1：配合 Windows 任务计划程序每天
开工具跑日常）：之前拿掉的「打开就跑」改成玩家自己在首页选；同一个勾
也打开启动器的「自动启动」，点启动器就会一路跑到日常。勾了之后，
工具打开几秒后照「跑没跑完的」开始（不跳确认视窗，倒数就是确认），今天（周常是本周）做完的不再跑；
游戏没开会自己打开并登录，不再问。都做完了、已经在跑、或在桌面分身里
（由外面的工具交派）就不跑。
"""

from __future__ import annotations

import time

from ok import Logger

from src.ui.shell import data

logger = Logger.get_logger(__name__)

CONFIG_KEY = "打开工具时自动开始"
DELAY_MS = 5000
# 定时启动 does not give up when the tool is not ready yet (still opening,
# another task running): it looks again every few seconds, and only after
# this long says it could not start (Leo 2026-10-22 「有沒有確保 打開程式
# 就是直接開始日常」).
WAIT_RETRY_MS = 10_000
WAIT_MINUTES = 30
WAIT_REASONS = ("busy", "running in the clone")
BUSY_NOTE = "等了 {m} 分钟，工具一直在忙（有别的任务在跑），一键日常没能开始，这次没有跑。"

# When the scheduled start is due (首页 counts down to it, Leo 2026-10-09:
# players must see that it is about to run); None when nothing is pending.
_due: float | None = None
# A scheduled start waiting for the tool to be free: since when.
_waiting_since: float | None = None


def enabled() -> bool:
    batch = data.task_by_name(data.DAILY_BATCH)
    return bool((getattr(batch, "config", None) or {}).get(CONFIG_KEY, False))


def set_enabled(on: bool) -> None:
    batch = data.task_by_name(data.DAILY_BATCH)
    if batch is not None:
        batch.config[CONFIG_KEY] = bool(on)
    set_launcher_auto_start(on)


def set_launcher_auto_start(on: bool) -> bool:
    """The launcher's own 「自动启动」: it opens the tool 10 s after it starts.

    Leo 2026-10-09: opening the launcher should go all the way to 一键日常,
    so the one box on 首页 sets both.  Only in installs the launcher made.
    """
    try:
        import pyappify

        if not pyappify.get_app_json_path():
            return False
        pyappify.set_auto_start(bool(on))
        return True
    except Exception as exc:
        logger.warning(f"auto-run on open: launcher auto start not changed ({exc})")
        return False


def remaining() -> list:
    batch = data.task_by_name(data.DAILY_BATCH)
    return [
        child
        for child in data.batch_children(batch)
        if child.included and not data.child_done(child)
    ]


def should_start(in_clone: bool, scheduled: bool = False) -> str | None:
    """None when it should start now, else why not (for the log).

    ``scheduled``: 定时启动 asked for it, the 首页 box does not matter.
    """
    if in_clone:
        return "in the clone"
    if not scheduled and not enabled():
        return "off"
    if not data.executor():
        return "busy"
    if data.busy():
        if scheduled and data.current_task() is data.task_by_name(data.DAILY_BATCH):
            return "already running"
        return "busy"
    if not remaining():
        return "nothing left today"
    return None


def maybe_start(scheduled: bool = False) -> bool:
    """Start 一键日常 (only what is left) when the player ticked it.

    ``scheduled``: 定时启动 asked; a start that cannot happen (lock screen,
    not started) leaves a report that says why (schedule_ui).
    """
    from src.ui.shell import actions, clone_flow, schedule_ui

    reason = _why_not(scheduled)
    if reason is not None:
        logger.info(f"auto-run on open: not started ({reason})")
        return False
    if scheduled and not schedule_ui.before_start():
        return False
    from src.tasks.DailyBatchTask import RUN_MODE_INCOMPLETE

    if not actions.game_running():
        clone_flow.log_in_this_run()  # opens the game and logs in, without asking
    logger.info("auto-run on open: starting 一键完成日常 (only what is left)")
    # No window: nothing to ask, and the game opens on its own if it is closed.
    started = actions.start(data.task_by_name(data.DAILY_BATCH), None, RUN_MODE_INCOMPLETE)
    if scheduled:
        schedule_ui.after_start(started)
    return started


def _why_not(scheduled: bool) -> str | None:
    from src.ui.shell import clone_flow
    from src.utils.clone_desktop import in_clone

    reason = should_start(in_clone(), scheduled)
    if reason is None and clone_flow.busy_in_clone():
        reason = "running in the clone"
    return reason


def schedule(delay_ms: int = DELAY_MS, scheduled: bool = False) -> bool:
    """Count down on 首页, then start (unless the player cancels).

    ``scheduled``: a tool that is not free yet is waited for (:func:`_wait`).
    """
    if _due is not None or _waiting_since is not None:
        return False  # already counting down or waiting
    reason = _why_not(scheduled)
    if scheduled and reason in WAIT_REASONS:
        _wait(delay_ms)
        return True
    if reason is not None:
        logger.info(f"auto-run on open: not scheduled ({reason})")
        return False
    _count_down(delay_ms, scheduled)
    return True


def _wait(delay_ms: int) -> None:
    """Look again in a moment; after :data:`WAIT_MINUTES`, say why not."""
    global _waiting_since
    from PySide6.QtCore import QTimer

    from src.ui.shell.safe import guarded

    if _waiting_since is None:
        _waiting_since = time.time()
        logger.info("scheduled start: the tool is not free yet, waiting")
    if time.time() - _waiting_since >= WAIT_MINUTES * 60:
        _waiting_since = None
        from src.ui.shell import schedule_ui

        schedule_ui.report_failure(BUSY_NOTE.format(m=WAIT_MINUTES))
        return
    QTimer.singleShot(WAIT_RETRY_MS, guarded("scheduled start wait", lambda: _retry(delay_ms)))


def _retry(delay_ms: int) -> None:
    global _waiting_since
    if _waiting_since is None:
        return  # cancelled
    reason = _why_not(True)
    if reason in WAIT_REASONS:
        _wait(delay_ms)
        return
    _waiting_since = None
    if reason is not None:
        logger.info(f"scheduled start: not started ({reason})")
        return
    _count_down(delay_ms, True)


def _count_down(delay_ms: int, scheduled: bool) -> None:
    global _due
    from PySide6.QtCore import QTimer

    _due = time.time() + delay_ms / 1000
    logger.info(f"auto-run on open: starting in {delay_ms // 1000} s")
    QTimer.singleShot(delay_ms, lambda: _fire(scheduled))


def schedule_on_open() -> bool:
    """When the tool opens: 定时启动 opened it, or the 首页 box is ticked."""
    from src.utils import scheduled_start

    return schedule(scheduled=scheduled_start.launched_by_schedule)


def _fire(scheduled: bool = False) -> None:
    global _due
    if _due is None:
        return  # cancelled
    _due = None
    if scheduled and _why_not(True) in WAIT_REASONS:
        _wait(DELAY_MS)  # something started during the count down
        return
    maybe_start(scheduled)


def seconds_left() -> int | None:
    if _due is None:
        return None
    return max(1, round(_due - time.time()))


def cancel() -> None:
    global _due, _waiting_since
    _waiting_since = None
    if _due is not None:
        _due = None
        logger.info("auto-run on open: cancelled by the player")
