"""Developer-only: keep the frames a run looked at, and what it read on them.

Leo 2026-10-12 asked not to wait for players to hit the next recognition
bug.  With real frames from every step (and at low / default / high game
brightness), every template and colour check can be measured for how much
room it has before it fails, the way tests/test_brightness_margins.py does
for the ones the tests already had frames for.

Off unless the environment variable ``BD2_RECORD_FRAMES`` names a folder
(players never set it; there is no setting in the app).  Then:

- a frame is saved (PNG, at most 1920x1080 so a 4K run stays a few GB) when
  it differs from the last saved one, at most ``MAX_FRAMES`` per run;
- every template match and every OCR read appends one line to
  ``reads.jsonl``: which frame, what was looked for, the score or the text.
"""

from __future__ import annotations

import functools
import json
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ENV = "BD2_RECORD_FRAMES"
MAX_FRAMES = 1500
SAVE_MAX_SIZE = (1920, 1080)
# Mean grey difference on a 1/16 thumbnail that counts as a new frame.
NEW_FRAME_MIN_DIFF = 3.0

_lock = threading.Lock()
_state = {"dir": None, "count": 0, "thumb": None, "name": None, "shape": None}
_depth = threading.local()


def folder() -> Path | None:
    return _state["dir"]


def _thumb(frame):
    return frame[::16, ::16, :3].astype(np.float32).mean(axis=2)


def frame_name(frame) -> str | None:
    """The saved file this frame is (saved now when it is new), or None."""
    if _state["dir"] is None or frame is None or getattr(frame, "ndim", 0) != 3:
        return None
    if frame.shape[0] < 200 or frame.shape[1] < 300:
        return None  # a crop, not a frame
    thumb = _thumb(frame)
    with _lock:
        last = _state["thumb"]
        if (
            last is not None
            and last.shape == thumb.shape
            and float(np.abs(last - thumb).mean()) < NEW_FRAME_MIN_DIFF
        ):
            return _state["name"]
        if _state["count"] >= MAX_FRAMES:
            return None
        _state["count"] += 1
        name = f"{_state['count']:05d}_{frame.shape[1]}x{frame.shape[0]}.png"
        _state["thumb"], _state["name"] = thumb, name
    image = frame[:, :, :3]
    width, height = SAVE_MAX_SIZE
    if image.shape[1] > width or image.shape[0] > height:
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(_state["dir"] / name), image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    return name


def note(kind: str, frame, **fields) -> None:
    if _state["dir"] is None:
        return
    try:
        name = frame_name(frame)
        row = {"t": round(time.time(), 2), "kind": kind, "frame": name, **fields}
        with _lock, open(_state["dir"] / "reads.jsonl", "a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass  # recording must never break a run


def _wrap_match_template(task_vision) -> None:
    original = task_vision.match_template

    def match_template(frame, spec, *args, **kwargs):
        depth = getattr(_depth, "n", 0)
        _depth.n = depth + 1
        try:
            result = original(frame, spec, *args, **kwargs)
        finally:
            _depth.n = depth
        if depth == 0:
            note(
                "match",
                frame,
                spec=getattr(spec, "file_name", ""),
                label=getattr(spec, "name", ""),
                score=round(float(result.score), 4),
                pixel=round(float(getattr(result, "pixel_score", -1.0)), 4),
                position=list(result.position),
                size=list(result.size),
            )
        return result

    task_vision.match_template = match_template


def _wrap_ocr(base_task_class) -> None:
    original = base_task_class.ocr

    @functools.wraps(original)  # keeps the reread switch visible (vision.py)
    def ocr(self, *args, **kwargs):
        boxes = original(self, *args, **kwargs)
        frame = kwargs.get("frame")
        if frame is None:
            frame = getattr(getattr(self, "executor", None), "_frame", None)
        note(
            "ocr",
            frame,
            name=kwargs.get("name", ""),
            box=str(kwargs.get("box", "")),
            text=[str(getattr(box, "name", "")) for box in boxes or ()],
        )
        return boxes

    base_task_class.ocr = ocr


def install() -> None:
    """Start recording when ``BD2_RECORD_FRAMES`` is set; no-op otherwise."""
    target = os.environ.get(ENV, "").strip()
    if not target or _state["dir"] is not None:
        return
    path = Path(target) / time.strftime("%Y%m%d-%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    _state["dir"] = path

    from src.tasks.BaseBD2Task import BaseBD2Task
    from src.utils import task_vision

    _wrap_match_template(task_vision)
    _wrap_ocr(BaseBD2Task)
