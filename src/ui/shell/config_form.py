"""A task's own settings as a short form: label on the left, control on the right.

Uses the same config, types, hidden rows and sub-settings as the old task
cards, so nothing a task reads changes; long explanations move into the
ⓘ tooltip next to each label.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget
from qfluentwidgets import ComboBox, DoubleSpinBox, FlowLayout, LineEdit, SpinBox

from src.ui.hide_config_rows import mark_hidden_config_keys
from src.ui.shell.widgets import (
    Button,
    CheckBox,
    IconLabel,
    Segmented,
    Text,
    Toggle,
    attach_hint,
    hbox,
    t,
    vbox,
)

SEGMENTED_MAX_TEXT = 26
# Task class -> the only settings that keep their ⓘ hint (Leo, 2026-10-04:
# 「日常設定 下面的備注 ... 不需要」).  Only the hint goes; the setting stays.
HINTS_KEPT = {
    "DailyTask": (),
    "QuickHuntTask": (),
    "JunkGearTask": ("分解3星4星角色的UR专用",),
    "PVPTask": ("舞台移动方式",),
    "EventBattleTask": ("全部通关后快速战斗",),
    "MissionRewardTask": (),
    "MailRewardTask": (),
}


def _type_of(task, key) -> dict:
    the_type = (getattr(task, "config_type", None) or {}).get(key)
    if isinstance(the_type, dict):
        return the_type
    if the_type is None:
        return {}
    return {"type": the_type}


def hidden_keys(task) -> set[str]:
    try:
        mark_hidden_config_keys(task)
    except Exception:
        pass
    hidden = set()
    for key in task.config.keys():
        if str(key).startswith("_") or _type_of(task, key).get("hidden"):
            hidden.add(key)
    return hidden


def visible_keys(task, skip: Iterable[str] = ()) -> list[str]:
    skip = set(skip) | hidden_keys(task)
    order = list((getattr(task, "default_config", None) or {}).keys())
    keys = [key for key in order if key in task.config]
    keys += [key for key in task.config.keys() if key not in keys]
    return [key for key in keys if key not in skip]


def parents(task) -> dict[str, tuple[str, object]]:
    """key -> (parent key, value the parent must have for it to show)."""
    result: dict[str, tuple[str, object]] = {}
    for key, the_type in (getattr(task, "config_type", None) or {}).items():
        if not isinstance(the_type, dict):
            continue
        rules = the_type.get("sub_configs")
        if not isinstance(rules, dict):
            continue
        for value, children in rules.items():
            if isinstance(children, str):
                children = [children]
            for child in children or ():
                result.setdefault(child, (key, value))
    return result


def condition_met(task, key: str, rules: dict[str, tuple[str, object]]) -> bool:
    seen = set()
    while key in rules and key not in seen:
        seen.add(key)
        parent, value = rules[key]
        current = task.config.get(parent)
        if isinstance(value, str) and isinstance(current, bool):
            current = str(current).lower()
        if current != value:
            return False
        key = parent
    return True


def _label_text(task, key: str) -> str:
    try:
        from ok import og

        return og.app.tr(key)
    except Exception:
        return key


class ConfigForm(QWidget):
    """Rows for ``keys`` of ``task.config``; writes go straight to the config."""

    def __init__(
        self,
        task,
        keys: list[str] | None = None,
        skip: Iterable[str] = (),
        labels: dict[str, str] | None = None,
        parent=None,
        on_change: Callable[[str], None] | None = None,
        right_inset: int = 0,
    ):
        super().__init__(parent)
        self.task = task
        self._labels = labels or {}
        self._on_change = on_change
        self.keys = keys if keys is not None else visible_keys(task, skip)
        self._rules = parents(task)
        self._rows: dict[str, tuple[QWidget, QWidget, Callable[[], None]]] = {}
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, right_inset, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(1, 1)
        row = 0
        for key in self.keys:
            label = self._label(key)
            control, sync = self._control(key)
            if _type_of(task, key).get("type") == "multi_selection":
                # Long option lists get the full width under their label.
                self.grid.addWidget(label, row, 0, 1, 2, Qt.AlignLeft | Qt.AlignVCenter)
                self.grid.addWidget(control, row + 1, 0, 1, 2)
                row += 2
            else:
                # Text boxes fill the row; switches and pickers sit on the right.
                align = Qt.AlignVCenter
                if not isinstance(control, LineEdit):
                    align |= Qt.AlignRight
                self.grid.addWidget(label, row, 0, Qt.AlignLeft | Qt.AlignVCenter)
                self.grid.addWidget(control, row, 1, align)
                row += 1
            self._rows[key] = (label, control, sync)
        self.sync()

    def is_empty(self) -> bool:
        return not self.keys

    # ---------------------------------------------------------------- rows

    def _label(self, key: str) -> QWidget:
        box = QWidget(self)
        row = hbox(box, (0, 0, 0, 0), 4)
        row.addWidget(Text(self._labels.get(key) or _label_text(self.task, key), "sub"))
        description = (getattr(self.task, "config_description", None) or {}).get(key)
        kept = HINTS_KEPT.get(type(self.task).__name__)
        if kept is not None and key not in kept:
            description = None
        # The ⓘ only where there is a hint to read; hovering the words shows it too.
        if description and str(description).strip() and attach_hint(box, t(str(description))):
            row.addWidget(IconLabel("info", 13, "ink3"))
        return box

    def _set(self, key: str, value) -> None:
        self.task.config[key] = value
        if self._on_change is not None:
            self._on_change(key)
        self.sync()

    def _control(self, key: str):
        value = self.task.config.get(key)
        the_type = _type_of(self.task, key)
        kind = the_type.get("type")
        if kind == "drop_down":
            return self._drop_down(key, list(the_type.get("options") or []))
        if kind == "multi_selection":
            return self._multi(key, list(the_type.get("options") or []))
        if kind == "button":
            return self._buttons(key, the_type)
        if isinstance(value, bool):
            toggle = Toggle(bool(value), self)
            toggle.toggled.connect(lambda checked, k=key: self._set(k, bool(checked)))
            return toggle, lambda: toggle.set_checked_quietly(bool(self.task.config.get(key)))
        if isinstance(value, int):
            spin = SpinBox(self)
            spin.setRange(int(the_type.get("min", -999999)), int(the_type.get("max", 999999)))
            spin.setValue(int(value))
            spin.setFixedWidth(150)
            spin.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
            return spin, lambda: self._quiet(
                spin, lambda: spin.setValue(int(self.task.config.get(key) or 0))
            )
        if isinstance(value, float):
            spin = DoubleSpinBox(self)
            spin.setRange(
                float(the_type.get("min", -999999.0)), float(the_type.get("max", 999999.0))
            )
            step = float(the_type.get("step", 0.1))
            spin.setSingleStep(step)
            spin.setDecimals(2 if step < 0.1 else 1)
            spin.setValue(float(value))
            spin.setFixedWidth(150)
            spin.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            return spin, lambda: self._quiet(
                spin, lambda: spin.setValue(float(self.task.config.get(key) or 0))
            )
        if isinstance(value, str):
            edit = LineEdit(self)
            edit.setMinimumWidth(180)
            edit.editingFinished.connect(lambda k=key, e=edit: self._set(k, e.text()))

            def sync_edit():
                if edit.hasFocus():
                    return
                text = str(self.task.config.get(key) or "")
                if edit.text() != text:
                    edit.setText(text)
                edit.setCursorPosition(0)  # show the start of long text

            sync_edit()
            return edit, sync_edit
        shown = Text(str(value), "muted")
        return shown, lambda: shown.set_text(str(self.task.config.get(key)))

    @staticmethod
    def _quiet(widget: QWidget, action: Callable[[], None]) -> None:
        widget.blockSignals(True)
        try:
            action()
        finally:
            widget.blockSignals(False)

    def _drop_down(self, key: str, options: list[str]):
        if len(options) <= 4 and sum(len(str(option)) for option in options) <= SEGMENTED_MAX_TEXT:
            segmented = Segmented(options, str(self.task.config.get(key)), self)
            segmented.changed.connect(lambda v, k=key: self._set(k, v))
            return segmented, lambda: segmented.set_value(str(self.task.config.get(key)))
        combo = ComboBox(self)
        for option in options:
            combo.addItem(t(str(option)), userData=option)
        combo.setMinimumWidth(200)

        def select():
            current = self.task.config.get(key)
            index = options.index(current) if current in options else -1
            if index >= 0 and combo.currentIndex() != index:
                self._quiet(combo, lambda: combo.setCurrentIndex(index))

        select()
        combo.currentIndexChanged.connect(
            lambda index, k=key: self._set(k, options[index]) if 0 <= index < len(options) else None
        )
        return combo, select

    def _multi(self, key: str, options: list[str]):
        box = QWidget(self)
        flow = FlowLayout(box, needAni=False)
        flow.setContentsMargins(0, 0, 0, 2)
        flow.setHorizontalSpacing(16)
        flow.setVerticalSpacing(8)
        boxes = {}
        for option in options:
            check = CheckBox(str(option), option in (self.task.config.get(key) or []), box)
            check.toggled.connect(lambda _c, k=key: self._set_multi(k, options, boxes))
            flow.addWidget(check)
            boxes[option] = check

        def sync():
            selected = set(self.task.config.get(key) or [])
            for option, check in boxes.items():
                check.set_checked_quietly(option in selected)

        return box, sync

    def _set_multi(self, key: str, options: list[str], boxes: dict) -> None:
        self._set(key, [option for option in options if boxes[option].isChecked()])

    def _buttons(self, key: str, the_type: dict):
        box = QWidget(self)
        row = hbox(box, (0, 0, 0, 0), 8)
        buttons = the_type.get("buttons") or [the_type]
        for spec in buttons:
            callback = spec.get("callback")
            button = Button(
                str(spec.get("text") or key),
                "secondary",
                size="sm",
                on_click=callback if callable(callback) else None,
            )
            row.addWidget(button)
        row.addStretch(1)
        return box, lambda: None

    # ---------------------------------------------------------------- state

    def sync(self) -> None:
        """Show only rows whose parent switch allows them; match saved values."""
        for key, (label, control, sync) in self._rows.items():
            visible = condition_met(self.task, key, self._rules)
            label.setVisible(visible)
            control.setVisible(visible)
            if visible:
                sync()
        self.updateGeometry()

    def reset(self) -> None:
        for key in self.keys:
            default = self.task.config.get_default(key)
            if default is not None:
                self.task.config[key] = default
        self.sync()


def form_card_body(form: ConfigForm, title: str | None = None) -> QWidget:
    box = QWidget()
    column = vbox(box, (0, 0, 0, 0), 10)
    if title:
        column.addWidget(Text(title, "h3"))
    column.addWidget(form)
    return box
