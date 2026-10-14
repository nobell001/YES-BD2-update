"""工作列按钮显示 YES-BD2 的图示，不是一张白纸（Leo 4K 2026-10-14 截图）。

工具是 pythonw.exe 跑的，又以管理员身份开着。没有自己的 AppUserModelID 时，
Windows 把按钮算在 pythonw.exe 名下，图示要去问一个比自己权限高的视窗，
问不到就画一张白纸。这里分三层补上，任何一层失败都只记一行日志：

1. 进程一开始就给自己一个固定的 AppUserModelID（必须在任何视窗出来之前）。
2. 主视窗的属性写上同一个 ID，加上图示档 icons\\icon.ico、名称 YES-BD2、
   重新打开的指令（安装版是启动器 exe）：工作列自己读 .ico 档，不用问视窗。
3. 视窗图示直接用 .ico 里系统要的大小（大、小各一个）再设一次。

只在 Windows 上做；桌面分身里也一样做（那里也有工作列）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_ID = "nobell001.YES-BD2"
DISPLAY_NAME = "YES-BD2"
ICON_FILE = Path("icons") / "icon.ico"

# win32con values, kept here so the module imports on any system.
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
SM_CXICON = 11
SM_CYICON = 12
SM_CXSMICON = 49
SM_CYSMICON = 50


def _log():
    from ok import Logger

    return Logger.get_logger(__name__)


def set_process_app_id(app_id: str = APP_ID) -> bool:
    """Give this process its own taskbar identity; call before any window exists."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id) == 0
    except (AttributeError, OSError):
        return False


def icon_path(script_dir: str | os.PathLike) -> Path | None:
    path = Path(script_dir) / ICON_FILE
    return path.resolve() if path.is_file() else None


def relaunch_command(script_dir: str | os.PathLike, python: str | None = None) -> str:
    """What a pinned button opens: the launcher when installed, so it updates first."""
    from src.compat.launcher_env import find_install

    install = find_install(script_dir)
    if install is not None:
        return subprocess.list2cmdline([str(install[0])])
    main = Path(script_dir) / "main.py"
    return subprocess.list2cmdline([python or sys.executable, str(main)])


def window_properties(script_dir: str | os.PathLike, app_id: str = APP_ID) -> list[tuple[str, str]]:
    """(property name, value) in the order to write; the ID goes last (Windows reads it then)."""
    properties = [
        ("System.AppUserModel.RelaunchCommand", relaunch_command(script_dir)),
        ("System.AppUserModel.RelaunchDisplayNameResource", DISPLAY_NAME),
    ]
    icon = icon_path(script_dir)
    if icon is not None:
        properties.append(("System.AppUserModel.RelaunchIconResource", f"{icon},0"))
    properties.append(("System.AppUserModel.ID", app_id))
    return properties


def set_window_properties(hwnd: int, properties: list[tuple[str, str]]) -> bool:
    import pythoncom
    from win32com.propsys import propsys

    store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
    for name, value in properties:
        key = propsys.PSGetPropertyKeyFromName(name)
        store.SetValue(key, propsys.PROPVARIANTType(value, pythoncom.VT_LPWSTR))
    store.Commit()
    return True


def set_window_icons(hwnd: int, icon: Path) -> bool:
    """WM_SETICON with the .ico's own big and small pictures (not a scaled PNG)."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
    done = False
    for which, cx, cy in ((ICON_BIG, SM_CXICON, SM_CYICON), (ICON_SMALL, SM_CXSMICON, SM_CYSMICON)):
        handle = user32.LoadImageW(
            None, str(icon), IMAGE_ICON,
            user32.GetSystemMetrics(cx), user32.GetSystemMetrics(cy), LR_LOADFROMFILE,
        )
        if handle:
            user32.SendMessageW(hwnd, WM_SETICON, which, handle)
            done = True
    return done


def apply_to_main_window(main_window, script_dir: str | os.PathLike | None = None) -> bool:
    """Set the taskbar identity and icon on ok-script's main window; never raises."""
    if sys.platform != "win32":
        return False
    logger = _log()
    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    ok = False
    try:
        icon = icon_path(script_dir)
        if icon is not None:
            from PySide6.QtGui import QIcon
            from PySide6.QtWidgets import QApplication

            qt_icon = QIcon(str(icon))
            QApplication.setWindowIcon(qt_icon)
            main_window.setWindowIcon(qt_icon)
        hwnd = int(main_window.winId())
        try:
            ok = set_window_properties(hwnd, window_properties(script_dir))
        except Exception as exc:
            logger.warning(f"taskbar icon: window properties not set ({exc})")
        if icon is not None:
            try:
                ok = set_window_icons(hwnd, icon) or ok
            except Exception as exc:
                logger.warning(f"taskbar icon: window icon not set ({exc})")
        logger.info(f"taskbar icon: {APP_ID} icon={icon} applied={ok}")
    except Exception as exc:
        logger.warning(f"taskbar icon: skipped ({exc})")
    return ok
