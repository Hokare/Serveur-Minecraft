"""Authentification HTTP Basic avec mot de passe modifiable depuis l'interface.

Le mot de passe est stocké haché (scrypt + sel) dans `<PANEL_DATA_DIR>/auth.json`.
Au premier démarrage : PANEL_PASSWORD (s'il est défini) sert de mot de passe initial,
sinon les identifiants par défaut sont admin / admin (l'interface avertit tant qu'ils n'ont pas été changés).
Ensuite le fichier fait foi et PANEL_PASSWORD est ignoré.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
from pathlib import Path

log = logging.getLogger("mc-panel.auth")

DEFAULT_PASSWORD = "admin"
MIN_PASSWORD = 8
USER_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


class AuthStore:
    def __init__(self, data_dir: Path, default_user: str = "admin", initial_password: str = ""):
        self.path = Path(data_dir) / "auth.json"
        self.user = default_user
        self._salt = b""
        self._hash = b""
        self._lock = threading.Lock()
        self._ok: set[str] = set()      # en-têtes déjà validés (évite un scrypt par requête)
        if not self._load():
            self._bootstrap(initial_password)
        # Vrai tant que le mot de passe est encore « admin » : l'interface affiche alors un avertissement.
        self.default_password = self.verify(self.user, DEFAULT_PASSWORD)

    # -- persistance
    def _load(self) -> bool:
        try:
            data = json.loads(self.path.read_text())
            self.user = data["user"]
            self._salt = bytes.fromhex(data["salt"])
            self._hash = bytes.fromhex(data["hash"])
            return True
        except (OSError, ValueError, KeyError):
            return False

    def _save(self) -> None:
        payload = json.dumps({"user": self.user, "salt": self._salt.hex(), "hash": self._hash.hex()})
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(payload)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Impossible d'enregistrer le mot de passe (%s) : il sera perdu au redémarrage.", exc)

    def _set(self, password: str) -> None:
        self._salt = secrets.token_bytes(16)
        self._hash = _scrypt(password, self._salt)

    def _bootstrap(self, initial_password: str) -> None:
        password = initial_password
        if not password:
            password = DEFAULT_PASSWORD
            log.warning("=" * 60)
            log.warning("Identifiants par défaut : %s / %s — change-les depuis le menu profil de l'interface.",
                        self.user, DEFAULT_PASSWORD)
            log.warning("=" * 60)
        self._set(password)
        self._save()

    # -- vérification
    def verify(self, user: str, password: str) -> bool:
        with self._lock:
            same_user = hmac.compare_digest(user.encode(), self.user.encode())
            same_pwd = hmac.compare_digest(_scrypt(password, self._salt), self._hash)
        return same_user and same_pwd

    def check(self, header: str) -> bool:
        """Valide un en-tête `Authorization: Basic ...`."""
        if not header.lower().startswith("basic "):
            return False
        key = hashlib.sha256(header.encode()).hexdigest()
        if key in self._ok:
            return True
        try:
            user, _, password = base64.b64decode(header[6:]).decode().partition(":")
        except ValueError:
            return False
        if not self.verify(user, password):
            return False
        if len(self._ok) > 256:
            self._ok.clear()
        self._ok.add(key)
        return True

    def update_credentials(self, current_password: str, new_user: str | None = None, new_password: str | None = None) -> None:
        """Change le nom d'utilisateur et/ou le mot de passe (le mot de passe actuel est exigé)."""
        if not self.verify(self.user, current_password):
            raise ValueError("Mot de passe actuel incorrect.")
        new_user = (new_user or "").strip() or None
        if new_user is not None and not USER_RE.match(new_user):
            raise ValueError("Nom d'utilisateur invalide (3 à 32 caractères : lettres, chiffres, . _ -).")
        if new_password:
            if len(new_password) < MIN_PASSWORD:
                raise ValueError(f"Le nouveau mot de passe doit contenir au moins {MIN_PASSWORD} caractères.")
            if len(new_password) > 128:
                raise ValueError("Mot de passe trop long (128 caractères max).")
        if new_user is None and not new_password:
            raise ValueError("Rien à modifier.")
        with self._lock:
            if new_user:
                self.user = new_user
            if new_password:
                self._set(new_password)
                self.default_password = new_password == DEFAULT_PASSWORD
            self._ok.clear()
        self._save()
