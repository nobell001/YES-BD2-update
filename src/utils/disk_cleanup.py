"""Keep the tool's own files on a player's PC small (Leo 2026-10-05).

Run once at start.  What is already bounded elsewhere:
- logs/ok-script*.log: ok rotates at midnight and keeps 7 days;
- screenshots/: ok keeps 7 days (cleared above 300 MB); the 今日报表
  pictures under screenshots/run_report keep 7 game days;
- configs/run_log.json keeps 7 game days.

What only grew, and is trimmed here:
- logs/crash-*.log: one file per start (almost always empty);
- logs/dependency_guard.log: appended on every start;
- probe_outputs/*.png: failure pictures named after the page, so new
  names (each event, each pass) added a 2-4 MB picture each.
"""

from __future__ import annotations

import time
from pathlib import Path

DAY = 86400
CRASH_KEEP = 10
GUARD_LOG_MAX_BYTES = 1024 * 1024
PROBE_KEEP_DAYS = 7
PROBE_MAX_BYTES = 150 * 1024 * 1024


def _files(folder: Path, pattern: str) -> list[Path]:
    try:
        return sorted(
            (path for path in folder.glob(pattern) if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []


def _remove(path: Path) -> int:
    try:
        size = path.stat().st_size
        path.unlink()
        return size
    except OSError:
        return 0


def trim_crash_logs(logs: Path, current: Path | None = None) -> int:
    """Empty crash logs of earlier starts go; of the rest the newest few stay."""
    freed = 0
    kept = 0
    for path in _files(logs, "crash-*.log"):
        if current is not None and path.resolve() == current.resolve():
            continue
        try:
            empty = path.stat().st_size == 0
        except OSError:
            continue
        if empty or kept >= CRASH_KEEP:
            freed += _remove(path)
        else:
            kept += 1
    return freed


def trim_guard_log(logs: Path) -> int:
    """Keep the last part of an over-long dependency_guard.log."""
    path = logs / "dependency_guard.log"
    try:
        size = path.stat().st_size
        if size <= GUARD_LOG_MAX_BYTES:
            return 0
        with open(path, "rb") as file:
            file.seek(size - GUARD_LOG_MAX_BYTES // 2)
            tail = file.read()
        path.write_bytes(tail)
        return size - len(tail)
    except OSError:
        return 0


def trim_probe_outputs(folder: Path, now: float | None = None) -> int:
    """Failure pictures older than a week go, then the oldest past the cap."""
    now = time.time() if now is None else now
    freed = 0
    total = 0
    for path in _files(folder, "*"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if now - stat.st_mtime > PROBE_KEEP_DAYS * DAY or total + stat.st_size > PROBE_MAX_BYTES:
            freed += _remove(path)
        else:
            total += stat.st_size
    return freed


def clean_up(root: Path | None = None, current_crash_log: Path | None = None) -> int:
    """Bytes freed; never raises (a failed clean-up must not stop the tool)."""
    root = Path.cwd() if root is None else root
    freed = 0
    try:
        freed += trim_crash_logs(root / "logs", current_crash_log)
        freed += trim_guard_log(root / "logs")
        freed += trim_probe_outputs(root / "probe_outputs")
    except Exception:
        pass
    return freed
