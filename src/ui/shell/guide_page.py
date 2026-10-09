"""使用说明: a short picture guide for new players (Leo, 2026-10-05).

Bullets, not paragraphs (Leo: 「條列式言簡意賅…提示即可」): the two ways to
run the dailies, a nudge to look at the settings once, and the three game
settings 跑图 depends on.  The game pictures are Leo's own screenshots with
the parts to look at circled (assets/ui/guide); a click shows one large.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.ui.shell import theme
from src.ui.shell.page import Page, pill
from src.ui.shell.widgets import Button, Card, IconTile, Picture, Text, hbox, vbox

ROOT = Path(__file__).resolve().parents[3]
GUIDE_DIR = ROOT / "assets" / "ui" / "guide"
# Remembers that the guide was opened once, so the sidebar stops pointing at it.
SEEN_FILE = ROOT / "configs" / "ui_guide.json"


def picture_path(name: str) -> str:
    return str(GUIDE_DIR / f"{name}.png")


def seen(key: str = "seen") -> bool:
    """Whether the guide (or another first-visit note, by ``key``) was shown once."""
    try:
        return bool(json.loads(SEEN_FILE.read_text(encoding="utf-8")).get(key))
    except (OSError, ValueError, AttributeError):
        return False


def mark_seen(key: str = "seen") -> None:
    try:
        try:
            marks = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            marks = {}
        if not isinstance(marks, dict):
            marks = {}
        marks[key] = True
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        SEEN_FILE.write_text(json.dumps(marks), encoding="utf-8")
    except OSError:
        pass


class GuidePicture(Picture):
    """A guide screenshot: keeps its shape, at most ``max_width`` wide; click to enlarge."""

    def __init__(self, name: str, max_width: int, parent=None):
        super().__init__(picture_path(name), parent, radius=theme.corner(4, 10))
        self._max_width = max_width
        native = self._pixmap.size()
        self._ratio = native.height() / native.width() if native.width() else 0.6
        self.setMaximumWidth(max_width)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._enlarge)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(min(width, self._max_width) * self._ratio)

    def sizeHint(self) -> QSize:
        return QSize(self._max_width, self.heightForWidth(self._max_width))

    def minimumSizeHint(self) -> QSize:
        return QSize(120, round(120 * self._ratio))

    def _enlarge(self) -> None:
        from src.ui.shell.home import PictureDialog

        PictureDialog(self._path, self).exec()

    def set_path(self, path: str | None) -> None:
        self._path = path or ""
        super().set_path(path)


class StepNumber(QWidget):
    """The violet numbered circle in front of each 跑图 step."""

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        self._number = str(number)
        self.setFixedSize(26, 26)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.color("primary"))
        painter.drawEllipse(QRectF(self.rect()))
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(theme.color("on_primary"))
        painter.drawText(QRectF(self.rect()), Qt.AlignCenter, self._number)


class GuidePage(Page):
    interval = 60000

    def __init__(self, navigate: Callable[[str], None] | None = None, sidebar=None):
        super().__init__("shellGuide", "使用说明", "第一次用，先花一分钟看完")
        self._navigate = navigate
        self._sidebar = sidebar
        self._build_ways()
        self._build_settings()
        self._build_map()
        self.body.addStretch(1)
        # Leo 2026-10-09: always marked 必看 (it used to go once opened).
        if sidebar is not None and "guide" in getattr(sidebar, "items", {}):
            sidebar.items["guide"].set_badge("必看")

    def showEvent(self, event):
        super().showEvent(event)
        if not seen():
            mark_seen()

    # ---------------------------------------------------------- pieces

    def _section(self, title: str) -> None:
        self.body.addWidget(Text(title, "h2"))

    def _card(self, margins=(18, 14, 18, 16), spacing: int = 10):
        card = Card()
        column = vbox(card, margins, spacing)
        return card, column

    def _bullets(self, column, lines) -> None:
        for line in lines:
            row = hbox(None, (0, 0, 0, 0), 8)
            dot = Text("•", "guide")
            dot.setFixedWidth(12)
            row.addWidget(dot, 0, Qt.AlignTop)
            row.addWidget(Text(line, "guide", wrap=True), 1)
            column.addLayout(row)

    def _go(self, key: str) -> None:
        if self._navigate is not None:
            self._navigate(key)

    # ---------------------------------------------------------- 1 两种跑法

    def _build_ways(self) -> None:
        self._section("日常有两种跑法")
        row = hbox(None, (0, 0, 0, 0), 14)
        for icon_name, title, tag, lines in (
            (
                "play",
                "一键完成日常",
                "最常用",
                (
                    "游戏开在前面，工具直接点游戏",
                    "跑的时候不要动鼠标、键盘",
                    "游戏没开会先问你，再帮你开",
                ),
            ),
            (
                "monitor",
                "在桌面分身跑",
                "边跑边用电脑",
                (
                    "游戏在另一个分身窗口里跑，缩小也照跑",
                    "电脑照常用，鼠标键盘不会被抢",
                    "要 Windows 专业版；第一次要设定，并输入微软账户密码",
                ),
            ),
        ):
            card, column = self._card()
            head = hbox(None, (0, 0, 0, 0), 10)
            head.addWidget(IconTile(icon_name, 34, 18))
            head.addWidget(Text(title, "h2"), 1)
            head.addWidget(pill(tag))
            column.addLayout(head)
            self._bullets(column, lines)
            column.addStretch(1)
            row.addWidget(card, 1)
        self.body.addLayout(row)
        self.body.addWidget(Text("两个按钮都在「首页」。", "guide_note"))

    # ---------------------------------------------------------- 2 设定

    def _build_settings(self) -> None:
        self._section("先看一次设定")
        card, column = self._card()
        head = hbox(None, (0, 0, 0, 0), 10)
        head.addWidget(IconTile("sliders-horizontal", 34, 18))
        texts = vbox(None, (0, 0, 0, 0), 2)
        texts.addWidget(Text("照自己的习惯调好再跑", "h2"))
        texts.addWidget(Text("要跑哪些、跑几次、要不要做料理，都在这几页", "guide_note", wrap=True))
        head.addLayout(texts, 1)
        column.addLayout(head)
        buttons = hbox(None, (44, 2, 0, 0), 8)
        for key, label in (
            ("daily", "任务设定"),
            ("trade", "跑商"),
            ("map", "跑图"),
        ):
            buttons.addWidget(
                Button(label, "secondary", size="sm", on_click=lambda k=key: self._go(k))
            )
        buttons.addStretch(1)
        column.addLayout(buttons)
        self.body.addWidget(card)

    # ---------------------------------------------------------- 3 跑图

    def _step(self, number: int, title: str, important: bool = False):
        card, column = self._card(spacing=12)
        head = hbox(None, (0, 0, 0, 0), 10)
        head.addWidget(StepNumber(number))
        head.addWidget(Text(title, "h2"), 1)
        if important:
            head.addWidget(pill("重要", "bad"))
        column.addLayout(head)
        self.body.addWidget(card)
        return column

    def _build_map(self) -> None:
        self._section("跑图前，游戏里先设好这三样")

        column = self._step(1, "技能按顺序放")
        row = hbox(None, (0, 0, 0, 0), 18)
        row.addWidget(GuidePicture("skills", 260), 0, Qt.AlignTop)
        texts = vbox(None, (0, 4, 0, 0), 8)
        self._bullets(
            texts,
            (
                "右下角技能，按 1 → 4 放：探查、吸收、召集、压制",
                "用哪一组技能（TAB 切换的 1/2/3）都可以",
                "建议跑之前先放好",
            ),
        )
        texts.addStretch(1)
        row.addLayout(texts, 1)
        column.addLayout(row)

        column = self._step(2, "左上角保持小地图")
        row = hbox(None, (0, 0, 0, 0), 14)
        for name, label, tone in (
            ("minimap_small", "✓ 保持小地图", "ok"),
            ("minimap_big", "✗ 不要放大", "bad"),
        ):
            box = vbox(None, (0, 0, 0, 0), 8)
            box.addWidget(GuidePicture(name, 280))
            box.addWidget(pill(label, tone), 0, Qt.AlignLeft)
            row.addLayout(box)
        row.addStretch(1)
        column.addLayout(row)
        self._bullets(column, ("地图放大了，按小地图旁边的「−」缩回来",))

        column = self._step(3, "战场角色设定", important=True)
        self._bullets(column, ("点画面最下面中间的按钮",))
        column.addWidget(GuidePicture("battle_button", 300), 0, Qt.AlignLeft)
        self._bullets(
            column,
            (
                "「天赋技能使用角色设置」一定要选右边的「战场角色」",
                "上面的阵形选哪个都可以",
            ),
        )
        column.addWidget(GuidePicture("battle_dialog", 620), 0, Qt.AlignLeft)
