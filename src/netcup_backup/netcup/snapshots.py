from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from .client import ScpClient

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    name: str
    creation_time: datetime

    @classmethod
    def from_api(cls, raw: dict) -> Snapshot:
        ts = raw.get("creationTime") or raw.get("creation_time")
        if isinstance(ts, str):
            created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, (int, float)):
            created = datetime.fromtimestamp(ts, tz=UTC)
        else:
            created = datetime.now(UTC)
        return cls(name=raw["name"], creation_time=created)


class Snapshots:
    def __init__(self, client: ScpClient, server_id: str) -> None:
        self._client = client
        self._server = server_id

    def list(self) -> list[Snapshot]:
        path = f"/servers/{self._server}/snapshots"
        raw = self._client.get(path)
        items = raw if isinstance(raw, list) else raw.get("items", [])
        return [Snapshot.from_api(it) for it in items]

    def dryrun(self) -> dict:
        path = f"/servers/{self._server}/snapshots/dryrun"
        return self._client.post(path, body={"online": True})

    def create(self, name: str, *, description: str = "") -> dict:
        path = f"/servers/{self._server}/snapshots"
        body = {"name": name, "online": True}
        if description:
            body["description"] = description
        return self._client.post(path, body=body)

    def delete(self, name: str) -> dict | None:
        path = f"/servers/{self._server}/snapshots/{name}"
        return self._client.delete(path)

    def create_and_wait(self, name: str) -> str:
        result = self.create(name)
        task_id = _extract_task_id(result)
        if task_id:
            log.info("snapshot task %s started for %s", task_id, name)
            final = self._client.wait_for_task(task_id)
            log.info("snapshot task %s -> %s", task_id, final.get("status"))
        return task_id or ""

    def prune_to(self, keep: int) -> int:
        snaps = sorted(self.list(), key=lambda s: s.creation_time, reverse=True)
        surplus = snaps[keep:]
        deleted = 0
        for s in surplus:
            log.info("deleting old snapshot %s (created %s)", s.name, s.creation_time.isoformat())
            self.delete(s.name)
            deleted += 1
        return deleted


def _extract_task_id(body: dict) -> str | None:
    if not isinstance(body, dict):
        return None
    return body.get("taskId") or body.get("task_id") or body.get("id")


def now_snapshot_name(prefix: str = "auto") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}"
