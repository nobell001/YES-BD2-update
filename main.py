if __name__ == "__main__":
    # 以管理员身份启动：Windows 确认一次，取代 ok-script 的「需要管理员权限」
    # 对话框（Leo, 2026-10-03）。桌面分身里不问。
    from src.compat.elevate import relaunch_as_admin

    if relaunch_as_admin():
        raise SystemExit(0)

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

        from src.config import config

        ok_instance = ok.OK(config)
        ok_instance.start()
