import json
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen

from ocbridge.api import make_server
from ocbridge.queue import enqueue_task, claim_task, list_pending
from ocbridge.store import Store


class SessionClaimLockTest(unittest.TestCase):
    def test_claim_is_atomic_pending_to_claimed(self):
        with tempfile.TemporaryDirectory() as td:
            db = f"{td}/bridge.db"
            store = Store(db)
            task = {
                "schema": "oc.task.dispatch.v1",
                "task_id": "TASK-CLAIM-001",
                "prompt": "ping",
                "status": "pending",
            }
            enqueue_task(store, task, subject="openclaw.dispatch.v1")

            updated1 = claim_task(store, "TASK-CLAIM-001", "sid-a")
            updated2 = claim_task(store, "TASK-CLAIM-001", "sid-b")

            self.assertEqual(updated1, 1)
            self.assertEqual(updated2, 0)
            rows = list_pending(store, limit=10)
            row = next(r for r in rows if r.get("task_id") == "TASK-CLAIM-001")
            self.assertEqual(row.get("status"), "claimed")
            self.assertEqual(row.get("claimed_by"), "sid-a")

    def test_pending_shows_claimed_by(self):
        with tempfile.TemporaryDirectory() as td:
            db = f"{td}/bridge.db"
            store = Store(db)
            enqueue_task(
                store,
                {
                    "schema": "oc.task.dispatch.v1",
                    "task_id": "TASK-CLAIM-002",
                    "prompt": "ping",
                    "status": "pending",
                },
                subject="openclaw.dispatch.v1",
            )
            claim_task(store, "TASK-CLAIM-002", "sid-x")
            rows = list_pending(store, limit=10)
            row = next(r for r in rows if r.get("task_id") == "TASK-CLAIM-002")
            self.assertEqual(row.get("claimed_by"), "sid-x")
            self.assertEqual(row.get("status"), "claimed")

    def test_whoami_returns_session_id_from_header(self):
        with tempfile.TemporaryDirectory() as td:
            db = f"{td}/bridge.db"
            httpd = make_server(db_path=db, host="127.0.0.1", port=0, mode="manual", node_id="node-a")
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            time.sleep(0.05)
            port = httpd.server_address[1]

            req = Request(f"http://127.0.0.1:{port}/whoami")
            req.add_header("X-Session-Id", "sid-header-001")
            with urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body.get("session_id"), "sid-header-001")

            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
