from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


@dataclass
class HealthState:
    last_snapshot: str | None = None
    last_backup_ok: bool | None = None
    last_prune_ok: bool | None = None
    deployed: bool = False
    started_at: float = 0.0

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "deployed": self.deployed,
            "last_snapshot": self.last_snapshot,
            "last_backup_ok": self.last_backup_ok,
            "last_prune_ok": self.last_prune_ok,
        }


@dataclass(frozen=True)
class Listener:
    host: str
    port: int


def build_server(state: HealthState, listener: Listener) -> ThreadingHTTPServer:
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

    return ThreadingHTTPServer((listener.host, listener.port), Handler)


def serve_forever(server: ThreadingHTTPServer) -> None:
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
