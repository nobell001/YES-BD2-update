"""The frame every new page shares: a scrolling view with a header."""

from __future__ import annotations

from ok import Logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QWidget
from qfluentwidgets import ScrollArea

from src.ui.shell import theme
from src.ui.shell.widgets import Text, hbox, set_prop, vbox

logger = Logger.get_logger(__name__)

PAGE_MARGINS = (28, 6, 28, 28)


class Page(ScrollArea):
    """Header (eyebrow, title, one line under it, buttons on the right) + body.

    ``refresh`` runs when the page is shown and then every ``interval`` ms
    while it stays visible; pages keep it cheap (labels change only when
    their text does).
    """

    interval = 2000

    def __init__(self, object_name: str, title: str, sub: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setProperty("shell", True)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view = QWidget()
        self.view.setObjectName("shellView")
        self.setWidget(self.view)
        self.body = vbox(self.view, PAGE_MARGINS, 16)

        header = QWidget(self.view)
        row = hbox(header, (0, 0, 0, 2), 12)
        titles = vbox(None, (0, 0, 0, 0), 2)
        self.eyebrow = Text("", "eyebrow")
        self.eyebrow.hide()
        self.title = Text(title, "h1")
        self.sub = Text(sub, "sub", elide=True)
        self.sub.setVisible(bool(sub))
        titles.addWidget(self.eyebrow)
        titles.addWidget(self.title)
        titles.addWidget(self.sub)
        row.addLayout(titles, 1)
        self.header_actions = hbox(None, (0, 0, 0, 0), 8)
        row.addLayout(self.header_actions)
        row.setAlignment(self.header_actions, Qt.AlignVCenter)
        self.body.addWidget(header)

        self._failed = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.interval)
        self._timer.timeout.connect(self._page_tick)
        self.apply_style()
        theme.on_theme_changed(self, self.apply_style)

    # ---------------------------------------------------------- header

    def set_title(self, text: str) -> None:
        self.title.set_text(text)

    def set_sub(self, text: str) -> None:
        self.sub.set_text(text)
        self.sub.setVisible(bool(text))

    def set_eyebrow(self, text: str) -> None:
        self.eyebrow.set_text(text)
        self.eyebrow.setVisible(bool(text))

    def add_action(self, widget: QWidget) -> QWidget:
        self.header_actions.addWidget(widget)
        return widget

    # ---------------------------------------------------------- life cycle

    def apply_style(self) -> None:
        self.setStyleSheet(theme.style_sheet())

    def showEvent(self, event):
        super().showEvent(event)
        self._page_tick()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _page_tick(self) -> None:
        # An exception escaping a Qt event handler takes the whole app down
        # in this PySide build, so a page that fails to refresh only logs.
        try:
            self.refresh()
        except RuntimeError:
            self._timer.stop()
        except Exception as exc:
            if not self._failed:
                self._failed = True
                logger.error(f"{self.objectName()} refresh failed", exc)

    def refresh(self) -> None:
        """Bring the page up to date (override)."""


def pill(text: str = "", tone: str | None = None) -> Text:
    label = Text(text, "pill")
    if tone:
        label.setProperty("tone", tone)
    label.setAlignment(Qt.AlignCenter)
    return label


def set_pill(label: Text, text: str, tone: str | None = None) -> None:
    label.set_text(text)
    set_prop(label, "tone", tone or "")
    label.setVisible(bool(text))


def section_title(text: str, parent=None) -> Text:
    return Text(text, "h2", parent)
