"""定时启动 on 首页: its window and the watch while the tool is open (Leo 2026-10-22).

The card on 首页 (home.ScheduleCard) shows the next start and has the one
switch that turns it all off; a click opens :class:`ScheduleDialog`.  Each
time slot has its own time and weekdays (Leo: not only one fixed time a
day), plus 「游戏每天重置后」.  保存 writes the settings and the Windows task
(src/utils/scheduled_start.py); the switch at the top off deletes the task.
"""

from __future__ import annotations

import copy
from datetime import datetime

from ok import Logger
from PySide6.QtCore import QObject, QRectF, Qt, QTime, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from src.ui.shell import theme
from src.ui.shell.accounts_ui import _Floating
from src.ui.shell.run_confirm import HeroIcon
from src.ui.shell.safe import guarded
from src.ui.shell.widgets import (
    Button,
    CheckBox,
    IconTile,
    Inset,
    Separator,
    Text,
    Toggle,
    hbox,
    t,
    tf,
    vbox,
)
from src.utils import scheduled_start
from src.utils.scheduled_start import KIND_RESET, KIND_TIME, MAX_SLOTS, Settings, Slot

logger = Logger.get_logger(__name__)

WATCH_MS = 20_000
WEEKDAYS = "一二三四五六日"

_settings: Settings | None = None
# Why the last change did not fully take, for the card (empty when fine).
problem = ""


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = scheduled_start.load()
    return _settings


def store(new: Settings) -> str:
    """Save ``new`` and make the Windows task match; the reason when Windows refused."""
    global _settings, problem
    try:
        scheduled_start.apply(new)
    except scheduled_start.TaskError as exc:
        logger.error(f"scheduled start: Windows task not changed ({exc})")
        return tf("Windows 没有接受这个设定：{why}", why=str(exc) or t("原因不明"))
    scheduled_start.save(new)
    _settings = new
    problem = ""
    if new.active_slots() and new.wake and scheduled_start.ensure_wake_timers() is False:
        problem = "电脑睡着时叫不醒：Windows 不让打开唤醒定时器"
        logger.warning("scheduled start: wake timers could not be turned on")
    logger.info(f"scheduled start: saved {new.to_json()}")
    return ""


def set_enabled(on: bool) -> str:
    new = copy.deepcopy(settings())
    new.enabled = on
    return store(new)


def next_text(now: datetime | None = None) -> tuple[str, str]:
    """(time, 「下次 · 今天」) of the next start on the player's clock, or ('', '')."""
    now = now or scheduled_start.local_now()
    moment = scheduled_start.next_run(settings(), now)
    if moment is None:
        return "", ""
    days = (moment.date() - now.date()).days
    if days == 0:
        word = t("下次 · 今天")
    elif days == 1:
        word = t("下次 · 明天")
    else:
        word = tf("下次 · 周{weekday}", weekday=t(WEEKDAYS[moment.weekday()]))
    return moment.strftime("%H:%M"), word


def reset_text() -> str:
    hour, minute = scheduled_start.reset_clock()
    return tf("每天 {time}，游戏重置后 {m} 分钟", time=f"{hour:02d}:{minute:02d}",
              m=scheduled_start.RESET_DELAY_MINUTES)


# ---------------------------------------------------------------- the run

LOCKED_NOTE = (
    "电脑停在锁屏画面，工具没办法操作游戏，这次没有跑。"
    "要让定时启动能跑，Windows 睡醒后不能要求输入密码。"
)
NOT_STARTED_NOTE = "一键日常没能开始（可能有别的任务正在跑），这次没有跑。"
NO_LOGIN_NOTE = "等了 {m} 分钟，游戏还是没打开或没登录进去，这次没有跑。"
# Opening the game and logging in (a patch download included) is done well
# within this; AutoLoginTask gives a stuck login up after 3 x 5 minutes.
WATCHDOG_MINUTES = 25
WATCHDOG_RECHECK_MINUTES = 5
WATCHDOG_RECHECKS = 3
_watch_started: float | None = None


def report_failure(note: str) -> None:
    """A scheduled start that never became a run still ends in a report.

    Leo 2026-10-22: 「設定好定時就不管他 … 有問題也要說」: the 跑完通知
    (run_report.finish) and the 结算 page read it like any other run.
    """
    from src.tasks import run_report
    from src.ui.shell import data

    if run_report.active() is not None:
        return  # a run is going; it reports for itself
    batch = data.task_by_name(data.DAILY_BATCH)
    label = getattr(batch, "batch_label", None) or "一键完成日常"
    logger.warning(f"scheduled start: no run ({note})")
    run_report.begin(label, "定时启动", [])
    run_report.mark("scheduled", True)
    run_report.set_notice(note)
    run_report.finish(run_report.ENDED_ERROR)


def before_start() -> bool:
    """Checks before a scheduled 一键日常; False when it cannot run (reported)."""
    if scheduled_start.screen_locked():
        report_failure(LOCKED_NOTE)
        return False
    scheduled_start.mark_run_pending()
    return True


def after_start(started: bool) -> None:
    """The run was asked for; make sure it really begins (or say why not)."""
    global _watch_started
    import time

    if not started:
        scheduled_start.mark_run_pending(False)
        report_failure(NOT_STARTED_NOTE)
        return
    _watch_started = time.time()
    QTimer.singleShot(WATCHDOG_MINUTES * 60_000, guarded("scheduled start check", _check_begun))


def _begun_since(since: float) -> bool:
    from src.tasks import run_report
    from src.ui.shell import data

    batch = data.task_by_name(data.DAILY_BATCH)
    label = getattr(batch, "batch_label", None) or "一键完成日常"
    for report in (run_report.active(), run_report.load(label)):
        if report and report.get("label") == label and (report.get("started") or 0) >= since:
            return True
    return False


def _check_begun(rechecks: int = 0) -> None:
    from src.ui.shell import data

    since = _watch_started
    if since is None or _begun_since(since):
        return
    if data.busy() and rechecks < WATCHDOG_RECHECKS:
        QTimer.singleShot(
            WATCHDOG_RECHECK_MINUTES * 60_000,
            guarded("scheduled start check", lambda: _check_begun(rechecks + 1)),
        )
        return
    scheduled_start.mark_run_pending(False)
    waited = WATCHDOG_MINUTES + rechecks * WATCHDOG_RECHECK_MINUTES
    report_failure(NO_LOGIN_NOTE.format(m=waited))


# ---------------------------------------------------------------- watch


class _Watch(QObject):
    """While the tool is open, start the run when a slot comes.

    The Windows task's own copy of the tool exits at once then (main.py), so
    this is what starts it; a slot noticed more than a few minutes late (the
    PC slept through it) does not start.
    """

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._last = scheduled_start.local_now()
        self._timer = QTimer(self)
        self._timer.timeout.connect(guarded("scheduled start watch", self._tick))
        self._timer.start(WATCH_MS)

    def _tick(self) -> None:
        from src.ui.shell import autorun

        now = scheduled_start.local_now()
        last, self._last = self._last, now
        due = scheduled_start.due_between(settings(), last, now)
        if due is None:
            return
        logger.info(f"scheduled start: slot {due:%H:%M} came while the tool is open")
        autorun.schedule(scheduled=True)


def start_watch(parent: QObject) -> _Watch:
    return _Watch(parent)


# ---------------------------------------------------------------- window


class DayChip(QAbstractButton):
    """A weekday to tick: a circle, or one even pill when the names are
    longer (Mon, 月曜 …); all seven share one width so the row stays straight."""

    SIZE = 30

    def __init__(self, day: int, on: bool, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(on)
        self.setText(t(WEEKDAYS[day]))
        self.setFixedSize(self.chip_width(self.font()), self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    @classmethod
    def _label_font(cls, base: QFont) -> QFont:
        font = theme.body_font(base)
        font.setPixelSize(13)
        return font

    @classmethod
    def chip_width(cls, base: QFont) -> int:
        metrics = QFontMetrics(cls._label_font(base))
        widest = max(metrics.horizontalAdvance(t(day)) for day in WEEKDAYS)
        return max(cls.SIZE, widest + 16)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        painter.setPen(Qt.NoPen)
        colour = theme.color("primary") if on else theme.color("pill")
        if not self.isEnabled():
            colour.setAlphaF(0.45)
        painter.setBrush(colour)
        radius = self.SIZE / 2
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.SIZE), radius, radius)
        painter.setFont(self._label_font(self.font()))
        painter.setPen(theme.color("on_primary") if on else theme.color("ink2"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())


DELETE_SIZE = 34
OPTION_GAP = 24


def _delete_button(on_click) -> Button:
    button = Button("", "ghost", "trash-2", on_click=on_click)
    button.setFixedSize(DELETE_SIZE, DELETE_SIZE)
    button.setToolTip(t("删除这个时段"))
    return button


class SlotRow(Inset):
    RIGHT_PAD = 8
    GAP = 12

    def __init__(self, slot: Slot, on_delete):
        super().__init__()
        self.slot = slot
        row = hbox(self, (14, 10, self.RIGHT_PAD, 10), self.GAP)
        self.days: list[DayChip] = []
        self.picker = None
        if slot.kind == KIND_RESET:
            row.addWidget(IconTile("sun", 36))
            titles = vbox(None, (0, 0, 0, 0), 2)
            titles.addWidget(Text("游戏每天重置后", "h3"))
            titles.addWidget(Text(reset_text(), "muted"))
            row.addLayout(titles)
        else:
            from qfluentwidgets import TimePicker

            self.picker = TimePicker(self)
            # Two narrow columns: the default 120 px each pushed the days off.
            for column in (0, 1):
                self.picker.setColumnWidth(column, 56)
            self.picker.setTime(QTime(slot.hour, slot.minute))
            self.picker.timeChanged.connect(self._time_changed)
            row.addWidget(self.picker)
            chips = hbox(None, (0, 0, 0, 0), 5)
            for day in range(7):
                chip = DayChip(day, day in slot.days)
                chip.toggled.connect(self._days_changed)
                chips.addWidget(chip)
                self.days.append(chip)
            row.addLayout(chips)
        row.addStretch(1)
        self.toggle = Toggle(slot.on, small=True)
        self.toggle.setToolTip(t("只开关这个时段"))
        self.toggle.toggled.connect(self._on_changed)
        row.addWidget(self.toggle)
        row.addWidget(_delete_button(lambda: on_delete(self)))
        self._dim()

    def _time_changed(self, value: QTime) -> None:
        self.slot.hour, self.slot.minute = value.hour(), value.minute()

    def _days_changed(self) -> None:
        self.slot.days = [day for day, chip in enumerate(self.days) if chip.isChecked()]

    def _on_changed(self, on: bool) -> None:
        self.slot.on = on
        self._dim()

    def _dim(self) -> None:
        for widget in [self.picker, *self.days]:
            if widget is not None:
                widget.setEnabled(self.slot.on)


class ScheduleDialog(_Floating):
    PANEL_WIDTH = 600

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)
        self.working = copy.deepcopy(settings())
        column = self.column

        head = hbox(None, (0, 0, 0, 0), 12)
        head.addWidget(HeroIcon("clock", 44))
        titles = vbox(None, (0, 0, 0, 0), 2)
        titles.addWidget(Text("定时启动", "h2"))
        titles.addWidget(Text("时间到自动打开游戏，跑今天还没做的", "sub", wrap=True))
        head.addLayout(titles, 1)
        self.master = Toggle(self.working.enabled)
        self.master.setToolTip(t("关掉就完全取消，Windows 里也不留"))
        self.master.toggled.connect(self._master_changed)
        head.addWidget(self.master, 0, Qt.AlignVCenter)
        # Over the slots' own switches, not over their delete buttons.
        head.addSpacing(SlotRow.RIGHT_PAD + SlotRow.GAP + DELETE_SIZE)
        column.addLayout(head)

        self.body = QWidget()
        body = vbox(self.body, (0, 4, 0, 0), 12)
        self.rows_box = vbox(None, (0, 0, 0, 0), 10)
        body.addLayout(self.rows_box)
        adds = hbox(None, (0, 0, 0, 0), 8)
        self.add_time = Button("新增时段", "ghost", "plus", on_click=self._add_time)
        self.add_reset = Button("加回「游戏每天重置后」", "ghost", "plus", on_click=self._add_reset)
        for button in (self.add_time, self.add_reset):
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            adds.addWidget(button)
        adds.addStretch(1)
        body.addLayout(adds)
        body.addWidget(Separator())
        self.wake = CheckBox("电脑睡着时叫醒它", self.working.wake)
        self.wake.setToolTip(t("睡眠中会被叫醒；完全关机的电脑叫不醒"))
        # Only for the runs 定时启动 starts (Leo 2026-10-22: set it and leave it).
        self.close_game = CheckBox("做完关闭游戏", self.working.close_game)
        self.shutdown = CheckBox("做完关机", self.working.shutdown)
        for box in (self.close_game, self.shutdown):
            box.setToolTip(t("定时启动跑的那次，全部做完且没有失败时才会做"))
        boxes = (self.wake, self.close_game, self.shutdown)
        # One row when it fits; longer words (日本語) get one line each
        # instead of running past the window's edge.
        width = sum(box.sizeHint().width() for box in boxes) + OPTION_GAP * 2
        one_row = width <= self.PANEL_WIDTH - 2 * 28 - 8
        if one_row:
            options = hbox(None, (0, 2, 0, 0), OPTION_GAP)
        else:
            options = vbox(None, (0, 2, 0, 0), 8)
        for box in boxes:
            options.addWidget(box)
        if one_row:
            options.addStretch(1)
        body.addLayout(options)
        column.addWidget(self.body)

        self.message = Text("", "warn", wrap=True)
        self.message.hide()
        column.addWidget(self.message)
        buttons = hbox(None, (0, 6, 0, 0), 8)
        buttons.addStretch(1)
        buttons.addWidget(Button("取消", "secondary", on_click=self.reject))
        buttons.addWidget(Button("保存", "primary", on_click=self._save))
        column.addLayout(buttons)

        self._rows: list[SlotRow] = []
        self._fill()
        self._master_changed(self.working.enabled)

    def _fill(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for slot in self.working.slots:
            row = SlotRow(slot, self._delete)
            self.rows_box.addWidget(row)
            self._rows.append(row)
        has_reset = any(slot.kind == KIND_RESET for slot in self.working.slots)
        self.add_reset.setVisible(not has_reset)
        self.add_time.setEnabled(len(self.working.slots) < MAX_SLOTS)
        self._place()

    def _delete(self, row: SlotRow) -> None:
        self.working.slots.remove(row.slot)
        self._fill()

    def _add_time(self) -> None:
        if len(self.working.slots) < MAX_SLOTS:
            self.working.slots.append(Slot(KIND_TIME))
            self._fill()

    def _add_reset(self) -> None:
        self.working.slots.insert(0, Slot(KIND_RESET))
        self._fill()

    def _master_changed(self, on: bool) -> None:
        self.working.enabled = on
        self.body.setEnabled(on)

    def _save(self) -> None:
        self.working.wake = self.wake.isChecked()
        self.working.close_game = self.close_game.isChecked()
        self.working.shutdown = self.shutdown.isChecked()
        why = store(self.working)
        if why:
            self.message.set_text(why)
            self.message.show()
            self._place()
            return
        self.accept()
