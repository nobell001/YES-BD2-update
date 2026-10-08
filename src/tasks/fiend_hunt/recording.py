"""Record a fight: the player arranges each turn, the tool saves it.

The player sets up each turn by hand as usual, but presses the save key
instead of BATTLE.  The tool then reads the planning screen (who stands
where, the order, team, skills), saves the turn with a screenshot, and
presses BATTLE itself.  record.json is rewritten after every saved turn,
so a fight cut short still keeps the turns saved so far.  A turn the
player starts with BATTLE directly is noted as not saved; replaying the
record stops at that turn.

Recording into an existing save edits it (Leo 2026-10-01): its turns are
kept, a turn recorded again is overwritten, and turns deleted on the
魔兽追踪者 page meanwhile stay deleted (the record is re-read before each
save).  The key always saves the turn the game shows (TURN, bottom right),
whatever the page shows (Leo 2026-10-06: the page doesn't follow the game;
a turn is added or overwritten by its TURN number, as in the first
version).

The screenshot also keeps each unit's action card: the left list shows it
(the portrait of the costume whose skill is up, with a round skill icon;
none on an attack), and a replay compares the list with the screenshot
(see fight.py).  The cards the screen reads (攻击/技能n; the task has it
read them) are saved too: they settle a unit the screenshot can't, as two
skills with near-identical icons (Leo's 尤里光盾 save, 2026-10-01).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from src.tasks.fiend_hunt.fight import FightScreen, ScreenReadError
from src.tasks.fiend_hunt.record import FightRecord, TurnState, TurnStateError, save_record
from src.tasks.fiend_hunt.saves import RECORD_FILE, load_save


class RecordingScreen(FightScreen, Protocol):
    def phase(self) -> Literal["planning", "battle", "end"] | None:
        """What the game shows now; None when it can't tell."""

    def save_screenshot(self, path: Path) -> None:
        """Save the planning screen with nobody selected, as a replay compares it."""


class SaveKey(Protocol):
    def pressed(self) -> bool:
        """True once for each press since the last call."""


@dataclass(frozen=True)
class RecordingOutcome:
    record: FightRecord
    finished: bool  # reached the end screen
    unsaved_turns: tuple[int, ...] = ()
    reason: str = ""


def record_fight(
    screen: RecordingScreen,
    key: SaveKey,
    folder: str | Path,
    *,
    title: str = "",
    poll: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = lambda message: None,
) -> RecordingOutcome:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    existing = load_save(folder)
    if existing is None and (folder / RECORD_FILE).is_file():
        # Recording would write a record with the new turns only.
        raise ScreenReadError(f"{folder.name} 的 {RECORD_FILE} 读不了，先不录，免得盖掉原来的回合")
    turns: dict[int, TurnState] = dict(existing.turns) if existing else {}
    screenshots: dict[int, str] = dict(existing.screenshots) if existing else {}
    # Chart edits of other turns are kept; a turn recorded again drops its own.
    edited: dict[int, frozenset[str]] = dict(existing.edited) if existing else {}
    title = existing.title if existing and existing.title else title
    unsaved: list[int] = []
    current: int | None = None  # TURN of the planning screen on show

    def outcome(finished: bool, reason: str = "") -> RecordingOutcome:
        record = FightRecord(
            turns=dict(turns), title=title, screenshots=dict(screenshots), edited=dict(edited)
        )
        return RecordingOutcome(record, finished, tuple(unsaved), reason)

    while True:
        phase = screen.phase()
        save_requested = key.pressed()  # drain presses made outside planning too
        if phase == "end":
            log(f"战斗结束，共存了 {len(turns)} 个回合")
            return outcome(True)
        if phase == "battle":
            if current is not None and current not in turns:
                unsaved.append(current)
                log(f"第 {current} 回合没按保存键就开打了，这回合没存")
            current = None
        elif phase == "planning":
            if current is None:
                current = screen.read_turn()
                if current is not None:
                    log(f"第 {current} 回合：排好后按保存键（不要按 BATTLE）")
            if save_requested:
                saved = _save_turn(screen, folder, turns, screenshots, edited, title, log)
                if saved is not None:
                    try:
                        screen.press_battle()
                    except ScreenReadError as error:
                        log(f"第 {saved} 回合已存，但工具没按 BATTLE（{error}）；请自己按 BATTLE")
                        sleep(poll)
                        continue
                    after = screen.wait_after_battle()
                    current = None
                    if after == "end":
                        log(f"战斗结束，共存了 {len(turns)} 个回合")
                        return outcome(True)
                    if after != "planning":
                        return outcome(False, f"第 {saved} 回合战斗后没回到排位画面")
                    continue
        sleep(poll)


def _merged_cards(saved: dict, seen: dict) -> dict[str, dict[str, str]]:
    """The costumes of each unit's cards: what this recording saw over what was saved."""
    cards = {unit: dict(labels) for unit, labels in saved.items()}
    for unit, labels in seen.items():
        mine = cards.setdefault(unit, {})
        for label, costume in labels.items():
            for other in [other for other, worn in mine.items() if worn == costume]:
                del mine[other]
            mine[label] = costume
    return {unit: labels for unit, labels in cards.items() if labels}


def _with_costumes(turns: dict[int, TurnState], cards: dict) -> dict[int, TurnState]:
    """Each turn with the costume of every skill whose card is now known
    (a card is often told on a later turn than the one it was used on)."""
    filled = {}
    for number, state in turns.items():
        worn = dict(state.costumes)
        for unit, label in state.skills.items():
            costume = cards.get(unit, {}).get(label)
            if unit not in worn and costume and label.startswith("技能"):
                worn[unit] = costume
        filled[number] = replace(state, costumes=worn) if worn != state.costumes else state
    return filled


def _save_turn(
    screen: RecordingScreen,
    folder: Path,
    turns: dict[int, TurnState],
    screenshots: dict[int, str],
    edited: dict[int, frozenset[str]],
    title: str,
    log: Callable[[str], None],
) -> int | None:
    turn = screen.read_turn()
    if turn is None:
        log("读不到回合数，这回合没存；请再按一次保存键")
        return None
    on_disk = load_save(folder)  # turns deleted on the 魔兽追踪者 page stay deleted
    if on_disk is None and (folder / RECORD_FILE).is_file():
        log(f"第 {turn} 回合没存上：{RECORD_FILE} 读不了，没去盖它；请再按一次保存键")
        return None
    if on_disk is not None:
        turns.clear()
        turns.update(on_disk.turns)
        screenshots.clear()
        screenshots.update(on_disk.screenshots)
        edited.clear()
        edited.update(on_disk.edited)
    again = turn in turns
    name = f"turn{turn:02d}.png"
    try:
        state = screen.read_state(turn)
        read_bursts = getattr(screen, "read_bursts", None)
        if callable(read_bursts):
            state = replace(state, bursts=read_bursts(state))
        cards = _merged_cards(on_disk.cards if on_disk else {}, getattr(screen, "unit_cards", {}))
        record = FightRecord(
            turns=_with_costumes({**turns, turn: state}, cards),
            title=title,
            screenshots={**screenshots, turn: name},
            edited={number: units for number, units in edited.items() if number != turn},
            cards=cards,
        )
    except (ScreenReadError, TurnStateError) as error:
        log(f"第 {turn} 回合没存上：{error}；请检查画面后再按一次保存键")
        return None
    screen.save_screenshot(folder / name)
    save_record(record, folder / RECORD_FILE)
    turns.update(record.turns)
    state = record.turns[turn]
    screenshots[turn] = name
    edited.pop(turn, None)
    cards = f"，读到 {len(state.skills)} 张卡" if state.skills else ""
    bursts = "、".join(f"{unit} {level}" for unit, level in state.bursts.items())
    bursts = f"，爆发 {bursts}" if bursts else ""
    log(
        f"第 {turn} 回合{'已覆盖' if again else '已存'}：{len(state.order)} 人在顺序里，"
        f"{len(state.dead)} 人阵亡{cards}{bursts}"
    )
    return turn
