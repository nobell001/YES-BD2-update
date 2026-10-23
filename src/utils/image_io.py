"""Read and write image files on any path, including 桌面 or a Chinese user name.

On Windows ``cv2.imread``/``cv2.imwrite`` can't open a path with non-English
letters: they return None/False.  main.py opens the tool through an
English-only link, but ``Path(__file__).resolve()`` follows that link back to
the real folder, so the templates were still read from the Chinese path (a
player's PVP run 2026-10-23: 「任务模板不存在或无法读取：…\\OneDrive\\桌面\\…」).
Python opens such paths fine, so the bytes go through numpy instead.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read(path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """The image at ``path`` (same ``flags`` as cv2.imread), or None if it can't be read."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if not data.size:
        return None
    return cv2.imdecode(data, flags)


def write(path, image: np.ndarray, params=()) -> bool:
    """Save ``image`` as ``path`` (format from its extension, same ``params`` as cv2.imwrite)."""
    path = Path(path)
    try:
        ok, encoded = cv2.imencode(path.suffix or ".png", image, list(params))
        if not ok:
            return False
        encoded.tofile(str(path))
    except (OSError, cv2.error):
        return False
    return True
