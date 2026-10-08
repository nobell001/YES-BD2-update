"""A fight played from screenshots alone, kept as a save (Leo 2026-10-01).

Leo: when a player only has screenshots, the tool can, once the fight is
done, turn what it worked out into a save like one recorded with the hotkey:
record.json (who stood where, the order, team, bursts) and the tool's own
screenshot of each turn just before BATTLE.  The next run finds record.json
in the folder and replays it the quick, steady way.

The screenshots go in a subfolder, so the player's own screenshots and the
folder's look stay as they were; record.json is written only when the whole
fight was played, never over one that is there.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Protocol

from src.tasks.fiend_hunt.record import FightRecord, TurnState, TurnStateError, save_record
from src.tasks.fiend_hunt.saves import RECORD_FILE

KEPT_SHOTS = "自动存档截图"


class KeepScreen(Protocol):
    def save_screenshot(self, path: Path) -> None: ...

    def wait_saved(self) -> None: ...


class Solver(Protocol):
    def solve(self, turn: int, record: FightRecord) -> tuple[FightRecord, TurnState]: ...

    def check(self, turn: int, state: TurnState) -> None: ...


class KeptFight:
    """Wraps a screenshot solver's ``solve`` and ``check`` for replay_fight and
    remembers each turn as it was left at BATTLE."""

    def __init__(
        self,
        screen: KeepScreen,
        folder: Path,
        solver: Solver,
        title: str,
        log: Callable[[str], None] = lambda message: None,
    ) -> None:
        self.screen = screen
        self.folder = Path(folder)
        self.solver = solver
        self.title = title
        self.log = log
        self.turns: dict[int, TurnState] = {}
        self.shots: dict[int, str] = {}
        self._solved: FightRecord | None = None

    def solve(self, turn: int, record: FightRecord) -> tuple[FightRecord, TurnState]:
        record, live = self.solver.solve(turn, record)
        self._solved = record
        return record, live

    def check(self, turn: int, state: TurnState) -> None:
        self.solver.check(turn, state)
        solved = self._solved.turns.get(turn) if self._solved is not None else None
        if solved is not None and not state.bursts:
            state = replace(state, bursts=solved.bursts)
        name = f"{KEPT_SHOTS}/turn{turn:02d}.png"
        try:
            (self.folder / KEPT_SHOTS).mkdir(exist_ok=True)
            self.screen.save_screenshot(self.folder / name)
        except OSError as error:
            self.log(f"第 {turn} 回合的截图没存上（{error}），这场打完不会存成存档")
            return
        self.turns[turn] = state
        self.shots[turn] = name

    def keep(self, played: tuple[int, ...]) -> Path | None:
        """Write record.json once the whole fight was played; None if not kept."""
        path = self.folder / RECORD_FILE
        if path.exists():
            self.log(f"{self.folder.name} 里已经有 record.json，不覆盖")
            return None
        if not played or any(turn not in self.turns for turn in played):
            self.log("有回合的截图没存上，这场没存成存档")
            return None
        try:
            self.screen.wait_saved()
            record = FightRecord(
                {turn: self.turns[turn] for turn in played},
                self.title,
                "screenshots",
                {turn: self.shots[turn] for turn in played},
            )
            save_record(record, path)
        except (OSError, TurnStateError) as error:
            self.log(f"没存成存档：{error}")
            return None
        return path
