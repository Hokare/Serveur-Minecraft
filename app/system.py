"""Informations de version et mise à jour du panel lui-même.

Principe : le panel lance un conteneur « updater » (la même image, qui embarque le client
docker + compose) qui reconstruit le panel depuis GitHub puis recrée son conteneur.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from .dockerops import Manager, PanelError

REPO = os.environ.get("PANEL_REPO", "Hokare/Serveur-Minecraft")
TRACK = os.environ.get("PANEL_TRACK", "main")
APP_SHA = os.environ.get("APP_SHA", "")

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
_CACHE_TTL = 60

_lock = threading.Lock()
_cache: tuple[float, dict | None] = (0.0, None)


def latest_commit(force: bool = False) -> dict | None:
    """Dernier commit de la branche suivie (API publique GitHub), mis en cache 60 s."""
    global _cache
    with _lock:
        if not force and time.time() - _cache[0] < _CACHE_TTL:
            return _cache[1]
    result = None
    if _REPO_RE.match(REPO) and _REF_RE.match(TRACK):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/commits/{TRACK}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "mc-panel"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - URL https fixe
                data = json.load(resp)
            result = {
                "sha": data["sha"],
                "short": data["sha"][:7],
                "message": data["commit"]["message"].splitlines()[0][:120],
                "date": data["commit"]["committer"]["date"],
            }
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            result = None
    with _lock:
        _cache = (time.time(), result)
    return result


def info(manager: Manager) -> dict:
    latest = latest_commit()
    up_to_date = None
    if APP_SHA and latest:
        up_to_date = APP_SHA == latest["sha"]
    return {
        "repo": REPO,
        "branch": TRACK,
        "current": APP_SHA[:7] or None,
        "latest": latest,
        "up_to_date": up_to_date,
        "supported": manager.updater_supported(),
        "update": _updater_status(manager),
    }


def _updater_status(manager: Manager) -> dict:
    try:
        return manager.updater_status()
    except PanelError:
        return {"state": "idle"}


def start_update(manager: Manager) -> dict:
    latest = latest_commit(force=True)
    if latest is None:
        raise PanelError(502, "Impossible de joindre GitHub pour connaître la dernière version.")
    manager.launch_updater({
        "PANEL_REF": latest["sha"],      # fige la construction sur ce commit précis
        "APP_SHA": latest["sha"],
        "PANEL_REPO": REPO,
        "PANEL_TRACK": TRACK,
    })
    return {"ok": True, "target": latest["short"]}
