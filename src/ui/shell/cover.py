"""Keeps a dimming overlay the size of the tool window.

Leo 2026-10-21 「以後這種通知 全螢幕也要做適配」: the 救赎之塔/亲密度谈心
walk-through kept the size the window had when it opened, so after 最大化
only the top-left part was dimmed.  Every overlay over the whole window (the
walk-throughs, the 一键完成日常 window, the dimmed dialogs) calls
:func:`follow`, so it covers the window at any size and keeps covering it
while the window is resized, maximized, restored or moved.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QRect, QTimer
from PySide6.QtWidgets import QWidget

_EVENTS = (QEvent.Resize, QEvent.Move, QEvent.WindowStateChange, QEvent.Show)


def target_rect(overlay: QWidget, window: QWidget) -> QRect:
    """Where ``overlay`` belongs: the window's inside for a child overlay, the
    window's place on screen for a separate (dialog) one."""
    if overlay.isWindow():
        return window.geometry()
    return window.rect()


class _Follow(QObject):
    def __init__(self, overlay: QWidget, window: QWidget, on_change: Callable[[], None] | None):
        super().__init__(overlay)
        self._overlay = overlay
        self._window = window
        self._on_change = on_change
        window.installEventFilter(self)  # Qt drops it with the overlay
        self.sync()

    def sync(self) -> bool:
        """Fit the overlay to the window; True when it had to move."""
        rect = target_rect(self._overlay, self._window)
        if rect.isEmpty() or self._overlay.geometry() == rect:
            return False
        self._overlay.setGeometry(rect)
        if self._on_change is not None:
            self._on_change()
        return True

    def eventFilter(self, watched, event):
        if watched is self._window and event.type() in _EVENTS:
            self.sync()
            if event.type() == QEvent.WindowStateChange:
                # Windows gives the maximized size a moment after the change.
                QTimer.singleShot(0, self.sync)
                QTimer.singleShot(150, self.sync)
        return False


def follow(
    overlay: QWidget, window: QWidget, on_change: Callable[[], None] | None = None
) -> _Follow:
    """Make ``overlay`` cover ``window`` now and whenever the window changes.

    ``window`` is the tool window (pass ``parent.window()`` for a dialog);
    ``on_change`` runs after each new size, to lay the overlay's own parts out
    again.  It stops by itself when the overlay is deleted.
    """
    return _Follow(overlay, window.window() if overlay.isWindow() else window, on_change)
