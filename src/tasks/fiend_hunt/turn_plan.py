"""Compare the live planning screen with the saved turn and plan the fix.

The saved turn is the target: the same team, the same living units on the
same cells, the same 1-5 order and the same action card for each unit.
Whatever differs is turned into actions (team switch, ⇅ swaps, drags,
cards to pick).  When the live battle has left the saved plan, for example
someone died who was still alive in the save, nothing is planned: the tool
stops without pressing BATTLE and hands the fight back to the player.

A unit's action is the lit card (bright frame in the unit's element
colour) in the column that opens when it is selected.  Cards are saved as
labels: 攻击 (the normal attack, first card), 击退 (the second card),
技能1, 技能2, ... (one skill card per costume, top to bottom).  Players
usually set each character's attack or skill in the 服装顺序设置 before
the fight and the game follows it, but a summon can't be set there:
魔法增幅器ET001 has to be switched to 攻击 by hand on the last turn of the
test fight.  So the player chooses (Leo, 2026-09-30) whether a replay
checks every unit's card (slower; for guides without a skill order) or
only the summons' (faster and steadier).  A chart only says attack or
skill: its bare 技能 is whichever skill card is up.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from src.tasks.fiend_hunt.planner import (
    Drag,
    FormationPlanError,
    plan_drags,
    plan_order_swaps,
)
from src.tasks.fiend_hunt.record import TurnState

ATTACK = "攻击"
KNOCKBACK = "击退"
SKILL = "技能"


class TurnMismatch(Exception):
    """The live battle has left the saved plan; stop and hand over."""


def action_matches(current: str | None, wanted: str) -> bool:
    """Whether the card on the screen is the saved one (a bare 技能: any skill card)."""
    if current is None:
        return False
    if wanted == SKILL:
        return current.startswith(SKILL)
    return current == wanted


def pick_order(changes: Mapping[str, str]) -> list[tuple[str, str]]:
    """Cards to pick, attacks first: they free the SP a skill may need."""
    return sorted(changes.items(), key=lambda change: change[1].startswith(SKILL))


@dataclass(frozen=True)
class TurnActions:
    """What to do on the planning screen, in this order.

    A team switch comes alone: afterwards the grid holds the other team, so
    the caller reads the screen again and plans once more.
    """

    switch_team: bool = False
    order_swaps: tuple[tuple[int, int], ...] = ()
    drags: tuple[Drag, ...] = ()
    skill_changes: Mapping[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        """Nothing left to do: the screen matches the saved turn."""
        return not (self.switch_team or self.order_swaps or self.drags or self.skill_changes)


def plan_turn(live: TurnState, saved: TurnState, *, skills: bool = True) -> TurnActions:
    """Actions that turn the live planning screen into the saved turn.

    Raises TurnMismatch when that can't or shouldn't be done: another turn,
    a team the game can't switch back to, a death the save doesn't have (or
    the other way round), units that don't match, a tombstone on another
    cell, or a card that couldn't be read.  ``skills=False`` leaves the
    cards out, for a caller that checks them after the grid is right.
    """
    if live.turn != saved.turn:
        raise TurnMismatch(f"现在是第 {live.turn} 回合，存档是第 {saved.turn} 回合")
    if saved.team < live.team:
        raise TurnMismatch(
            f"存档第 {saved.turn} 回合用 TEAM{saved.team}，现在已经是 TEAM{live.team}，换不回去"
        )
    if saved.team > live.team:
        return TurnActions(switch_team=True)

    missing, extra = set(saved.cells) - set(live.cells), set(live.cells) - set(saved.cells)
    if missing or extra:
        # Leo 2026-10-06: the player sets the team up as recorded first.
        parts = ([f"少了 {_names(missing)}"] if missing else []) + (
            [f"多了 {_names(extra)}"] if extra else []
        )
        raise TurnMismatch(
            f"第 {saved.turn} 回合 TEAM{saved.team} 跟存档不一样：{'，'.join(parts)}"
            "（队伍要组得跟录的时候一样）"
        )

    newly_dead = live.dead - saved.dead
    if newly_dead:
        raise TurnMismatch(f"{_names(newly_dead)} 已阵亡，存档里第 {saved.turn} 回合还活着")
    still_alive = saved.dead - live.dead
    if still_alive:
        raise TurnMismatch(f"{_names(still_alive)} 还活着，存档里第 {saved.turn} 回合已阵亡")

    try:
        drags = plan_drags(live.cells, saved.cells, fixed=live.dead)
        swaps = plan_order_swaps(live.order, saved.order)
    except FormationPlanError as error:
        raise TurnMismatch(str(error)) from error

    skill_changes: dict[str, str] = {}
    for unit, wanted in saved.skills.items() if skills else ():
        current = live.skills.get(unit)
        if current is None:
            raise TurnMismatch(f"读不到 {unit} 第 {live.turn} 回合选的卡")
        if not action_matches(current, wanted):
            skill_changes[unit] = wanted
    return TurnActions(order_swaps=tuple(swaps), drags=tuple(drags), skill_changes=skill_changes)


def _names(units: Iterable[str]) -> str:
    return "、".join(sorted(units))
