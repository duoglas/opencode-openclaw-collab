from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .store import Store
from .queue import get_task_payload, list_pending, mark_task


class Handler(BaseHTTPRequestHandler):
    server_version = "ocbridge-api/0.1"

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
            self._send(
                200,
                {
                    "ok": True,
                    "db": getattr(self.server, "db_path", ""),
                    "mode": getattr(self.server, "mode", "auto"),
                    "node": getattr(self.server, "node_id", ""),
                    "nats": getattr(self.server, "nats_url", ""),
                },
            )
            return

        if u.path == "/inbox":
            qs = parse_qs(u.query or "")
            limit = int((qs.get("limit") or ["20"])[0])
            task_id = (qs.get("task_id") or [""])[0]
            store: Store = getattr(self.server, "store")
            rows = store.recent(limit=limit, task_id=task_id)
            self._send(200, rows)
            return

        if u.path == "/pending":
            qs = parse_qs(u.query or "")
            limit = int((qs.get("limit") or ["20"])[0])
            store: Store = getattr(self.server, "store")
            rows = list_pending(store, limit=limit)
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
            store.add_message(
                direction="out",
                subject="ocbridge.api.publish",
                payload={
                    "schema": "ocbridge.api.publish.v0",
                    "ts": time.time(),
                    **body,
                },
            )
            self._send(200, {"ok": True, "note": "publish is stubbed in v0"})
            return

        if u.path == "/mode":
            mode = str(body.get("mode") or "").strip().lower()
            if mode not in ("auto", "manual"):
                self._send(400, {"error": "mode must be auto|manual"})
                return
            # set on server instance (shared in-process)
            setattr(self.server, "mode", mode)
            self._send(200, {"ok": True, "mode": mode})
            return

        if u.path == "/claim":
            task_id = str(body.get("task_id") or "").strip()
            if not task_id:
                self._send(400, {"error": "task_id required"})
                return
            store: Store = getattr(self.server, "store")
            n = mark_task(store, task_id, "claimed")
            self._send(200, {"ok": True, "updated": n})
            return

        if u.path == "/run":
            task_id = str(body.get("task_id") or "").strip()
            if not task_id:
                self._send(400, {"error": "task_id required"})
                return
            store: Store = getattr(self.server, "store")
            # ensure it exists
            payload = get_task_payload(store, task_id)
            if not payload:
                self._send(404, {"error": "task not found"})
                return
            # Mark status and enqueue to in-process executor queue.
            mark_task(store, task_id, "ready")
            q = getattr(self.server, "exec_queue", None)
            if q is not None:
                try:
                    q.put_nowait(task_id)
                except Exception:
                    pass
            self._send(200, {"ok": True, "task_id": task_id, "status": "ready"})
            return

        self._send(404, {"error": "not found"})


def make_server(
    db_path: str,
    host: str = "127.0.0.1",
    port: int = 7341,
    *,
    mode: str = "auto",
    node_id: str = "",
    nats_url: str = "",
    exec_queue=None,
) -> HTTPServer:
    store = Store(db_path)
    httpd = HTTPServer((host, port), Handler)
    httpd.store = store
    httpd.db_path = db_path
    httpd.mode = mode
    httpd.node_id = node_id
    httpd.nats_url = nats_url
    httpd.exec_queue = exec_queue
    return httpd


def run_server(
    db_path: str,
    host: str = "127.0.0.1",
    port: int = 7341,
    *,
    mode: str = "auto",
    node_id: str = "",
    nats_url: str = "",
) -> None:
    httpd = make_server(db_path, host, port, mode=mode, node_id=node_id, nats_url=nats_url)
    httpd.serve_forever()


if __name__ == "__main__":
    db = os.getenv("OCBRIDGE_DB", os.path.expanduser("~/.local/share/ocbridge/bridge.db"))
    host = os.getenv("OCBRIDGE_API_HOST", "127.0.0.1")
    port = int(os.getenv("OCBRIDGE_API_PORT", "7341"))
    mode = os.getenv("OCBRIDGE_MODE", "auto")
    node = os.getenv("NODE_ID", "")
    nats = os.getenv("NATS_URL", "")
    run_server(db, host=host, port=port, mode=mode, node_id=node, nats_url=nats)
