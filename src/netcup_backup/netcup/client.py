from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import Auth, BearerAuth
from .errors import NetcupBusy, NetcupError

log = logging.getLogger(__name__)

API_BASE = "https://www.servercontrolpanel.de/scp-core/api/v1"


class ScpClient:
    def __init__(self, auth: Auth, *, base_url: str = API_BASE) -> None:
        self._auth = auth
        self._client = httpx.Client(
            base_url=base_url,
            auth=BearerAuth(auth),
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(30.0, read=120.0),
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, *, json_body: dict | None = None) -> Any:
        return self._request("POST", path, json_body=json_body)

    def patch(
        self,
        path: str,
        body: dict,
        *,
        content_type: str = "application/merge-patch+json",
    ) -> Any:
        return self._request("PATCH", path, json_body=body, content_type=content_type)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, NetcupBusy)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
        content_type: str | None = None,
    ) -> Any:
        headers: dict[str, str] = {}
        if json_body is not None:
            headers["Content-Type"] = content_type or "application/json"
        resp = self._client.request(method, path, json=json_body, headers=headers)
        if resp.status_code in (409, 503):
            raise NetcupBusy(resp.status_code, resp.text[:200])
        if resp.status_code >= 400:
            raise NetcupError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text
