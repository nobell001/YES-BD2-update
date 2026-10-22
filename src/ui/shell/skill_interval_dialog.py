"""跑图's 技能间隔 as a small window over the tool (Leo 2026-10-20: 「一開始用個
小圖標就好 寫1.2s 然後點開彈窗」).

A slider from 0.5 to 2.0 s in 0.1 s steps, the value in big type, and
取消 / 确定; the value is kept only on 确定.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider, QWidget

from src.ui.shell import theme
from src.ui.shell.floating import Floating, Panel
from src.ui.shell.run_confirm import HeroIcon
from src.ui.shell.widgets import Button, Text, hbox, tf, vbox

PANEL_WIDTH = 420
STEPS_PER_SECOND = 10


def seconds_text(value: float) -> str:
    return f"{value:.1f}s"


class SkillIntervalDialog(Floating):
    PANEL_WIDTH = PANEL_WIDTH - 2 * Panel.SHADOW
    MARGIN = 64
    PAD = (24, 20)

    def __init__(
        self,
        value: float,
        limits: tuple[float, float],
        default: float,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._default = default
        column = self.column

        head = hbox(None, (0, 0, 0, 0), 12)
        # Next to the title, not halfway down a long explanation.
        head.addWidget(HeroIcon("clock", 40), 0, Qt.AlignTop)
        titles = vbox(None, (0, 0, 0, 0), 2)
        titles.addWidget(Text("技能间隔", "h2"))
        titles.addWidget(
            Text(
                "吸收、召集、压制之间隔几秒再按下一个。电脑或网络较慢、技能常常没按上时调大。",
                "sub",
                wrap=True,
            )
        )
        head.addLayout(titles, 1)
        column.addLayout(head)

        self.value_text = Text("", "huge")
        self.value_text.setAlignment(Qt.AlignCenter)
        column.addWidget(self.value_text)

        self.slider = QSlider(Qt.Horizontal, self.panel)
        tokens = theme.tokens()
        self.slider.setStyleSheet(
            f"""
            QSlider {{ min-height: 24px; background: transparent; }}
            QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {tokens["track"]}; }}
            QSlider::sub-page:horizontal {{ height: 6px; border-radius: 3px; background: {tokens["primary"]}; }}
            QSlider::handle:horizontal {{ width: 18px; height: 18px; margin: -7px 0; border-radius: 10px;
                background: {tokens["card"]}; border: 2px solid {tokens["primary"]}; }}
            QSlider::handle:horizontal:hover {{ background: {tokens["accent_soft"]}; }}
            """
        )
        self.slider.setRange(
            round(limits[0] * STEPS_PER_SECOND), round(limits[1] * STEPS_PER_SECOND)
        )
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(lambda _v: self._show())
        column.addWidget(self.slider)
        ends = hbox(None, (0, 0, 0, 0), 8)
        ends.addWidget(Text(seconds_text(limits[0]), "muted"))
        ends.addStretch(1)
        ends.addWidget(Text(tf("默认 {s}", s=seconds_text(default)), "muted"))
        ends.addStretch(1)
        ends.addWidget(Text(seconds_text(limits[1]), "muted"))
        column.addLayout(ends)

        buttons = hbox(None, (0, 6, 0, 0), 8)
        buttons.addWidget(Button("恢复默认", "ghost", size="sm", on_click=self._reset))
        buttons.addStretch(1)
        buttons.addWidget(Button("取消", "secondary", on_click=self.reject))
        buttons.addWidget(Button("确定", "primary", on_click=self.accept))
        column.addLayout(buttons)

        self.slider.setValue(round(value * STEPS_PER_SECOND))
        self._show()

    def value(self) -> float:
        return round(self.slider.value() / STEPS_PER_SECOND, 1)

    def _show(self) -> None:
        self.value_text.set_text(seconds_text(self.value()))

    def _reset(self) -> None:
        self.slider.setValue(round(self._default * STEPS_PER_SECOND))

    # ---------------------------------------------------------------- look

    def mouseReleaseEvent(self, event):
        # A click on the dimmed part outside the panel is 取消.
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.reject()
        super().mouseReleaseEvent(event)


def ask(window: QWidget | None, value: float, limits, default: float) -> float | None:
    """The chosen seconds on 确定, ``None`` on 取消."""
    dialog = SkillIntervalDialog(value, tuple(limits), default, window)
    if not dialog.exec():
        return None
    return dialog.value()
