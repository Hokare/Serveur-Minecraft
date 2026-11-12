import io
import tarfile
from types import SimpleNamespace

import pytest

from app.dockerops import PanelError
from app.files import MAX_EDIT, FileManager


def tar_of(name, data):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeContainer:
    def __init__(self, files=None):
        self.files = files or {}
        self.put = []

    def get_archive(self, path):
        from docker.errors import NotFound
        rel = path.removeprefix("/data/")
        if rel not in self.files:
            raise NotFound("absent")
        data = self.files[rel]
        mode = (1 << 31) if data is None else 0o644
        raw = tar_of(rel.rsplit("/", 1)[-1], data or b"")
        return iter([raw[:512], raw[512:]]), {"size": len(data or b""), "mode": mode}

    def put_archive(self, path, data):
        self.put.append((path, data))


@pytest.fixture()
def fm():
    container = FakeContainer({"server.properties": b"motd=Salut\n", "world": None, "blob.bin": b"\x00\x01\x02",
                               "big.txt": b"a" * (MAX_EDIT + 10), "latin.txt": "caf\xe9".encode("latin-1")})
    helper_calls = []
    manager = SimpleNamespace(_get=lambda n: container)
    manager._helper = lambda c, entrypoint, command: helper_calls.append((entrypoint, command)) or manager.helper_out
    manager.helper_out = ""
    f = FileManager(manager)
    f.container, f.calls, f.manager = container, helper_calls, manager
    return f


@pytest.mark.parametrize("bad", ["../etc", "a/../../b", "x\x00y", "a" * 2000])
def test_clean_rejects_traversal(fm, bad):
    with pytest.raises(PanelError):
        fm.clean(bad)


def test_clean_normalises(fm):
    assert fm.clean("/plugins//./Essentials/") == "plugins/Essentials"
    assert fm.clean("") == "" and fm.clean(None) == ""
    for bad in ("", ".", "..", "a/b", "x\x00"):
        with pytest.raises(PanelError):
            fm.check_name(bad)


def test_list_parses_and_sorts_dirs_first(fm):
    fm.manager.helper_out = "f\t12\tzeta.txt\nd\t0\tplugins\nf\t5\tAlpha.yml\nd\t0\tWorld\nbruit\n"
    names = [(e["name"], e["dir"]) for e in fm.list("survie", "")]
    assert names == [("plugins", True), ("World", True), ("Alpha.yml", False), ("zeta.txt", False)]
    fm.manager.helper_out = "NODIR\n"
    with pytest.raises(PanelError) as e:
        fm.list("survie", "nope")
    assert e.value.status == 404


def test_read_text_binary_big_dir_missing(fm):
    assert fm.read("survie", "server.properties") == {"content": "motd=Salut\n", "size": 11}
    for path, status in (("blob.bin", 415), ("big.txt", 413), ("latin.txt", 415), ("world", 400), ("absent.txt", 404), ("", 400)):
        with pytest.raises(PanelError) as e:
            fm.read("survie", path)
        assert e.value.status == status, path


def test_write_builds_owned_tar_in_parent(fm):
    fm.write("survie", "plugins/Essentials/config.yml", "a: 1\n")
    path, data = fm.container.put[0]
    assert path == "/data/plugins/Essentials"
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member = tar.getmembers()[0]
        assert member.name == "config.yml" and member.uid == 1000 and tar.extractfile(member).read() == b"a: 1\n"
    with pytest.raises(PanelError):
        fm.write("survie", "x.txt", "a" * (MAX_EDIT + 1))


def test_create_refuses_existing(fm):
    fm.manager.helper_out = "yes\n"
    with pytest.raises(PanelError) as e:
        fm.create("survie", "notes.txt", "file")
    assert e.value.status == 409
    fm.manager.helper_out = "no\n"
    fm.create("survie", "dossier", "dir")
    fm.create("survie", "plugins/notes.txt", "file")
    assert [p for p, _ in fm.container.put] == ["/data", "/data/plugins"]


def test_delete_and_rename_rules(fm):
    with pytest.raises(PanelError):
        fm.delete("survie", "")
    with pytest.raises(PanelError):
        fm.delete("survie", "../..")
    fm.delete("survie", "plugins/old.jar")
    assert fm.calls[-1] == (["rm", "-rf", "--"], ["/data/plugins/old.jar"])
    fm.manager.helper_out = "OK\n"
    fm.rename("survie", "plugins/a.yml", "b.yml")
    assert fm.calls[-1][1] == ["/data/plugins/a.yml", "/data/plugins/b.yml"]
    fm.manager.helper_out = "EXISTS\n"
    with pytest.raises(PanelError) as e:
        fm.rename("survie", "a.yml", "b.yml")
    assert e.value.status == 409
    with pytest.raises(PanelError):
        fm.rename("survie", "a.yml", "../evil")


def test_upload_and_download(fm):
    fm.manager.helper_out = "no\n"
    fm.upload("survie", "config", "data.json", b"{}")
    assert fm.container.put[-1][0] == "/data/config"
    fm.manager.helper_out = "yes\n"
    with pytest.raises(PanelError) as e:
        fm.upload("survie", "config", "data.json", b"{}")
    assert e.value.status == 409
    with pytest.raises(PanelError):
        fm.upload("survie", "config", "../x", b"{}")
    assert fm.download("survie", "blob.bin") == (b"\x00\x01\x02", "blob.bin")
