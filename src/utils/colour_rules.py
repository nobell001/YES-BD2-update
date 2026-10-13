"""Colour rules shared by several pages, written to survive a brighter,
darker or more saturated capture (HDR, gamma, vibrance or tint filters;
Leo 2026-09-30: such settings must not break the judgement)."""

from __future__ import annotations

import cv2
import numpy as np

# The yellow "on" colour of the game's toggles (bag 查看详情, 免费AP, lock):
# live BGR (23, 128, 169), HSV (22, 220, 169).  The per-channel rule alone
# sat right at its edges (r > 150, g > 110): a capture 25 % darker read every
# switch as off, one washed out by HDR pushed blue over 90.  Hue, saturation
# and brightness floors keep "on" under both; an off switch is grey or blue.
SWITCH_YELLOW_HUE = (15, 35)
SWITCH_YELLOW_MIN_SATURATION = 120
SWITCH_YELLOW_MIN_VALUE = 90


def switch_yellow_ratio(crop) -> float:
    """Share of a toggle crop showing the game's yellow "on" colour."""

    if crop is None or crop.size == 0 or crop.ndim != 3 or crop.shape[2] < 3:
        return 0.0
    bgr = np.ascontiguousarray(crop[..., :3])
    b, g, r = bgr[..., 0], bgr[..., 1], bgr[..., 2]
    by_channels = (r > 150) & (g > 110) & (b < 90)
    hue, saturation, value = cv2.split(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV))
    low, high = SWITCH_YELLOW_HUE
    by_hue = (
        (hue >= low)
        & (hue <= high)
        & (saturation >= SWITCH_YELLOW_MIN_SATURATION)
        & (value >= SWITCH_YELLOW_MIN_VALUE)
    )
    return float((by_channels | by_hue).mean())


# The switch's white knob sits left when off and right when on, whatever the
# colours (player 10-13, v0.1.30: 镜中之战 refused an off switch because the
# capture's colours were flagged).  Knob: the brightest grey pixels; at 1080p
# about 22 px wide, 11 px either side of the switch middle (Leo's 1080p PVP
# dialog: off centre 1290, on 1312, middle 1301).
KNOB_MAX_SATURATION = 70
KNOB_MIN_VALUE = 140
KNOB_BRIGHT_SHARE = 0.85
KNOB_MIN_AREA_SHARE = 0.01
KNOB_MAX_WIDTH_SHARE = 0.45
# Middle of the knob this many knob widths off the switch middle.
KNOB_SIDE_SHARE = 0.25


def switch_knob_side(crop, middle_x: float) -> str | None:
    """"on" / "off" from where a toggle's knob sits in ``crop``; None unclear.

    ``middle_x`` is the switch's middle in crop pixels.  The knob is the
    brightest low-saturation blob; it must be knob-sized (narrow) and clearly
    on one side.
    """

    if crop is None or crop.size == 0 or crop.ndim != 3 or crop.shape[2] < 3:
        return None
    hsv = cv2.cvtColor(np.ascontiguousarray(crop[..., :3]), cv2.COLOR_BGR2HSV)
    saturation, value = hsv[..., 1], hsv[..., 2]
    grey = saturation < KNOB_MAX_SATURATION
    if not grey.any():
        return None
    floor = max(KNOB_MIN_VALUE, KNOB_BRIGHT_SHARE * float(value[grey].max()))
    ys, xs = np.nonzero(grey & (value >= floor))
    if xs.size < KNOB_MIN_AREA_SHARE * value.size:
        return None
    left, right = np.percentile(xs, (2, 98))
    width = right - left + 1
    if width > KNOB_MAX_WIDTH_SHARE * crop.shape[1]:
        return None
    offset = (left + right) / 2 - middle_x
    if offset <= -KNOB_SIDE_SHARE * width:
        return "off"
    if offset >= KNOB_SIDE_SHARE * width:
        return "on"
    return None
