from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts REAL NOT NULL,
              direction TEXT NOT NULL,
              subject TEXT NOT NULL,
              schema TEXT,
              task_id TEXT,
              payload_json TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_task_ts ON messages(task_id, ts);"
        )
        self._conn.commit()

    def add_message(self, *, direction: str, subject: str, payload: dict[str, Any]) -> None:
        ts = float(payload.get("ts") or payload.get("created_at") or time.time())
        schema = str(payload.get("schema", ""))
        task_id = str(payload.get("task_id", ""))
        self._conn.execute(
            "INSERT INTO messages(ts, direction, subject, schema, task_id, payload_json) VALUES(?,?,?,?,?,?)",
            (ts, direction, subject, schema, task_id, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def recent(self, limit: int = 50, task_id: str = "") -> list[dict[str, Any]]:
        if task_id:
            cur = self._conn.execute(
                "SELECT ts, direction, subject, schema, task_id, payload_json FROM messages WHERE task_id=? ORDER BY ts DESC LIMIT ?",
                (task_id, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT ts, direction, subject, schema, task_id, payload_json FROM messages ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
        rows = []
        for ts, direction, subject, schema, task_id, payload_json in cur.fetchall():
            rows.append(
                {
                    "ts": ts,
                    "direction": direction,
                    "subject": subject,
                    "schema": schema,
                    "task_id": task_id,
                    "payload": json.loads(payload_json),
                }
            )
        return rows
