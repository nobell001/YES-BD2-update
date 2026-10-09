"""Settings files that a power cut or a busy file can't break (review 2026-10-09).

ok-script writes each settings file in place: the old content is gone before
the new is written, so a power cut, a forced shutdown or the tool's own
关机 after 一键日常 can leave half a file.  Its reader only expects broken
JSON; half of a Chinese character is a ``UnicodeDecodeError`` instead, and
then the tool stops at every start with no window until the file is deleted.

Here a file is written next to the old one and swapped in at once, and an
unreadable file is kept as ``<name>.corrupt`` and read as missing, so the
tool starts with default settings rather than not at all.
"""

from __future__ import annotations

import json
import os
import shutil
import time

# The tool in the 桌面分身 may be reading the same file at that moment.
REPLACE_TRIES = 5
REPLACE_WAIT_SECONDS = 0.05


def read_json_file(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except ValueError:  # broken JSON, or bytes cut in the middle of a character
        try:
            shutil.copy2(file_path, f"{file_path}.corrupt")
        except OSError:
            pass
        return None


def write_json_file(file_path, data):
    folder = os.path.dirname(file_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temp = f"{file_path}.tmp"
    with open(temp, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(temp, file_path)
            return True
        except PermissionError:
            if attempt + 1 < REPLACE_TRIES:
                time.sleep(REPLACE_WAIT_SECONDS)
    # Still held open elsewhere: write in place as ok-script always did.
    try:
        os.remove(temp)
    except OSError:
        pass
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
    return True


def install_safe_json() -> None:
    """Swap ok-script's readers and writers; call before ``src.config`` is imported."""
    import ok.util.config
    import ok.util.file
    import ok.util.GlobalConfig

    for module in (ok.util.file, ok.util.config, ok.util.GlobalConfig):
        module.read_json_file = read_json_file
        module.write_json_file = write_json_file
