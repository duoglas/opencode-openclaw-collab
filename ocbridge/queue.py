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
        "SELECT ts, direction, subject, schema, task_id, payload_json, status, claimed_by FROM messages WHERE status='pending' ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    rows = []
    for ts, direction, subject, schema, task_id, payload_json, status, claimed_by in cur.fetchall():
        rows.append(
            {
                "ts": ts,
                "direction": direction,
                "subject": subject,
                "schema": schema,
                "task_id": task_id,
                "status": status,
                "claimed_by": claimed_by,
                "payload": __import__("json").loads(payload_json),
            }
        )
    return rows


def mark_task(store: Store, task_id: str, status: str, *, claimed_by: str | None = None) -> int:
    # Generic update by task_id for messages (latest row wins by SQLite semantics on update of all matching rows).
    if claimed_by is None:
        cur = store._conn.execute(
            "UPDATE messages SET status=? WHERE task_id=?",
            (status, task_id),
        )
    else:
        cur = store._conn.execute(
            "UPDATE messages SET status=?, claimed_by=? WHERE task_id=?",
            (status, claimed_by, task_id),
        )
    store._conn.commit()
    return cur.rowcount


def claim_task(store: Store, task_id: str, session_id: str) -> int:
    """Atomic claim: set status=claimed and claimed_by=session_id only if currently pending."""
    cur = store._conn.execute(
        "UPDATE messages SET status='claimed', claimed_by=? WHERE task_id=? AND status='pending'",
        (session_id, task_id),
    )
    store._conn.commit()
    return cur.rowcount


def get_task_payload(store: Store, task_id: str) -> dict[str, Any] | None:
    cur = store._conn.execute(
        "SELECT payload_json FROM messages WHERE task_id=? ORDER BY ts DESC LIMIT 1",
        (task_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return __import__("json").loads(row[0])


def get_task_meta(store: Store, task_id: str) -> dict[str, Any] | None:
    cur = store._conn.execute(
        "SELECT status, claimed_by FROM messages WHERE task_id=? ORDER BY ts DESC LIMIT 1",
        (task_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"status": row[0] or "", "claimed_by": row[1] or ""}
