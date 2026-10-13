"""Popups the game shows on top of any page, closed the same way everywhere.

Reward overlays, 获得道具 dialogs and season reward pages appear whenever the
game decides (after a battle, at the first visit of the day, at a season
change), not only at the step that expects them.  Each task used to close the
ones it had met itself, so a popup that showed up one step early or late
stopped a different task (赛季奖励 after a 镜中之战 battle, #238).  BetterGI
does it once for every task; this module is that one place (Leo 2026-10-12,
「共用彈窗處理」).

``pick`` only ever chooses a harmless press:

- a 「点击画面即可返回」 style line: tapping it closes an overlay;
- 「关闭」;
- 「确认」 only while an info-only title (获得道具, 奖励已发放至背包...) is on
  the same frame, never a purchase or spend confirm;
- 「取消」 only when the caller allows it (the way home), never mid-task,
  where it could cancel a dialog the task itself opened.

The game's quit dialog (Esc pressed on a top page) is recognised so the way
home cancels it and stops pressing Esc (Leo 2026-10-12 「這遊戲按沒幾下就會變成
問你要不要關閉遊戲」).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.ocr_utils import normalize_ocr_text

OVERLAY_DISMISS_KEYWORDS = (
    "点击画面即可返回",
    "点击画面返回",
    "点击任意位置",
    "点击空白处",
    "点击屏幕",
    "轻触画面",
)
# A "确认" button is only pressed when one of these reward titles is on screen.
REWARD_DIALOG_TITLES = ("获得道具", "获得奖励", "领取奖励", "奖励领取", "领取成功", "获得物品")
# Info-only dialogs whose 确认 just closes them.
CONFIRM_ONLY_TITLES = REWARD_DIALOG_TITLES + (
    "恭喜晋级",
    "段位下滑",
    "奖励已发放至背包",
    "奖励已通过邮件发放",
)
CONFIRM_TEXT = "确认"
CLOSE_TEXT = "关闭"
CANCEL_TEXT = "取消"
# The quit dialog: one of these verbs next to 游戏 (exact wording not yet
# captured; any of them with 游戏 on a dialog that has 取消 is the quit one).
QUIT_VERBS = ("退出", "结束", "关闭", "离开")
QUIT_OBJECT = "游戏"


@dataclass(frozen=True)
class PopupPress:
    label: str
    box: object


def _named(boxes) -> list[tuple[str, object]]:
    return [(normalize_ocr_text(getattr(box, "name", "")), box) for box in boxes or ()]


def _exact(named, text: str):
    wanted = normalize_ocr_text(text)
    return next((box for name, box in named if name == wanted), None)


def is_quit_dialog(boxes) -> bool:
    """The game asks whether to quit: 游戏 with a quit verb, and a 取消 button."""
    named = _named(boxes)
    if _exact(named, CANCEL_TEXT) is None:
        return False
    for name, _box in named:
        if QUIT_OBJECT in name and any(verb in name for verb in QUIT_VERBS):
            return True
    return False


def pick(boxes, *, allow_cancel: bool = False) -> PopupPress | None:
    """The harmless press that closes the popup on screen, or None."""
    named = _named(boxes)
    if not named:
        return None
    if is_quit_dialog(boxes):
        # Never 确认 here; 取消 keeps the game open (allowed even mid-task).
        return PopupPress(CANCEL_TEXT, _exact(named, CANCEL_TEXT))
    box = _exact(named, OVERLAY_DISMISS_KEYWORDS[0])
    if box is not None:
        return PopupPress(OVERLAY_DISMISS_KEYWORDS[0], box)
    if allow_cancel:
        box = _exact(named, CANCEL_TEXT)
        if box is not None:
            return PopupPress(CANCEL_TEXT, box)
    box = _exact(named, CLOSE_TEXT)
    if box is not None:
        return PopupPress(CLOSE_TEXT, box)
    overlays = tuple(normalize_ocr_text(keyword) for keyword in OVERLAY_DISMISS_KEYWORDS)
    box = next((box for name, box in named if any(k in name for k in overlays)), None)
    if box is not None:
        return PopupPress("点击画面返回", box)
    text = "".join(name for name, _box in named)
    if any(normalize_ocr_text(title) in text for title in CONFIRM_ONLY_TITLES):
        box = _exact(named, CONFIRM_TEXT)
        if box is not None:
            return PopupPress(CONFIRM_TEXT, box)
    return None
