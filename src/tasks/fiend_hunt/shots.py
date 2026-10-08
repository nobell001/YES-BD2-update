"""Fight from screenshots alone (Leo's first idea, 2026-09-30; built 2026-10-01).

A save folder may hold only the player's screenshots of each turn's
planning screen (top-down view, nobody selected, taken right before
BATTLE), with no record.json.  Each screenshot shows the TURN, the team,
the 1-N order of the list, each unit's card and 爆发, and where units stand,
but not who stands where: names only show when a unit is selected.  So
each turn the tool works it out on the live screen, in this order:

1. Read the live planning screen as usual (hold every unit: names, cells).
2. Tell which live unit is each entry of the screenshot's list: the same
   portrait (each costume has its own face), else the unit whose card column
   has the entry's skill icon or the entry's portrait among its costumes'
   art (an attack shows a costume too, the one last worn: another session
   or a skin shows another face), else the one unit left.  Unsure: stop.
3. Put the list in that order and every card and 爆发 as the screenshot
   shows, without moving anyone, so each unit now wears the costume it wears
   in the screenshot.
4. Compare each unit's look on the grid with every cell of the screenshot
   and take the placement that fits best; unsure: stop.
5. After the usual arranging, check every unit once more against the
   screenshot before BATTLE: each must look most like the screenshot's unit
   on its own cell, else stop (认不准就不按).

Measured on the 2K saves self_2k_a/self_2k_b (the same fight recorded
twice): step 2 matched 60/60 entries by face on the same turn and never
mismatched across turns; step 4/5 found 60/60 units' cells (see
vision.sprite_likeness).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Protocol

import numpy as np

from src.tasks.fiend_hunt import vision
from src.tasks.fiend_hunt.fight import ScreenReadError, prepare_turn
from src.tasks.fiend_hunt.planner import COLS, ROWS, Cell, Drag
from src.tasks.fiend_hunt.record import FightRecord, TurnState, TurnStateError
from src.tasks.fiend_hunt.turn_plan import ATTACK, TurnMismatch

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
# A file named like the recorder's (turn07.png): its turn when TURN can't be read.
_TURN_NAME = re.compile(r"turn\D*(\d{1,2})", re.IGNORECASE)
ALL_CELLS: tuple[Cell, ...] = tuple((row, col) for row in range(ROWS) for col in range(COLS))
# Placement (step 4): the best placement must beat every other by this much
# in summed likeness.  Check (step 5): a unit must look more like the
# screenshot's own cell than any other by this much.  Measured gaps: 0.084+.
PLACE_MARGIN_MIN = 0.03
CHECK_GAP_MIN = 0.03
# Placement rounds (step 4) before the check before BATTLE decides.
PLACE_ROUNDS = 3
# A summon tried on every free cell (_try_cells): its best cell's score must
# lead the next by this much (4K PC: 11.1 on TURN 15, 20.7 on TURN 19), and
# each try waits this long after the drag for the selection glow to go.
TRY_GAP_MIN = 5.0
TRY_SETTLE = 0.4
TRY_LOOKS = 2
# Drags to put it on its cell after the tries, each checked by a look.
TRY_DRAGS = 2
TRY_CELLS_MAX = 3  # free cells tried besides the one it stands on
# After the first move: the cell it left got this much worse (it was right
# there), or the cell it reached this much better (it is right there).
TRY_LEFT_WORSE = 8.0
TRY_REACHED_BETTER = 6.0
TRY_FIRST_SETTLE = 0.25
# ...or any lead when the unit's own likeness to the screenshot's cell picks
# the same cell by this much (4K PC TURN 23: 0.14-0.29 in six runs; on the
# other turns it was unreliable alone, so it only ever confirms).
TRY_LOOK_GAP_MIN = 0.10


class ShotScreen(Protocol):
    """What fighting from screenshots needs of the live screen (GameFightScreen)."""

    record: FightRecord | None

    def read_state(self, turn: int) -> TurnState: ...

    def switch_team(self, team: int) -> bool: ...

    def list_frame(self) -> np.ndarray | None:
        """The planning screen, nobody selected, once the list holds still."""

    def card_column(self, slot: int) -> tuple[np.ndarray, int, int] | None:
        """Select list slot ``slot``: (frame, cards, lit row) of its card column."""

    def clear_selection(self) -> None: ...

    def drag(self, drag: Drag) -> None: ...

    def grid_frame(self) -> np.ndarray:
        """The planning screen in the top-down view, nobody selected."""


def find_screenshots(
    folder: Path,
    read_turn: Callable[[np.ndarray], int | None],
    load: Callable[[Path], np.ndarray | None],
    log: Callable[[str], None] = lambda message: None,
) -> dict[int, str]:
    """TURN -> file name of each usable planning screenshot directly in ``folder``.

    Files are taken in name order; a later file of the same turn replaces
    an earlier one.  Anything that isn't a top-down planning screen is
    skipped with a note.
    """
    found: dict[int, str] = {}
    paths = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    for path in paths:
        frame = load(path)
        if frame is None:
            log(f"截图 {path.name} 打不开，跳过")
            continue
        height, width = frame.shape[:2]
        if abs(width / height - 16 / 9) > 0.02:
            log(f"截图 {path.name} 不是 16:9 的游戏全画面（{width}x{height}），跳过")
            continue
        if not vision.planning_visible(frame):
            log(f"截图 {path.name} 不是排位画面（右下角要有 TURN/BATTLE），跳过")
            continue
        if not vision.is_topdown(frame):
            log(f"截图 {path.name} 不是俯视视角（先按「切换视角」再截），跳过")
            continue
        if vision.selected_slots(frame):
            log(f"截图 {path.name} 里有人被选中（要没选人时截），跳过")
            continue
        turn = read_turn(frame)
        named = _TURN_NAME.fullmatch(path.stem)
        if turn is None and named:
            turn = int(named.group(1))
            log(f"截图 {path.name} 读不到回合数，照文件名当第 {turn} 回合")
        if turn is None:
            log(f"截图 {path.name} 读不到回合数，跳过")
            continue
        if turn in found:
            log(f"第 {turn} 回合有两张截图，用 {path.name}（不用 {found[turn]}）")
        found[turn] = path.name
    return found


def match_list(live: np.ndarray, live_order: tuple[str, ...], shot: np.ndarray) -> dict[int, str]:
    """Screenshot list slot -> live unit, for the entries whose portrait is a live one's.

    Each costume has its own portrait, so the same face means the same
    character; an entry with no clear match, or with two, is left out.
    """
    count = len(live_order)
    near: dict[int, list[int]] = {
        slot: [
            mine
            for mine in range(count)
            if vision.face_difference(shot, slot, live, mine) <= vision.FACE_SAME_MAX
        ]
        for slot in range(count)
    }
    claims: dict[int, int] = {}
    for mine in range(count):
        claims[mine] = sum(mine in found for found in near.values())
    return {
        slot: live_order[found[0]]
        for slot, found in near.items()
        if len(found) == 1 and claims[found[0]] == 1
    }


def pick_costumes(likeness: Mapping[str, Mapping[int, float]]) -> dict[int, str]:
    """Screenshot slot -> unit, for slots whose portrait clearly is one of that
    unit's costumes (vision.costume_likeness per unit and slot)."""
    picked: dict[int, str] = {}
    slots = {slot for scores in likeness.values() for slot in scores}
    for slot in slots:
        ranked = sorted(
            ((scores[slot], unit) for unit, scores in likeness.items() if slot in scores),
            reverse=True,
        )
        best, unit = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else -1.0
        if best >= vision.COSTUME_SAME_MIN and best - runner_up >= vision.COSTUME_MARGIN:
            picked[slot] = unit
    taken = list(picked.values())
    return {slot: unit for slot, unit in picked.items() if taken.count(unit) == 1}


def shot_bursts(shot: np.ndarray, order: Iterable[str]) -> dict[str, int]:
    """爆发 level of each unit the screenshot shows on a skill (0 = off)."""
    levels = {}
    for slot, unit in enumerate(order):
        if vision.has_skill_icon(shot, slot):
            level = vision.burst_flame(shot, slot)
            if level is not None:
                levels[unit] = level
    return levels


def best_placement(
    likeness: Mapping[str, Mapping[Cell, float]],
) -> tuple[dict[str, Cell], float]:
    """The cells (one each) with the highest summed likeness, and its lead over
    the best placement that puts any unit elsewhere (inf with one choice)."""
    units = list(likeness)
    if not units:
        return {}, float("inf")
    cells = sorted({cell for scores in likeness.values() for cell in scores})

    def solve(banned: tuple[str, Cell] | None) -> tuple[float, dict[str, Cell]]:
        best: dict[int, tuple[float, dict[str, Cell]]] = {0: (0.0, {})}
        for unit in units:
            step: dict[int, tuple[float, dict[str, Cell]]] = {}
            for used, (total, placed) in best.items():
                for index, cell in enumerate(cells):
                    if used >> index & 1 or (unit, cell) == banned:
                        continue
                    score = likeness[unit].get(cell)
                    if score is None:
                        continue
                    key = used | 1 << index
                    if key not in step or step[key][0] < total + score:
                        step[key] = (total + score, {**placed, unit: cell})
            best = step
        if not best:
            return float("-inf"), {}
        return max(best.values(), key=lambda item: item[0])

    total, placed = solve(None)
    if not placed:
        return {}, float("-inf")
    runner_up = max(solve(pair)[0] for pair in placed.items())
    return placed, total - runner_up


def misplaced(
    live: np.ndarray, cells: Mapping[str, Cell], shot: np.ndarray, candidates: Iterable[Cell]
) -> list[str]:
    """Units that don't look most like the screenshot's unit on their own cell."""
    candidates = list(candidates)
    wrong = []
    for unit, cell in cells.items():
        scores = {other: vision.sprite_likeness(live, cell, shot, other) for other in candidates}
        rivals = [score for other, score in scores.items() if other != cell]
        if rivals and scores[cell] - max(rivals) < CHECK_GAP_MIN:
            wrong.append(unit)
    return wrong


class ScreenshotTurns:
    """replay_fight's ``solve`` and ``check`` for a save of screenshots only."""

    def __init__(
        self,
        screen: ShotScreen,
        folder: Path,
        files: Mapping[int, str],
        read_team: Callable[[np.ndarray], int | None],
        load: Callable[[Path], np.ndarray | None],
        log: Callable[[str], None] = lambda message: None,
        is_summon: Callable[[str], bool] = lambda unit: False,
        check_card: Callable[[str], bool] | None = None,
    ) -> None:
        self.screen = screen
        self.folder = Path(folder)
        self.files = dict(files)
        self.read_team = read_team
        self.load = load
        self.log = log
        self.is_summon = is_summon
        # Whose card is set from the screenshot (None: everyone's).  只认召唤物
        # leaves the characters' to the costume order, as in a record replay.
        self.check_card = check_card
        self._shots: dict[int, np.ndarray] = {}

    def shot(self, turn: int) -> np.ndarray:
        if turn not in self._shots:
            frame = self.load(self.folder / self.files[turn]) if turn in self.files else None
            if frame is None:
                raise ScreenReadError(f"没有第 {turn} 回合的截图")
            self._shots = {turn: frame}  # a replay only goes forward
        return self._shots[turn]

    def solve(self, turn: int, record: FightRecord) -> tuple[FightRecord, TurnState]:
        """Turn ``turn`` worked out from its screenshot, with the list, cards and
        爆发 already set on the screen; returns the record with it, and the screen."""
        if turn not in self.files:
            raise TurnMismatch(f"存档里没有第 {turn} 回合的截图")
        shot = self.shot(turn)
        team = self.read_team(shot)
        if team is None:
            raise ScreenReadError(f"第 {turn} 回合的截图读不到 TEAM1/TEAM2/TEAM3")
        live = self.screen.read_state(turn)
        if live.team != team:
            self.log(f"第 {turn} 回合换成 TEAM{team}（照截图）")
            if not self.screen.switch_team(team):
                raise TurnMismatch(f"换不成 TEAM{team}")
            live = self.screen.read_state(turn)
            if live.team != team:
                raise TurnMismatch(f"换队后还是 TEAM{live.team}，截图是 TEAM{team}")
        order = self._order(turn, live, shot)
        try:
            first = TurnState(
                turn, team, order, live.cells, live.dead, bursts=shot_bursts(shot, order)
            )
        except TurnStateError as error:
            raise TurnMismatch(f"第 {turn} 回合：{error}") from error
        self.screen.record = self._with(record, first)
        checked = [unit for unit in order if self.check_card is None or self.check_card(unit)]
        cards = {
            "by_screenshot": checked,
            "loose_bursts": [unit for unit in order if unit not in checked],
            "confirmed": True,
        }
        # Step 3: cards (so costumes) as in the screenshot, nobody moved.
        live = prepare_turn(self.screen, first, self.log, live, **cards)
        self._dress(turn, order, shot)
        # Step 4.  A sprite reaches into the cell above it, so a unit's look
        # depends a little on its neighbours: after a move, look again until
        # the placement holds (the neighbours are then the screenshot's).
        state = first
        for _ in range(PLACE_ROUNDS):
            placed, lead = self._place(live, shot)
            cells = {**placed, **{unit: live.cells[unit] for unit in live.dead}}
            if cells == dict(live.cells):
                if lead < PLACE_MARGIN_MIN and len(cards["by_screenshot"]) < len(order):
                    # 只看召唤物: the costume order put someone in another
                    # costume than the screenshot (4K PC real fight TURN 17:
                    # lead 0.016).  Set this turn's cards as the screenshot
                    # shows, so everyone looks as there, and look again.
                    self.log(f"第 {turn} 回合：站位认不准（{lead:.3f}），这回合的卡照截图设")
                    cards = {**cards, "by_screenshot": list(order), "loose_bursts": []}
                    live = prepare_turn(self.screen, state, self.log, live, **cards)
                    self._dress(turn, order, shot)
                    continue
                if lead < PLACE_MARGIN_MIN:
                    raise TurnMismatch(
                        f"第 {turn} 回合：截图里谁站哪格认不准（差距 {lead:.3f}），停下"
                    )
                break
            try:
                state = replace(first, cells=cells)
            except TurnStateError as error:
                raise TurnMismatch(f"第 {turn} 回合：{error}") from error
            moved = [unit for unit in order if cells[unit] != live.cells[unit]]
            self.log(f"第 {turn} 回合（照截图）：顺序 {'、'.join(order)}；移动 {'、'.join(moved)}")
            self.screen.record = self._with(record, state)
            live = prepare_turn(self.screen, state, self.log, live, **cards)
        for unit in order:
            if self.is_summon(unit):
                live = self._try_cells(turn, live, unit, shot)
        updated = self._with(record, replace(first, cells=dict(live.cells)))
        self.screen.record = updated
        return updated, live

    def check(self, turn: int, state: TurnState) -> None:
        """Before BATTLE: everyone must look like the screenshot's unit on their cell."""
        shot = self.shot(turn)
        frame = self.screen.grid_frame()
        tombs = {state.cells[unit] for unit in state.dead}
        # Summons were put where they look most like the screenshot by trying
        # every free cell (_try_cells); their small sprite can't be told by
        # likeness alone (4K PC TURN 13/15: the robot passed on a wrong cell).
        summons = [unit for unit in state.order if self.is_summon(unit)]
        badges = vision.badge_cells(shot)
        if len(summons) == 1 and len(badges) == 1 and state.cells[summons[0]] != badges[0][1]:
            raise TurnMismatch(
                f"第 {turn} 回合排好后，{summons[0]} 在 {state.cells[summons[0]]}，"
                f"截图的徽章在 {badges[0][1]}，没按 BATTLE"
            )
        living = {unit: state.cells[unit] for unit in state.order if not self.is_summon(unit)}
        wrong = misplaced(frame, living, shot, [c for c in ALL_CELLS if c not in tombs])
        if wrong:
            # A buff aura pulses (4K PC TURN 21: 格兰希特 had a buff the 2K
            # run lacked and failed on one frame, passed on the next): look
            # again, all units at once; everyone must still fit their cell.
            placed, lead = self._place(state, shot)
            if lead >= PLACE_MARGIN_MIN and all(placed[u] == c for u, c in living.items()):
                self.log(
                    f"第 {turn} 回合：{'、'.join(wrong)} 单看不够像，"
                    f"整体再比一次都在截图那格（差距 {lead:.2f}）"
                )
                return
            raise TurnMismatch(
                f"第 {turn} 回合排好后，{'、'.join(wrong)} 跟截图里那格的人不像，没按 BATTLE"
            )

    def _sleep(self, seconds: float) -> None:
        sleep = getattr(self.screen, "sleep", None)
        if callable(sleep):
            sleep(seconds)

    def _with(self, record: FightRecord, state: TurnState) -> FightRecord:
        try:
            return FightRecord(
                {**record.turns, state.turn: state},
                record.title,
                record.source,
                {**record.screenshots, state.turn: self.files[state.turn]},
            )
        except TurnStateError as error:
            raise TurnMismatch(f"第 {state.turn} 回合：{error}") from error

    def _order(self, turn: int, live: TurnState, shot: np.ndarray) -> tuple[str, ...]:
        """Step 2: the live unit of each entry of the screenshot's list."""
        count = vision.slot_count(shot)
        out = vision.out_slots(shot, count)
        living = count - len(out)
        if living != len(live.order) or len(out) != len(live.dead):
            raise TurnMismatch(
                f"第 {turn} 回合：截图里 {living} 人活着、{len(out)} 人阵亡，"
                f"游戏里 {len(live.order)} 人活着、{len(live.dead)} 人阵亡"
            )
        frame = self.screen.list_frame()
        if frame is None:
            raise ScreenReadError("左侧列表一直在变，没法跟截图比")
        found = match_list(frame, live.order, shot)
        units = [unit for unit in live.order if unit not in found.values()]
        unknown = [slot for slot in range(living) if slot not in found]
        if len(unknown) > 1 and units:
            # Faces that differ: the costume differs (a skin, or another
            # session last wore another one).  Look in each unit's card column.
            icons: dict[int, list[str]] = {}
            costumes: dict[str, dict[int, float]] = {}
            for unit in units:
                column = self.screen.card_column(live.order.index(unit))
                if column is None:
                    continue
                cards_frame, cards, _ = column
                costumes[unit] = {
                    slot: vision.costume_likeness(cards_frame, cards, shot, slot)
                    for slot in unknown
                }
                for slot in unknown:
                    if (
                        vision.has_skill_icon(shot, slot) is True
                        and vision.card_with_icon(cards_frame, cards, shot, slot) is not None
                    ):
                        icons.setdefault(slot, []).append(unit)
            self.screen.clear_selection()
            for slot, hits in icons.items():
                if len(hits) == 1 and hits[0] not in found.values():
                    found[slot] = hits[0]
            for slot, unit in pick_costumes(costumes).items():
                if slot not in found and unit not in found.values():
                    found[slot] = unit
            units = [unit for unit in live.order if unit not in found.values()]
        left = [slot for slot in range(living) if slot not in found]
        if len(left) == 1 and len(units) == 1:
            found[left[0]] = units[0]
            left = []
        if left:
            slots = "、".join(str(slot + 1) for slot in left)
            raise TurnMismatch(f"第 {turn} 回合：认不出截图列表第 {slots} 位是谁")
        return tuple(found[slot] for slot in range(living))

    def _dress(self, turn: int, order: tuple[str, ...], shot: np.ndarray) -> None:
        """Step 3 for attackers: an attack shows the costume last worn, on the list
        and on the grid, so one in another costume than the screenshot's (another
        session wore another) puts that costume's skill card up and goes back to
        attack: it then wears the screenshot's costume, and step 4 compares like
        with like (4K PC 2026-10-01, TURN 1: three attackers looked different)."""
        frame = self.screen.list_frame()
        if frame is None:
            raise ScreenReadError("左侧列表一直在变，没法跟截图比")
        changed = []
        for slot, unit in enumerate(order):
            if vision.has_skill_icon(shot, slot) is not False:
                continue  # a skill: its card already put its costume on
            if vision.face_difference(frame, slot, shot, slot) <= vision.FACE_SAME_MAX:
                continue
            column = self.screen.card_column(slot)
            if column is None:
                raise ScreenReadError(f"点不开 {unit} 的技能卡")
            cards_frame, cards, _ = column
            score, row = vision.costume_card(cards_frame, cards, shot, slot)
            self.screen.clear_selection()
            if row is None or score < vision.COSTUME_SAME_MIN:
                raise TurnMismatch(f"第 {turn} 回合：{unit} 的技能卡里没有截图里那件服装")
            card = vision.card_label(row)
            if not (self.screen.pick_skill(slot, card) and self.screen.pick_skill(slot, ATTACK)):
                raise TurnMismatch(f"第 {turn} 回合：{unit} 换不成截图里的服装（{card}）")
            changed.append(unit)
        if not changed:
            return
        frame = self.screen.list_frame()
        if frame is None:
            raise ScreenReadError("左侧列表一直在变，没法跟截图比")
        still = [
            unit
            for unit in changed
            if vision.face_difference(frame, order.index(unit), shot, order.index(unit))
            > vision.FACE_SAME_MAX
        ]
        if still:
            raise TurnMismatch(f"第 {turn} 回合：{'、'.join(still)} 换了服装还是跟截图不一样")
        self.log(f"第 {turn} 回合：{'、'.join(changed)} 换成截图里的服装后改回攻击")

    def _place(self, live: TurnState, shot: np.ndarray) -> tuple[dict[str, Cell], float]:
        """Step 4: the cell each living unit stands on in the screenshot, and how sure.

        A unit's likeness to a screenshot cell counts less the more that cell
        looks like a cell that is empty on the live grid: a small unit (the
        summon robot, 4K PC TURN 15) hardly looks like itself, but it is never
        left on bare floor while a cell of the screenshot has someone on it.
        On the 2K saves this raised the weakest turn's lead from 0.08 to 0.36.
        """
        frame = self.screen.grid_frame()
        tombs = {live.cells[unit] for unit in live.dead}
        candidates = [cell for cell in ALL_CELLS if cell not in tombs]
        taken = set(live.cells.values())
        empty = [cell for cell in ALL_CELLS if cell not in taken]
        floor = {
            cell: max(
                (vision.sprite_likeness(frame, bare, shot, cell) for bare in empty), default=0.0
            )
            for cell in candidates
        }
        units = [unit for unit in live.order if not self.is_summon(unit)]
        likeness = {
            unit: {
                cell: vision.sprite_likeness(frame, live.cells[unit], shot, cell) - floor[cell]
                for cell in candidates
            }
            for unit in units
        }
        placed, lead = best_placement(likeness)
        if units and not placed:
            raise TurnMismatch("截图里的格子放不下这些人")
        # Summons stay put for now (moved aside if someone needs their cell);
        # _try_cells then finds theirs.
        used = set(placed.values()) | tombs
        for unit in live.order:
            if unit in placed:
                continue
            cell = live.cells[unit]
            if cell in used:
                cell = next(c for c in candidates if c not in used)
            placed[unit] = cell
            used.add(cell)
        return placed, lead

    def _try_cells(self, turn: int, live: TurnState, unit: str, shot: np.ndarray) -> TurnState:
        """Put ``unit`` on each free cell in turn and leave it where it makes the
        grid most like the screenshot (Leo 2026-10-01: a summon looks the same in
        every save, so stand it where the screenshot shows it).

        The game draws it with its overlaps and the skill glow.  Each cell's
        score is how much closer that cell gets to the screenshot with the unit
        on it than without (its median over the other tries), so the cell's own
        glow and the 2K/4K tone cancel out (vision.cell_differences).  4K PC,
        the robot: TURN 15 its cell -15.8, the next -2.8; TURN 19 -13.3 / +12.6
        (summed differences had given 91 / 94 there and stopped).
        """
        taken = {cell for other, cell in live.cells.items() if other != unit}
        start = live.cells[unit]
        # The screenshot's countdown badge says the summon's cell outright
        # (Leo 2026-10-01: look at the screenshot first, don't keep moving
        # it).  94 screenshots at 2K/4K/1080p: right every time, none on
        # turns without a summon.  One summon and one badge only; else try.
        summons = [other for other in live.order if self.is_summon(other)]
        badges = vision.badge_cells(shot) if len(summons) == 1 else []
        # The robot's own look (vision.robot_cells) confirms the badge, or
        # stands in for one that can't be read when it leads clearly.
        looks = (
            vision.robot_cells(shot, [c for c in ALL_CELLS if c not in taken])
            if unit == vision.ROBOT_NAME
            else []
        )
        target, how = None, ""
        if len(badges) == 1:
            target, how = badges[0][1], f"徽章 {badges[0][0]:.2f}"
            if looks:
                at_target = next(score for score, cell in looks if cell == target)
                if looks[0][1] != target and looks[0][0] - at_target >= vision.ROBOT_LEAD_ALONE:
                    self.log(
                        f"第 {turn} 回合（照截图）：截图徽章在 {target}，{unit} 的样子更像 "
                        f"{looks[0][1]}，改成一格格试"
                    )
                    target = None
                else:
                    how += f"，样子也对 {at_target:.2f}"
        elif len(looks) > 1 and looks[0][0] - looks[1][0] >= vision.ROBOT_LEAD_ALONE:
            target, how = looks[0][1], f"样子 {looks[0][0]:.2f}"
        if target == start:
            self.log(f"第 {turn} 回合（照截图）：{unit} 已在截图那格 {start}（{how}）")
            return live
        if target is not None and target not in taken:
            self._drag_until_landed(turn, live, unit, start, target)
            self.log(f"第 {turn} 回合（照截图）：{unit} 放到 {target}（{how}）")
            try:
                return replace(live, cells={**live.cells, unit: target})
            except TurnStateError as error:
                raise TurnMismatch(f"第 {turn} 回合：{error}") from error
        free = [cell for cell in ALL_CELLS if cell not in taken and cell != start]
        if not free:
            return live

        def look(cells: list[Cell], times: int = TRY_LOOKS) -> tuple[list[float], np.ndarray]:
            looks, frame = [], None
            for _ in range(times):  # the skill glow pulses: average a few looks
                frame = self.screen.grid_frame()
                looks.append(vision.cell_differences(frame, shot, cells))
            return [float(value) for value in np.mean(looks, axis=0)], frame

        # Where the screenshot shows someone and the live grid bare floor
        # differs most: only the likeliest free cells are tried (4K PC TURN
        # 19/23: the robot's cell came first of 6 both times).
        cells = [start, *free]
        first, frame = look(cells)
        likely = sorted(free, key=lambda cell: first[cells.index(cell)], reverse=True)
        alike: dict[Cell, float] = {start: vision.sprite_likeness(frame, start, shot, start)}
        # One move to the likeliest cell often settles it (Leo 2026-10-01: it
        # kept moving after the right cell).  Leaving the right cell makes it
        # clearly worse (4K PC: +14 to +19, else -17 to -2); reaching it makes
        # that one clearly better (TURN 19: -12, wrong cells +0.1 and up).
        top = likely[0]
        self.screen.drag(Drag(start, top))
        self._sleep(TRY_FIRST_SETTLE)
        # One look is enough here: both answers clear their bar by 3+ (Leo
        # 2026-10-01: the summon's time matters most).
        moved, frame = look(cells, 1)
        at_start = moved[0] - first[0]
        at_top = moved[cells.index(top)] - first[cells.index(top)]
        lit_slot = getattr(self.screen, "lit_slot", None)
        unclear = at_start < TRY_LEFT_WORSE and at_top > -TRY_REACHED_BETTER
        if unclear and callable(lit_slot) and lit_slot(top) != live.order.index(unit):
            # Nothing changed: the drag may have missed the unit.  Redo it.
            self._drag_until_landed(turn, live, unit, start, top)
            self._sleep(TRY_FIRST_SETTLE)
            moved, frame = look(cells, 1)
            at_start = moved[0] - first[0]
            at_top = moved[cells.index(top)] - first[cells.index(top)]
        alike[top] = vision.sprite_likeness(frame, top, shot, top)
        if at_start >= TRY_LEFT_WORSE:
            self._drag_until_landed(turn, live, unit, top, start)
            self.log(f"第 {turn} 回合（照截图）：{unit} 本来就在截图那格（{at_start:+.1f}）")
            return live
        if at_top <= -TRY_REACHED_BETTER:
            self.log(f"第 {turn} 回合（照截图）：{unit} 放到 {top}（{at_top:+.1f}）")
            try:
                return replace(live, cells={**live.cells, unit: top})
            except TurnStateError as error:
                raise TurnMismatch(f"第 {turn} 回合：{error}") from error
        # Unclear (TURN 23: the robot half behind the unit below it): try more.
        tried = [start, *likely[:TRY_CELLS_MAX]]
        seen: list[list[float]] = [
            [first[cells.index(cell)] for cell in tried],
            [moved[cells.index(cell)] for cell in tried],
        ]
        here = top
        for cell in tried[2:]:
            self.screen.drag(Drag(here, cell))
            here = cell
            self._sleep(TRY_SETTLE)
            differences, frame = look(tried)
            seen.append(differences)
            alike[cell] = vision.sprite_likeness(frame, cell, shot, cell)
        scores = {
            cell: seen[k][k] - float(np.median([row[k] for j, row in enumerate(seen) if j != k]))
            for k, cell in enumerate(tried)
        }
        ranked = sorted(tried, key=scores.__getitem__)
        best, second = ranked[0], ranked[1]
        by_look = sorted(tried, key=alike.__getitem__, reverse=True)
        shown = "，".join(f"{cell} {scores[cell]:+.1f}/{alike[cell]:.2f}" for cell in ranked)
        self.log(f"第 {turn} 回合（照截图）：{unit} 试 {len(tried)} 格：{shown}")
        clear = scores[best] < 0 and scores[second] - scores[best] >= TRY_GAP_MIN
        # A weaker lead holds when the unit's own look picks the same cell
        # clearly (4K PC TURN 23, the robot half behind the unit below it:
        # leads 0.5-4.6, its look 0.71-0.93 against 0.53-0.64 elsewhere).
        agreed = (
            by_look[0] == best
            and scores[best] < 0
            and alike[by_look[0]] - alike[by_look[1]] >= TRY_LOOK_GAP_MIN
        )
        # Never against the unit's own look: 4K PC TURN 23 (2026-10-01) put
        # the robot on (2, 2) by a 5.2 lead while its look said (1, 1), 0.80
        # against 0.52, and BATTLE went off on the wrong cell.
        contradicted = by_look[0] != best and alike[by_look[0]] - alike[best] >= TRY_LOOK_GAP_MIN
        if contradicted or not (clear or agreed):
            raise TurnMismatch(
                f"第 {turn} 回合：{unit} 放哪格都差不多像截图"
                f"（{scores[best]:+.1f} / {scores[second]:+.1f}），停下"
            )
        # The check before BATTLE leaves summons out, so make sure the last drag
        # landed: the grid must look like the try on ``best`` again.  A drag can
        # miss its unit (2K PC); then it stands where the grid looks like.
        for _ in range(TRY_DRAGS):
            if best == here:
                break
            self.screen.drag(Drag(here, best))
            self._sleep(TRY_SETTLE)
            here = self._tried_on(shot, tried, seen)
        if best != here:
            raise TurnMismatch(f"第 {turn} 回合：{unit} 拖不到 {best}（还在 {here}），停下")
        if best != start:
            self.log(f"第 {turn} 回合（照截图）：{unit} 放到 {best}")
        try:
            return replace(live, cells={**live.cells, unit: best})
        except TurnStateError as error:
            raise TurnMismatch(f"第 {turn} 回合：{error}") from error

    def _drag_until_landed(
        self, turn: int, live: TurnState, unit: str, start: Cell, target: Cell
    ) -> None:
        """Drag ``unit`` from ``start`` to ``target`` and hold ``target``: its list
        slot must light.  A drag can miss its unit (2K PC), and the turn's cells
        aren't held again after this (fight.prepare_turn ``confirmed``)."""
        lit_slot = getattr(self.screen, "lit_slot", None)
        slot = live.order.index(unit)
        here = start
        for _ in range(TRY_DRAGS):
            self.screen.drag(Drag(here, target))
            if not callable(lit_slot) or lit_slot(target) == slot:
                return
            if callable(lit_slot) and lit_slot(start) == slot:
                here = start  # it never left: drag again
                continue
            break
        raise TurnMismatch(f"第 {turn} 回合：{unit} 拖不到 {target}，停下")

    def _tried_on(self, shot: np.ndarray, tried: list[Cell], seen: list[list[float]]) -> Cell:
        """The tried cell whose look the grid matches now (_try_cells)."""
        now = vision.cell_differences(self.screen.grid_frame(), shot, tried)
        gaps = [sum(abs(a - b) for a, b in zip(now, row)) for row in seen]
        return tried[int(np.argmin(gaps))]
