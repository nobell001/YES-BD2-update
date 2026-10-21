"""What the 亲密度谈心 task remembers per account (configs/affinity_talk.json).

Leo 2026-10-21: a costume at LV20 with 谈心记录 15/15 is finished for good;
its name is kept so it is never opened again (costumes keep growing:
「進度完成的就不要再一個一個點進去浪費時間」).  Costumes below LV20 talked
today are kept with the game day (08:00 UTC+8), so a second run the same
day does not open them again.  Costumes found locked at LV15 are kept too:
they are talked last.  A broken or missing file only means opening a few
costumes again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.compat.safe_json import read_text_retrying, write_text_atomic
from src.tasks.run_history import day_start_ts, game_day_key

RECORD_PATH = Path("configs") / "affinity_talk.json"


def game_day() -> str:
    return game_day_key(day_start_ts())


@dataclass
class TalkRecord:
    done: set[str] = field(default_factory=set)
    locked: set[str] = field(default_factory=set)
    day: str = ""
    talked: set[str] = field(default_factory=set)

    def talked_today(self, today: str) -> set[str]:
        return self.talked if self.day == today else set()

    def mark_talked(self, key: str, today: str) -> None:
        if self.day != today:
            self.day, self.talked = today, set()
        self.talked.add(key)


def record_path() -> Path:
    from src.utils import accounts, test_run

    path = Path(accounts.scoped(RECORD_PATH))
    return test_run.scratch() / path if test_run.active() else path


def load(path: Path | None = None) -> TalkRecord:
    path = record_path() if path is None else path
    try:
        data = json.loads(read_text_retrying(path))
    except (OSError, ValueError):
        return TalkRecord()
    if not isinstance(data, dict):
        return TalkRecord()

    def keys(name: str) -> set[str]:
        value = data.get(name)
        return {str(v) for v in value} if isinstance(value, list) else set()

    return TalkRecord(
        done=keys("done"),
        locked=keys("locked"),
        day=str(data.get("day", "") or ""),
        talked=keys("talked"),
    )


def save(record: TalkRecord, path: Path | None = None) -> bool:
    path = record_path() if path is None else path
    data = {
        "done": sorted(record.done),
        "locked": sorted(record.locked),
        "day": record.day,
        "talked": sorted(record.talked),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=1))
    except OSError:
        return False
    return True
