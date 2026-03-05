from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .store import Store
from .queue import get_task_payload, list_pending, mark_task, claim_task, get_task_meta
from .events import list_events


class BridgeHTTPServer(HTTPServer):
    store: Store | None = None
    db_path: str = ""
    mode: str = "auto"
    node_id: str = ""
    nats_url: str = ""
    exec_queue: Any = None
    publish_callback: Callable[[str, bytes, dict[str, Any]], None] | None = None
    chat_from_prefix: str = "oc.chat.from."


def normalize_subject_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return ""
    return p if p.endswith(".") else f"{p}."


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

        if u.path == "/whoami":
            qs = parse_qs(u.query or "")
            session_id = (qs.get("session_id") or [""])[0]
            if not session_id:
                session_id = self.headers.get("X-Session-Id", "")
            self._send(
                200,
                {
                    "node": getattr(self.server, "node_id", ""),
                    "mode": getattr(self.server, "mode", "auto"),
                    "session_id": session_id,
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

        if u.path in ("/events", "/watch"):
            # Long-poll watcher (MVP): query events from the local inbox DB.
            # Query params:
            #   since_ts: float unix ts (inclusive)
            #   timeout_ms: how long to wait for a new event (default 25000)
            #   limit: max events to return
            qs = parse_qs(u.query or "")
            since_ts = float((qs.get("since_ts") or ["0"])[0] or 0)
            timeout_ms = int((qs.get("timeout_ms") or ["25000"])[0] or 25000)
            limit = int((qs.get("limit") or ["200"])[0] or 200)
            deadline = time.time() + max(1, timeout_ms) / 1000.0
            store: Store = getattr(self.server, "store")
            while True:
                rows = list_events(store, since_ts=since_ts, limit=limit)
                if rows:
                    self._send(200, {"ok": True, "events": rows})
                    return
                if time.time() >= deadline:
                    self._send(200, {"ok": True, "events": []})
                    return
                time.sleep(0.25)

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
            text = str(body.get("text") or "").strip()
            if not text:
                self._send(400, {"error": "text required"})
                return

            node_id = str(getattr(self.server, "node_id", "") or "").strip()
            if not node_id:
                self._send(400, {"error": "node_id not configured"})
                return

            payload = {
                "schema": "oc.chat.v1",
                "task_id": str(body.get("task_id") or ""),
                "session_id": str(body.get("session_id") or ""),
                "from_id": f"node:{node_id}",
                "to_id": str(body.get("to_id") or "openclaw"),
                "text": text,
                "ts": time.time(),
            }
            prefix = str(
                getattr(self.server, "chat_from_prefix", "oc.chat.from.") or ""
            )
            subject = f"{normalize_subject_prefix(prefix)}{node_id}"
            publisher = getattr(self.server, "publish_callback", None)
            if publisher is None:
                self._send(503, {"error": "publish callback unavailable"})
                return
            try:
                publisher(
                    subject,
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    payload,
                )
            except Exception as exc:
                self._send(500, {"error": f"publish failed: {exc}"})
                return

            self._send(200, {"ok": True, "subject": subject})
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
            session_id = str(body.get("session_id") or "").strip()
            if not task_id:
                self._send(400, {"error": "task_id required"})
                return
            if not session_id:
                self._send(400, {"error": "session_id required"})
                return
            store: Store = getattr(self.server, "store")
            # atomic: only if pending
            updated = claim_task(store, task_id, session_id)
            meta = get_task_meta(store, task_id) or {}
            self._send(200, {"ok": True, "updated": updated, **meta})
            return

        if u.path == "/run":
            task_id = str(body.get("task_id") or "").strip()
            session_id = str(body.get("session_id") or "").strip()
            if not task_id:
                self._send(400, {"error": "task_id required"})
                return
            store: Store = getattr(self.server, "store")
            # ensure it exists
            payload = get_task_payload(store, task_id)
            if not payload:
                self._send(404, {"error": "task not found"})
                return
            # Only allow the claimer to run (if claimed)
            meta = get_task_meta(store, task_id) or {}
            claimed_by = meta.get("claimed_by") or ""
            if claimed_by and session_id and claimed_by != session_id:
                self._send(403, {"error": "not owner"})
                return
            # Mark status and enqueue to in-process executor queue.
            mark_task(store, task_id, "ready", claimed_by=claimed_by or session_id)
            q = getattr(self.server, "exec_queue", None)
            if q is not None:
                try:
                    q.put_nowait(task_id)
                except Exception:
                    pass
            self._send(200, {"ok": True, "task_id": task_id, "status": "ready", "claimed_by": claimed_by or session_id})
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
    publish_callback=None,
    chat_from_prefix: str = "oc.chat.from.",
) -> HTTPServer:
    store = Store(db_path)
    httpd = BridgeHTTPServer((host, port), Handler)
    httpd.store = store
    httpd.db_path = db_path
    httpd.mode = mode
    httpd.node_id = node_id
    httpd.nats_url = nats_url
    httpd.exec_queue = exec_queue
    httpd.publish_callback = publish_callback
    httpd.chat_from_prefix = chat_from_prefix
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
    httpd = make_server(
        db_path, host, port, mode=mode, node_id=node_id, nats_url=nats_url
    )
    httpd.serve_forever()


if __name__ == "__main__":
    db = os.getenv(
        "OCBRIDGE_DB", os.path.expanduser("~/.local/share/ocbridge/bridge.db")
    )
    host = os.getenv("OCBRIDGE_API_HOST", "127.0.0.1")
    port = int(os.getenv("OCBRIDGE_API_PORT", "7341"))
    mode = os.getenv("OCBRIDGE_MODE", "auto")
    node = os.getenv("OC_NODE_ID", os.getenv("NODE_ID", ""))
    nats = os.getenv("NATS_URL", "")
    run_server(db, host=host, port=port, mode=mode, node_id=node, nats_url=nats)
