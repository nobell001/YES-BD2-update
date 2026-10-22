"""The game's 公告事项 on the title screen says it is under maintenance.

Leo 2026-10-22 (screenshot of the 公告事项 dialog, 「重點字 維護」): 「看到這視窗
就直接關掉 送通知就好」.  The dialog gives the time, e.g.
「更新时间：2026年10月22日(四) 上午7:50 ~11:00」 (game time, UTC+8); only
while now is inside it is the game closed.  The same notice days ahead is an
announcement, and the run goes on.  A notice that says 维护 with no time that
can be read counts as now (what Leo asked for).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.utils.game_day import GAME_TZ

MAINTENANCE_WORDS = ("维护", "維護", "점검", "メンテナンス", "maintenance")
# Only the login screen counts (Leo 「只有登入畫面喔」): its 「游戏启动中」 under
# the logo, or the version 「v2.37.11(FHD-802:514)」 in the corner.
LOGIN_SCREEN_WORDS = ("游戏启动中", "遊戲啟動中")
VERSION_PATTERN = re.compile(r"v\d+\.\d+\.\d+\s*[(（]", re.IGNORECASE)

_AMPM = r"(上午|下午|早上|中午|晚上|凌晨|午前|午後|오전|오후|AM|PM|am|pm)?"
_DATE = r"(?:(\d{4})\s*[年년]\s*)?(\d{1,2})\s*[月월]\s*(\d{1,2})\s*[日일]"
_TIME = r"(\d{1,2})\s*[:：]\s*(\d{2})"
# A date, its weekday 「(四)」, then 上午 7:50 ~ (another date) 11:00.
WINDOW_PATTERN = re.compile(
    _DATE + r"[^\d~～]{0,12}?\s*" + _AMPM + r"\s*" + _TIME
    + r"\s*[~～\-－—至到]\s*"
    + r"(?:" + _DATE + r"[^\d~～]{0,12}?\s*)?" + _AMPM + r"\s*" + _TIME
)
_AFTERNOON = ("下午", "晚上", "午後", "오후", "PM", "pm")
_MORNING = ("上午", "早上", "凌晨", "午前", "오전", "AM", "am")


@dataclass(frozen=True)
class Notice:
    start: datetime | None  # game time (UTC+8); None when no time was read
    end: datetime | None

    def now_in(self, now: datetime) -> bool:
        if self.start is None or self.end is None:
            return True
        return self.start <= now <= self.end

    def until_text(self) -> str:
        return f"{self.end:%m/%d %H:%M}" if self.end is not None else ""


def _hour(hour: int, ampm: str | None) -> int:
    if ampm in _AFTERNOON and hour < 12:
        return hour + 12
    if ampm in _MORNING and hour == 12:
        return 0
    return hour


def _year_near(month: int, day: int, now: datetime) -> int:
    """The year of a 「10月22日」 with no year: the one closest to now."""
    best = now.year
    for year in (now.year - 1, now.year + 1):
        try:
            if abs(datetime(year, month, day) - now.replace(tzinfo=None)) < abs(
                datetime(best, month, day) - now.replace(tzinfo=None)
            ):
                best = year
        except ValueError:
            continue
    return best


def parse_window(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    """The first 「date time ~ time」 in ``text`` as game-time datetimes."""
    now = now.astimezone(GAME_TZ)
    for match in WINDOW_PATTERN.finditer(text):
        (y1, m1, d1, ap1, h1, mi1, y2, m2, d2, ap2, h2, mi2) = match.groups()
        try:
            month, day = int(m1), int(d1)
            year = int(y1) if y1 else _year_near(month, day, now)
            start = datetime(year, month, day, _hour(int(h1), ap1), int(mi1), tzinfo=GAME_TZ)
            if m2:
                month2, day2 = int(m2), int(d2)
                year2 = int(y2) if y2 else (year + 1 if month2 < month else year)
                end_day = datetime(year2, month2, day2, tzinfo=GAME_TZ)
            else:
                end_day = start.replace(hour=0, minute=0)
            # 「下午 2:00 ~ 5:00」: the end shares the start's 上午/下午.
            end_hour = _hour(int(h2), ap2 or ap1)
            if end_hour < start.hour and not ap2 and ap1 in _MORNING and end_hour < 12:
                end_hour += 12  # 「上午 10:00 ~ 1:00」 is 13:00
            end = end_day.replace(hour=end_hour, minute=int(mi2))
        except ValueError:
            continue  # 「13月」 and the like: an OCR slip, not a time
        if end <= start:
            end += timedelta(days=1)
        return start, end
    return None


def read(text: str, now: datetime) -> Notice | None:
    """A maintenance notice on the login screen in this OCR text, or None."""
    compact = re.sub(r"\s+", "", text).lower()
    if not any(word in compact for word in MAINTENANCE_WORDS):
        return None
    if not (any(word in compact for word in LOGIN_SCREEN_WORDS) or VERSION_PATTERN.search(text)):
        return None  # a 公告 inside the game
    window = parse_window(text, now)
    if window is None:
        return Notice(None, None)
    return Notice(*window)


def _when(notice: Notice) -> str:
    until = notice.until_text()
    return f"游戏正在维护（到 {until}）" if until else "游戏正在维护"


def message(notice: Notice, closed: bool = True) -> str:
    """Why this run did not happen (the 跑完通知 sends it too)."""
    if closed:
        return f"{_when(notice)}，已关闭游戏，这次没有跑。"
    return f"{_when(notice)}，这次没有跑。游戏没能自动关掉，请自己关一下。"


def waiting_message(notice: Notice) -> str:
    """The game the player opened, with no run waiting: only a word."""
    return f"{_when(notice)}，维护完再登录。"
