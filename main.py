def _ascii_root(script_dir: str, prefix: str) -> str:
    """The folder to reach through an English-only link: the whole install
    (pyappify's <root>\\data\\apps\\<name>\\working, so Python and its packages
    too), else what the tool and its Python share, else the tool's folder."""
    import os

    parts = script_dir.split(os.sep)
    lowered = [part.lower() for part in parts]
    if len(parts) >= 4 and lowered[-1] == "working" and lowered[-3] == "apps" and lowered[-4] == "data":
        return os.sep.join(parts[:-4])
    try:
        common = os.path.commonpath([script_dir, prefix])
    except ValueError:
        common = ""
    if common and not common.isascii() and os.path.dirname(common) != common:
        return common
    return script_dir


def _link_for(target: str) -> str | None:
    """An English-only folder that leads to ``target`` (a junction; no Administrator needed)."""
    import _winapi
    import hashlib
    import os

    base = os.path.join(os.environ.get("ProgramData") or r"C:\ProgramData", "YES-BD2", "links")
    if not base.isascii():
        return None
    link = os.path.join(base, hashlib.sha1(target.lower().encode("utf-8")).hexdigest()[:10])
    try:
        if os.path.isdir(link) and os.path.samefile(link, target):
            return link
        if os.path.lexists(link):
            os.rmdir(link)  # an old link to somewhere else; removes only the link
        os.makedirs(base, exist_ok=True)
        _winapi.CreateJunction(target, link)
    except OSError:
        return None
    return link if os.path.samefile(link, target) else None


def use_ascii_paths() -> None:
    """安装文件夹有中文（例如 C:\\Users\\<中文用户名>\\AppData\\Local\\yes-bd2）时，经由英文路径的连结打开。

    ok-script 遇到非英文路径就不启动，OpenCV 也读不了这种路径的图片。中文
    Windows 给中文文件夹的短名仍是中文（4K 实测 10-09：中文路~1），所以在
    C:\\ProgramData\\YES-BD2\\links 建一个指向安装文件夹的连结，在导入任何
    src 模块之前把路径都换成经由它的路径（2026-10-09 检查）。路径本来就是
    英文时什么都不做。
    """
    import os
    import sys

    if sys.platform != "win32":
        return
    script = os.path.abspath(sys.argv[0])
    if script.isascii():
        return
    target = _ascii_root(os.path.dirname(script), os.path.abspath(sys.prefix))
    link = _link_for(target)
    if link is None:
        return  # ok-script then shows its own 「必须是英文路径」 message

    def mapped(path: str) -> str:
        if not path:
            return path
        full = os.path.abspath(path)
        if full.lower() == target.lower():
            return link
        if full.lower().startswith(target.lower() + os.sep):
            return link + full[len(target):]
        return path

    sys.argv[0] = mapped(script)
    # The Administrator copy and the tool in the 桌面分身 start from these.
    sys.executable = mapped(sys.executable)
    sys.path[:] = [mapped(entry) for entry in sys.path]
    try:
        os.chdir(mapped(os.getcwd()))
    except OSError:
        pass


if __name__ == "__main__":
    use_ascii_paths()

    # 以管理员身份启动：Windows 确认一次，取代 ok-script 的「需要管理员权限」
    # 对话框（Leo, 2026-10-03）。桌面分身里不问。
    from src.compat.elevate import relaunch_as_admin

    if relaunch_as_admin():
        raise SystemExit(0)

    # 不是从启动器打开时（桌面分身等）补上启动器的版本资讯，「检查更新」
    # 才问得到新版（YES-BD2 issue #2）。必须在任何 import pyappify 之前。
    import os
    import sys

    from src.compat.launcher_env import restore_launcher_env

    restore_launcher_env(os.path.dirname(os.path.abspath(sys.argv[0])))

    # 更新内容每个版本只跳一次，不是每次打开都跳到「关于」（Leo, 2026-10-09）。
    from src.compat.launcher_env import show_update_notice_once

    show_update_notice_once(os.path.dirname(os.path.abspath(sys.argv[0])))

    # 旧启动器一打开工具就在背景换成新版，关掉工具也会换完，玩家不用重装
    # （Leo, 2026-10-09）。
    from src.compat.launcher_self_update import start_launcher_swap

    start_launcher_swap(os.path.dirname(os.path.abspath(sys.argv[0])))

    # 原生崩溃（如 0xc0000005）不经过 Python 异常，必须在导入 ok 之前
    # 启用 faulthandler，把各线程栈写入 logs/crash-*.log 供事后定位。
    import datetime
    import faulthandler
    from pathlib import Path

    Path("logs").mkdir(exist_ok=True)
    _crash_path = Path("logs") / f"crash-{datetime.datetime.now():%Y%m%d-%H%M%S}.log"
    with open(_crash_path, "a", encoding="utf-8") as _crash_log:
        faulthandler.enable(file=_crash_log, all_threads=True)

        # 旧的空崩溃日志、过长的依赖日志、一周前的失败截图（Leo, 2026-10-05：
        # 别在玩家电脑里留太多文件）。
        from src.utils.disk_cleanup import clean_up

        clean_up(current_crash_log=_crash_path)

        # 角色名单：GitHub 上每天自动补的新角色、新服装，开工具时带过来，
        # 不动程序本身（Leo, 2026-10-07）。没网、没 git 就照旧。
        from src.tasks.fiend_hunt.character_files import refresh_in_background

        refresh_in_background()

        # 「登记在文件缺」的损坏安装 pip 永远按 already satisfied 跳过
        # （BUG-20260905-07），进框架 import 前先校验核心依赖，缺失时强制重装。
        from src.compat.dependency_guard import ensure_core_dependencies

        ensure_core_dependencies()

        import ok

        # 设置文件写到一半断电也不会让工具从此打不开（2026-10-09 检查）。
        from src.compat.safe_json import install_safe_json

        install_safe_json()

        from src.config import config

        ok_instance = ok.OK(config)

        # 启动器写的「yes-bd2」捷径直接开工具、跳过更新：改成开启动器
        # （YES-BD2 issue #2，Leo 2026-10-09）。
        from src.compat.launcher_shortcut import install_launcher_shortcut_fix

        install_launcher_shortcut_fix(os.path.dirname(os.path.abspath(sys.argv[0])))
        ok_instance.start()
