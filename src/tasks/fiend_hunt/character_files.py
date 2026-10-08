"""Where the built-in character list is read from, and its update at start
(Leo 2026-10-07: new characters and costumes reach the PCs by themselves).

The list ships in data/ beside this file.  A daily job on GitHub adds new
costumes to it (tools/fetch_official_costumes.py, fetch_souseha_characters.py)
and pushes them to the branch.  On a PC that runs the tool from a git
checkout, ``refresh`` fetches that branch at start and, when only the
branch has a newer list, copies the list and its new portraits into
configs/characters/ without touching the checkout (no merge, no changed
files: a later ``git pull`` brings the same list into data/ and the copy is
dropped).  No git, no network, a checkout ahead of the branch: nothing
happens and the shipped list is used.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent / "data"
BUNDLED_FILE = DATA / "characters.json"
BUNDLED_PORTRAITS = DATA / "costumes"
ROOT = Path(__file__).resolve().parents[3]
UPDATE = ROOT / "configs" / "characters"
UPDATE_FILE = UPDATE / "characters.json"
UPDATE_PORTRAITS = UPDATE / "costumes"
UPDATE_BASE = UPDATE / "base.txt"  # the shipped list the copy was made against

REPO_PATH = "src/tasks/fiend_hunt/data"
GIT_TIMEOUT = 30  # s; a slow or absent network never holds the tool up


def blob_id(data: bytes) -> str:
    """The id git gives a file's content (to tell the shipped list changed)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def characters_file() -> Path:
    """The newer list copied from the branch, while the shipped one is still
    the one it was copied against; else the shipped list."""
    base = _read(UPDATE_BASE)
    shipped = _read(BUNDLED_FILE)
    if base is None or shipped is None or not UPDATE_FILE.is_file():
        return BUNDLED_FILE
    if base.decode("ascii", "ignore").strip() != blob_id(shipped):
        return BUNDLED_FILE  # data/ moved on (a pull): the copy is stale
    return UPDATE_FILE


def portrait_file(costume_id: str, folder: Path | None = None) -> Path:
    """A costume's portrait: shipped, else one copied with a newer list."""
    folder = BUNDLED_PORTRAITS if folder is None else Path(folder)
    path = folder / f"{costume_id}.webp"
    if folder == BUNDLED_PORTRAITS and not path.is_file():
        copied = UPDATE_PORTRAITS / f"{costume_id}.webp"
        if copied.is_file():
            return copied
    return path


def _git(args: list[str], run=subprocess.run) -> bytes | None:
    try:
        result = run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            # never a sign-in window or prompt: without saved access it just fails
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _tracked_branch(run) -> tuple[str, str] | None:
    """(remote, branch) this checkout follows: its upstream, else the remote
    it last pulled the current branch from (Leo's PCs pull by hand,
    ``git pull <remote> <branch>``, which leaves <remote>/<branch> behind
    but sets no upstream)."""
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], run)
    if upstream and b"/" in upstream:
        remote, branch = upstream.decode().strip().split("/", 1)
        return remote, branch
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], run)
    remotes = _git(["remote"], run)
    if not branch or not remotes or branch.strip() == b"HEAD":
        return None
    branch_name = branch.decode().strip()
    for remote in remotes.decode(errors="ignore").split():
        ref = f"refs/remotes/{remote}/{branch_name}"
        if _git(["rev-parse", "--verify", "--quiet", ref], run) is not None:
            return remote, branch_name
    return None


def refresh(run=subprocess.run) -> str:
    """Bring a newer list from the checkout's branch on GitHub; what happened."""
    if not (ROOT / ".git").exists() or (run is subprocess.run and shutil.which("git") is None):
        return "not a git checkout"
    tracked = _tracked_branch(run)
    if tracked is None:
        return "no branch on GitHub"
    remote, branch = tracked
    upstream_name = f"{remote}/{branch}"
    if _git(["fetch", "--quiet", remote, branch], run) is None:
        return "fetch failed"
    # only a branch ahead of this checkout: never undo what a pull brought
    if _git(["merge-base", "--is-ancestor", "HEAD", upstream_name], run) is None:
        return "checkout not behind the branch"
    shipped = _read(BUNDLED_FILE)
    newer = _git(["show", f"{upstream_name}:{REPO_PATH}/characters.json"], run)
    if shipped is None or newer is None:
        return "list missing"
    if newer == shipped:
        if UPDATE.exists():
            shutil.rmtree(UPDATE, ignore_errors=True)
        return "up to date"
    try:
        data = json.loads(newer.decode("utf-8"))
    except ValueError:
        return "branch list unreadable"
    if not isinstance(data, dict) or not data.get("characters"):
        return "branch list unreadable"
    listed = _git(["ls-tree", "--name-only", f"{upstream_name}:{REPO_PATH}/costumes"], run)
    on_branch = set(listed.decode().split()) if listed else set()
    UPDATE_PORTRAITS.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in sorted(on_branch):
        if (BUNDLED_PORTRAITS / name).is_file() or (UPDATE_PORTRAITS / name).is_file():
            continue
        picture = _git(["show", f"{upstream_name}:{REPO_PATH}/costumes/{name}"], run)
        if picture:
            _write(UPDATE_PORTRAITS / name, picture)
            copied += 1
    _write(UPDATE_FILE, newer)
    _write(UPDATE_BASE, blob_id(shipped).encode("ascii"))
    return f"newer list copied ({copied} portraits)"


def _write(path: Path, data: bytes) -> None:
    """Whole or not at all: a half-written list must never be read."""
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def forget_loaded() -> None:
    """Drop what was read from the old list, so the next look uses the new one."""
    import sys

    costumes = sys.modules.get("src.tasks.fiend_hunt.costumes")
    if costumes is not None:
        for cached in (costumes.book, costumes.portrait, costumes.picture_alpha):
            cached.cache_clear()
    team = sys.modules.get("src.ui.shell.fiend_team")
    if team is not None and hasattr(getattr(team, "_by_name", None), "cache_clear"):
        team._by_name.cache_clear()
    chart = sys.modules.get("src.ui.shell.fiend_chart")
    if chart is not None and hasattr(getattr(chart, "_costume_pixmap", None), "cache_clear"):
        chart._costume_pixmap.cache_clear()


def refresh_in_background(done=None) -> threading.Thread:
    """``refresh`` off the start-up path; ``done(result)`` when it is over."""

    def work():
        try:
            result = refresh()
            if result.startswith("newer list") or result == "up to date":
                forget_loaded()
        except Exception as error:  # never let the list stop the tool
            result = f"error: {error}"
        logger.info("角色名单更新：%s", result)
        if done is not None:
            done(result)

    thread = threading.Thread(target=work, name="character-list-update", daemon=True)
    thread.start()
    return thread
