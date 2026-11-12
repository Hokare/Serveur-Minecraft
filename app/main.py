"""API FastAPI du panel Minecraft."""
from __future__ import annotations

import base64
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .dockerops import ROUTER_IMAGE, SERVER_IMAGE, Manager, PanelError
from .models import CommandBody, RouterSpec, ServerSpec
from .monitor import ROUTER_KEY, Monitor, host_stats

log = logging.getLogger("mc-panel")

PANEL_USER = os.environ.get("PANEL_USER", "admin")
PANEL_PASSWORD = os.environ.get("PANEL_PASSWORD", "")
STATIC_DIR = Path(__file__).parent / "static"

manager = Manager()
monitor = Monitor(manager)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not PANEL_PASSWORD:
        log.warning("PANEL_PASSWORD n'est pas défini : le panel n'est PAS protégé. "
                    "Ne l'expose jamais hors de localhost dans cet état.")
    monitor.start()
    yield
    monitor.stop()


app = FastAPI(title="MC Panel", lifespan=lifespan)


# --------------------------------------------------------------------------- sécurité
@app.middleware("http")
async def security(request: Request, call_next):
    if PANEL_PASSWORD:
        ok = False
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(user, PANEL_USER) & secrets.compare_digest(pwd, PANEL_PASSWORD)
            except ValueError:
                ok = False
        if not ok:
            return JSONResponse({"detail": "Authentification requise"}, status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="MC Panel"'})
    # Anti-CSRF : un en-tête personnalisé force une requête « preflight » cross-origin.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "mc-panel":
        return JSONResponse({"detail": "En-tête X-Requested-With manquant"}, status_code=403)
    return await call_next(request)


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


@app.post("/api/servers/{name}/{action}")
def server_action(name: str, action: str):
    return manager.action(name, action)


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


@app.get("/api/servers/{name}/stats")
def server_stats(name: str):
    return {"points": monitor.history(name)}


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


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
