"""快捷键：暂停/继续、停止、魔兽录制，三个都在「设置」里换（F6~F12）。

Leo 2026-10-09（玩家建议 YES-BD2 issue #1）：暂停和停止是两个不同的键，
魔兽录制键也放进设置。F 键不会被当成玩家接手（takeover 放过 F1~F24），
游戏本身也不用 F6~F12。

暂停、停止用 Windows 的全局热键（工具在后台、游戏在前面也收得到），
按下去等于按首页的「暂停」「停止」，桌面分身里跑的也一样。录制键不注册
热键：录制时工具自己轮询这个键（FiendHuntTask.HotKey），注册了游戏和
工具就收不到了。三个键不能重复，选了别人正在用的键就跟它对调。

ok-script 原本的 F9（暂停整个执行器）会被关掉，免得一个键做两件事。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

from ok import Logger

logger = Logger.get_logger(__name__)

ROOT = Path(__file__).resolve().parents[3]
KEYS_FILE = ROOT / "configs" / "hotkeys.json"

KEY_CHOICES = tuple(f"F{number}" for number in range(6, 13))
PAUSE = "pause"
STOP = "stop"
RECORD = "record"
ACTIONS = (PAUSE, STOP, RECORD)
LABELS = {PAUSE: "暂停/继续", STOP: "停止", RECORD: "魔兽录制"}
DEFAULTS = {PAUSE: "F9", STOP: "F10", RECORD: "F8"}
# The 魔兽追踪者 record task keeps its key in its own config (its page has a picker too).
RECORD_TASK = "FiendHuntRecordTask"
RECORD_CONFIG_KEY = "录制按键"
OK_START_STOP = "Start/Stop"


def key_code(name: str) -> int:
    return 0x70 + int(name[1:]) - 1


def _record_task():
    try:
        from src.ui.shell import data

        return data.task_by_class_name(RECORD_TASK)
    except Exception:
        return None


def _read_file() -> dict:
    try:
        saved = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def keys(record_task=None) -> dict[str, str]:
    """The three keys now; anything missing or broken falls back to the defaults
    (and a duplicate falls back too, so two actions never share a key)."""
    saved = _read_file()
    task = record_task if record_task is not None else _record_task()
    if task is not None:
        saved[RECORD] = (getattr(task, "config", None) or {}).get(RECORD_CONFIG_KEY)
    chosen: dict[str, str] = {}
    for action in ACTIONS:
        key = saved.get(action)
        chosen[action] = key if key in KEY_CHOICES else DEFAULTS[action]
    if len(set(chosen.values())) < len(ACTIONS):
        used: set[str] = set()
        for action in (RECORD, PAUSE, STOP):  # the recorded fights' key wins
            if chosen[action] in used:
                chosen[action] = next(k for k in (DEFAULTS[action], *KEY_CHOICES) if k not in used)
            used.add(chosen[action])
    return chosen


def set_key(action: str, key: str, record_task=None) -> dict[str, str]:
    """Give ``action`` this key; whoever had it takes ``action``'s old key."""
    if action not in ACTIONS or key not in KEY_CHOICES:
        return keys(record_task)
    current = keys(record_task)
    for other, other_key in current.items():
        if other != action and other_key == key:
            current[other] = current[action]
    current[action] = key
    task = record_task if record_task is not None else _record_task()
    if task is not None:
        try:
            task.config[RECORD_CONFIG_KEY] = current[RECORD]
        except Exception as exc:
            logger.warning(f"hotkeys: record key not saved ({exc})")
    try:
        KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEYS_FILE.write_text(
            json.dumps({PAUSE: current[PAUSE], STOP: current[STOP]}), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning(f"hotkeys: not saved ({exc})")
    if _listener is not None:
        _listener.rebind()
    for callback in list(_changed):
        try:
            callback()
        except Exception as exc:
            logger.warning(f"hotkeys: change callback failed ({exc})")
    return current


def hint(current: dict[str, str] | None = None) -> str:
    """The line on 首页 while a run is on."""
    from src.ui.shell.widgets import tf

    current = current or keys()
    return tf(
        "按 {pause} 暂停、{stop} 停止，可在设置里改", pause=current[PAUSE], stop=current[STOP]
    )


_changed: list[Callable[[], None]] = []


def on_changed(callback: Callable[[], None]) -> None:
    _changed.append(callback)


def turn_off_ok_hotkey() -> None:
    """ok-script's own F9 pauses the whole executor; ours replaces it."""
    try:
        from ok import og

        options = og.executor.basic_options
        if options.get(OK_START_STOP) != "None":
            options[OK_START_STOP] = "None"
    except Exception as exc:
        logger.warning(f"hotkeys: could not turn off ok's Start/Stop key ({exc})")


WM_HOTKEY = 0x0312
WM_APP_REBIND = 0x8000 + 1
MOD_NOREPEAT = 0x4000
_IDS = {PAUSE: 0xB201, STOP: 0xB202}


class HotkeyListener:
    """A thread holding the two global hotkeys; calls ``on_press(action)`` from it."""

    def __init__(self, on_press: Callable[[str], None]):
        self._on_press = on_press
        self._thread_id = 0
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="Hotkeys", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(2)

    def rebind(self) -> None:
        if self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_APP_REBIND, 0, 0)

    def stop(self) -> None:
        if self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT

    def _bind(self, user32) -> None:
        current = keys()
        for action, hotkey_id in _IDS.items():
            user32.UnregisterHotKey(None, hotkey_id)
            if not user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, key_code(current[action])):
                # Another program already holds the key: the button still works.
                logger.warning(
                    f"hotkeys: {current[action]} for {action} is taken by another program"
                )
        logger.info(f"hotkeys: {LABELS[PAUSE]} {current[PAUSE]}, {LABELS[STOP]} {current[STOP]}")

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        msg = wintypes.MSG()
        # A thread has a message queue only once it asks for a message.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._thread_id = kernel32.GetCurrentThreadId()
        try:
            self._bind(user32)
        finally:
            self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    action = next((a for a, i in _IDS.items() if i == msg.wParam), None)
                    if action is not None:
                        try:
                            self._on_press(action)
                        except Exception as exc:
                            logger.warning(f"hotkeys: {action} failed ({exc})")
                elif msg.message == WM_APP_REBIND:
                    self._bind(user32)
        finally:
            for hotkey_id in _IDS.values():
                user32.UnregisterHotKey(None, hotkey_id)


_listener: HotkeyListener | None = None


def start(on_press: Callable[[str], None]) -> HotkeyListener | None:
    """Turn the hotkeys on (Windows, not in the 桌面分身: nobody types there)."""
    global _listener
    import sys

    if sys.platform != "win32" or _listener is not None:
        return _listener
    try:
        from src.utils.clone_desktop import in_clone

        if in_clone():
            return None
    except Exception:
        pass
    turn_off_ok_hotkey()
    _listener = HotkeyListener(on_press)
    _listener.start()
    return _listener
