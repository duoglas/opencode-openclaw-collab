from __future__ import annotations

import sqlite3
from typing import Any

from .store import Store


def enqueue_task(store: Store, task_payload: dict[str, Any], *, subject: str = "openclaw.dispatch.v1") -> None:
    # Mark with a status so the TUI can list pending tasks.
    payload = dict(task_payload)
    payload.setdefault("status", "pending")
    store.add_message(direction="in", subject=subject, payload=payload)


def list_pending(store: Store, limit: int = 20) -> list[dict[str, Any]]:
    # Direct SQL query to filter pending quickly.
    cur = store._conn.execute(
        "SELECT ts, direction, subject, schema, task_id, payload_json, status FROM messages WHERE status='pending' ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    rows = []
    for ts, direction, subject, schema, task_id, payload_json, status in cur.fetchall():
        rows.append(
            {
                "ts": ts,
                "direction": direction,
                "subject": subject,
                "schema": schema,
                "task_id": task_id,
                "status": status,
                "payload": __import__("json").loads(payload_json),
            }
        )
    return rows


def mark_task(store: Store, task_id: str, status: str) -> int:
    # Update by task_id for pending messages.
    cur = store._conn.execute(
        "UPDATE messages SET status=? WHERE task_id=?",
        (status, task_id),
    )
    store._conn.commit()
    return cur.rowcount
