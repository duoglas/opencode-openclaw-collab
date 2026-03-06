import json
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ocbridge.api import make_server


class PublishReliabilityTest(unittest.TestCase):
    def test_publish_success_returns_ok(self):
        with tempfile.TemporaryDirectory() as td:
            db = f"{td}/bridge.db"

            calls = []

            def publisher(subject: str, blob: bytes, payload: dict):
                calls.append((subject, blob, payload))

            httpd = make_server(
                db_path=db,
                host="127.0.0.1",
                port=0,
                mode="auto",
                node_id="node-a",
                publish_callback=publisher,
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            time.sleep(0.05)
            port = httpd.server_address[1]

            req = Request(
                f"http://127.0.0.1:{port}/publish",
                data=json.dumps({"text": "hello"}).encode("utf-8"),
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            self.assertTrue(body.get("ok"))
            self.assertEqual(len(calls), 1)

            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=1)

    def test_publish_failure_returns_500_not_ok(self):
        with tempfile.TemporaryDirectory() as td:
            db = f"{td}/bridge.db"

            def publisher(_subject: str, _blob: bytes, _payload: dict):
                raise RuntimeError("NATS not connected")

            httpd = make_server(
                db_path=db,
                host="127.0.0.1",
                port=0,
                mode="auto",
                node_id="node-a",
                publish_callback=publisher,
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            time.sleep(0.05)
            port = httpd.server_address[1]

            req = Request(
                f"http://127.0.0.1:{port}/publish",
                data=json.dumps({"text": "hello"}).encode("utf-8"),
                method="POST",
            )
            req.add_header("Content-Type", "application/json")

            with self.assertRaises(HTTPError) as ctx:
                urlopen(req, timeout=3)

            self.assertEqual(ctx.exception.code, 500)
            body = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertIn("publish failed", body.get("error", ""))

            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
