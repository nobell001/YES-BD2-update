"""Saved fights on disk.

Each save is a folder under configs/fiend_hunt holding record.json and one
screenshot per recorded turn (turn01.png ...).  The 魔兽追踪者 page lists a
save's turns, deletes one, or adjusts one on the chart; recording into a
save overwrites a turn recorded again.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from src.tasks.fiend_hunt.record import (
    FightRecord,
    TurnState,
    TurnStateError,
    load_record,
    save_record,
)

RECORD_FILE = "record.json"
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass(frozen=True)
class SavedTurn:
    turn: int
    team: int
    screenshot: Path | None  # None for a turn without one (an imported chart)


def valid_save_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and not _BAD_CHARS.search(name)


def clean_save_name(text: str) -> str:
    """``text`` made usable as a folder name ('' when nothing is left)."""
    name = _BAD_CHARS.sub("", text).strip().strip(".")
    return name[:60].strip()


def unique_save_name(root: Path, base: str) -> str:
    """``base``, or ``base_2``, ``base_3`` ... whichever has no save yet."""
    name, number = base, 1
    while (Path(root) / name).exists():
        number += 1
        name = f"{base}_{number}"
    return name


def list_saves(root: Path) -> list[str]:
    """Names of the folders under ``root`` that hold a record, newest first."""
    root = Path(root)
    if not root.is_dir():
        return []
    found = [path for path in root.iterdir() if (path / RECORD_FILE).is_file()]
    found.sort(key=lambda path: (path / RECORD_FILE).stat().st_mtime, reverse=True)
    return [path.name for path in found]


def load_save(folder: Path) -> FightRecord | None:
    """The save's record; None when it has none yet or can't be read."""
    path = Path(folder) / RECORD_FILE
    if not path.is_file():
        return None
    try:
        return load_record(path)
    except (OSError, TurnStateError):
        return None


def saved_turns(folder: Path) -> list[SavedTurn]:
    record = load_save(folder)
    if record is None:
        return []
    turns = []
    for number in sorted(record.turns):
        name = record.screenshots.get(number)
        shot = Path(folder) / name if name else None
        turns.append(
            SavedTurn(number, record.turns[number].team, shot if shot and shot.is_file() else None)
        )
    return turns


def delete_turn(folder: Path, turn: int) -> bool:
    """Drop ``turn`` (and its screenshot) from the save; False when it isn't there."""
    folder = Path(folder)
    record = load_save(folder)
    if record is None or turn not in record.turns:
        return False
    name = record.screenshots.get(turn)
    turns = {number: state for number, state in record.turns.items() if number != turn}
    shots = {number: shot for number, shot in record.screenshots.items() if number != turn}
    edited = {number: units for number, units in record.edited.items() if number != turn}
    save_record(
        replace(record, turns=turns, screenshots=shots, edited=edited), folder / RECORD_FILE
    )
    if name:
        (folder / name).unlink(missing_ok=True)
    return True


def edit_turn(folder: Path, state: TurnState, changed: Iterable[str]) -> FightRecord:
    """Save a turn the player changed on the chart (Leo 2026-10-06: the order,
    the cells and each unit's card and 爆发 can be adjusted after recording).

    ``state`` is the whole turn as it should now be played; ``changed`` the
    units whose card the player touched.  A change to the order touches
    everyone, as the list slots no longer line up with the screenshot; a
    move on the grid touches no card.  The team, who is dead and the
    tombstones' cells stay as recorded.  Raises TurnStateError when the turn
    doesn't hold together.
    """
    folder = Path(folder)
    record = load_save(folder)
    if record is None or state.turn not in record.turns:
        raise TurnStateError(f"存档里没有第 {state.turn} 回合")
    before = record.turns[state.turn]
    tombstones = {unit: before.cells.get(unit) for unit in before.dead}
    if (
        state.team != before.team
        or state.dead != before.dead
        or set(state.cells) != set(before.cells)
        or any(state.cells.get(unit) != cell for unit, cell in tombstones.items())
    ):
        raise TurnStateError(f"第 {state.turn} 回合只能改顺序、站位、攻击或技能和爆发")
    touched = set(changed) | record.edited.get(state.turn, frozenset())
    if state.order != before.order:
        touched |= set(state.order)
    turns = {**record.turns, state.turn: state}
    edited = {number: units for number, units in record.edited.items() if number != state.turn}
    if touched & state.living:
        edited[state.turn] = frozenset(touched & state.living)
    updated = replace(record, turns=turns, edited=edited)
    save_record(updated, folder / RECORD_FILE)
    return updated


def set_team(folder: Path, team: int, members: Iterable[str]) -> FightRecord:
    """Give every turn of TEAM ``team`` these members (Leo 2026-10-06: the
    player can add and remove characters after recording).

    A removed unit leaves each of the team's turns.  An added one joins at
    the end of the order on the first free cell (front column first) with
    an attack card; the player then sets it up on the chart.  The screenshot
    no longer shows the turn, so a removal has everyone checked by card
    label, and an addition the new unit.  Raises TurnStateError when a turn
    would be left without a living unit or has no free cell.
    """
    folder = Path(folder)
    record = load_save(folder)
    members = list(dict.fromkeys(members))
    if record is None:
        raise TurnStateError("存档里还没有回合")
    numbers = [number for number, state in record.turns.items() if state.team == team]
    if not numbers:
        raise TurnStateError(f"存档里没有 TEAM{team} 的回合")
    turns = dict(record.turns)
    edited = dict(record.edited)
    for number in numbers:
        state = turns[number]
        removed = set(state.cells) - set(members)
        added = [name for name in members if name not in state.cells]
        if not removed and not added:
            continue
        keep = lambda mapping: {k: v for k, v in mapping.items() if k not in removed}  # noqa: E731
        order = [name for name in state.order if name not in removed]
        cells = keep(state.cells)
        skills, bursts = keep(state.skills), keep(state.bursts)
        for name in added:
            cell = _free_cell(cells)
            if cell is None:
                raise TurnStateError(f"第 {number} 回合没有空格放 {name}")
            cells[name] = cell
            order.append(name)
            skills[name] = "攻击"
        if not order:
            raise TurnStateError(f"第 {number} 回合 TEAM{team} 至少要留一个活着的角色")
        turns[number] = replace(
            state,
            order=tuple(order),
            cells=cells,
            dead=frozenset(state.dead - removed),
            skills=skills,
            bursts=bursts,
            costumes=keep(state.costumes),
        )
        touched = set(order) if removed else set(edited.get(number, frozenset())) | set(added)
        edited[number] = frozenset(touched & turns[number].living)
    updated = replace(record, turns=turns, edited=edited)
    save_record(updated, folder / RECORD_FILE)
    return updated


def _free_cell(cells) -> tuple[int, int] | None:
    from src.tasks.fiend_hunt.planner import COLS, ROWS

    taken = set(cells.values())
    for col in reversed(range(COLS)):  # the boss is to the right: front column first
        for row in range(ROWS):
            if (row, col) not in taken:
                return row, col
    return None
