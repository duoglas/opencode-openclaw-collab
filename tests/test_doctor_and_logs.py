import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

from ocbridge.api import make_server
from ocbridge.store import Store


class DoctorAndLogsTest(unittest.TestCase):
    def test_doctor_reports_db_and_version(self):
        with tempfile.TemporaryDirectory() as td:
            db = f"{td}/bridge.db"
            logs_dir = Path(td) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = logs_dir / "ocbridge.log"
            log_file.write_text("line1\nline2\n", encoding="utf-8")

            store = Store(db)
            store.add_message(
                direction="out",
                subject="oc.task.event.demo",
                payload={"schema": "oc.task.event.v1", "task_id": "t-1", "ts": time.time()},
            )

            httpd = make_server(
                db_path=db,
                host="127.0.0.1",
                port=0,
                mode="auto",
                node_id="node-a",
                nats_url="nats://127.0.0.1:4222",
            )
            httpd.nats_connected = True
            httpd.subscriptions = ["openclaw.dispatch.v1", "oc.chat.to.node-a"]
            httpd.last_error = ""
            httpd.version = "0.0.test"
            httpd.logs_path = str(log_file)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            time.sleep(0.05)
            port = httpd.server_address[1]

            with urlopen(f"http://127.0.0.1:{port}/doctor", timeout=3) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            self.assertTrue(body.get("ok"))
            self.assertTrue(body.get("nats", {}).get("connected"))
            self.assertIn("openclaw.dispatch.v1", body.get("nats", {}).get("subscriptions", []))
            self.assertTrue(body.get("db", {}).get("writable"))
            self.assertEqual(body.get("version"), "0.0.test")

            with urlopen(f"http://127.0.0.1:{port}/logs?lines=1", timeout=3) as resp:
                logs = json.loads(resp.read().decode("utf-8"))

            self.assertTrue(logs.get("ok"))
            self.assertEqual(len(logs.get("lines", [])), 1)
            self.assertEqual(logs.get("lines", [""])[0], "line2")

            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
