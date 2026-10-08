"""The game's 强化设置 dialog, shared by the bag's 一键强化 and 装备制作.

Both entry points open the same dialog (简体 client, 2026-09-26): a target
level row, then either 强化尝试次数 / 金额上限 (自动分解 off) or a fixed-count
layout with an item-count row once 自动分解 is on — 已选择装备 in the bag,
装备制作数量 when crafting.  The game resets 自动分解 to off every time.
"""

from __future__ import annotations

from time import monotonic

import re

import cv2
from ok.task.exceptions import FinishedException, TaskDisabledException

from src.tasks.task_vision_mixin import REFERENCE_HEIGHT, REFERENCE_WIDTH
from src.utils.colour_rules import switch_yellow_ratio
from src.utils.ocr_utils import keyword_match_count, normalize_ocr_text
from src.utils.pvp_dialog import adjust_step

# 1920x1080 reference coordinates / ROIs.
ENHANCE_DIALOG_ROI = (570, 220, 780, 460)
# Row label plus the number printed under it.  Read together: a tight crop
# of the lone digit read "4" as "A" (live 2026-09-26), with the label every
# value 1-9 read correctly, and the label proves which row was read.
TARGET_ROW_ROI = (590, 320, 230, 75)
TARGET_ROW_LABEL = "单个目标强化值"
COUNT_ROW_ROI = (590, 560, 230, 75)
# The bag's selected-count digit, read alone (its row label was never
# confirmed by OCR).
COUNT_DIGIT_ROI = (585, 592, 80, 38)
COUNT_STEP_POINTS = {"plus": (1301, 586), "minus": (817, 586)}
AUTO_LAYOUT_TEXT = "系统会根据平均成功率"
LONE_NUMBER_PAD = 30
TARGET_PRESETS = {3: (993, 390), 6: (1124, 390)}
TARGET_MIN_POINT = (864, 390)
TARGET_STEP_POINTS = {"plus": (1301, 344), "minus": (817, 344)}
AUTO_DISMANTLE_SWITCH_POINT = (1297, 707)
AUTO_DISMANTLE_SWITCH_ROI = (1265, 690, 65, 35)
ENHANCE_CANCEL_POINT = (875, 828)
ENHANCE_START_ROI = (960, 800, 170, 60)
RESULT_ROI = (560, 250, 800, 520)
YELLOW_ON_RATIO = 0.05


def yellow_ratio(crop) -> float:
    """Share of the yellow 'on' colour used by the game's toggles."""
    return switch_yellow_ratio(crop)


def crop_reference(frame, roi):
    height, width = frame.shape[:2]
    x, y, w, h = roi
    return frame[
        round(y / REFERENCE_HEIGHT * height) : round((y + h) / REFERENCE_HEIGHT * height),
        round(x / REFERENCE_WIDTH * width) : round((x + w) / REFERENCE_WIDTH * width),
    ]


# Letters a lone digit is misread as.  Live 2K 2026-09-30: the 已选择装备
# count "4" read "a" and the run stopped before dismantling anything.
DIGIT_LOOKALIKES = str.maketrans(
    {"a": "4", "A": "4", "l": "1", "I": "1", "i": "1", "|": "1", "O": "0", "o": "0",
     "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "b": "6", "q": "9", "g": "9"}
)


def lone_digits(text: str) -> str:
    """A 1-3 character read made only of digits and digit look-alikes, as
    digits; anything else is returned unchanged (and so rejected)."""
    compact = str(text).replace(" ", "")
    if 1 <= len(compact) <= 3:
        mapped = compact.translate(DIGIT_LOOKALIKES)
        if mapped.isdigit():
            return mapped
    return str(text)


def row_number(boxes, label: str) -> int | None:
    """The single number under a row label, or None if either is missing."""
    texts = [normalize_ocr_text(getattr(box, "name", "")) for box in boxes]
    if keyword_match_count(" ".join(texts), (label,), fuzzy_ratio=0.8) < 1:
        return None
    numbers = [text.replace(",", "") for text in texts if re.fullmatch(r"\d[\d,]*", text)]
    return int(numbers[0]) if len(numbers) == 1 else None


class EnhanceDialogMixin:
    """Needs ClaimPageMixin (_roi_boxes, _reference_boxes, _box_with, ...) in the MRO."""

    def _wait_until(self, check, timeout: float, interval: float = 0.4) -> bool:
        end_at = monotonic() + timeout
        while True:
            if check():
                return True
            if monotonic() >= end_at:
                return False
            self.sleep(interval)

    def _dialog_text(self) -> str:
        boxes = self._roi_boxes(self.capture_frame(), ENHANCE_DIALOG_ROI, "强化设置")
        return self._boxes_text(boxes)

    def _lone_number(self, roi: tuple[int, int, int, int], name: str) -> int | None:
        """Read a single number from a tight crop at 4K detail with a margin.

        The shared OCR path shrinks crops to 1080p, where the thin lone "7"
        of the target level was never detected, and the text detector found
        the lone "4" of 已选择装备 only once the crop had a margin around it
        (live 2026-09-26).
        """
        for attempt in range(3):
            frame = self.capture_frame()
            crop = crop_reference(frame, roi)
            scale = max(1.0, 2160 / max(1, frame.shape[0]))
            if scale != 1.0:
                crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            padded = cv2.copyMakeBorder(
                crop,
                LONE_NUMBER_PAD,
                LONE_NUMBER_PAD,
                LONE_NUMBER_PAD,
                LONE_NUMBER_PAD,
                cv2.BORDER_REPLICATE,
            )
            try:
                boxes = self.ocr(frame=padded, threshold=0.5, target_height=0, log=False, name=name)
            except (TaskDisabledException, FinishedException):
                raise
            except Exception as exc:
                self.info_set(f"{name} OCR 错误", str(exc))
                boxes = []
            text = normalize_ocr_text(self._boxes_text(boxes))
            self.info_set(f"{name} OCR", text or "-")
            text = lone_digits(text)
            match = re.fullmatch(r"(\d{1,3})", text.replace(",", ""))
            if match:
                return int(match.group(1))
            if attempt < 2:
                self.sleep(0.4)
        return None

    def _row_value(self, roi: tuple[int, int, int, int], label: str, name: str) -> int | None:
        for attempt in range(3):
            boxes = self._roi_boxes(self.capture_frame(), roi, name)
            self.info_set(f"{name} OCR", self._boxes_text(boxes) or "-")
            value = row_number(boxes, label)
            if value is not None:
                return value
            if attempt < 2:
                self.sleep(0.4)
        return None

    def _target_value(self) -> int | None:
        return self._row_value(TARGET_ROW_ROI, TARGET_ROW_LABEL, "目标等级")

    def _auto_dismantle_on(self) -> bool:
        crop = crop_reference(self.capture_frame(), AUTO_DISMANTLE_SWITCH_ROI)
        return yellow_ratio(crop) > YELLOW_ON_RATIO

    # -- dialog steps ----------------------------------------------------------------------

    def _enable_auto_dismantle(self, label: str, row_text: str | None = None) -> bool:
        """Switch 自动分解 on first: it re-lays out the dialog.

        ``row_text``, when given, names the item-count row the new layout
        must show (装备制作数量 was read live; the bag's label was not).
        """
        for _ in range(3):
            if self._auto_dismantle_on():
                break
            self._click_reference(*AUTO_DISMANTLE_SWITCH_POINT, after_sleep=0.8)
            # Let a slow switch finish before judging it: a second click
            # while it still read OFF would turn it back off.
            if self._wait_until(self._auto_dismantle_on, 2.0):
                break
        if not self._auto_dismantle_on():
            self.log_info(f"{label}：无法确认「自动分解」已开启。")
            return False
        wanted_row = normalize_ocr_text(row_text) if row_text is not None else None
        text = ""

        def laid_out() -> bool:
            nonlocal text
            text = normalize_ocr_text(self._dialog_text())
            return AUTO_LAYOUT_TEXT in text and (wanted_row is None or wanted_row in text)

        self._wait_until(laid_out, 3.0)
        missing_row = wanted_row is not None and wanted_row not in text
        if AUTO_LAYOUT_TEXT not in text or missing_row:
            self.log_info(f"{label}：自动分解开启后的强化设置画面不符，取消。")
            return False
        self.info_set("自动分解", "开")
        return True

    def _set_target_level(self, target: int, label: str) -> bool:
        preset = max((value for value in TARGET_PRESETS if value <= target), default=None)
        point = TARGET_PRESETS[preset] if preset else TARGET_MIN_POINT
        self._click_reference(*point, after_sleep=0.6)
        for _ in range(12):
            current = self._target_value()
            if current is None:
                self.log_info(f"{label}：读不到目标强化等级。")
                return False
            step = adjust_step(current, target, 99)
            if step is None:
                break
            self._click_reference(*TARGET_STEP_POINTS[step], after_sleep=0.5)
        if self._target_value() != target:
            self.log_info(f"{label}：无法把目标强化等级设为 {target}。")
            return False
        self.info_set("目标强化等级", target)
        return True

    def _set_item_count(self, planned: int, row_name: str, label: str) -> bool:
        """Step the item-count row to ``planned`` with its − / + buttons."""
        for _ in range(12):
            current = self._row_value(COUNT_ROW_ROI, row_name, row_name)
            if current is None:
                self.log_info(f"{label}：读不到{row_name}。")
                return False
            step = adjust_step(current, planned, 999)
            if step is None:
                break
            self._click_reference(*COUNT_STEP_POINTS[step], after_sleep=0.5)
        current = self._row_value(COUNT_ROW_ROI, row_name, row_name)
        if current != planned:
            self.log_info(f"{label}：{row_name} {current} 与计划 {planned} 不符。")
            return False
        self.info_set(row_name, current)
        return True

    def _enhance_start_box(self):
        buttons = self._reference_boxes(self.capture_frame(), ENHANCE_START_ROI, "强化按钮")
        return self._box_with(buttons, ("强化",))
