"""Plan the drags that turn one 魔兽追踪者 formation into another.

Two things change between turns: where the units stand, and the 1-5 order
in the left list (the order they act in).  The player grid is 3 rows x 4
columns.  Row 0 is the top row on screen and
column 3 is the front column next to the boss, the same layout the souseha
formation charts use.  Dragging a unit onto an empty cell moves it there;
dropping it onto an occupied cell swaps the two units (Leo, 2026-09-30).

Units are any hashable ids (a character, a summon, a list slot).  The
planner only reasons about cells, so it doesn't matter how the caller
recognised who stands where.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass

ROWS = 3
COLS = 4

Cell = tuple[int, int]


class FormationPlanError(ValueError):
    """The two formations can't be matched by dragging."""


@dataclass(frozen=True)
class Drag:
    source: Cell
    target: Cell


def all_cells() -> list[Cell]:
    return [(row, col) for row in range(ROWS) for col in range(COLS)]


def validate_formation(formation: Mapping[Hashable, Cell]) -> None:
    seen: dict[Cell, Hashable] = {}
    for unit, cell in formation.items():
        row, col = cell
        if not (0 <= row < ROWS and 0 <= col < COLS):
            raise FormationPlanError(f"{unit!r} 的格子 {cell} 不在 {ROWS}x{COLS} 范围内")
        if cell in seen:
            raise FormationPlanError(f"{seen[cell]!r} 和 {unit!r} 站在同一格 {cell}")
        seen[cell] = unit


def apply_drags(formation: Mapping[Hashable, Cell], drags: Iterable[Drag]) -> dict[Hashable, Cell]:
    """Return the formation after the drags, with the game's move/swap rule."""
    positions = dict(formation)
    occupant = {cell: unit for unit, cell in positions.items()}
    for drag in drags:
        unit = occupant.pop(drag.source, None)
        if unit is None:
            raise FormationPlanError(f"拖动起点 {drag.source} 没有角色")
        other = occupant.pop(drag.target, None)
        positions[unit] = drag.target
        occupant[drag.target] = unit
        if other is not None:
            positions[other] = drag.source
            occupant[drag.source] = other
    return positions


def plan_drags(
    current: Mapping[Hashable, Cell],
    target: Mapping[Hashable, Cell],
    fixed: Iterable[Hashable] = (),
) -> list[Drag]:
    """Fewest drags that turn ``current`` into ``target``.

    Units whose target cell is empty are moved first, working back along
    each chain of moves; what is left forms cycles, which are closed with
    swaps (a cycle of k units takes k-1 swaps).  ``fixed`` units can't be
    dragged; they must already stand on their target cell, and since target
    cells are unique no swap ever displaces them.
    """
    validate_formation(current)
    validate_formation(target)
    if set(current) != set(target):
        missing = sorted(map(repr, set(target) - set(current)))
        extra = sorted(map(repr, set(current) - set(target)))
        raise FormationPlanError(f"场上角色和目标不一致：缺少 {missing}，多出 {extra}")
    for unit in fixed:
        if unit in current and current[unit] != target[unit]:
            raise FormationPlanError(f"{unit!r} 不能拖，但它不在目标格 {target[unit]}")

    positions = dict(current)
    occupant = {cell: unit for unit, cell in positions.items()}
    order = list(current)  # stable, caller-defined tie-break
    drags: list[Drag] = []

    def drag(unit: Hashable) -> None:
        source, goal = positions[unit], target[unit]
        other = occupant.pop(goal, None)
        occupant.pop(source)
        positions[unit] = goal
        occupant[goal] = unit
        if other is not None:
            positions[other] = source
            occupant[source] = other
        drags.append(Drag(source, goal))

    while True:
        misplaced = [unit for unit in order if positions[unit] != target[unit]]
        if not misplaced:
            return drags
        into_empty = next((unit for unit in misplaced if target[unit] not in occupant), None)
        drag(into_empty if into_empty is not None else misplaced[0])


def apply_order_swaps(
    order: Sequence[Hashable], swaps: Iterable[tuple[int, int]]
) -> list[Hashable]:
    """Return the list order after the swaps (0-based slot indices)."""
    result = list(order)
    for first, second in swaps:
        result[first], result[second] = result[second], result[first]
    return result


def plan_order_swaps(
    current: Sequence[Hashable], target: Sequence[Hashable]
) -> list[tuple[int, int]]:
    """Fewest list swaps that turn the order ``current`` into ``target``.

    In battle, dragging one slot's ⇅ onto another slot's ⇅ swaps the two
    entries without moving anyone on the grid.  Slots are 0-based.
    """
    if len(set(current)) != len(current) or len(set(target)) != len(target):
        raise FormationPlanError("顺序里有重复的角色")
    if set(current) != set(target):
        raise FormationPlanError(f"顺序里的角色和目标不一致：{list(current)} / {list(target)}")
    order = list(current)
    swaps: list[tuple[int, int]] = []
    for slot, wanted in enumerate(target):
        if order[slot] != wanted:
            other = order.index(wanted, slot + 1)
            order[slot], order[other] = order[other], order[slot]
            swaps.append((slot, other))
    return swaps
