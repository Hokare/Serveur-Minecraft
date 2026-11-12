import socket
import struct
import threading
import json

import pytest
from pydantic import ValidationError

from app.models import RouterSpec, ServerSpec
from app.monitor import _read_varint, _recv_exact, _varint, compute_cpu, compute_mem, ping


def test_spec_defaults_and_validation():
    spec = ServerSpec(name="survie", hosts="a.example.com, b.example.com", env={"EULA": "TRUE"})
    assert spec.hosts == "a.example.com,b.example.com"
    assert spec.memory == "2G"


@pytest.mark.parametrize("bad", [
    {"name": "Survie"}, {"name": "../x"}, {"name": "ok", "memory": "2 Go"},
    {"name": "ok", "image_tag": "latest; rm"}, {"name": "ok", "data_path": "relatif/chemin"},
    {"name": "ok", "data_path": "/srv/../etc"}, {"name": "ok", "env": {"1BAD": "x"}},
    {"name": "ok", "hosts": "bad host"}, {"name": "ok", "host_port": 70000},
])
def test_spec_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        ServerSpec(**bad)


def test_access_mode_controls_whitelist_env():
    from app.dockerops import Manager
    base = {"EULA": "TRUE", "WHITELIST": "Steve,Alex", "ENFORCE_WHITELIST": "TRUE"}
    wl = Manager.build_env(ServerSpec(name="a", access_mode="whitelist", env=base))
    assert wl["ENABLE_WHITELIST"] == "TRUE" and wl["WHITELIST"] == "Steve,Alex"
    for mode in ("none", "blacklist"):
        env = Manager.build_env(ServerSpec(name="a", access_mode=mode, env=base))
        assert not {"WHITELIST", "ENABLE_WHITELIST", "ENFORCE_WHITELIST"} & env.keys()


def test_legacy_spec_with_whitelist_stays_whitelisted():
    assert ServerSpec(name="a", env={"WHITELIST": "Steve"}).access_mode == "whitelist"
    assert ServerSpec(name="a", env={"EULA": "TRUE"}).access_mode == "none"


def test_updater_mounts_project_at_its_real_host_path(monkeypatch):
    """Régression : compose résout `.:/project` côté client, le chemin hôte doit donc rester identique."""
    import socket as _socket
    from types import SimpleNamespace
    from docker.errors import NotFound
    from app.dockerops import Manager

    me = SimpleNamespace(attrs={"Image": "sha256:abc", "Mounts": [
        {"Destination": "/project", "Source": "/root/Serveur-Minecraft"}]})
    captured = {}

    class Containers:
        def get(self, name):
            if name == "me":
                return me
            raise NotFound("absent")

        def run(self, **kwargs):
            captured.update(kwargs)

    m = Manager()
    m._client = SimpleNamespace(containers=Containers())
    monkeypatch.setattr(_socket, "gethostname", lambda: "me")
    assert m.updater_supported()
    m.launch_updater({"APP_SHA": "x"})
    assert captured["volumes"]["/root/Serveur-Minecraft"]["bind"] == "/root/Serveur-Minecraft"
    assert captured["working_dir"] == "/root/Serveur-Minecraft"
    cmd = captured["command"][-1]
    assert "--project-directory /root/Serveur-Minecraft" in cmd and "-f /root/Serveur-Minecraft/docker-compose.yml" in cmd


def test_route_conflicts(monkeypatch):
    from app.dockerops import Manager, PanelError
    m = Manager()
    existing = ServerSpec(name="survie", hosts="survie.exemple.com,play.exemple.com", router_default=True).model_dump()
    monkeypatch.setattr(m, "list_servers", lambda: [{"name": "survie", "spec": existing}])

    def check(**kw):
        m.check_route_conflicts(ServerSpec(**{"name": "creatif", **kw}))

    check(hosts="creatif.exemple.com")                              # aucun conflit
    check(hosts="creatif.exemple.com", router_default=False)
    with pytest.raises(PanelError) as e:
        check(hosts="PLAY.exemple.com")                              # même nom, casse différente
    assert e.value.status == 409 and "survie" in e.value.message
    with pytest.raises(PanelError) as e:
        check(hosts="creatif.exemple.com", router_default=True)      # second serveur par défaut
    assert e.value.status == 409 and "par défaut" in e.value.message
    with pytest.raises(PanelError) as e:
        check(router_default=True)                                   # défaut sans hostname
    assert e.value.status == 400
    # modifier le serveur existant ne doit pas entrer en conflit avec lui-même
    m.check_route_conflicts(ServerSpec(name="survie", hosts="survie.exemple.com", router_default=True))


def _manager_with_server(monkeypatch):
    import io as _io
    from types import SimpleNamespace
    from app.dockerops import Manager

    captured = {}
    container = SimpleNamespace(
        id="abc", attrs={"Image": "sha256:img"},
        labels={"mc-panel.managed": "true", "mc-panel.kind": "server"},
        put_archive=lambda path, data: captured.update(path=path, data=data))
    m = Manager()
    m._client = SimpleNamespace(containers=SimpleNamespace(get=lambda n: container))
    return m, captured


def test_upload_builds_owned_tar_and_validates(monkeypatch):
    import io as _io
    import tarfile
    from app.dockerops import PanelError

    m, captured = _manager_with_server(monkeypatch)
    jar = b"PK\x03\x04" + b"0" * 100
    m.upload_file("survie", "plugins", "Mon Plugin-1.2.jar", jar)
    assert captured["path"] == "/data"
    with tarfile.open(fileobj=_io.BytesIO(captured["data"])) as tar:
        members = {t.name: t for t in tar.getmembers()}
        assert set(members) == {"plugins", "plugins/Mon Plugin-1.2.jar"}
        assert members["plugins/Mon Plugin-1.2.jar"].uid == 1000 and members["plugins/Mon Plugin-1.2.jar"].size == len(jar)
    for bad_name in ("../evil.jar", "a/b.jar", "notes.txt", ".hidden.jar", "x.jar.exe"):
        with pytest.raises(PanelError) as e:
            m.upload_file("survie", "plugins", bad_name, jar)
        assert e.value.status == 400
    with pytest.raises(PanelError):
        m.upload_file("survie", "plugins", "fake.jar", b"MZ not a zip")
    with pytest.raises(PanelError):
        m.upload_file("survie", "config", "ok.jar", jar)


def test_list_and_delete_files(monkeypatch):
    m, _ = _manager_with_server(monkeypatch)
    calls = []

    def fake_helper(c, entrypoint, command):
        calls.append((entrypoint, command))
        return "123\tZeta.jar\n456\tbeta plugin.jar\nbruit sans tab\n"

    monkeypatch.setattr(m, "_helper", fake_helper)
    assert m.list_files("survie", "mods") == [{"name": "beta plugin.jar", "size": 456}, {"name": "Zeta.jar", "size": 123}]
    m.delete_file("survie", "mods", "Zeta.jar")
    assert calls[-1] == (["rm", "-f", "--"], ["/data/mods/Zeta.jar"])


def test_updater_script_checks_compose_file_itself_and_runs_once(monkeypatch):
    """Le test du fichier compose est dans le script de l'updater (un seul conteneur lancé), avec un message clair."""
    import shlex
    import socket as _socket
    from types import SimpleNamespace
    from docker.errors import NotFound
    from app.dockerops import Manager

    me = SimpleNamespace(attrs={"Image": "sha256:abc", "Mounts": [{"Destination": "/project", "Source": "/root/Serveur-Minecraft"}]})
    runs = []

    class Containers:
        def get(self, name):
            if name == "me":
                return me
            raise NotFound("absent")

        def run(self, **kwargs):
            runs.append(kwargs)

    m = Manager()
    m._client = SimpleNamespace(containers=Containers())
    monkeypatch.setattr(_socket, "gethostname", lambda: "me")
    m.launch_updater({})
    assert len(runs) == 1
    script = runs[0]["command"][-1]
    assert script.startswith("[ -f /root/Serveur-Minecraft/docker-compose.yml ] ||")
    assert "docker compose up -d --build" in script and "exit 2" in script
    assert shlex.split(script)  # le script est correctement échappé


def test_router_spec():
    assert RouterSpec().host_port == 25565
    with pytest.raises(ValidationError):
        RouterSpec(image_tag="x y")


def test_cpu_and_mem():
    stats = {
        "cpu_stats": {"cpu_usage": {"total_usage": 300}, "system_cpu_usage": 2000, "online_cpus": 4},
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        "memory_stats": {"usage": 1000, "limit": 4000, "stats": {"inactive_file": 200}},
    }
    assert compute_cpu(stats) == 80.0
    assert compute_mem(stats) == (800, 4000)
    assert compute_cpu({}) == 0.0


def test_ping_against_fake_server():
    payload = json.dumps({"version": {"name": "1.21"}, "players": {"online": 3, "max": 20}}).encode()
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        conn.settimeout(3)
        _recv_exact(conn, _read_varint(conn))   # handshake
        _recv_exact(conn, 2)                    # status request
        body = b"\x00" + _varint(len(payload)) + payload
        conn.sendall(_varint(len(body)) + body)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    info = ping("127.0.0.1", port)
    assert info["players"]["online"] == 3 and info["version"]["name"] == "1.21"
    srv.close()
