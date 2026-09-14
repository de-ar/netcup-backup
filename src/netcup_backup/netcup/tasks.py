from __future__ import annotations

import logging
import time

from .client import ScpClient

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 5
DEFAULT_MAX_ATTEMPTS = 240


def wait_for_task(
    client: ScpClient,
    task_id: str,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    path = f"/tasks/{task_id}"
    terminal = {"done", "success", "succeeded", "failed", "error", "cancelled", "canceled"}
    for attempt in range(1, max_attempts + 1):
        result = client.get(path)
        status = (result or {}).get("status") or (result or {}).get("state") or ""
        status_l = status.lower()
        if status_l in terminal:
            return result
        if attempt % 12 == 0:
            log.debug("task %s still %s (attempt %d)", task_id, status or "?", attempt)
        time.sleep(interval_s)
    raise TimeoutError(f"task {task_id} did not finish after {max_attempts} polls")
