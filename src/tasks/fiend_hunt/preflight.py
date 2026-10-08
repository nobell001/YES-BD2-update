"""Check a folder of screenshots before the fight starts (Leo 2026-10-01).

Leo: say before the fight which turns there are, which are missing and which
images can't be used, instead of stopping halfway through.  Every turn from
the one the game is on up to the last screenshot needs one, or the fight
would stop at the gap.  The number of turns isn't fixed (it differs per
boss, Leo).  The turns go 1, 3, 5, ... in every fight seen; a smaller gap
between the screenshots' turns would be taken as the step instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

STEP = 2  # TURN 1, 3, 5, ...


@dataclass(frozen=True)
class FolderCheck:
    turns: tuple[int, ...]  # turns with a usable screenshot
    missing: tuple[int, ...]  # turns the fight will reach without one
    unusable: tuple[str, ...]  # what was said about each image that can't be used
    start: int  # the turn the fight starts from

    @property
    def problem(self) -> str | None:
        """Why not to start, or None."""
        if not self.turns:
            return None
        if self.start > self.turns[-1]:
            return f"游戏在第 {self.start} 回合，截图只到第 {self.turns[-1]} 回合"
        if self.missing:
            gaps = "、".join(str(turn) for turn in self.missing)
            return f"截图缺第 {gaps} 回合，打到那里会停下：请补上这几回合的排位截图再开始"
        return None

    def summary(self) -> list[str]:
        """Lines for the log, before the fight."""
        lines = [f"截图：有第 {'、'.join(str(turn) for turn in self.turns)} 回合"]
        if self.missing:
            lines.append(f"截图：缺第 {'、'.join(str(turn) for turn in self.missing)} 回合")
        if self.unusable:
            lines.append(f"截图：{len(self.unusable)} 张不能用：" + "；".join(self.unusable))
        if self.turns:
            lines.append(f"截图到第 {self.turns[-1]} 回合为止：那回合打完战斗还没结束就会停下")
        return lines


def check_folder(
    found: Mapping[int, str], unusable: Sequence[str], live_turn: int | None
) -> FolderCheck:
    """``found`` from shots.find_screenshots, ``unusable`` the notes it gave on
    the images it skipped, ``live_turn`` the TURN the game shows (None if it
    can't be read: then the first screenshot's turn)."""
    turns = tuple(sorted(found))
    start = live_turn if live_turn is not None else (turns[0] if turns else 1)
    last = turns[-1] if turns else start
    gaps = [b - a for a, b in zip(turns, turns[1:])]
    step = min([STEP, *gaps])
    missing = tuple(turn for turn in range(start, last + 1, step) if turn not in found)
    return FolderCheck(turns, missing, tuple(unusable), start)
