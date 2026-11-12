import base64
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "s3cret")
    monkeypatch.setenv("PANEL_USER", "admin")
    from app import main
    importlib.reload(main)
    # pas de Docker dans les tests : le panel doit répondre proprement
    monkeypatch.setattr(main.manager, "available", lambda: False)
    with TestClient(main.app) as c:
        yield c
    importlib.reload(main)


def basic(user="admin", pwd="s3cret"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()}


def test_requires_auth(client):
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers=basic(pwd="nope")).status_code == 401


def test_overview_without_docker(client):
    r = client.get("/api/overview", headers=basic())
    assert r.status_code == 200 and r.json()["docker"]["ok"] is False


def test_csrf_header_required_for_writes(client):
    r = client.post("/api/servers/x/start", headers=basic())
    assert r.status_code == 403


def test_validation_error_is_422(client):
    r = client.post("/api/servers", headers={**basic(), "X-Requested-With": "mc-panel"}, json={"name": "BAD NAME"})
    assert r.status_code == 422


def test_static_index_served(client):
    assert "MC Panel" in client.get("/", headers=basic()).text
