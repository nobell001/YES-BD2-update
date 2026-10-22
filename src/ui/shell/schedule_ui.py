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
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QAbstractButton, QGraphicsEffect, QSizePolicy, QWidget
from qfluentwidgets import ComboBox, ScrollArea

from src.ui.shell import motion, theme
from src.ui.shell.floating import Floating
from src.ui.shell.run_confirm import HeroIcon
from src.ui.shell.safe import guarded
from src.ui.shell.widgets import (
    Button,
    CheckBox,
    Inset,
    Separator,
    Text,
    Toggle,
    hbox,
    mix,
    set_prop,
    t,
    tf,
    vbox,
)
from src.utils import scheduled_start
from src.utils.scheduled_start import KIND_TIME, MAX_SLOTS, Settings, Slot

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
    current = settings()
    if current.migrated:
        # An older save (「游戏每天重置后」, minutes off the quarter): the
        # Windows task still holds the old times until it is written again.
        why = store(copy.deepcopy(current))
        if why:
            logger.warning(f"scheduled start: old settings not rewritten ({why})")
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
        # The colour slides between off and on (Leo 2026-10-22 「加一點小動效」).
        self._fill = motion.Tween(self, self.update, 160, 1.0 if on else 0.0)
        self.toggled.connect(lambda checked: self._fill.go(1.0 if checked else 0.0))

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
        fill = float(self._fill.value)
        painter.setPen(Qt.NoPen)
        colour = mix(theme.color("pill"), theme.color("primary"), fill)
        if not self.isEnabled():
            colour.setAlphaF(0.45)
        painter.setBrush(colour)
        # A little pop while it turns on: from 90 % up to full size.
        grow = 1.0 - 0.1 * (1.0 - fill) if self.isChecked() else 1.0
        box = QRectF(0, 0, self.width(), self.SIZE)
        inset_x, inset_y = box.width() * (1 - grow) / 2, box.height() * (1 - grow) / 2
        box.adjust(inset_x, inset_y, -inset_x, -inset_y)
        radius = box.height() / 2
        painter.drawRoundedRect(box, radius, radius)
        painter.setFont(self._label_font(self.font()))
        painter.setPen(mix(theme.color("ink2"), theme.color("on_primary"), fill))
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())


class _Slide(QGraphicsEffect):
    """Draws its widget faded and a few px low; ``progress`` 1 is as is."""

    RISE_PX = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0

    def draw(self, painter):
        painter.save()
        painter.setOpacity(self.progress)
        painter.translate(0, self.RISE_PX * (1 - self.progress))
        self.drawSource(painter)
        painter.restore()


def slide(widget: QWidget, out: bool = False, done=None, duration: int = 220) -> None:
    """Fade ``widget`` in from a little below (or out, then call ``done``)."""
    effect = _Slide(widget)
    effect.progress = 1.0 if out else 0.0
    widget.setGraphicsEffect(effect)
    anim = QVariantAnimation(widget)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.OutCubic if not out else QEasingCurve.InCubic)
    anim.setStartValue(effect.progress)
    anim.setEndValue(0.0 if out else 1.0)

    def step(value) -> None:
        effect.progress = float(value)
        effect.update()

    def finished() -> None:
        if not out:
            widget.setGraphicsEffect(None)  # nothing left to draw differently
        if done is not None:
            done()

    anim.valueChanged.connect(step)
    anim.finished.connect(finished)
    anim.start(QVariantAnimation.DeleteWhenStopped)


DELETE_SIZE = 34
OPTION_GAP = 24


def _delete_button(on_click) -> Button:
    button = Button("", "ghost", "trash-2", on_click=on_click)
    button.setFixedSize(DELETE_SIZE, DELETE_SIZE)
    button.setToolTip(t("删除这个时段"))
    return button


TIME_BOX_WIDTH = 76
HOURS = range(24)
MINUTES = range(0, 60, scheduled_start.MINUTE_STEP)


class _RowsView(ScrollArea):
    """Asks for all its rows' height, makes do with one: when the tool window
    is too short (5 slots at 175 % on a 1080p screen) the rows scroll
    instead of being squashed."""

    def setWidget(self, widget: QWidget) -> None:
        super().setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        # The rows changed: this view's own wish changed with them, and the
        # window must hear of it (a scroll area does not pass it on).
        if watched is self.widget() and event.type() == QEvent.LayoutRequest:
            self.updateGeometry()
        return super().eventFilter(watched, event)

    def sizeHint(self) -> QSize:
        content = self.widget()
        hint = content.sizeHint() if content is not None else QSize(0, 0)
        return QSize(hint.width(), hint.height())

    def minimumSizeHint(self) -> QSize:
        content = self.widget()
        layout = content.layout() if content is not None else None
        first = layout.itemAt(0) if layout is not None and layout.count() else None
        return QSize(0, first.sizeHint().height() if first is not None else 0)


def _number_box(values: range, value: int, on_change) -> ComboBox:
    box = ComboBox()
    box.addItems([f"{n:02d}" for n in values])
    box.setCurrentIndex(min(range(len(values)), key=lambda i: abs(values[i] - value)))
    box.setMaxVisibleItems(8)
    box.setFixedWidth(TIME_BOX_WIDTH)
    box.currentIndexChanged.connect(on_change)
    return box


class SlotRow(Inset):
    RIGHT_PAD = 8
    GAP = 12

    def __init__(self, slot: Slot, on_delete, on_change):
        super().__init__()
        self.slot = slot
        self._on_change = on_change
        # Always a 1 px edge (clear until something is wrong), so a marked
        # row's contents do not move by that pixel.
        self.setProperty("outlined", True)
        lines = vbox(self, (14, 10, self.RIGHT_PAD, 10), 6)
        row = hbox(None, (0, 0, 0, 0), self.GAP)
        lines.addLayout(row)
        self.days: list[DayChip] = []
        # Two plain lists, 00-23 and 00/15/30/45: they open right under
        # themselves.  qfluentwidgets' TimePicker opened a wheel whose
        # highlight sat crooked and wrote 0 for 00 (Leo 2026-10-22).
        clock = hbox(None, (0, 0, 0, 0), 4)
        self.hour = _number_box(HOURS, slot.hour, self._time_changed)
        self.minute = _number_box(MINUTES, slot.minute, self._time_changed)
        clock.addWidget(self.hour)
        clock.addWidget(Text(":", "h3"))
        clock.addWidget(self.minute)
        row.addLayout(clock)
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
        # Why this slot cannot be saved (a clash, no day ticked).
        self.problem = Text("", "bad", wrap=True)
        self.problem.hide()
        lines.addWidget(self.problem)
        self._dim()

    def set_problem(self, why: str) -> None:
        shown = self.problem.isVisibleTo(self)
        self.problem.set_text(why)
        self.problem.setVisible(bool(why))
        set_prop(self, "bad", bool(why))
        if why and not shown and self.isVisible():
            slide(self.problem, duration=180)

    def _time_changed(self, _index: int = 0) -> None:
        self.slot.hour = HOURS[self.hour.currentIndex()]
        self.slot.minute = MINUTES[self.minute.currentIndex()]
        self._on_change()

    def _days_changed(self) -> None:
        self.slot.days = [day for day, chip in enumerate(self.days) if chip.isChecked()]
        self._on_change()

    def _on_changed(self, on: bool) -> None:
        self.slot.on = on
        self._dim()
        self._on_change()

    def _dim(self) -> None:
        for widget in [self.hour, self.minute, *self.days]:
            widget.setEnabled(self.slot.on)


class ScheduleDialog(Floating):
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
        # The rows scroll only when the tool window is too short for all of
        # them (5 slots at 175 % on a 1080p screen); otherwise all show.
        # Selectors by name: a bare 「background: transparent」 would reach
        # the rows too and wipe their own background.
        self.rows_holder = QWidget()
        self.rows_holder.setObjectName("slotRows")
        self.rows_holder.setStyleSheet("QWidget#slotRows { background: transparent; }")
        self.rows_box = vbox(self.rows_holder, (0, 0, 0, 0), 10)
        self.scroll = _RowsView()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(ScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.viewport().setObjectName("slotView")
        self.scroll.viewport().setStyleSheet("QWidget#slotView { background: transparent; }")
        self.scroll.setWidget(self.rows_holder)
        body.addWidget(self.scroll, 1)
        adds = hbox(None, (0, 0, 0, 0), 8)
        self.add_time = Button("新增时段", "ghost", "plus", on_click=self._add_time)
        self.add_time.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        adds.addWidget(self.add_time)
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
        # Leo 2026-10-22 「要備註關機時不能使用」.
        body.addWidget(Text("电脑完全关机时不会启动；睡眠中可以叫醒", "muted", wrap=True))
        column.addWidget(self.body)

        self.message = Text("", "warn", wrap=True)
        self.message.hide()
        column.addWidget(self.message)
        buttons = hbox(None, (0, 6, 0, 0), 8)
        buttons.addStretch(1)
        buttons.addWidget(Button("取消", "secondary", on_click=self.reject))
        self.save_button = Button("保存", "primary", on_click=self._save)
        buttons.addWidget(self.save_button)
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
            row = SlotRow(slot, self._delete, self._check)
            self.rows_box.addWidget(row)
            self._rows.append(row)
        room = len(self.working.slots) < MAX_SLOTS
        self.add_time.setEnabled(room)
        self.add_time.setToolTip("" if room else tf("最多 {n} 个时段", n=MAX_SLOTS))
        self._check()
        self.scroll.setVisible(bool(self._rows))
        self.scroll.updateGeometry()
        self._place()

    def least_width(self) -> int:
        # A scroll area asks for no width of its own: count the rows' need.
        margins = self.column.contentsMargins()
        rows = self.rows_holder.minimumSizeHint().width() + margins.left() + margins.right()
        return max(super().least_width(), rows)

    def _delete(self, row: SlotRow) -> None:
        if row.slot not in self.working.slots:
            return  # already going
        self.working.slots.remove(row.slot)
        if row.isVisible():
            row.setEnabled(False)
            slide(row, out=True, done=self._fill, duration=160)
        else:
            self._fill()

    def _add_time(self) -> None:
        # A time no slot uses yet, not a copy of the last one (Leo 2026-10-22
        # 「時間不可以衝突吧」).
        if len(self.working.slots) < MAX_SLOTS:
            hour, minute = scheduled_start.free_time(self.working.slots)
            self.working.slots.append(Slot(KIND_TIME, hour, minute))
            self._fill()
            slide(self._rows[-1])
            # The new row may be below the fold when the rows scroll.
            QTimer.singleShot(0, lambda: self.scroll.ensureWidgetVisible(self._rows[-1]))

    def _check(self) -> None:
        """Mark the slots that cannot be saved; 保存 waits until none is left."""
        problems = scheduled_start.slot_problems(self.working.slots)
        for row, why in zip(self._rows, problems):
            row.set_problem(why)
        self.save_button.setEnabled(not (self.working.enabled and any(problems)))

    def _master_changed(self, on: bool) -> None:
        self.working.enabled = on
        self.body.setEnabled(on)
        self._check()

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
