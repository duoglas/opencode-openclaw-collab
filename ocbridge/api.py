from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .store import Store


class Handler(BaseHTTPRequestHandler):
    server_version = "ocbridge-api/0.0"

    def _send(self, code: int, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/status":
            self._send(200, {
                "ok": True,
                "db": getattr(self.server, "db_path", ""),
            })
            return

        if u.path == "/inbox":
            qs = parse_qs(u.query or "")
            limit = int((qs.get("limit") or ["20"])[0])
            task_id = (qs.get("task_id") or [""])[0]
            store: Store = getattr(self.server, "store")
            rows = store.recent(limit=limit, task_id=task_id)
            self._send(200, rows)
            return

        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send(400, {"error": "invalid json"})
            return

        if u.path == "/publish":
            # Minimal stub for route-A plugin integration.
            # We currently only persist the outgoing intent for traceability.
            store: Store = getattr(self.server, "store")
            store.add_message(direction="out", subject="ocbridge.api.publish", payload={
                "schema": "ocbridge.api.publish.v0",
                "ts": __import__("time").time(),
                **body,
            })
            self._send(200, {"ok": True, "note": "publish is stubbed in v0"})
            return

        self._send(404, {"error": "not found"})


def run_server(db_path: str, host: str = "127.0.0.1", port: int = 7341):
    store = Store(db_path)
    httpd = HTTPServer((host, port), Handler)
    httpd.store = store
    httpd.db_path = db_path
    httpd.serve_forever()


if __name__ == "__main__":
    db = os.getenv("OCBRIDGE_DB", os.path.expanduser("~/.local/share/ocbridge/bridge.db"))
    host = os.getenv("OCBRIDGE_API_HOST", "127.0.0.1")
    port = int(os.getenv("OCBRIDGE_API_PORT", "7341"))
    run_server(db, host=host, port=port)
