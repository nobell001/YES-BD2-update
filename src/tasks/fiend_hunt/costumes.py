"""The built-in character list: every costume's name, skill and portrait
(Leo 2026-10-06: skills are picked by the costume's picture, as in the game).

The data comes from souseha's BD2DB (tools/fetch_souseha_characters.py):
characters.json beside this file and one 128 px portrait per costume in
data/costumes.  Each skill card in the game's card column shows its
costume's art, the same picture as souseha's, so a card can be told by
matching its face against the unit's costumes (seen on the 4K PC,
艾尼尔's three skill cards: 0.85-0.89 for the right costume, 0.60 at most
for the others).  A unit the list doesn't know (a summon, a character
newer than the snapshot) simply has no costumes here; callers then go by
the card's row as before.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from src.tasks.fiend_hunt import character_files, layout
from src.utils.chinese import to_simplified
from src.utils.image_utils import template_match_response

DATA = Path(__file__).resolve().parent / "data"
CHARACTERS_FILE = DATA / "characters.json"
PORTRAITS = DATA / "costumes"

# The face part of a skill card, between the skill icon and the range grid
# (fractions of layout.card_box).
CARD_ART_X = (0.25, 0.68)
CARD_ART_TOP, CARD_ART_BOTTOM = 4.0, -12.0  # reference px inside the card box
# Card art (1920x1080 reference) to portrait (128 px) size: about 0.85 on
# the 4K PC; a few steps around it allow for other window sizes.
ART_SCALES = (0.75, 0.8, 0.85, 0.9, 0.95)
MATCH_MIN = 0.72  # the right costume scored 0.85+
MATCH_MARGIN = 0.15  # ahead of the unit's next best costume


@dataclass(frozen=True)
class Costume:
    id: str
    character: str  # in-game (简中) character name
    name: str  # 简中 costume name
    skill: str = ""  # 简中 skill name
    sp: tuple[int, ...] = ()  # SP by skill level
    burst_sp: tuple[int, ...] = ()  # 爆发 SP by level
    names: dict[str, str] = field(default_factory=dict, compare=False)  # lang -> name
    # Only announced on the official site so far (tools/fetch_official_costumes.py,
    # Leo 2026-10-07): names, no portrait or skill until souseha lists it.
    temporary: bool = False


@dataclass(frozen=True)
class Character:
    name: str  # in-game (简中) name
    star: int = 0  # 3 / 4 / 5
    element: str = ""  # fire / water / wind / light / dark
    costume: str = ""  # the original costume's id, for its portrait
    names: dict[str, str] = field(default_factory=dict, compare=False)  # lang -> name


@dataclass(frozen=True)
class CharacterBook:
    """Costumes by in-game character name, in souseha's order."""

    by_character: dict[str, tuple[Costume, ...]] = field(default_factory=dict)
    characters: tuple[Character, ...] = ()
    summons: dict[str, str] = field(default_factory=dict)  # in-game name -> picture id
    # a temporary costume's id -> the souseha id that replaced it, so saves
    # made in between still find their costume
    aliases: dict[str, str] = field(default_factory=dict)

    def canonical(self, costume_id: str) -> str:
        return self.aliases.get(costume_id, costume_id)

    def picture_id(self, name: str, costume: str | None = None) -> str | None:
        """The picture to show for a unit: the costume it wears when known
        (and pictured), else the character's original costume, or the
        summon's own."""
        worn = self.costume(costume) if costume else None
        if worn is not None and not worn.temporary:  # a temporary one has no picture yet
            return worn.id
        character = next((c for c in self.characters if c.name == name), None)
        if character is not None and character.costume:
            return character.costume
        return self.summons.get(name)

    def costumes(self, character: str) -> tuple[Costume, ...]:
        return self.by_character.get(character, ())

    def costume(self, costume_id: str) -> Costume | None:
        costume_id = self.canonical(costume_id)
        for costumes in self.by_character.values():
            for costume in costumes:
                if costume.id == costume_id:
                    return costume
        return None


def load_book(path: str | Path | None = None) -> CharacterBook:
    """The saved character list; empty when it is missing or unreadable.

    By default the newer copy an update brought, if any (character_files.py)."""
    if path is None:
        path = character_files.characters_file()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return CharacterBook()
    book: dict[str, tuple[Costume, ...]] = {}
    characters: list[Character] = []
    for entry in data.get("characters") or []:
        if not isinstance(entry, dict) or not entry.get("name_zh_cn"):
            continue
        character = entry["name_zh_cn"]
        listed = [c.get("id") for c in entry.get("costumes") or [] if isinstance(c, dict)]
        characters.append(
            Character(
                character,
                int(entry.get("star") or 0),
                str(entry.get("element") or ""),
                str(entry.get("costume") or (listed[0] if listed else "") or ""),
                {
                    lang: entry.get(f"name_{lang}", "")
                    for lang in ("zh_cn", "zh_tw", "en", "ja", "ko")
                },
            )
        )
        costumes = []
        for costume in entry.get("costumes") or []:
            if not isinstance(costume, dict) or not costume.get("id"):
                continue
            costumes.append(
                Costume(
                    costume["id"],
                    character,
                    costume.get("name_zh_cn") or costume.get("name_zh_tw") or costume["id"],
                    costume.get("skill_zh_cn") or costume.get("skill_zh_tw", ""),
                    tuple(int(value) for value in costume.get("sp") or []),
                    tuple(int(value) for value in costume.get("burst_sp") or []),
                    {
                        lang: costume.get(f"name_{lang}", "")
                        for lang in ("zh_cn", "zh_tw", "en", "ja", "ko")
                    },
                    bool(costume.get("temporary")),
                )
            )
        book[character] = tuple(costumes)
    summons = {
        entry["name_zh_cn"]: entry["id"]
        for entry in data.get("summons") or []
        if isinstance(entry, dict) and entry.get("name_zh_cn") and entry.get("id")
    }
    aliases = data.get("aliases")
    aliases = (
        {str(old): str(new) for old, new in aliases.items() if old and new}
        if isinstance(aliases, dict)
        else {}
    )
    return CharacterBook(book, tuple(characters), summons, aliases)


@lru_cache(maxsize=1)
def book() -> CharacterBook:
    return load_book()


# The size the card-art scales (ART_SCALES) were measured against; the
# files are souseha's 256 px, kept sharp for the page (Leo 2026-10-06).
MATCH_SIZE = 128


@lru_cache(maxsize=256)
def portrait(costume_id: str, folder: str = str(PORTRAITS)) -> np.ndarray | None:
    """A costume's portrait for matching card art (BGR, 128 px), or None."""
    image = picture(costume_id, folder)
    if image is None or image.shape[1] == MATCH_SIZE:
        return image
    return cv2.resize(image, (MATCH_SIZE, MATCH_SIZE), interpolation=cv2.INTER_AREA)


# Memory (2026-10-06): only the 128 px matching copy is kept for every
# costume (about 9 MB); the 256 px files are decoded when asked for, with a
# few kept for the page, instead of three full-size copies of each (~130 MB).
def picture(costume_id: str, folder: str = str(PORTRAITS)) -> np.ndarray | None:
    """A costume's portrait as saved (BGR, transparency on mid grey), or None."""
    image = picture_alpha(costume_id, folder)
    if image is not None and image.ndim == 3 and image.shape[2] == 4:
        alpha = image[..., 3:4].astype(np.float32) / 255.0
        image = (image[..., :3] * alpha + 128 * (1 - alpha)).astype(np.uint8)
    return image


@lru_cache(maxsize=32)  # one save's units; the page keeps its own pixmaps
def picture_alpha(costume_id: str, folder: str = str(PORTRAITS)) -> np.ndarray | None:
    """A costume's portrait as saved, transparency kept (BGRA), for the page."""
    try:
        data = np.fromfile(character_files.portrait_file(costume_id, Path(folder)), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None


def card_art(frame: np.ndarray, row: int) -> np.ndarray:
    """The face part of card ``row`` of the open card column, at reference size."""
    left, top, right, bottom = layout.card_box(row)
    width = right - left
    part = layout.crop(
        frame,
        (
            left + width * CARD_ART_X[0],
            top + CARD_ART_TOP,
            left + width * CARD_ART_X[1],
            bottom + CARD_ART_BOTTOM,
        ),
    )
    scale = layout.REF_W / frame.shape[1]
    size = (max(1, round(part.shape[1] * scale)), max(1, round(part.shape[0] * scale)))
    return cv2.resize(part, size, interpolation=cv2.INTER_AREA)


def art_score(art: np.ndarray, picture: np.ndarray) -> float:
    """How well a card's art matches a costume portrait (TM_CCOEFF_NORMED, best scale)."""
    best = -1.0
    for scale in ART_SCALES:
        size = (max(4, round(art.shape[1] * scale)), max(4, round(art.shape[0] * scale)))
        if size[0] >= picture.shape[1] or size[1] >= picture.shape[0]:
            continue
        template = cv2.resize(art, size, interpolation=cv2.INTER_AREA)
        best = max(best, float(template_match_response(picture, template).max()))
    return best


def which_costume(art: np.ndarray, costumes: tuple[Costume, ...], load=portrait) -> Costume | None:
    """The costume a card's art shows, among the unit's; None unless clearly one."""
    scores = []
    for costume in costumes:
        picture = load(costume.id)
        if picture is not None:
            scores.append((art_score(art, picture), costume))
    if not scores:
        return None
    scores.sort(key=lambda pair: pair[0], reverse=True)
    best, costume = scores[0]
    runner_up = scores[1][0] if len(scores) > 1 else -1.0
    if best < MATCH_MIN or best - runner_up < MATCH_MARGIN:
        return None
    return costume


def art_score_grey(art: np.ndarray, picture: np.ndarray) -> float:
    """art_score on equalised grey: holds for a greyed card (cooldown, 先发制人),
    whose colours are washed out (4K/2K fixtures: 0.62-0.79 for the right
    costume, 0.56 at most for the others left)."""
    grey_art = cv2.equalizeHist(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY))
    grey_picture = cv2.equalizeHist(cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY))
    best = -1.0
    for scale in ART_SCALES:
        size = (
            max(4, round(grey_art.shape[1] * scale)),
            max(4, round(grey_art.shape[0] * scale)),
        )
        if size[0] >= grey_picture.shape[1] or size[1] >= grey_picture.shape[0]:
            continue
        template = cv2.resize(grey_art, size, interpolation=cv2.INTER_AREA)
        best = max(best, float(template_match_response(grey_picture, template).max()))
    return best


GREY_MIN = 0.6
GREY_MARGIN = 0.12


def _grey_costume(art: np.ndarray, left: list[Costume], load) -> Costume | None:
    scores = []
    for costume in left:
        picture = load(costume.id)
        if picture is not None:
            scores.append((art_score_grey(art, picture), costume))
    if not scores:
        return None
    scores.sort(key=lambda pair: pair[0], reverse=True)
    best, costume = scores[0]
    runner_up = scores[1][0] if len(scores) > 1 else -1.0
    if best < GREY_MIN or best - runner_up < GREY_MARGIN:
        return None
    return costume


def column_costumes(
    frame: np.ndarray,
    count: int,
    lit: int | None,
    costumes: tuple[Costume, ...],
    load=portrait,
) -> dict[int, Costume]:
    """Skill-card row -> costume, for the cards of an open column that can be told.

    First by colour.  A greyed card (cooldown, 先发制人) is dimmed and fails
    that; it is then matched on equalised grey against the costumes not yet
    found.  The lit card shows another expression of its art: it is left
    out (the header's skill name tells it, see costume_by_skill).  When the
    unit has as many skill cards as costumes and one unlit card is still
    unknown, it is the one costume left.
    """
    found: dict[int, Costume] = {}
    rows = [row for row in range(layout.FIRST_SKILL_ROW, count) if row != lit]
    arts = {row: card_art(frame, row) for row in rows}
    for row in rows:
        costume = which_costume(arts[row], costumes, load)
        if costume is not None and costume not in found.values():
            found[row] = costume
    for row in rows:
        if row in found:
            continue
        left = [costume for costume in costumes if costume not in found.values()]
        costume = _grey_costume(arts[row], left, load)
        if costume is not None:
            found[row] = costume
    unknown = [row for row in rows if row not in found]
    left = [costume for costume in costumes if costume not in found.values()]
    lit_is_skill = lit is not None and lit >= layout.FIRST_SKILL_ROW
    skill_cards = max(count - layout.FIRST_SKILL_ROW, 0)
    if skill_cards == len(costumes) and len(unknown) == 1 and len(left) == 1 and not lit_is_skill:
        found[unknown[0]] = left[0]
    return found


def last_costume(
    count: int, found: dict[int, Costume], costumes: tuple[Costume, ...]
) -> Costume | None:
    """The one costume no other card is, when the unit has a card for each costume."""
    skill_cards = max(count - layout.FIRST_SKILL_ROW, 0)
    left = [costume for costume in costumes if costume not in found.values()]
    if skill_cards == len(costumes) and len(found) == skill_cards - 1 and len(left) == 1:
        return left[0]
    return None


_NOT_A_LETTER = re.compile(r"[\W_]+")
SKILL_NAME_MIN = 0.8  # similarity of the name read to the list's (OCR slips a glyph)


def _plain(text: str) -> str:
    return _NOT_A_LETTER.sub("", to_simplified(text)).lower()


def costume_by_skill(text: str, costumes: tuple[Costume, ...]) -> Costume | None:
    """The costume whose skill name the header shows, among the unit's.

    The header can put a level word in front ("特级三重箭矢" for 三重箭矢,
    Leo's 4K screenshot 2026-10-06) and a "+5" after it, so a name that
    contains the costume's skill counts; otherwise the closest name if it
    is close enough and clearly ahead of the next.
    """
    read = _plain(text)
    if not read:
        return None
    named = [costume for costume in costumes if _plain(costume.skill)]
    inside = [costume for costume in named if _plain(costume.skill) in read]
    if inside:
        # the longest name contained wins (one skill's name can hold another's)
        inside.sort(key=lambda costume: len(_plain(costume.skill)), reverse=True)
        if len(inside) == 1 or len(_plain(inside[0].skill)) > len(_plain(inside[1].skill)):
            return inside[0]
        return None
    scored = sorted(
        (
            (SequenceMatcher(None, read, _plain(costume.skill)).ratio(), costume)
            for costume in named
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored or scored[0][0] < SKILL_NAME_MIN:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.1:
        return None
    return scored[0][1]
