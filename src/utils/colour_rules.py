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
