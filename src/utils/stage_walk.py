"""Locate the PVP stage and plan WASD steps onto its centre.

For players who move with WASD instead of mouse clicks (click-to-move off),
the mirror-battle stage must be reached by walking.  The camera keeps the
player character at the screen centre, so the red stage's position on screen
is the offset still to walk.  Calibrated 2026-09-26 on the live client
(1920x1080 reference): the pre-battle screen opens once the character stands
on the stage centre, which is then about (-35, +25) px from the sprite at
(955, 500); S moved the view ~390 px/s vertically, A/D ~550 px/s.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Where the stage centre sits on screen when the character stands on it.
STAGE_TARGET = (925, 535)
# Only look for the stage around the character: the bar carpet at the top
# right and the red crossed-swords marker are also red.
SEARCH_ROI = (460, 260, 1460, 860)
MIN_STAGE_AREA = 2500
ARRIVED_DISTANCE = 30.0
PIXELS_PER_SECOND = {"x": 550.0, "y": 390.0}
MIN_STEP_SECONDS = 0.06
MAX_STEP_SECONDS = 0.35


@dataclass(frozen=True)
class WalkStep:
    key: str
    seconds: float


def find_stage(frame_1080: np.ndarray) -> tuple[int, int] | None:
    """Centre of the red stage top in a 1920x1080 BGR frame, or None."""
    hsv = cv2.cvtColor(frame_1080[:, :, :3], cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    red = ((hue <= 8) | (hue >= 168)) & (saturation >= 120) & (value >= 50)
    mask = np.zeros(red.shape, dtype=np.uint8)
    x0, y0, x1, y1 = SEARCH_ROI
    mask[y0:y1, x0:x1] = red[y0:y1, x0:x1].astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    best = None
    for index in range(1, count):
        area = int(stats[index][cv2.CC_STAT_AREA])
        if area < MIN_STAGE_AREA:
            continue
        if best is None or area > best[0]:
            best = (area, int(centroids[index][0]), int(centroids[index][1]))
    return None if best is None else (best[1], best[2])


def plan_step(stage: tuple[int, int], target: tuple[int, int] = STAGE_TARGET) -> WalkStep | None:
    """Next key press that brings the stage toward ``target`` (None: arrived).

    The camera follows the character, so walking left moves the stage right on
    screen: a stage left of the target means walk left (A), below means S.
    """
    dx = stage[0] - target[0]
    dy = stage[1] - target[1]
    if (dx * dx + dy * dy) ** 0.5 <= ARRIVED_DISTANCE:
        return None
    if abs(dx) / PIXELS_PER_SECOND["x"] >= abs(dy) / PIXELS_PER_SECOND["y"]:
        key, distance, speed = ("a" if dx < 0 else "d"), abs(dx), PIXELS_PER_SECOND["x"]
    else:
        key, distance, speed = ("s" if dy > 0 else "w"), abs(dy), PIXELS_PER_SECOND["y"]
    seconds = min(MAX_STEP_SECONDS, max(MIN_STEP_SECONDS, distance / speed))
    return WalkStep(key, round(seconds, 3))


# Short taps tried around the centre when the stage is reached but the
# pre-battle screen has not opened yet (occlusion biases the stage centroid).
NUDGE_SEQUENCE = (
    WalkStep("s", 0.08),
    WalkStep("a", 0.08),
    WalkStep("w", 0.08),
    WalkStep("w", 0.08),
    WalkStep("d", 0.08),
    WalkStep("d", 0.08),
    WalkStep("s", 0.08),
    WalkStep("s", 0.08),
)


# 末日之书 (LAST NIGHT) field: the red crossed-swords battle marker, about
# 30x28 px and 420 red pixels (live 2026-09-26).  Walking onto it opens the
# boss page.  The whole screen is searched (the field keeps the character's
# last position, so the marker can sit at the very edge, live (1877, 133))
# except the HUD parts that carry red: minimap with its own small marker,
# the event logo, the red "!" badges of the top-right icons.
MARKER_HUD_MASKS = (
    (115, 85, 180, 175),  # minimap
    (1560, 100, 285, 115),  # event logo
    (1540, 10, 350, 95),  # top-right icons and their badges
)
MARKER_AREA = (250, 900)
MARKER_SIDE = (18, 48)
# The character's feet: the marker sits here when the character stands on it.
MARKER_TARGET = (955, 545)


def find_marker(frame_1080: np.ndarray) -> tuple[int, int] | None:
    """Centre of the red crossed-swords battle marker, or None."""
    hsv = cv2.cvtColor(frame_1080[:, :, :3], cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    red = ((hue <= 8) | (hue >= 168)) & (saturation >= 120) & (value >= 50)
    mask = red.astype(np.uint8) * 255
    for x, y, w, h in MARKER_HUD_MASKS:
        mask[y : y + h, x : x + w] = 0
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    best = None
    for index in range(1, count):
        area = int(stats[index][cv2.CC_STAT_AREA])
        width = int(stats[index][cv2.CC_STAT_WIDTH])
        height = int(stats[index][cv2.CC_STAT_HEIGHT])
        if not MARKER_AREA[0] <= area <= MARKER_AREA[1]:
            continue
        low, high = MARKER_SIDE
        if not (low <= width <= high and low <= height <= high):
            continue
        if best is None or area > best[0]:
            best = (area, int(centroids[index][0]), int(centroids[index][1]))
    return None if best is None else (best[1], best[2])


def predict_after_step(position: tuple[int, int], step: WalkStep) -> tuple[int, int]:
    """Where a ground point moves on screen after ``step``.

    Used while the marker hides behind a masked HUD area (live: it slid under
    the event logo after one D step): walking right moves the view right, so
    the point moves left on screen, and so on.
    """
    x, y = position
    if step.key in ("a", "d"):
        shift = round(PIXELS_PER_SECOND["x"] * step.seconds)
        x += shift if step.key == "a" else -shift
    else:
        shift = round(PIXELS_PER_SECOND["y"] * step.seconds)
        y += shift if step.key == "w" else -shift
    return x, y
