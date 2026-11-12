import os
import time
from types import SimpleNamespace

import pytest

from app.backups import Backups
from app.dockerops import PanelError


class FakeManager:
    """Manager minimal : un serveur « survie » dont on enregistre les commandes RCON."""

    def __init__(self, status="running"):
        self.commands = []
        self.container = SimpleNamespace(
            id="abc", status=status, attrs={"Image": "sha256:img"},
            stopped=False, started=False)
        self.container.stop = lambda timeout=None: setattr(self.container, "stopped", True)
        self.container.start = lambda: setattr(self.container, "started", True)

    def _get(self, name):
        if name != "survie":
            raise PanelError(404, "Serveur introuvable")
        return self.container

    def command(self, name, cmd):
        self.commands.append(cmd)
        return "ok"


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    fm = FakeManager()
    b = Backups(fm, root=tmp_path)
    runs = []
    monkeypatch.setattr(b, "_run", lambda container, script, *args: runs.append((script, args)))
    monkeypatch.setattr(b, "_backup_mount", lambda: object())
    return fm, b, runs


def _make(tmp_path, name, ts, reason="manuelle", size=10):
    d = tmp_path / "survie"
    d.mkdir(exist_ok=True)
    f = d / f"survie-{ts}-{reason}.tar.gz"
    f.write_bytes(b"x" * size)
    return f


def test_create_freezes_world_then_unfreezes(setup):
    fm, b, runs = setup
    name = b._create_sync("survie", "manuelle")
    assert fm.commands == ["save-off", "save-all flush", "save-on"]
    script, args = runs[0]
    assert args == ("survie", name) and "--exclude=./logs" in script and "tar czf" in script
    assert name.startswith("survie-") and name.endswith("-manuelle.tar.gz")


def test_create_always_unfreezes_even_on_failure(setup, monkeypatch):
    fm, b, _ = setup

    def boom(*a):
        raise PanelError(500, "tar a échoué")

    monkeypatch.setattr(b, "_run", boom)
    with pytest.raises(PanelError):
        b._create_sync("survie", "manuelle")
    assert fm.commands[-1] == "save-on"


def test_create_stopped_server_skips_rcon(setup):
    fm, b, runs = setup
    fm.container.status = "exited"
    b._create_sync("survie", "avant-modif")
    assert fm.commands == [] and len(runs) == 1


def test_list_download_delete_and_traversal(setup, tmp_path):
    _, b, _ = setup
    old = _make(tmp_path, "survie", "20260101-100000")
    new = _make(tmp_path, "survie", "20260202-100000", "avant-modif", size=99)
    os.utime(old, (1, 1))
    os.utime(new, (time.time(), time.time()))
    (tmp_path / "survie" / "notes.txt").write_text("ignoré")
    listed = b.list("survie")
    assert [x["file"] for x in listed] == [new.name, old.name]
    assert listed[0]["reason"] == "avant-modif" and listed[0]["size"] == 99
    assert b.path("survie", new.name) == new
    for bad in ("../../etc/passwd", "autre-20260101-100000-manuelle.tar.gz", "survie-1-2-manuelle.tar.gz", "notes.txt"):
        with pytest.raises(PanelError):
            b.path("survie", bad)
    b.delete("survie", old.name)
    assert not old.exists()


def test_restore_backs_up_current_state_then_validates_before_wiping(setup, tmp_path):
    fm, b, runs = setup
    target = _make(tmp_path, "survie", "20260101-100000")
    b._restore_sync("survie", target.name)
    assert fm.container.stopped and fm.container.started          # arrêté puis redémarré
    assert "avant-restauration" in runs[0][1][1]                  # 1) sauvegarde de l'état actuel
    script, args = runs[1]                                        # 2) restauration
    assert args == ("survie", target.name)
    assert script.index("tar tzf") < script.index("rm -rf") < script.index("tar xzf")   # test avant effacement


def test_only_one_job_at_a_time(setup, monkeypatch):
    _, b, _ = setup
    import threading
    gate = threading.Event()
    monkeypatch.setattr(b, "_create_sync", lambda n, r: gate.wait(2))
    b.start_create("survie")
    with pytest.raises(PanelError) as e:
        b.start_create("survie")
    assert e.value.status == 409
    gate.set()
    for _ in range(50):
        if b.jobs["survie"]["state"] != "running":
            break
        time.sleep(0.05)
    assert b.jobs["survie"]["state"] == "done"


def test_unknown_reason_and_unknown_server(setup):
    _, b, _ = setup
    with pytest.raises(PanelError):
        b.start_create("survie", "nimporte")
    with pytest.raises(PanelError) as e:
        b.status("inconnu")
    assert e.value.status == 404
