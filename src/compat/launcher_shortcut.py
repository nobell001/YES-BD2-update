"""让「yes-bd2」捷径也先开启动器，玩家点哪个图示都会先更新。

PyAppify 启动器每次开工具后，会在开始菜单写一个「yes-bd2」捷径（用工具
的图示），桌面上有同名捷径也会改写；但这个捷径直接用 Python 开工具，
完全跳过启动器，所以不会自动更新，检查更新也问不到（YES-BD2 issue #2；
Leo 4K 10-09 实际点开确认）。启动器是别人的程序，没法改它写捷径的方式，
只能由工具在启动器写完之后（它在工具开起来 10 秒内写）把目标换成
启动器 exe，图示留着（Leo 10-09：只让启动器带这个图示，避免点错）。

只在安装版、不在桌面分身里做；源码版找不到启动器就什么都不做。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from ok import Logger

logger = Logger.get_logger(__name__)

# The launcher writes its shortcuts within ~10 s of the tool starting
# (check_running_on_start polls up to 10 s); look a few times after that.
CHECK_AFTER_SECONDS = (20, 60, 180)


def shortcut_paths(app_name: str, start_menu: Path, desktop: Path) -> list[Path]:
    return [start_menu / f"{app_name}.lnk", desktop / f"{app_name}.lnk"]


def needs_retarget(target: str, launcher: Path) -> bool:
    if not target:
        return False
    return os.path.normcase(os.path.abspath(target)) != os.path.normcase(str(launcher))


def retarget(link: Path, launcher: Path, shell=None) -> bool:
    """Point ``link`` at the launcher; True when it was changed."""
    if not link.is_file():
        return False
    if shell is None:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(link))
    if not needs_retarget(str(shortcut.TargetPath or ""), launcher):
        return False
    icon = str(shortcut.IconLocation or "")
    shortcut.TargetPath = str(launcher)
    shortcut.Arguments = ""
    shortcut.WorkingDirectory = str(launcher.parent)
    if icon and not icon.startswith(","):
        shortcut.IconLocation = icon  # keep the tool's picture
    shortcut.Save()
    return True


def fix_shortcuts(launcher: Path, app_name: str) -> list[Path]:
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    start_menu = (
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    )
    desktop = Path(str(shell.SpecialFolders("Desktop") or ""))
    changed = []
    for link in shortcut_paths(app_name, start_menu, desktop):
        try:
            if retarget(link, launcher, shell):
                changed.append(link)
        except Exception as exc:
            logger.warning(f"launcher shortcut: could not update {link} ({exc})")
    if changed:
        logger.info(f"launcher shortcut: now opens the launcher: {[str(p) for p in changed]}")
    return changed


def install_launcher_shortcut_fix(script_dir: str | os.PathLike, exit_event=None) -> bool:
    """Start the background fix; False when there is nothing to do here."""
    import sys

    if sys.platform != "win32":
        return False
    from src.compat.launcher_env import find_install

    install = find_install(script_dir)
    if install is None:
        return False
    try:
        from src.utils.clone_desktop import in_clone

        if in_clone():
            return False
    except Exception:
        pass
    launcher, app_dir = install

    def run() -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass
        waited = 0
        for at in CHECK_AFTER_SECONDS:
            delay = at - waited
            waited = at
            if exit_event is not None:
                if exit_event.wait(delay):
                    return
            else:
                threading.Event().wait(delay)
            try:
                fix_shortcuts(launcher, app_dir.name)
            except Exception as exc:
                logger.warning(f"launcher shortcut: check failed ({exc})")

    threading.Thread(target=run, name="LauncherShortcut", daemon=True).start()
    return True
