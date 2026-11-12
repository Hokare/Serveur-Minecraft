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
