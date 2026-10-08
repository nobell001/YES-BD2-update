"""Start the tool as Administrator, asking Windows once, before ok-script loads.

ok-script refuses to start the PC game without Administrator and shows
「PC 版需要管理员权限，请以管理员权限重新启动此应用程序！」; Leo (2026-10-03)
chose one Windows confirmation per launch instead of that dialog.  The game
itself does not need it (BrownDust II.exe and the Starter are asInvoker), but
a game started by an elevated tool runs elevated and then only an elevated
tool can send it input.

Not on the 桌面分身: nobody can answer a confirmation there, and the clone
window already starts the tool elevated.  When the user says no, the tool
starts without it as before (ok-script's dialog is the last resort).
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys

NO_ELEVATE_ENV = "OK_BD2_NO_ELEVATE"


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return True  # not Windows: nothing to do


def _in_clone() -> bool:
    try:
        from src.utils.clone_desktop import in_clone

        return in_clone()
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """True when an elevated copy was started and this one should exit."""
    if sys.platform != "win32" or os.environ.get(NO_ELEVATE_ENV) or _is_admin() or _in_clone():
        return False
    arguments = [os.path.abspath(sys.argv[0]), *sys.argv[1:]]
    if getattr(sys, "frozen", False):
        arguments = sys.argv[1:]
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.restype = ctypes.c_void_p
    result = shell_execute(
        None, "runas", sys.executable, subprocess.list2cmdline(arguments), os.getcwd(), 1
    )
    return (result or 0) > 32
