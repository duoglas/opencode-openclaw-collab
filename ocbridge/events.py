from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any

from .store import Store


def list_events(store: Store, *, since_ts: float = 0.0, limit: int = 200) -> list[dict[str, Any]]:
    """Return recent task events from the inbox DB.

    We store TaskEvent publishes as direction='out' with schema='oc.task.event.v1'.
    This enables long-poll watchers without requiring NATS from the TUI.
    """
    cur = store._conn.execute(
        "SELECT ts, direction, subject, schema, task_id, payload_json, status, claimed_by "
        "FROM messages WHERE schema='oc.task.event.v1' AND ts>=? ORDER BY ts ASC LIMIT ?",
        (float(since_ts or 0.0), int(limit)),
    )
    rows: list[dict[str, Any]] = []
    for ts, direction, subject, schema, task_id, payload_json, status, claimed_by in cur.fetchall():
        try:
            payload = json.loads(payload_json)
        except Exception:
            payload = {"raw": payload_json}
        rows.append(
            {
                "ts": ts,
                "direction": direction,
                "subject": subject,
                "schema": schema,
                "task_id": task_id,
                "status": status,
                "claimed_by": claimed_by,
                "payload": payload,
            }
        )
    return rows


def now_ts() -> float:
    return time.time()
