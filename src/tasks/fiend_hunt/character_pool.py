"""The built-in character list's upkeep (Leo 2026-10-07): new costumes from
the official maintenance notices first, souseha's full entry later.

Pure logic, used by tools/fetch_souseha_characters.py, by
official_notices.py (the tool on each PC, and tools/fetch_official_costumes.py)
and by character_files.py; nothing here goes online.

- The zh-tw maintenance notice names every pickup costume in one fixed
  sentence, ``N) <服裝><角色>的服裝和<角色>的專用裝備…將出現在本次Pickup中``
  (17 notices 2026-02..10 checked, 49/49).  A costume the list lacks, of a
  character it knows, is added as *temporary*: names only, no portrait,
  skill or SP.  Reruns (【復刻】) and characters the list lacks are left out.
- The other four languages' notices are separate posts in their own
  wording; their names are taken where the same costume can be found, else
  left empty (the page then shows the zh-tw name).
- When souseha lists a new costume for that character, its entry replaces
  the temporary one and the old id is kept as an alias, so saves made in
  between still find it (2 of 49 official names differ from souseha's,
  e.g. 客棧暖陽 / 客棧的陽光, so names alone can't be trusted).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, timedelta
from difflib import SequenceMatcher

LANGS = ("zh_tw", "zh_cn", "en", "ja", "ko")
# the official site's locales for the five languages
LOCALES = {"zh_tw": "zh-tw", "zh_cn": "zh-cn", "en": "en-us", "ja": "ja-jp", "ko": "ko-kr"}

MAINTENANCE = re.compile(r"定期維護|維護更新|維護和更新")
NOT_MAINTENANCE = re.compile(r"補償|延長|完成|無維護|結束")
PICKUP = re.compile(
    r"\d\)\s*([^0-9)]{2,40}?)的服裝(?:和[^的]{1,12}的專用裝備)?[^。]{0,30}?"
    r"(?:將出現在本次|Pickup|PICK UP)"
)
TAG = re.compile(r"[【\[][^】\]]*[】\]]")
RERUN = re.compile(r"復刻|复刻")
NOTICE_DAYS = 21  # a maintenance notice older than this is not looked at
SOUSEHA_AHEAD_DAYS = 7  # souseha added a costume this close to the notice: it has it


def plain(text: str) -> str:
    return re.sub(r"[\s・·•\-.'’\"“”「」『』【】\[\]()（）:：,，※]", "", text).lower()


def is_maintenance(subject: str) -> bool:
    return bool(MAINTENANCE.search(subject)) and not NOT_MAINTENANCE.search(subject)


def pickups(content: str) -> list[tuple[str, bool]]:
    """The pickup costumes a zh-tw notice names: (服裝+角色 name, is a rerun)."""
    found = []
    for match in PICKUP.finditer(content or ""):
        full = match.group(1).strip()
        name = TAG.sub("", full).strip()
        if name and (name, bool(RERUN.search(full))) not in found:
            found.append((name, bool(RERUN.search(full))))
    return found


def split_name(full: str, characters: list[dict]) -> tuple[dict, str] | None:
    """(character entry, costume name) for '殘破木乃伊涅肯達莉亞': the longest
    character name it ends with.  None when no character fits."""
    fits = [
        entry
        for entry in characters
        if entry.get("name_zh_tw")
        and full.endswith(entry["name_zh_tw"])
        and len(full) > len(entry["name_zh_tw"])
    ]
    if not fits:
        return None
    entry = max(fits, key=lambda item: len(item["name_zh_tw"]))
    return entry, full[: -len(entry["name_zh_tw"])].strip()


SAME_NAME = 0.75  # 潛藏之夢 / 潛藏的夢: one costume written two ways


def known_costume(entry: dict, name: str) -> bool:
    for costume in entry.get("costumes") or []:
        listed = costume.get("name_zh_tw", "")
        if plain(listed) == plain(name):
            return True
        if SequenceMatcher(None, plain(listed), plain(name)).ratio() >= SAME_NAME:
            return True
    return False


def souseha_has_new(entry: dict, announced: date) -> bool:
    """Souseha already added a costume to this character around the notice
    (its name may differ from the official one): nothing to add."""
    since = announced - timedelta(days=SOUSEHA_AHEAD_DAYS)
    for costume in entry.get("costumes") or []:
        if costume.get("temporary"):
            continue
        added = costume.get("added")
        if added and date.fromisoformat(added) >= since:
            return True
    return False


def temporary_id(character_id: str, name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"official_{character_id}_{digest}"


# Where each language's notice names the pickups, and how a costume is
# written there before the character's name.
SECTIONS = {
    "zh_cn": r"Pick ?Up及",
    "en": r"Pickup and New Character",
    "ja": r"ピックアップ及び",
    "ko": r"픽업 및 신규",
}


def _pattern(lang: str, character: str) -> str:
    name = re.escape(character)
    if lang == "en":
        return (
            r"(?:\d\)|^|\.|- )\s*(?:\[[^\]]*\]\s*)*([A-Z][^.:()\[\]]{1,60}?)\s+"
            + name
            + r"(?:'s)?\s+Costume"
        )
    if lang == "ja":
        return (
            r"[「『]\s*(?:[【\[][^】\]]*[】\]]\s*)*([^」』「『]{1,40}?)[\s・　]*"
            + name
            + r"\s*[」』]"
        )
    if lang == "ko":
        return (
            r"(?:\d\)|-|^|\.|\])\s*(?:\[[^\]]*\]\s*)*([^()\[\]:.]{1,40}?)\s+" + name + r"\s*코스튬"
        )
    # zh_cn
    return (
        r"(?:\d[)）]|-|「|“|\"|'|^)\s*(?:[【\[][^】\]]*[】\]]\s*)*"
        r"([^\s「」“”\"'()（）:：\-、，。]{1,20}?)\s*" + name + r"\s*」?\s*(?:的)?服装"
    )


def costume_name(text: str, lang: str, character: str, listed: list[str]) -> str:
    """The new costume's name in another language's notice, or ''.

    ``character`` is the character's name in that language, ``listed`` the
    names of its costumes the list already has there (an old costume named
    in the same notice, e.g. a rerun, is not the new one)."""
    if not text or not character:
        return ""
    section = re.search(SECTIONS[lang], text)
    part = text[section.start() :] if section else text
    seen = {plain(name) for name in listed if name}
    counts: Counter[str] = Counter()
    for match in re.finditer(_pattern(lang, character), part, re.M):
        # past a heading caught in front ("…Information- Eternal Chains")
        name = re.split(r"-\s+", match.group(1))[-1].strip(" 　・-※")
        name = re.sub(r"^(?:NEW|※)\s*", "", name).strip()
        if name and plain(name) not in seen:
            counts[name] += 1
    if not counts:
        return ""
    best = max(counts.values())
    return next(name for name in counts if counts[name] == best)


def temporary_costume(
    entry: dict,
    name_tw: str,
    notice_id: str,
    announced: date,
    texts: dict[str, str],
    simplify=lambda text: text,
) -> dict:
    """The list entry for a costume only the official notice has so far.

    ``texts`` holds the other languages' notices of the same maintenance."""
    names = {"zh_tw": name_tw}
    for lang in ("zh_cn", "en", "ja", "ko"):
        listed = [costume.get(f"name_{lang}", "") for costume in entry.get("costumes") or []]
        names[lang] = costume_name(texts.get(lang, ""), lang, entry.get(f"name_{lang}", ""), listed)
    if not names["zh_cn"]:
        names["zh_cn"] = simplify(name_tw)
    costume = {"id": temporary_id(entry["id"], name_tw), "temporary": True}
    for lang in LANGS:
        costume[f"name_{lang}"] = names[lang]
    for lang in LANGS:
        costume[f"skill_{lang}"] = ""
    costume.update(
        {"sp": [], "burst_sp": [], "notice": notice_id, "announced": announced.isoformat()}
    )
    return costume


def add_from_notice(
    data: dict,
    notice_id: str,
    announced: date,
    content_tw: str,
    texts: dict[str, str],
    simplify=lambda text: text,
) -> list[str]:
    """Add the costumes a zh-tw maintenance notice announces and the list
    lacks; returns what was added ('角色 服裝') and, prefixed '?', what was
    named but left out (a character the list lacks)."""
    report = []
    characters = data.get("characters") or []
    for full, rerun in pickups(content_tw):
        if rerun:
            continue
        split = split_name(full, characters)
        if split is None:
            report.append(f"?{full}")
            continue
        entry, name = split
        if not name or known_costume(entry, name) or souseha_has_new(entry, announced):
            continue
        entry.setdefault("costumes", []).append(
            temporary_costume(entry, name, notice_id, announced, texts, simplify)
        )
        report.append(f"{entry['name_zh_tw']} {name}")
    return report


def merge_souseha(old: dict, new: dict, today: date) -> list[str]:
    """Carry what the old list knew into a fresh souseha snapshot ``new``:
    each costume's first-seen date, the temporary costumes souseha doesn't
    have yet, and aliases.  A temporary costume whose character gained a
    souseha costume is replaced by it.  Returns what was replaced."""
    report = []
    aliases = dict(old.get("aliases") or {})
    old_by_id = {entry.get("id"): entry for entry in old.get("characters") or []}
    for entry in new.get("characters") or []:
        before = old_by_id.get(entry.get("id"), {})
        before_costumes = before.get("costumes") or []
        dates = {c.get("id"): c.get("added") for c in before_costumes if not c.get("temporary")}
        fresh = []
        for costume in entry.get("costumes") or []:
            if costume["id"] in dates:
                if dates[costume["id"]]:
                    costume["added"] = dates[costume["id"]]
            else:
                costume["added"] = today.isoformat()
                if before:  # a new costume of a character the list had
                    fresh.append(costume)
        temporary = [c for c in before_costumes if c.get("temporary")]
        for waiting in temporary:
            match = _replacement(waiting, fresh)
            if match is not None:
                fresh.remove(match)
                aliases[waiting["id"]] = match["id"]
                names = (entry, waiting, match)
                report.append("{} {} → {}".format(*(item.get("name_zh_tw") for item in names)))
            else:
                entry.setdefault("costumes", []).append(waiting)
    if aliases:
        new["aliases"] = aliases
    return report


def _replacement(waiting: dict, fresh: list[dict]) -> dict | None:
    """The souseha costume that is the temporary one: the only new one, or
    the new one whose name is closest."""
    if not fresh:
        return None
    if len(fresh) == 1:
        return fresh[0]

    def score(costume: dict) -> float:
        ratios = [
            SequenceMatcher(None, plain(mine), plain(theirs)).ratio()
            for mine, theirs in (
                (waiting.get(f"name_{lang}", ""), costume.get(f"name_{lang}", "")) for lang in LANGS
            )
            if mine and theirs
        ]
        return max(ratios, default=0.0)

    return max(fresh, key=score)
