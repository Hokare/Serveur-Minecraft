"""Sauvegardes des mondes : archives .tar.gz stockées dans le volume de données du panel.

L'archive est produite par un conteneur jetable qui voit à la fois le /data du serveur
(volumes_from) et le volume du panel (monté sur /backups) : rien ne transite par l'API Docker.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

from docker.errors import APIError, ContainerError
from docker.types import Mount

from .dockerops import STOP_TIMEOUT, Manager, PanelError

BACKUP_DIR = Path(os.environ.get("PANEL_DATA_DIR", "./data")) / "backups"
REASONS = ("manuelle", "avant-modif", "avant-restauration")
FILE_RE = re.compile(r"^([a-z0-9][a-z0-9_-]{0,30})-(\d{8})-(\d{6})-(manuelle|avant-modif|avant-restauration)\.tar\.gz$")
# Fichiers inutiles ou régénérés automatiquement : on ne les sauvegarde pas.
EXCLUDES = ("./logs", "./cache", "./crash-reports")

_NO_PANEL_CONTAINER = ("Les sauvegardes nécessitent que le panel tourne via le docker-compose.yml fourni "
                       "(volume de données monté sur /data).")


class Backups:
    def __init__(self, manager: Manager, root: Path = BACKUP_DIR):
        self.m = manager
        self.root = Path(root)
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ montage
    def _backup_mount(self) -> Mount:
        me = self.m._self_container()
        if me is None:
            raise PanelError(501, _NO_PANEL_CONTAINER)
        for mount in me.attrs.get("Mounts", []):
            if mount.get("Destination") == "/data":
                if mount.get("Type") == "volume":
                    return Mount(target="/backups", source=mount["Name"], type="volume")
                return Mount(target="/backups", source=mount["Source"], type="bind")
        raise PanelError(501, _NO_PANEL_CONTAINER)

    def supported(self) -> bool:
        try:
            self._backup_mount()
            return True
        except PanelError:
            return False

    def _run(self, container, script: str, *args: str) -> None:
        try:
            self.m.client.containers.run(
                image=container.attrs["Image"], entrypoint=["sh", "-c", script, "sh", *args],
                volumes_from=[container.id], mounts=[self._backup_mount()],
                network_mode="none", user="0", remove=True)
        except ContainerError as exc:
            detail = exc.stderr.decode(errors="replace").strip() if exc.stderr else str(exc)
            raise PanelError(500, f"Échec de l'opération : {detail[-300:]}") from exc
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc

    # ------------------------------------------------------------------ fichiers
    def _dir(self, name: str) -> Path:
        return self.root / name

    def path(self, name: str, filename: str) -> Path:
        m = FILE_RE.match(filename)
        if not m or m.group(1) != name:
            raise PanelError(400, "Nom de sauvegarde invalide.")
        path = self._dir(name) / filename
        if not path.is_file():
            raise PanelError(404, "Sauvegarde introuvable.")
        return path

    def list(self, name: str) -> list[dict]:
        out = []
        folder = self._dir(name)
        if folder.is_dir():
            for entry in folder.iterdir():
                m = FILE_RE.match(entry.name)
                if m and m.group(1) == name and entry.is_file():
                    stat = entry.stat()
                    out.append({"file": entry.name, "size": stat.st_size, "created": stat.st_mtime, "reason": m.group(4)})
        return sorted(out, key=lambda b: b["created"], reverse=True)

    def delete(self, name: str, filename: str) -> None:
        self.path(name, filename).unlink()

    def status(self, name: str) -> dict:
        self.m._get(name)      # 404 si le serveur n'existe pas
        backups = self.list(name)
        return {"supported": self.supported(), "backups": backups,
                "total_size": sum(b["size"] for b in backups), "job": self.jobs.get(name)}

    # ------------------------------------------------------------------ création
    def _create_sync(self, name: str, reason: str) -> str:
        container = self.m._get(name)
        filename = f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-{reason}.tar.gz"
        running = container.status == "running"
        frozen = False
        if running:     # fige l'écriture du monde pour obtenir une archive cohérente
            try:
                self.m.command(name, "save-off")
                frozen = True
                self.m.command(name, "save-all flush")
            except PanelError:
                pass    # RCON indisponible : on sauvegarde quand même (le serveur peut encore écrire)
        excludes = " ".join(f"--exclude={e}" for e in EXCLUDES)
        script = (f'd="/backups/backups/$1" && mkdir -p "$d" && '
                  f'tar czf "$d/$2.part" -C /data {excludes} . ; rc=$?; '
                  f'if [ $rc -le 1 ]; then mv "$d/$2.part" "$d/$2"; else rm -f "$d/$2.part"; exit $rc; fi')
        try:
            self._run(container, script, name, filename)
        finally:
            if frozen:
                try:
                    self.m.command(name, "save-on")
                except PanelError:
                    pass
        return filename

    def _restore_sync(self, name: str, filename: str) -> None:
        self.path(name, filename)   # valide le nom et l'existence
        container = self.m._get(name)
        was_running = container.status in ("running", "restarting")
        self._create_sync(name, "avant-restauration")        # filet de sécurité
        if was_running:
            container.stop(timeout=STOP_TIMEOUT)
        # L'archive est testée AVANT d'effacer quoi que ce soit.
        script = ('f="/backups/backups/$1/$2" && tar tzf "$f" > /dev/null && '
                  'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf "$f" -C /data')
        self._run(container, script, name, filename)
        if was_running:
            container.start()

    # ------------------------------------------------------------------ tâches en arrière-plan
    def _spawn(self, name: str, label: str, fn) -> dict:
        with self._lock:
            if self.jobs.get(name, {}).get("state") == "running":
                raise PanelError(409, "Une opération de sauvegarde est déjà en cours pour ce serveur.")
            self.jobs[name] = {"state": "running", "label": label, "started": time.time()}

        def work() -> None:
            try:
                fn()
                result = {"state": "done"}
            except PanelError as exc:
                result = {"state": "failed", "error": exc.message}
            except Exception as exc:  # noqa: BLE001 - l'erreur est restituée à l'interface
                result = {"state": "failed", "error": str(exc)}
            with self._lock:
                self.jobs[name] = {**self.jobs[name], **result, "finished": time.time()}

        threading.Thread(target=work, name=f"backup-{name}", daemon=True).start()
        return self.jobs[name]

    def start_create(self, name: str, reason: str = "manuelle") -> dict:
        if reason not in REASONS:
            raise PanelError(400, "Motif de sauvegarde inconnu.")
        self.m._get(name)
        self._backup_mount()
        return self._spawn(name, "Sauvegarde en cours", lambda: self._create_sync(name, reason))

    def start_restore(self, name: str, filename: str) -> dict:
        self.path(name, filename)
        self._backup_mount()
        return self._spawn(name, "Restauration en cours", lambda: self._restore_sync(name, filename))
