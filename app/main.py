"""API FastAPI du panel Minecraft."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import system
from .auth import AuthStore
from .backups import Backups
from .files import FileManager
from .dockerops import ROUTER_IMAGE, SERVER_IMAGE, Manager, PanelError
from .models import (AccountUpdate, CommandBody, FileCreate, FileRename, FileWrite, PlayerBody, RouterSpec,
                     ServerSpec)
from .monitor import ROUTER_KEY, Monitor, host_stats

log = logging.getLogger("mc-panel")

STATIC_DIR = Path(__file__).parent / "static"

auth = AuthStore(
    Path(os.environ.get("PANEL_DATA_DIR", "./data")),
    default_user=os.environ.get("PANEL_USER", "admin"),
    initial_password=os.environ.get("PANEL_PASSWORD", ""),
)
manager = Manager()
monitor = Monitor(manager)
backups = Backups(manager)
fsm = FileManager(manager)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        manager.cleanup_updater()      # supprime l'updater terminé d'une mise à jour précédente
    except Exception:  # noqa: BLE001 - Docker peut être indisponible au démarrage
        pass
    monitor.start()
    yield
    monitor.stop()


app = FastAPI(title="MC Panel", lifespan=lifespan)


# --------------------------------------------------------------------------- sécurité
@app.middleware("http")
async def security(request: Request, call_next):
    if not auth.check(request.headers.get("authorization", "")):
        return JSONResponse({"detail": "Authentification requise"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="MC Panel"'})
    # Anti-CSRF : un en-tête personnalisé force une requête « preflight » cross-origin.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "mc-panel":
        return JSONResponse({"detail": "En-tête X-Requested-With manquant"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"      # l'interface se met à jour sans vider le cache
    return response


@app.exception_handler(PanelError)
async def panel_error(_: Request, exc: PanelError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


# --------------------------------------------------------------------------- vue d'ensemble
def _with_stats(server: dict) -> dict:
    server["stats"] = monitor.latest(server["name"])
    return server


@app.get("/api/overview")
def overview():
    if not manager.available():
        return {"docker": {"ok": False, "error": "Docker injoignable (socket /var/run/docker.sock ?)"},
                "host": host_stats(), "servers": [], "router": None}
    router = manager.get_router()
    router["stats"] = monitor.latest(ROUTER_KEY)
    return {
        "docker": manager.info(),
        "host": host_stats(),
        "servers": [_with_stats(s) for s in manager.list_servers()],
        "router": router,
    }


# --------------------------------------------------------------------------- serveurs
@app.post("/api/servers", status_code=201)
def create_server(spec: ServerSpec):
    return manager.create_server(spec)


@app.get("/api/servers/{name}")
def get_server(name: str):
    return _with_stats(manager.get_server(name))


@app.put("/api/servers/{name}")
def update_server(name: str, spec: ServerSpec):
    return manager.update_server(name, spec)


@app.delete("/api/servers/{name}")
def delete_server(name: str, remove_data: bool = False):
    manager.delete_server(name, remove_data)
    return {"ok": True}


@app.get("/api/servers/{name}/logs")
def server_logs(name: str, tail: int = 300):
    return {"logs": manager.logs(name, tail)}


@app.post("/api/servers/{name}/command")
def server_command(name: str, body: CommandBody):
    return {"output": manager.command(name, body.command)}


@app.get("/api/servers/{name}/fs/list")
def fs_list(name: str, path: str = ""):
    return {"path": fsm.clean(path), "entries": fsm.list(name, path)}


@app.get("/api/servers/{name}/fs/read")
def fs_read(name: str, path: str):
    return fsm.read(name, path)


@app.put("/api/servers/{name}/fs/write")
def fs_write(name: str, body: FileWrite):
    fsm.write(name, body.path, body.content)
    return {"ok": True}


@app.post("/api/servers/{name}/fs/create")
def fs_create(name: str, body: FileCreate):
    fsm.create(name, body.path, body.kind)
    return {"ok": True}


@app.post("/api/servers/{name}/fs/rename")
def fs_rename(name: str, body: FileRename):
    fsm.rename(name, body.path, body.new_name)
    return {"ok": True}


@app.delete("/api/servers/{name}/fs")
def fs_delete(name: str, path: str):
    fsm.delete(name, path)
    return {"ok": True}


@app.put("/api/servers/{name}/fs/upload")
async def fs_upload(name: str, filename: str, request: Request, path: str = ""):
    if int(request.headers.get("content-length") or 0) > MAX_UPLOAD:
        raise PanelError(413, f"Fichier trop gros (limite {MAX_UPLOAD // 1024 // 1024} Mo).")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_UPLOAD:
            raise PanelError(413, f"Fichier trop gros (limite {MAX_UPLOAD // 1024 // 1024} Mo).")
    await run_in_threadpool(fsm.upload, name, path, filename, bytes(data))
    return {"ok": True}


@app.get("/api/servers/{name}/fs/download")
def fs_download(name: str, path: str):
    data, filename = fsm.download(name, path)
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename.replace(chr(34), "")}"'})


@app.get("/api/servers/{name}/backups")
def backups_status(name: str):
    return backups.status(name)


@app.post("/api/servers/{name}/backups")
def backups_create(name: str, reason: str = "manuelle"):
    return backups.start_create(name, reason)


@app.get("/api/servers/{name}/backups/{filename}")
def backups_download(name: str, filename: str):
    path = backups.path(name, filename)
    return FileResponse(path, filename=filename, media_type="application/gzip")


@app.delete("/api/servers/{name}/backups/{filename}")
def backups_delete(name: str, filename: str):
    backups.delete(name, filename)
    return {"ok": True}


@app.post("/api/servers/{name}/backups/{filename}/restore")
def backups_restore(name: str, filename: str):
    return backups.start_restore(name, filename)


MAX_UPLOAD = int(os.environ.get("PANEL_MAX_UPLOAD_MB", "128")) * 1024 * 1024


@app.get("/api/servers/{name}/files/{kind}")
def list_files(name: str, kind: str):
    return {"files": manager.list_files(name, kind)}


@app.put("/api/servers/{name}/files/{kind}")
async def upload_file(name: str, kind: str, filename: str, request: Request):
    """Envoi d'un .jar : le fichier est le corps brut de la requête (pas de multipart)."""
    if int(request.headers.get("content-length") or 0) > MAX_UPLOAD:
        raise PanelError(413, f"Fichier trop gros (limite {MAX_UPLOAD // 1024 // 1024} Mo).")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_UPLOAD:
            raise PanelError(413, f"Fichier trop gros (limite {MAX_UPLOAD // 1024 // 1024} Mo).")
    await run_in_threadpool(manager.upload_file, name, kind, filename, bytes(data))
    return {"ok": True}


@app.delete("/api/servers/{name}/files/{kind}")
def delete_file(name: str, kind: str, filename: str):
    manager.delete_file(name, kind, filename)
    return {"ok": True}


@app.get("/api/servers/{name}/banned")
def banned(name: str):
    return {"players": manager.banned_players(name)}


@app.post("/api/servers/{name}/ban")
def ban_player(name: str, body: PlayerBody):
    manager.ban(name, body.player)
    return {"players": manager.banned_players(name)}


@app.post("/api/servers/{name}/pardon")
def pardon_player(name: str, body: PlayerBody):
    manager.ban(name, body.player, pardon=True)
    return {"players": manager.banned_players(name)}


@app.get("/api/servers/{name}/stats")
def server_stats(name: str):
    return {"points": monitor.history(name)}


# À déclarer en dernier : cette route générique capturerait sinon /command, /ban, /pardon.
@app.post("/api/servers/{name}/{action}")
def server_action(name: str, action: str):
    return manager.action(name, action)


# --------------------------------------------------------------------------- routeur
@app.get("/api/router")
def get_router():
    router = manager.get_router()
    router["stats"] = monitor.latest(ROUTER_KEY)
    router["live_routes"] = manager.router_routes()
    return router


@app.put("/api/router")
def put_router(spec: RouterSpec):
    return manager.apply_router(spec)


@app.post("/api/router/{action}")
def router_action(action: str):
    return manager.router_action(action)


@app.delete("/api/router")
def delete_router():
    manager.delete_router()
    return {"ok": True}


@app.get("/api/router/logs")
def router_logs(tail: int = 200):
    return {"logs": manager.router_logs(tail)}


@app.get("/api/router/stats")
def router_stats():
    return {"points": monitor.history(ROUTER_KEY)}


# --------------------------------------------------------------------------- images
@app.get("/api/images")
def images():
    return {"images": manager.list_images()}


@app.post("/api/images/pull")
def pull_image(kind: str, tag: str = "latest"):
    repo = {"server": SERVER_IMAGE, "router": ROUTER_IMAGE}.get(kind)
    if repo is None:
        raise PanelError(400, "kind doit valoir server ou router")
    ServerSpec.model_validate({"name": "x", "image_tag": tag})   # réutilise la validation du tag
    manager.pull(repo, tag)
    return {"ok": True}


# --------------------------------------------------------------------------- compte et mise à jour
@app.get("/api/account")
def account():
    return {"username": auth.user}


@app.post("/api/account")
def update_account(body: AccountUpdate):
    try:
        auth.update_credentials(body.current_password, body.new_username, body.new_password)
    except ValueError as exc:
        raise PanelError(400, str(exc)) from exc
    return {"ok": True, "username": auth.user}


@app.get("/api/system")
def system_info():
    return system.info(manager)


@app.post("/api/system/update")
def system_update():
    return system.start_update(manager)


@app.get("/api/system/update")
def system_update_status():
    return manager.updater_status()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
