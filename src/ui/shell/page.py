"""The frame every new page shares: a scrolling view with a header."""

from __future__ import annotations

from ok import Logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QBoxLayout, QFrame, QLayout, QWidget
from qfluentwidgets import ScrollArea

from src.ui.shell import theme
from src.ui.shell.widgets import SHADOW_MARGINS, Card, Text, hbox, set_prop, vbox

logger = Logger.get_logger(__name__)

PAGE_MARGINS = (28, 6, 28, 28)
# A card's body starts this far inside its widget (the room for its shadow);
# titles, notes and buttons outside cards move in as far, so their edges line
# up with the cards' edges (2026-10-22 check: everything else sat 6 px out).
CARD_EDGE = SHADOW_MARGINS[0]


def _has_card(item) -> bool:
    widget = item.widget() if hasattr(item, "widget") else item
    if isinstance(widget, QWidget):
        return isinstance(widget, Card) or bool(widget.findChildren(Card))
    layout = item.layout() if hasattr(item, "layout") else None
    if layout is None:
        return False
    return any(_has_card(layout.itemAt(index)) for index in range(layout.count()))


def _empty(item) -> bool:
    """A container with nothing in it yet (filled later, maybe with cards)."""
    widget = item.widget() if hasattr(item, "widget") else item
    if isinstance(widget, QWidget):
        return widget.layout() is not None and not widget.findChildren(QWidget)
    layout = item.layout() if hasattr(item, "layout") else None
    if layout is None:
        return True
    return all(_empty(layout.itemAt(index)) for index in range(layout.count()))


def _inset(target: QWidget | QLayout) -> None:
    if target.property("cardEdge"):
        return
    margins = target.contentsMargins()
    target.setContentsMargins(
        margins.left() + CARD_EDGE, margins.top(), margins.right() + CARD_EDGE, margins.bottom()
    )
    target.setProperty("cardEdge", True)


def align_to_cards(layout: QLayout) -> None:
    """Move what is not a card in ``layout`` in to the cards' edges.

    Containers that hold cards are walked into (a column of a title and a
    card); a grid of cards is left alone.  Safe to call again after a page
    adds rows: what was moved already is marked and kept.
    """
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            if widget.isWindow() or isinstance(widget, Card) or _empty(widget):
                continue
            if not _has_card(widget):
                _inset(widget)
            elif isinstance(widget.layout(), QBoxLayout):
                align_to_cards(widget.layout())
        elif child is not None and not _empty(child):
            if not _has_card(child):
                _inset(child)
            elif isinstance(child, QBoxLayout):
                align_to_cards(child)


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

    def _align(self) -> None:
        # Rows a refresh adds (report lines, the run view) are lined up too;
        # the walk only reruns when the page's widgets changed.
        count = len(self.view.findChildren(QWidget))
        if count != getattr(self, "_aligned_count", -1):
            self._aligned_count = count
            align_to_cards(self.body)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _page_tick(self) -> None:
        # An exception escaping a Qt event handler takes the whole app down
        # in this PySide build, so a page that fails to refresh only logs.
        try:
            self.refresh()
            self._align()
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
