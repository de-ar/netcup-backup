from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from .errors import NetcupError

log = logging.getLogger(__name__)

TOKEN_URL = "https://www.servercontrolpanel.de/realms/scp/protocol/openid-connect/token"
REFRESH_SKEW_S = 60


@dataclass
class TokenSet:
    access_token: str
    expires_at: float

    def is_fresh(self) -> bool:
        return time.time() < self.expires_at - REFRESH_SKEW_S


class Auth:
    def __init__(self, refresh_token: str, client: httpx.Client | None = None) -> None:
        self._refresh_token = refresh_token
        self._client = client or httpx.Client(timeout=15.0)
        self._token: TokenSet | None = None

    def access_token(self) -> str:
        if self._token is None or not self._token.is_fresh():
            self._refresh()
        assert self._token is not None
        return self._token.access_token

    def _refresh(self) -> None:
        log.debug("refreshing netcup access token")
        resp = self._client.post(
            TOKEN_URL,
            data={
                "client_id": "scp",
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
        )
        if resp.status_code >= 400:
            raise NetcupError(f"refresh failed: {resp.status_code} {resp.text[:200]}")
        body = resp.json()
        access = body.get("access_token")
        expires_in = int(body.get("expires_in", 300))
        if not access:
            raise NetcupError("refresh response missing access_token")
        self._token = TokenSet(access_token=access, expires_at=time.time() + expires_in)


class BearerAuth(httpx.Auth):
    def __init__(self, auth: Auth) -> None:
        self._auth = auth

    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        token = self._auth.access_token()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request
