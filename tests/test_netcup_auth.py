import httpx
import pytest
import respx

from netcup_backup.netcup.auth import Auth
from netcup_backup.netcup.client import ScpClient
from netcup_backup.netcup.errors import NetcupError


@pytest.fixture
def refresh_token() -> str:
    return "refresh-abc"


@pytest.fixture(autouse=True)
def lax_respx():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def test_auth_refreshes_and_caches_token(lax_respx, refresh_token):
    route = lax_respx.post("/realms/scp/protocol/openid-connect/token")
    route.return_value = httpx.Response(200, json={"access_token": "access-1", "expires_in": 300})
    auth = Auth(refresh_token)
    assert auth.access_token() == "access-1"
    assert auth.access_token() == "access-1"
    assert route.call_count == 1


def test_auth_force_refresh_on_expiry(lax_respx, refresh_token):
    route = lax_respx.post("/realms/scp/protocol/openid-connect/token")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "access-1", "expires_in": 0}),
        httpx.Response(200, json={"access_token": "access-2", "expires_in": 300}),
    ]
    auth = Auth(refresh_token)
    auth.access_token()
    auth.access_token()
    assert route.call_count == 2


def test_auth_raises_on_bad_refresh(lax_respx, refresh_token):
    route = lax_respx.post("/realms/scp/protocol/openid-connect/token")
    route.return_value = httpx.Response(401, text="bad")
    auth = Auth(refresh_token)
    with pytest.raises(NetcupError):
        auth.access_token()


def test_bearer_auth_attaches_token(lax_respx, refresh_token):
    token_route = lax_respx.post("/realms/scp/protocol/openid-connect/token")
    token_route.return_value = httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    get = lax_respx.get("/scp-core/api/v1/servers")
    get.return_value = httpx.Response(200, json=[])
    auth = Auth(refresh_token)
    client = ScpClient(auth)
    client.get("/servers")
    assert get.calls.last.request.headers["Authorization"] == "Bearer tok"


def test_client_retries_on_busy(lax_respx, refresh_token):
    token_route = lax_respx.post("/realms/scp/protocol/openid-connect/token")
    token_route.return_value = httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    route = lax_respx.get("/scp-core/api/v1/servers")
    route.side_effect = [
        httpx.Response(503, text="locked"),
        httpx.Response(200, json=[]),
    ]
    auth = Auth(refresh_token)
    client = ScpClient(auth)
    result = client.get("/servers")
    assert result == []
    assert route.call_count == 2


def test_client_raises_on_hard_error(lax_respx, refresh_token):
    token_route = lax_respx.post("/realms/scp/protocol/openid-connect/token")
    token_route.return_value = httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    route = lax_respx.get("/scp-core/api/v1/servers")
    route.return_value = httpx.Response(400, text="bad")
    auth = Auth(refresh_token)
    client = ScpClient(auth)
    with pytest.raises(NetcupError):
        client.get("/servers")
