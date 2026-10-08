"""Timer callbacks that log a failure instead of closing the window.

An exception escaping a Qt slot takes the whole app down in this PySide
build (see ``Page._page_tick``), so callbacks that run on a timer go through
``guarded``.  Each one logs its first failure only, so a callback that keeps
failing every second does not flood the log.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

from ok import Logger

logger = Logger.get_logger(__name__)


def guarded(name: str, func: Callable, on_gone: Callable[[], None] | None = None) -> Callable:
    """``func`` wrapped so an exception is logged (once) rather than raised.

    ``on_gone`` runs on a RuntimeError, which PySide raises when a widget
    the callback touches has already been deleted; it usually stops the timer.
    """
    failed = {"logged": False}

    @functools.wraps(func)
    def run(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RuntimeError as exc:
            if on_gone is not None:
                on_gone()
                return None
            _log_once(failed, name, exc)
        except Exception as exc:
            _log_once(failed, name, exc)
        return None

    return run


def _log_once(failed: dict, name: str, exc: Exception) -> None:
    if not failed["logged"]:
        failed["logged"] = True
        logger.error(f"{name} failed", exc)
