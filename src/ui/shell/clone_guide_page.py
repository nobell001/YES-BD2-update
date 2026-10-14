"""桌面分身: what this PC needs, how to go in, and what to do when it fails.

Leo 2026-10-14 「綜合之前遇到的桌面分身問題 這樣能引導解答就好」「甚至你左邊
側邊欄多一個好看的教學」: players got stuck on the password (PIN, Microsoft
account), on Windows Hello, on the 远程桌面服务, on an antivirus deleting the
clone program and on 516.  The top card checks this PC and offers the same
fixes as the 在桌面分身跑 button; the questions below give the steps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from src.ui.shell.guide_page import StepNumber
from src.ui.shell.page import Page
from src.ui.shell.widgets import Button, Card, IconLabel, Text, hbox, t, tf, vbox
from src.utils import clone_desktop

OK, WARN, BAD = "ok", "warn", "bad"


@dataclass(frozen=True)
class Check:
    label: str
    tone: str
    text: str
    action: str = ""  # 第一次设定 / 帮我打开 / 帮我关掉


def password_text(microsoft: bool | None) -> str:
    """Which password the sign-in box wants."""
    if microsoft:
        return "微软帐号的密码（登录微软网站用的那组），不是 PIN"
    if microsoft is False:
        return "这台电脑的开机密码，不是 PIN"
    return "Windows 帐户的密码，不是 PIN"


def checks(
    *,
    supported: bool,
    removed: bool,
    ready: bool,
    service: str,
    microsoft: bool | None,
    account: str | None,
    hello_only: bool,
) -> list[Check]:
    """This PC, one row per thing players got stuck on."""
    if not supported:
        return [Check("Windows", BAD, "家庭版不能用桌面分身，请用「一键完成日常」")]
    rows = [Check("Windows", OK, "专业版，可以用")]
    if removed:
        rows.append(Check("分身程序", BAD, "不见了，可能被防毒软件删掉", "第一次设定"))
    elif not ready:
        rows.append(Check("第一次设定", WARN, "还没设定", "第一次设定"))
    else:
        rows.append(Check("第一次设定", OK, "已设定"))
    if service == "missing":
        rows.append(Check("远程桌面服务", BAD, "这台电脑没有（精简版 Windows），不能用"))
    elif service == "disabled":
        rows.append(Check("远程桌面服务", WARN, "被停用了", "帮我打开"))
    else:
        rows.append(Check("远程桌面服务", OK, "正常"))
    shown = (account or "").removeprefix("MicrosoftAccount\\")
    if microsoft:
        rows.append(Check("登录帐户", OK, tf("微软帐户 {name}", name=shown).strip()))
    elif microsoft is False:
        rows.append(Check("登录帐户", OK, tf("本地帐户 {name}", name=shown).strip()))
    else:
        rows.append(Check("登录帐户", WARN, "认不出是哪种帐户"))
    rows.append(Check("要打的密码", OK, password_text(microsoft)))
    if hello_only:
        rows.append(Check("Windows Hello", WARN, "只允许 Windows Hello 登录", "帮我关掉"))
    else:
        rows.append(Check("Windows Hello", OK, "可以用密码登录"))
    return rows


def this_pc() -> list[Check]:
    supported = clone_desktop.supported()
    if not supported:
        return checks(
            supported=False, removed=False, ready=False, service="ok",
            microsoft=None, account=None, hello_only=False,
        )
    return checks(
        supported=True,
        removed=clone_desktop.viewer_removed(),
        ready=clone_desktop.ready(),
        service=clone_desktop.remote_desktop_service(),
        microsoft=clone_desktop.microsoft_account(),
        account=clone_desktop.sign_in_account(),
        hello_only=clone_desktop.hello_only(),
    )


# (question, steps, show the 打开分身文件夹 button)
QUESTIONS = (
    (
        "提示「登录失败」",
        (
            "密码打上面「要打的密码」那组，不是 PIN",
            "平常只用 PIN 或人脸开机：按 Win+L，选钥匙图示，用密码登录电脑一次",
            "再按一次首页的「在桌面分身跑」",
        ),
        False,
    ),
    (
        "提示「连不上桌面分身」（代码 516 等）",
        (
            "关掉工具，重新打开再按一次",
            "重新开机后再试（刚设定完常要重新开机）",
            "用过系统优化／精简工具或 RDP Wrapper 的电脑，可能不能用",
        ),
        False,
    ),
    (
        "提示「分身程序不见了」",
        (
            "在防毒软件（例如 360、火绒）把分身文件夹设为信任",
            "按上面的「第一次设定」重新建立",
        ),
        True,
    ),
    (
        "首页没有「在桌面分身跑」",
        (
            "桌面分身要 Windows 专业版，家庭版没有",
            "请用「一键完成日常」",
        ),
        False,
    ),
    (
        "帐户没有设密码",
        (
            "没有密码的帐户进不了分身（Windows 的规定）",
            "到 Windows「设置 > 帐户 > 登录选项」加一组密码",
        ),
        False,
    ),
    (
        "还是不行",
        (
            "在左边「回报问题」送出",
            "或把分身文件夹里的 viewer.log 传给我们",
        ),
        True,
    ),
)


class Question(QWidget):
    """A question; a click shows or hides its numbered steps."""

    def __init__(self, question: str, steps, folder_button: bool, parent=None):
        super().__init__(parent)
        column = vbox(self, (0, 0, 0, 0), 6)
        head = QWidget(self)
        head.setCursor(Qt.PointingHandCursor)
        row = hbox(head, (0, 4, 0, 4), 8)
        self.arrow = IconLabel("chevron-right", 16, "ink3")
        row.addWidget(self.arrow)
        row.addWidget(Text(question, "h3"), 1)
        head.mousePressEvent = lambda _e: self.toggle()
        column.addWidget(head)
        self.answer = QWidget(self)
        lines = vbox(self.answer, (24, 0, 0, 6), 4)
        for number, step in enumerate(steps, 1):
            lines.addWidget(Text(f"{number}. {t(step)}", "guide", wrap=True))
        if folder_button:
            button = Button(
                "打开分身文件夹", "secondary", size="sm", on_click=open_clone_folder
            )
            lines.addWidget(button, 0, Qt.AlignLeft)
        self.answer.hide()
        column.addWidget(self.answer)

    def toggle(self) -> None:
        shown = not self.answer.isVisible()
        self.answer.setVisible(shown)
        self.arrow.set_icon("chevron-down" if shown else "chevron-right")


def open_clone_folder() -> None:
    try:
        clone_desktop.DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(clone_desktop.DATA_DIR))  # noqa: S606 - the player's own folder
    except (AttributeError, OSError):
        pass


class CloneGuidePage(Page):
    interval = 60000

    def __init__(self, parent=None):
        super().__init__("shellCloneGuide", "桌面分身", "边跑边用电脑；进不去就照这页做", parent)
        self._shown: list[Check] | None = None
        self.body.addWidget(Text("这台电脑（自动检查）", "h2"))
        card = Card()
        self.rows = vbox(card, (18, 12, 18, 12), 2)
        self.body.addWidget(card)
        self.note = Text("", "guide_note", wrap=True)
        self.note.hide()
        self.body.addWidget(self.note)

        self.body.addWidget(Text("第一次怎么用", "h2"))
        steps = hbox(None, (0, 0, 0, 0), 12)
        for number, text in enumerate(
            (
                "首页按「在桌面分身跑」",
                "Windows 确认按「是」",
                "打上面写的密码，勾「记住」",
            ),
            1,
        ):
            step = Card()
            line = hbox(step, (14, 12, 14, 12), 10)
            line.addWidget(StepNumber(number), 0, Qt.AlignTop)
            line.addWidget(Text(text, "guide", wrap=True), 1)
            steps.addWidget(step, 1)
        self.body.addLayout(steps)

        self.body.addWidget(Text("遇到问题（点开看做法）", "h2"))
        card = Card()
        questions = vbox(card, (18, 10, 18, 10), 4)
        for question, lines, folder in QUESTIONS:
            questions.addWidget(Question(question, lines, folder))
        self.body.addWidget(card)
        self.body.addStretch(1)

    def refresh(self) -> None:
        found = this_pc()
        if found == self._shown:
            return
        self._shown = found
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for check in found:
            self.rows.addWidget(self._row(check))

    def _row(self, check: Check) -> QWidget:
        row = QWidget()
        line = hbox(row, (0, 6, 0, 6), 10)
        icon = {OK: "circle-check", WARN: "circle-alert", BAD: "circle-x"}[check.tone]
        line.addWidget(IconLabel(icon, 18, check.tone))
        label = Text(check.label, "muted", wrap=True)
        label.setFixedWidth(110)
        line.addWidget(label)
        line.addWidget(Text(check.text, "guide", wrap=True), 1)
        if check.action:
            line.addWidget(
                Button(
                    check.action, "primary", size="sm",
                    on_click=lambda a=check.action: self._fix(a),
                )
            )
        return row

    def _fix(self, action: str) -> None:
        """The same fixes as the 在桌面分身跑 button (one Windows confirmation)."""
        if action == "第一次设定":
            clone_desktop.run_setup()
            done = "设定好后，回来这页看一次"
        elif action == "帮我打开":
            ok = clone_desktop.enable_remote_desktop_service()
            done = (
                "「远程桌面服务」已经打开"
                if ok
                else "没有打开（Windows 的确认按了「否」或改不了）"
            )
        else:
            ok = clone_desktop.turn_off_hello_only()
            done = "已经关掉" if ok else "没有关掉（Windows 的确认按了「否」或改不了）"
        self.note.set_text(done)
        self.note.show()
        self._shown = None
        self.refresh()

