"""The in-game (简中) names of characters and summons, by souseha id.

They come from the character list saved with the tool (data/characters.json,
made from souseha's BD2DB with tools/fetch_souseha_characters.py).  The chart
import that used this was removed (Leo 2026-10-06): saves are recorded in the
game with the record key.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

CHARACTERS_FILE = Path(__file__).resolve().parent / "data" / "characters.json"


@dataclass(frozen=True)
class GameNames:
    """In-game (简中) names by souseha character id and summon id."""

    characters: Mapping[str, str] = field(default_factory=dict)
    summons: Mapping[str, str] = field(default_factory=dict)


def load_game_names(path: str | Path | None = None) -> GameNames:
    """The saved character list; empty when it is missing or unreadable."""
    if path is None:
        from src.tasks.fiend_hunt.character_files import characters_file

        path = characters_file()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return GameNames()

    def names(entries: object) -> dict[str, str]:
        found: dict[str, str] = {}
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict):
                unit, name = entry.get("id"), entry.get("name_zh_cn")
                if isinstance(unit, str) and isinstance(name, str) and name:
                    found[unit] = name
        return found

    return GameNames(names(data.get("characters")), names(data.get("summons")))
