"""Explorateur de fichiers du dossier /data d'un serveur (fonctionne serveur allumé ou arrêté).

Lecture / écriture : API d'archives de Docker (get_archive / put_archive).
Listage, suppression, renommage : conteneur jetable qui voit le /data du serveur (volumes_from).
Tous les chemins sont relatifs à /data et normalisés : aucun « .. » n'est accepté.
"""
from __future__ import annotations

import io
import tarfile

from docker.errors import APIError, NotFound

from .dockerops import Manager, PanelError

MAX_EDIT = 1_000_000                 # taille max d'un fichier ouvert dans l'éditeur
MAX_DOWNLOAD = 256 * 1024 * 1024
UID = GID = 1000                     # utilisateur par défaut de l'image itzg/minecraft-server


class FileManager:
    def __init__(self, manager: Manager):
        self.m = manager

    # ------------------------------------------------------------------ validation
    @staticmethod
    def clean(rel: str | None) -> str:
        """Chemin relatif normalisé ('' = racine). Refuse « .. », NUL et chemins démesurés."""
        rel = (rel or "").strip()
        if "\x00" in rel or len(rel) > 1024:
            raise PanelError(400, "Chemin invalide.")
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise PanelError(400, "Chemin invalide (« .. » interdit).")
        return "/".join(parts)

    @staticmethod
    def check_name(name: str) -> str:
        name = (name or "").strip()
        if not name or name in (".", "..") or "/" in name or "\x00" in name or len(name) > 255:
            raise PanelError(400, "Nom invalide (pas de « / », 255 caractères max).")
        return name

    @staticmethod
    def split(rel: str) -> tuple[str, str]:
        parent, _, name = rel.rpartition("/")
        return parent, name

    @staticmethod
    def abs(rel: str) -> str:
        return f"/data/{rel}" if rel else "/data"

    # ------------------------------------------------------------------ utilitaires Docker
    def _exists(self, c, rel: str) -> bool:
        out = self.m._helper(c, ["sh", "-c", '[ -e "$1" ] || [ -L "$1" ] && echo yes || echo no', "sh"], [self.abs(rel)])
        return out.strip() == "yes"

    @staticmethod
    def _tar(name: str, data: bytes | None) -> bytes:
        """Archive d'une entrée (fichier si data n'est pas None, sinon dossier), appartenant à l'utilisateur du jeu."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name)
            info.uid, info.gid = UID, GID
            if data is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            else:
                info.size, info.mode = len(data), 0o644
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def _put(self, c, parent_rel: str, name: str, data: bytes | None) -> None:
        try:
            c.put_archive(self.abs(parent_rel), self._tar(name, data))
        except NotFound as exc:
            raise PanelError(404, "Dossier introuvable.") from exc
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc

    def _fetch(self, c, rel: str, limit: int) -> tuple[bytes, dict]:
        """Contenu d'un fichier (via get_archive), en refusant dossiers et fichiers trop gros."""
        try:
            stream, stat = c.get_archive(self.abs(rel))
        except NotFound as exc:
            raise PanelError(404, "Fichier introuvable.") from exc
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc
        if stat.get("mode", 0) & (1 << 31):
            raise PanelError(400, "C'est un dossier.")
        if stat.get("size", 0) > limit:
            raise PanelError(413, f"Fichier trop gros ({stat['size'] // 1024} Ko, limite {limit // 1024} Ko).")
        buf = bytearray()
        for chunk in stream:
            buf.extend(chunk)
            if len(buf) > limit + 65536:
                raise PanelError(413, "Fichier trop gros.")
        with tarfile.open(fileobj=io.BytesIO(bytes(buf))) as tar:
            member = tar.next()
            if member is None or not member.isfile():
                raise PanelError(400, "Ce n'est pas un fichier régulier.")
            return tar.extractfile(member).read(), stat

    # ------------------------------------------------------------------ opérations
    def list(self, server: str, rel: str) -> list[dict]:
        rel = self.clean(rel)
        c = self.m._get(server)
        script = ('[ -d "$1" ] || { echo NODIR; exit 0; }; d="$1"; '
                  'for f in "$d"/* "$d"/.[!.]* "$d"/..?*; do '
                  '[ -e "$f" ] || [ -L "$f" ] || continue; n=$(basename "$f"); '
                  'if [ -d "$f" ]; then printf "d\\t0\\t%s\\n" "$n"; '
                  'else printf "f\\t%s\\t%s\\n" "$(wc -c < "$f" 2>/dev/null || echo 0)" "$n"; fi; done; true')
        out = self.m._helper(c, ["sh", "-c", script, "sh"], [self.abs(rel)])
        if out.strip() == "NODIR":
            raise PanelError(404, "Dossier introuvable.")
        entries = []
        for line in out.splitlines():
            kind, _, rest = line.partition("\t")
            size, _, name = rest.partition("\t")
            if kind in ("d", "f") and name and size.strip().isdigit():
                entries.append({"name": name, "dir": kind == "d", "size": int(size)})
        return sorted(entries, key=lambda e: (not e["dir"], e["name"].lower()))

    def read(self, server: str, rel: str) -> dict:
        rel = self.clean(rel)
        if not rel:
            raise PanelError(400, "Chemin de fichier requis.")
        raw, _ = self._fetch(self.m._get(server), rel, MAX_EDIT)
        if b"\x00" in raw[:8192]:
            raise PanelError(415, "Fichier binaire : téléchargement uniquement.")
        try:
            return {"content": raw.decode("utf-8"), "size": len(raw)}
        except UnicodeDecodeError as exc:
            raise PanelError(415, "Fichier non textuel (UTF-8) : téléchargement uniquement.") from exc

    def write(self, server: str, rel: str, content: str) -> None:
        rel = self.clean(rel)
        data = content.encode("utf-8")
        if not rel or len(data) > MAX_EDIT:
            raise PanelError(413 if rel else 400, "Fichier trop gros pour l'éditeur." if rel else "Chemin de fichier requis.")
        parent, name = self.split(rel)
        self._put(self.m._get(server), parent, self.check_name(name), data)

    def create(self, server: str, rel: str, kind: str) -> None:
        rel = self.clean(rel)
        if kind not in ("file", "dir") or not rel:
            raise PanelError(400, "Demande invalide.")
        parent, name = self.split(rel)
        self.check_name(name)
        c = self.m._get(server)
        if self._exists(c, rel):
            raise PanelError(409, f"« {name} » existe déjà.")
        self._put(c, parent, name, None if kind == "dir" else b"")

    def delete(self, server: str, rel: str) -> None:
        rel = self.clean(rel)
        if not rel:
            raise PanelError(400, "Impossible de supprimer la racine du serveur.")
        self.m._helper(self.m._get(server), ["rm", "-rf", "--"], [self.abs(rel)])

    def rename(self, server: str, rel: str, new_name: str) -> None:
        rel = self.clean(rel)
        if not rel:
            raise PanelError(400, "Impossible de renommer la racine du serveur.")
        new_name = self.check_name(new_name)
        parent, _ = self.split(rel)
        target = f"{parent}/{new_name}" if parent else new_name
        c = self.m._get(server)
        out = self.m._helper(c, ["sh", "-c", 'if [ -e "$2" ] || [ -L "$2" ]; then echo EXISTS; else mv -- "$1" "$2" && echo OK; fi', "sh"],
                             [self.abs(rel), self.abs(target)])
        if out.strip() == "EXISTS":
            raise PanelError(409, f"« {new_name} » existe déjà dans ce dossier.")

    def upload(self, server: str, dir_rel: str, filename: str, data: bytes) -> None:
        dir_rel = self.clean(dir_rel)
        filename = self.check_name(filename)
        c = self.m._get(server)
        target = f"{dir_rel}/{filename}" if dir_rel else filename
        if self._exists(c, target):
            raise PanelError(409, f"« {filename} » existe déjà dans ce dossier. Supprime-le d'abord pour le remplacer.")
        self._put(c, dir_rel, filename, data)

    def download(self, server: str, rel: str) -> tuple[bytes, str]:
        rel = self.clean(rel)
        if not rel:
            raise PanelError(400, "Chemin de fichier requis.")
        raw, _ = self._fetch(self.m._get(server), rel, MAX_DOWNLOAD)
        return raw, self.split(rel)[1]
