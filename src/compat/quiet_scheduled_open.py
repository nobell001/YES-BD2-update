"""A tool 定时启动 opened shows no notice that waits for a click.

Leo 2026-10-22 「使用排程開啟的 有沒有確保 打開程式就是直接開始日常」,
「如果遇到更新 要點掉框框甚麼的 也要處理」: nobody is at the PC then.  ok's
「免费软件」 dialog after an update and its jump to 关于 (更新内容) are left
out; the next time the player opens the tool, the 更新内容 still shows (main.py
does not mark it shown on a scheduled open).
"""

from __future__ import annotations

from ok import Logger

logger = Logger.get_logger(__name__)

PATCH_MARKER = "_ok_bd2_quiet_scheduled_open"


def scheduled() -> bool:
    from src.utils import scheduled_start

    return bool(scheduled_start.launched_by_schedule)


def install() -> None:
    from ok.ui.qt.MainWindow import MainWindow

    if getattr(MainWindow, PATCH_MARKER, False):
        return

    def quiet(name: str):
        original = getattr(MainWindow, name)

        def call(self, *args, **kwargs):
            if scheduled():
                logger.info(f"scheduled start: {name} left out (nobody at the PC)")
                return None
            return original(self, *args, **kwargs)

        setattr(MainWindow, name, call)

    quiet("show_update_copyright")
    quiet("show_startup_version_change_notice")
    setattr(MainWindow, PATCH_MARKER, True)
