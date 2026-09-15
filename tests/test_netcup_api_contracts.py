"""Contract tests pinned to real netcup SCP API response/error bodies captured
during manual debugging against a live server (RS 2000 G12, UEFI-boot vServer).
These guard against the client silently breaking if our parsing assumptions
about the API's actual shape (as opposed to its documented/expected shape)
drift.
"""

import httpx
import pytest
import respx

from netcup_backup.netcup.auth import Auth
from netcup_backup.netcup.client import ScpClient
from netcup_backup.netcup.errors import NetcupError
from netcup_backup.netcup.snapshots import Snapshots

SERVER_ID = "932359"

# Captured verbatim from GET /servers (list) on the real account.
REAL_SERVERS_LIST_RESPONSE = [
    {
        "id": 932359,
        "name": "v2202609411537513402",
        "disabled": False,
        "hostname": "v2202609411537513402.luckysrv.de",
        "nickname": "",
        "template": {"id": 1354, "name": "RS 2000 G12"},
    }
]

# Captured verbatim from GET /servers/{id}.
REAL_SERVER_DETAIL_RESPONSE = {
    "id": 932359,
    "name": "v2202609411537513402",
    "disabled": False,
    "hostname": "v2202609411537513402.luckysrv.de",
    "nickname": "",
    "template": {"id": 1354, "name": "RS 2000 G12"},
    "architecture": "AMD64",
    "disksAvailableSpaceInMiB": 7864320,
    "gpuDriverAvailable": False,
    "ipv4Addresses": [
        {
            "broadcast": "159.195.207.255",
            "gateway": "159.195.204.1",
            "id": 283725,
            "ip": "159.195.207.68",
            "netmask": "255.255.252.0",
        }
    ],
    "ipv6Addresses": [
        {
            "gateway": "fe80::1",
            "id": 1222140,
            "networkPrefix": "2a0a:4cc0:c2:bc95::",
            "networkPrefixLength": 64,
        }
    ],
    "maxCpuCount": 8,
    "rescueSystemActive": False,
    "serverLiveInfo": {
        "autostart": True,
        "bootorder": ["HDD", "CDROM", "NETWORK"],
        "cloudinitAttached": False,
        "configChanged": False,
        "coresPerSocket": 1,
        "cpuCount": 8,
        "cpuMaxCount": 8,
        "currentServerMemoryInMiB": 16384,
        "disks": [
            {"allocationInMiB": 10465, "capacityInMiB": 524288, "dev": "vda", "driver": "virtio"}
        ],
        "state": "RUNNING",
        "template": "RS 2000 G12",
        "uefi": True,
        "uptimeInSeconds": 479641,
    },
    "site": {"city": "Nuremberg", "id": 1},
    "snapshotAllowed": True,
    "snapshotCount": 0,
}

# Captured verbatim from GET /servers/{id}/disks.
REAL_DISKS_RESPONSE = [
    {
        "allocationInMiB": 10465,
        "capacityInMiB": 524288,
        "name": "vda",
        "path": None,
        "storageDriver": "VIRTIO",
    }
]

# Captured verbatim from GET /servers/{id}/snapshots after a successful create.
REAL_SNAPSHOT_LIST_RESPONSE = [
    {
        "creationTime": "2026-09-15T11:20:30Z",
        "description": "",
        "disks": ["vda"],
        "exported": False,
        "exportedSizeInKiB": None,
        "name": "probe-disk",
        "online": False,
        "state": "SHUTOFF",
        "uuid": "519e6940-82ad-48f6-8a1a-a052b73a8c76",
    }
]

# Captured verbatim error bodies hit while debugging.
ERROR_WRONG_SERVER_ID = (400, {"code": "error.path.invaliddatatype", "message": (
    "One path parameter has an invalid data type (f.e. a string instead of an integer)."
)})
ERROR_MISSING_DISK = (422, {
    "code": None,
    "message": "Validation failed",
    "errors": [{"field": None, "message": "Disk name cannot be blank"}],
})
ERROR_NOT_FOUND = (404, {"code": "error.notfound", "message": "Resource not found"})
ERROR_METHOD_NOT_ALLOWED = (405, {"code": "error.method.not.allowed", "message": "Method not allowed"})


@pytest.fixture(autouse=True)
def lax_respx():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def client(lax_respx):
    lax_respx.post("/realms/scp/protocol/openid-connect/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    )
    return ScpClient(Auth("refresh-abc"))


def test_get_servers_list_matches_real_shape(lax_respx, client):
    lax_respx.get("/scp-core/api/v1/servers").mock(
        return_value=httpx.Response(200, json=REAL_SERVERS_LIST_RESPONSE)
    )
    result = client.get("/servers")
    assert result[0]["id"] == 932359
    assert result[0]["name"] == "v2202609411537513402"


def test_get_server_detail_matches_real_shape(lax_respx, client):
    lax_respx.get(f"/scp-core/api/v1/servers/{SERVER_ID}").mock(
        return_value=httpx.Response(200, json=REAL_SERVER_DETAIL_RESPONSE)
    )
    result = client.get(f"/servers/{SERVER_ID}")
    assert result["serverLiveInfo"]["uefi"] is True
    assert result["serverLiveInfo"]["disks"][0]["dev"] == "vda"
    assert result["snapshotAllowed"] is True


def test_snapshots_default_disk_uses_real_disks_response(lax_respx, client):
    lax_respx.get(f"/scp-core/api/v1/servers/{SERVER_ID}/disks").mock(
        return_value=httpx.Response(200, json=REAL_DISKS_RESPONSE)
    )
    snaps = Snapshots(client, SERVER_ID)
    assert snaps._default_disk() == "vda"


def test_snapshots_create_round_trips_disk_against_real_api_shapes(lax_respx, client):
    lax_respx.get(f"/scp-core/api/v1/servers/{SERVER_ID}/disks").mock(
        return_value=httpx.Response(200, json=REAL_DISKS_RESPONSE)
    )
    create_route = lax_respx.post(f"/scp-core/api/v1/servers/{SERVER_ID}/snapshots").mock(
        return_value=httpx.Response(200, json={"taskId": "t-1"})
    )
    snaps = Snapshots(client, SERVER_ID)
    snaps.create("probe-disk")
    sent_body = create_route.calls.last.request.content
    import json

    assert json.loads(sent_body)["disks"] == ["vda"]


def test_snapshots_list_parses_real_snapshot_response(lax_respx, client):
    lax_respx.get(f"/scp-core/api/v1/servers/{SERVER_ID}/snapshots").mock(
        return_value=httpx.Response(200, json=REAL_SNAPSHOT_LIST_RESPONSE)
    )
    snaps = Snapshots(client, SERVER_ID)
    result = snaps.list()
    assert len(result) == 1
    assert result[0].name == "probe-disk"
    assert result[0].creation_time.isoformat() == "2026-09-15T11:20:30+00:00"


@pytest.mark.parametrize(
    "status_code, body",
    [ERROR_WRONG_SERVER_ID, ERROR_MISSING_DISK, ERROR_NOT_FOUND, ERROR_METHOD_NOT_ALLOWED],
)
def test_client_surfaces_real_error_bodies(lax_respx, client, status_code, body):
    lax_respx.get(f"/scp-core/api/v1/servers/{SERVER_ID}/snapshots").mock(
        return_value=httpx.Response(status_code, json=body)
    )
    with pytest.raises(NetcupError) as exc_info:
        client.get(f"/servers/{SERVER_ID}/snapshots")
    assert str(status_code) in str(exc_info.value)
    assert body["message"] in str(exc_info.value)


def test_client_does_not_retry_on_client_errors(lax_respx, client):
    # 400/404/405/422 are caller mistakes, not transient busy states (409/503) --
    # they must not trigger tenacity retries, unlike test_client_retries_on_busy
    # in test_netcup_auth.py.
    route = lax_respx.get(f"/scp-core/api/v1/servers/{SERVER_ID}/snapshots").mock(
        return_value=httpx.Response(ERROR_MISSING_DISK[0], json=ERROR_MISSING_DISK[1])
    )
    with pytest.raises(NetcupError):
        client.get(f"/servers/{SERVER_ID}/snapshots")
    assert route.call_count == 1
