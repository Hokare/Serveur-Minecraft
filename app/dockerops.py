"""Opérations Docker : serveurs itzg/minecraft-server et routeur itzg/mc-router."""
from __future__ import annotations

import io
import json
import shlex
import socket
import tarfile
import threading
import urllib.request

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from .models import RouterSpec, ServerSpec

NETWORK = "mc-net"
SERVER_IMAGE = "itzg/minecraft-server"
ROUTER_IMAGE = "itzg/mc-router"
ROUTER_NAME = "mc-router"
UPDATER_NAME = "mc-panel-updater"
ROUTER_API_PORT = 25564
STOP_TIMEOUT = 60          # laisse le serveur sauvegarder le monde

LABEL_MANAGED = "mc-panel.managed"
LABEL_KIND = "mc-panel.kind"
LABEL_NAME = "mc-panel.name"
LABEL_SPEC = "mc-panel.spec"


class PanelError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Manager:
    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ connexion
    @property
    def client(self) -> docker.DockerClient:
        with self._lock:
            if self._client is None:
                try:
                    self._client = docker.from_env()
                    self._client.ping()
                except DockerException as exc:
                    self._client = None
                    raise PanelError(503, f"Docker injoignable : {exc}") from exc
            return self._client

    def available(self) -> bool:
        try:
            self.client.ping()
            return True
        except (PanelError, DockerException):
            with self._lock:
                self._client = None
            return False

    def info(self) -> dict:
        info = self.client.info()
        return {
            "ok": True,
            "version": info.get("ServerVersion"),
            "containers_running": info.get("ContainersRunning"),
            "containers_total": info.get("Containers"),
            "images": info.get("Images"),
            "os": info.get("OperatingSystem"),
            "cpus": info.get("NCPU"),
            "mem_total": info.get("MemTotal"),
        }

    def ensure_network(self) -> None:
        try:
            self.client.networks.get(NETWORK)
        except NotFound:
            self.client.networks.create(NETWORK, driver="bridge")

    def ensure_image(self, repo: str, tag: str) -> None:
        try:
            self.client.images.get(f"{repo}:{tag}")
        except ImageNotFound:
            try:
                self.client.images.pull(repo, tag=tag)
            except APIError as exc:
                raise PanelError(502, f"Impossible de télécharger {repo}:{tag} : {exc.explanation or exc}") from exc

    def list_images(self) -> list[dict]:
        out = []
        for img in self.client.images.list():
            for tag in img.tags:
                if tag.startswith((SERVER_IMAGE, ROUTER_IMAGE)):
                    out.append({"tag": tag, "size": img.attrs.get("Size", 0), "created": img.attrs.get("Created")})
        return sorted(out, key=lambda i: i["tag"])

    def pull(self, repo: str, tag: str) -> None:
        if repo not in (SERVER_IMAGE, ROUTER_IMAGE):
            raise PanelError(400, "image non autorisée")
        try:
            self.client.images.pull(repo, tag=tag)
        except APIError as exc:
            raise PanelError(502, f"Téléchargement impossible : {exc.explanation or exc}") from exc

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def cname(name: str) -> str:
        return f"mc-{name}"

    @staticmethod
    def key_of(container) -> str:
        if container.labels.get(LABEL_KIND) == "router":
            return "__router__"
        return container.labels.get(LABEL_NAME, container.name)

    @staticmethod
    def ip_of(container) -> str | None:
        nets = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        return (nets.get(NETWORK) or {}).get("IPAddress") or None

    @staticmethod
    def health_of(container) -> str | None:
        return (container.attrs.get("State", {}).get("Health") or {}).get("Status")

    def is_ready(self, container) -> bool:
        if container.status != "running":
            return False
        health = self.health_of(container)
        return health in (None, "healthy")

    def running_managed(self) -> list:
        return self.client.containers.list(filters={"label": f"{LABEL_MANAGED}=true", "status": "running"})

    def _get(self, name: str):
        try:
            c = self.client.containers.get(self.cname(name))
        except NotFound as exc:
            raise PanelError(404, f"Serveur introuvable : {name}") from exc
        if c.labels.get(LABEL_MANAGED) != "true" or c.labels.get(LABEL_KIND) != "server":
            raise PanelError(404, f"Serveur introuvable : {name}")
        return c

    @staticmethod
    def _spec_of(container) -> ServerSpec | None:
        raw = container.labels.get(LABEL_SPEC)
        try:
            return ServerSpec.model_validate_json(raw) if raw else None
        except ValueError:
            return None

    def _server_view(self, c) -> dict | None:
        spec = self._spec_of(c)
        if spec is None:
            return None
        state = c.attrs.get("State", {})
        return {
            "name": spec.name,
            "status": c.status,
            "health": self.health_of(c),
            "started_at": state.get("StartedAt"),
            "id": c.short_id,
            "ip": self.ip_of(c),
            "spec": spec.model_dump(),
        }

    # ------------------------------------------------------------------ serveurs
    def list_servers(self) -> list[dict]:
        found = self.client.containers.list(all=True, filters={"label": [f"{LABEL_MANAGED}=true", f"{LABEL_KIND}=server"]})
        views = [v for v in (self._server_view(c) for c in found) if v]
        return sorted(views, key=lambda v: v["name"])

    def get_server(self, name: str) -> dict:
        view = self._server_view(self._get(name))
        if view is None:
            raise PanelError(500, "Configuration du serveur illisible")
        return view

    @staticmethod
    def build_env(spec: ServerSpec) -> dict[str, str]:
        env = dict(spec.env)
        env["MEMORY"] = spec.memory
        if spec.access_mode == "whitelist":
            env["ENABLE_WHITELIST"] = "TRUE"
        else:   # la liste blanche n'est active que dans ce mode
            for key in ("WHITELIST", "ENABLE_WHITELIST", "ENFORCE_WHITELIST"):
                env.pop(key, None)
        return env

    def _server_kwargs(self, spec: ServerSpec) -> dict:
        labels = {
            LABEL_MANAGED: "true",
            LABEL_KIND: "server",
            LABEL_NAME: spec.name,
            LABEL_SPEC: spec.model_dump_json(),
        }
        if spec.hosts:
            labels["mc-router.host"] = spec.hosts
            labels["mc-router.port"] = "25565"
            labels["mc-router.network"] = NETWORK
            if spec.router_default:
                labels["mc-router.default"] = "true"
        source = spec.data_path or f"mc-data-{spec.name}"
        kwargs: dict = dict(
            image=f"{SERVER_IMAGE}:{spec.image_tag}",
            name=self.cname(spec.name),
            environment=self.build_env(spec),
            labels=labels,
            network_mode=NETWORK,
            tty=True,
            stdin_open=True,
            restart_policy={"Name": spec.restart},
            volumes={source: {"bind": "/data", "mode": "rw"}},
        )
        if spec.host_port:
            kwargs["ports"] = {"25565/tcp": spec.host_port}
        if spec.mem_limit:
            kwargs["mem_limit"] = spec.mem_limit
            kwargs["memswap_limit"] = spec.mem_limit
        if spec.cpu_limit:
            kwargs["nano_cpus"] = int(spec.cpu_limit * 1_000_000_000)
        return kwargs

    def create_server(self, spec: ServerSpec) -> dict:
        if spec.env.get("EULA", "").upper() != "TRUE":
            raise PanelError(400, "Tu dois accepter l'EULA Minecraft (EULA=TRUE).")
        self.ensure_network()
        try:
            self.client.containers.get(self.cname(spec.name))
            raise PanelError(409, f"Un serveur nommé « {spec.name} » existe déjà.")
        except NotFound:
            pass
        self.ensure_image(SERVER_IMAGE, spec.image_tag)
        try:
            c = self.client.containers.create(**self._server_kwargs(spec))
            c.start()
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc
        c.reload()
        return self._server_view(c)

    def update_server(self, name: str, spec: ServerSpec) -> dict:
        """Docker ne permet pas de modifier l'environnement d'un conteneur :
        on le recrée à l'identique (même volume), puis on le redémarre s'il tournait."""
        old = self._get(name)
        spec.name = name
        if spec.env.get("EULA", "").upper() != "TRUE":
            raise PanelError(400, "EULA=TRUE est requis.")
        self.ensure_image(SERVER_IMAGE, spec.image_tag)
        was_running = old.status in ("running", "restarting")
        original, backup = old.name, f"{old.name}-old"
        try:  # reste d'une opération interrompue
            self.client.containers.get(backup).remove(force=True)
        except NotFound:
            pass
        try:
            if was_running:
                old.stop(timeout=STOP_TIMEOUT)
            old.rename(backup)
            try:
                new = self.client.containers.create(**self._server_kwargs(spec))
            except APIError:
                old.rename(original)
                if was_running:
                    old.start()
                raise
            old.remove()
            if was_running:
                new.start()
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc
        new.reload()
        return self._server_view(new)

    def action(self, name: str, action: str) -> dict:
        c = self._get(name)
        try:
            if action == "start":
                c.start()
            elif action == "stop":
                c.stop(timeout=STOP_TIMEOUT)
            elif action == "restart":
                c.restart(timeout=STOP_TIMEOUT)
            else:
                raise PanelError(400, "action inconnue")
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc
        c.reload()
        return self._server_view(c)

    def delete_server(self, name: str, remove_data: bool) -> None:
        c = self._get(name)
        spec = self._spec_of(c)
        try:
            c.stop(timeout=STOP_TIMEOUT)
        except APIError:
            pass
        try:
            c.remove(force=True)
            if remove_data and spec and not spec.data_path:
                try:
                    self.client.volumes.get(f"mc-data-{name}").remove()
                except NotFound:
                    pass
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc

    def logs(self, name: str, tail: int = 300) -> str:
        c = self._get(name)
        return c.logs(tail=max(1, min(tail, 2000))).decode("utf-8", errors="replace")

    def command(self, name: str, command: str) -> str:
        c = self._get(name)
        if c.status != "running":
            raise PanelError(409, "Le serveur n'est pas démarré.")
        code, out = c.exec_run(["rcon-cli", *command.split()])
        text = out.decode("utf-8", errors="replace").strip()
        if code != 0 and not text:
            raise PanelError(502, "RCON indisponible (le serveur démarre-t-il encore ?)")
        return text

    # ------------------------------------------------------------------ joueurs bannis (liste noire)
    def banned_players(self, name: str) -> list[str]:
        """Lit banned-players.json dans le conteneur (fonctionne aussi serveur arrêté)."""
        c = self._get(name)
        try:
            stream, _ = c.get_archive("/data/banned-players.json")
            raw = b"".join(stream)
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                member = tar.getmembers()[0]
                entries = json.load(tar.extractfile(member))
        except NotFound:
            return []
        except (tarfile.TarError, ValueError, IndexError, AttributeError, TypeError):
            raise PanelError(500, "banned-players.json illisible")
        return sorted((e.get("name", "") for e in entries if isinstance(e, dict) and e.get("name")), key=str.lower)

    def ban(self, name: str, player: str, pardon: bool = False) -> None:
        verb = "pardon" if pardon else "ban"
        self.command(name, f"{verb} {player}")

    # ------------------------------------------------------------------ mise à jour du panel
    def _self_container(self):
        try:
            return self.client.containers.get(socket.gethostname())
        except (NotFound, PanelError):
            return None

    def _project_dir(self) -> str | None:
        """Dossier du projet sur l'hôte (monté sur /project dans le conteneur du panel)."""
        me = self._self_container()
        if me is None:
            return None
        for mount in me.attrs.get("Mounts", []):
            if mount.get("Destination") == "/project":
                return mount.get("Source")
        return None

    def updater_supported(self) -> bool:
        try:
            return self._project_dir() is not None
        except PanelError:
            return False

    def launch_updater(self, env: dict[str, str]) -> None:
        me = self._self_container()
        project = self._project_dir()
        if me is None or project is None:
            raise PanelError(501, "Mise à jour automatique indisponible : le panel doit tourner via le "
                                  "docker-compose.yml fourni (volume .:/project).")
        if self.updater_status()["state"] == "running":
            raise PanelError(409, "Une mise à jour est déjà en cours.")
        self.cleanup_updater()
        if not project.startswith("/"):
            raise PanelError(501, f"Chemin de projet inattendu : {project}")
        try:
            # Le dossier est monté au MÊME chemin que sur l'hôte : compose résout `.:/project` côté client,
            # le démon Docker doit donc recevoir le vrai chemin de l'hôte (et non un chemin interne).
            self.client.containers.run(
                image=me.attrs["Image"],          # même image : elle embarque docker + compose
                name=UPDATER_NAME,
                command=["sh", "-c", f"sleep 3 && docker compose --project-directory {shlex.quote(project)} "
                                     f"-f {shlex.quote(project + '/docker-compose.yml')} up -d --build"],
                environment=env,
                working_dir=project,
                volumes={
                    project: {"bind": project, "mode": "ro"},
                    "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
                },
                detach=True,
            )
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc

    def updater_status(self) -> dict:
        try:
            c = self.client.containers.get(UPDATER_NAME)
        except NotFound:
            return {"state": "idle"}
        c.reload()
        st = c.attrs.get("State", {})
        if st.get("Running"):
            state = "running"
        else:
            state = "done" if st.get("ExitCode") == 0 else "failed"
        return {"state": state, "exit_code": st.get("ExitCode"),
                "logs": c.logs(tail=60).decode("utf-8", errors="replace")}

    def cleanup_updater(self) -> None:
        try:
            c = self.client.containers.get(UPDATER_NAME)
        except (NotFound, PanelError):
            return
        if c.status != "running":
            c.remove(force=True)

    # ------------------------------------------------------------------ routeur
    def _router_container(self):
        try:
            return self.client.containers.get(ROUTER_NAME)
        except NotFound:
            return None

    def get_router(self) -> dict:
        c = self._router_container()
        if c is None or c.labels.get(LABEL_KIND) != "router":
            return {"exists": False, "status": "absent", "spec": RouterSpec().model_dump()}
        try:
            spec = RouterSpec.model_validate_json(c.labels.get(LABEL_SPEC, "{}"))
        except ValueError:
            spec = RouterSpec()
        return {
            "exists": True,
            "status": c.status,
            "started_at": c.attrs.get("State", {}).get("StartedAt"),
            "id": c.short_id,
            "ip": self.ip_of(c),
            "spec": spec.model_dump(),
        }

    def apply_router(self, spec: RouterSpec) -> dict:
        self.ensure_network()
        self.ensure_image(ROUTER_IMAGE, spec.image_tag)
        env = {
            "IN_DOCKER": "true",
            "API_BINDING": f":{ROUTER_API_PORT}",
            "DOCKER_NETWORK": NETWORK,
        }
        if spec.mappings.strip():
            env["MAPPING"] = spec.mappings.strip()
        env.update(spec.env)
        old = self._router_container()
        was_running = old is not None and old.status == "running"
        kwargs = dict(
            image=f"{ROUTER_IMAGE}:{spec.image_tag}",
            name=ROUTER_NAME,
            environment=env,
            labels={LABEL_MANAGED: "true", LABEL_KIND: "router", LABEL_SPEC: spec.model_dump_json()},
            network_mode=NETWORK,
            ports={"25565/tcp": spec.host_port},
            volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "ro"}},
            restart_policy={"Name": "unless-stopped"},
        )
        try:
            if old is not None:
                old.remove(force=True)
            c = self.client.containers.create(**kwargs)
            if old is None or was_running:
                c.start()
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc
        return self.get_router()

    def router_action(self, action: str) -> dict:
        c = self._router_container()
        if c is None:
            raise PanelError(404, "Le routeur n'est pas encore créé.")
        try:
            {"start": c.start, "stop": c.stop, "restart": c.restart}[action]()
        except KeyError as exc:
            raise PanelError(400, "action inconnue") from exc
        except APIError as exc:
            raise PanelError(500, exc.explanation or str(exc)) from exc
        return self.get_router()

    def delete_router(self) -> None:
        c = self._router_container()
        if c is not None:
            c.remove(force=True)

    def router_logs(self, tail: int = 200) -> str:
        c = self._router_container()
        if c is None:
            return ""
        return c.logs(tail=max(1, min(tail, 2000))).decode("utf-8", errors="replace")

    def router_routes(self) -> list[dict] | None:
        """Routes actives selon l'API de mc-router (None si injoignable)."""
        c = self._router_container()
        if c is None or c.status != "running":
            return None
        ip = self.ip_of(c)
        if not ip:
            return None
        req = urllib.request.Request(f"http://{ip}:{ROUTER_API_PORT}/routes", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310 - IP interne issue de Docker
                data = json.load(resp)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(data, dict):
            return [{"host": k, "backend": v} for k, v in sorted(data.items())]
        return None
