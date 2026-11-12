import base64
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("PANEL_PASSWORD", "s3cretpass")
    monkeypatch.setenv("PANEL_USER", "admin")
    monkeypatch.setenv("PANEL_DATA_DIR", str(tmp_path))
    from app import main
    importlib.reload(main)
    # pas de Docker dans les tests : le panel doit répondre proprement
    monkeypatch.setattr(main.manager, "available", lambda: False)
    monkeypatch.setattr(main.manager, "cleanup_updater", lambda: None)
    with TestClient(main.app) as c:
        yield c


def basic(user="admin", pwd="s3cretpass"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()}


def w(headers=None):
    return {**(headers or basic()), "X-Requested-With": "mc-panel"}


def test_requires_auth(client):
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers=basic(pwd="nope")).status_code == 401
    assert client.get("/api/overview", headers=basic(user="autre")).status_code == 401


def test_overview_without_docker(client):
    r = client.get("/api/overview", headers=basic())
    assert r.status_code == 200 and r.json()["docker"]["ok"] is False


def test_csrf_header_required_for_writes(client):
    assert client.post("/api/servers/x/start", headers=basic()).status_code == 403


def test_validation_error_is_422(client):
    assert client.post("/api/servers", headers=w(), json={"name": "BAD NAME"}).status_code == 422


def test_specific_post_routes_not_shadowed_by_generic_action(client, monkeypatch):
    from app import main
    calls = []
    monkeypatch.setattr(main.manager, "command", lambda n, c: calls.append(("cmd", c)) or "ok")
    monkeypatch.setattr(main.manager, "banned_players", lambda n: [])
    monkeypatch.setattr(main.manager, "action", lambda n, a: calls.append(("action", a)) or {})
    assert client.post("/api/servers/s/command", headers=w(), json={"command": "list"}).json() == {"output": "ok"}
    assert client.post("/api/servers/s/ban", headers=w(), json={"player": "Troll"}).status_code == 200
    assert client.post("/api/servers/s/pardon", headers=w(), json={"player": "Troll"}).status_code == 200
    assert client.post("/api/servers/s/restart", headers=w()).status_code == 200
    assert calls == [("cmd", "list"), ("cmd", "ban Troll"), ("cmd", "pardon Troll"), ("action", "restart")]


def test_upload_endpoint_streams_body_and_enforces_limit(client, monkeypatch):
    from app import main
    got = {}
    monkeypatch.setattr(main.manager, "upload_file", lambda n, k, f, d: got.update(name=n, kind=k, filename=f, size=len(d)))
    r = client.put("/api/servers/survie/files/mods?filename=a.jar", headers=w(), content=b"PK\x03\x04" + b"x" * 50)
    assert r.status_code == 200 and got == {"name": "survie", "kind": "mods", "filename": "a.jar", "size": 54}
    monkeypatch.setattr(main, "MAX_UPLOAD", 10)
    assert client.put("/api/servers/survie/files/mods?filename=a.jar", headers=w(), content=b"x" * 50).status_code == 413
    assert client.put("/api/servers/survie/files/mods?filename=a.jar", content=b"x").status_code == 401


def test_backup_routes_not_shadowed_and_download(client, monkeypatch, tmp_path):
    from app import main
    calls = []
    monkeypatch.setattr(main.backups, "start_create", lambda n, r="manuelle": calls.append(("create", n, r)) or {"state": "running"})
    monkeypatch.setattr(main.backups, "start_restore", lambda n, f: calls.append(("restore", n, f)) or {"state": "running"})
    monkeypatch.setattr(main.manager, "action", lambda n, a: calls.append(("action", a)) or {})
    assert client.post("/api/servers/survie/backups?reason=avant-modif", headers=w()).json() == {"state": "running"}
    assert client.post("/api/servers/survie/backups/survie-20260101-100000-manuelle.tar.gz/restore", headers=w()).status_code == 200
    assert calls == [("create", "survie", "avant-modif"), ("restore", "survie", "survie-20260101-100000-manuelle.tar.gz")]
    f = tmp_path / "x.tar.gz"
    f.write_bytes(b"data")
    monkeypatch.setattr(main.backups, "path", lambda n, fn: f)
    r = client.get("/api/servers/survie/backups/survie-20260101-100000-manuelle.tar.gz", headers=basic())
    assert r.status_code == 200 and r.content == b"data"
    assert client.get("/api/servers/survie/backups/x.tar.gz").status_code == 401


def test_static_index_served(client):
    r = client.get("/", headers=basic())
    assert "MC Panel" in r.text and r.headers["cache-control"] == "no-cache"


def test_change_password_and_username(client):
    r = client.post("/api/account", headers=w(), json={
        "current_password": "s3cretpass", "new_username": "martin", "new_password": "nouveau-mdp-123"})
    assert r.status_code == 200 and r.json()["username"] == "martin"
    assert client.get("/api/account", headers=basic()).status_code == 401           # ancien identifiant refusé
    assert client.get("/api/account", headers=basic("martin", "nouveau-mdp-123")).json() == {"username": "martin"}


def test_account_update_rejects_bad_input(client):
    base = {"current_password": "s3cretpass"}
    assert client.post("/api/account", headers=w(), json={**base, "current_password": "faux", "new_password": "longenough1"}).status_code == 400
    assert client.post("/api/account", headers=w(), json={**base, "new_password": "court"}).status_code == 400
    assert client.post("/api/account", headers=w(), json={**base, "new_username": "a b"}).status_code == 400
    assert client.post("/api/account", headers=w(), json=base).status_code == 400   # rien à modifier
    assert client.get("/api/account", headers=basic()).status_code == 200          # inchangé


def test_update_unavailable_without_github_or_compose(client, monkeypatch):
    from app import main, system
    monkeypatch.setattr(system, "latest_commit", lambda force=False: None)
    assert client.post("/api/system/update", headers=w()).status_code == 502
    assert main.system.info(main.manager)["supported"] is False


def test_password_persisted_and_env_ignored_afterwards(monkeypatch, tmp_path):
    from app.auth import AuthStore
    a = AuthStore(tmp_path, "admin", "premier-mdp")
    a.update_credentials("premier-mdp", new_password="second-mdp-ok")
    b = AuthStore(tmp_path, "admin", "premier-mdp")          # redémarrage avec le même PANEL_PASSWORD
    assert b.verify("admin", "second-mdp-ok") and not b.verify("admin", "premier-mdp")


def test_random_password_generated_when_none_given(tmp_path, caplog):
    from app.auth import AuthStore
    store = AuthStore(tmp_path, "admin", "")
    assert (tmp_path / "auth.json").exists()
    assert "Mot de passe initial généré" in caplog.text and not store.verify("admin", "")
