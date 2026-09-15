import pytest

from netcup_backup.netcup.errors import NetcupError
from netcup_backup.netcup.snapshots import Snapshots


class FakeClient:
    def __init__(self, disks=None):
        self._disks = disks if disks is not None else [{"name": "vda"}]
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path, None))
        if path.endswith("/disks"):
            return self._disks
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return {"taskId": "t1"}

    def delete(self, path):
        self.calls.append(("DELETE", path, None))
        return None


def test_create_includes_disk_name_from_api():
    client = FakeClient(disks=[{"name": "vda"}])
    snaps = Snapshots(client, "932359")

    snaps.create("auto-20260915-000000")

    post_calls = [c for c in client.calls if c[0] == "POST"]
    assert len(post_calls) == 1
    _, path, body = post_calls[0]
    assert path == "/servers/932359/snapshots"
    assert body["diskName"] == "vda"
    # UEFI vServers can't do online snapshots (server.snapshot.create.error
    # .online.uefi), so this must always be offline.
    assert body["onlineSnapshot"] is False


def test_default_disk_is_cached_across_calls():
    client = FakeClient(disks=[{"name": "vda"}])
    snaps = Snapshots(client, "932359")

    snaps.create("s1")
    snaps.create("s2")

    disk_lookups = [c for c in client.calls if c[0] == "GET" and c[1].endswith("/disks")]
    assert len(disk_lookups) == 1


def test_default_disk_raises_when_server_has_no_disks():
    client = FakeClient(disks=[])
    snaps = Snapshots(client, "932359")

    with pytest.raises(NetcupError, match="no disks"):
        snaps.create("s1")


def test_dryrun_includes_disk_name():
    client = FakeClient(disks=[{"name": "vda"}])
    snaps = Snapshots(client, "932359")

    snaps.dryrun()

    _, path, body = client.calls[-1]
    assert path == "/servers/932359/snapshots:dryrun"
    assert body["diskName"] == "vda"
