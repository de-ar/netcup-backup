from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


class HealthState:
    def __init__(self) -> None:
        self.last_snapshot: str | None = None
        self.last_backup_ok: bool | None = None
        self.last_prune_ok: bool | None = None
        self.deployed: bool = False
        self.started_at: float = 0.0

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "deployed": self.deployed,
            "last_snapshot": self.last_snapshot,
            "last_backup_ok": self.last_backup_ok,
            "last_prune_ok": self.last_prune_ok,
        }


def build_server(state: HealthState, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = json.dumps({"status": "ok", **state.as_dict()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"netcup-backup")
            else:
                self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            log.debug("http " + format, *args)

    return ThreadingHTTPServer((host, port), Handler)


def serve_forever(server: ThreadingHTTPServer) -> None:
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
