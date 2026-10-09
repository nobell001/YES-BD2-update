"""Installer for the app-wide UI hooks that still run under the new shell.

Called once from ``src/config.py`` before the framework builds the main
window.  The old task-page chrome it used to install (cards, run panel,
banner, motion) went with the old pages (Leo, 2026-10-04).
"""

from __future__ import annotations


def install_quest_ui() -> None:
    from src.tasks.problem_report import install_log_ring
    from src.tasks.run_history import install_run_history_recorder
    from src.tasks.takeover import install_takeover_monitor
    from src.ui.traditional import install_traditional_fallback

    install_traditional_fallback()
    install_log_ring()
    install_run_history_recorder()
    install_takeover_monitor()
