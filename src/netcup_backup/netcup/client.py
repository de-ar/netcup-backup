from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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

POLL_INTERVAL_S = 5
POLL_MAX_ATTEMPTS = 240
TASK_TERMINAL_STATES = frozenset(
    {
        "done",
        "success",
        "succeeded",
        "failed",
        "error",
        "cancelled",
        "canceled",
    }
)


@dataclass(frozen=True)
class ApiRequest:
    method: str
    path: str
    body: dict | None = None
    content_type: str = "application/json"


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
        return self._request(ApiRequest(method="GET", path=path))

    def post(self, path: str, body: dict | None = None) -> Any:
        return self._request(ApiRequest(method="POST", path=path, body=body))

    def patch(self, path: str, body: dict) -> Any:
        return self._request(
            ApiRequest(
                method="PATCH",
                path=path,
                body=body,
                content_type="application/merge-patch+json",
            )
        )

    def delete(self, path: str) -> Any:
        return self._request(ApiRequest(method="DELETE", path=path))

    def wait_for_task(self, task_id: str) -> dict:
        path = f"/tasks/{task_id}"
        for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
            result = self.get(path)
            status = (result or {}).get("status") or (result or {}).get("state") or ""
            if status.lower() in TASK_TERMINAL_STATES:
                return result
            if attempt % 12 == 0:
                log.debug("task %s still %s (attempt %d)", task_id, status or "?", attempt)
            time.sleep(POLL_INTERVAL_S)
        raise TimeoutError(f"task {task_id} did not finish after {POLL_MAX_ATTEMPTS} polls")

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, NetcupBusy)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, req: ApiRequest) -> Any:
        headers: dict[str, str] = {}
        if req.body is not None:
            headers["Content-Type"] = req.content_type
        resp = self._client.request(req.method, req.path, json=req.body, headers=headers)
        if resp.status_code in (409, 503):
            raise NetcupBusy(resp.status_code, resp.text[:200])
        if resp.status_code >= 400:
            raise NetcupError(f"{req.method} {req.path} -> {resp.status_code}: {resp.text[:300]}")
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text
