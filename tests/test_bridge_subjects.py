import json
import unittest

from ocbridge.bridge_daemon import (
    build_chat_store_payload,
    build_node_subject,
    parse_subject_list,
    publish_result_to_subjects,
    resolve_subjects,
)
from ocbridge.protocol import TaskResult


class FakeStore:
    def __init__(self):
        self.rows = []

    def add_message(self, *, direction: str, subject: str, payload: dict):
        self.rows.append((direction, subject, payload))


class FakeBus:
    def __init__(self):
        self.published = []

    async def publish(self, subject: str, payload: bytes):
        self.published.append((subject, payload))


class BridgeSubjectsTest(unittest.TestCase):
    def test_parse_subject_list_trims_and_dedupes(self):
        raw = " openclaw.dispatch.v1, op.task.home ,openclaw.dispatch.v1 ,, "
        self.assertEqual(
            parse_subject_list(raw), ["openclaw.dispatch.v1", "op.task.home"]
        )

    def test_resolve_subjects_merges_csv_and_legacy_single(self):
        merged = resolve_subjects(
            "openclaw.result.v1,op.result.controller", "oc.task.result"
        )
        self.assertEqual(
            merged,
            ["openclaw.result.v1", "op.result.controller", "oc.task.result"],
        )

    def test_build_node_subject_normalizes_prefix(self):
        self.assertEqual(
            build_node_subject("oc.chat.to", "worker-a"), "oc.chat.to.worker-a"
        )
        self.assertEqual(
            build_node_subject("oc.chat.from.", "worker-a"), "oc.chat.from.worker-a"
        )

    def test_build_chat_store_payload_extracts_trace_subject_and_timestamp(self):
        payload = build_chat_store_payload(
            subject="oc.chat.to.worker-a",
            data=json.dumps(
                {"schema": "oc.chat.v1", "text": "hello", "ts": 1700000000}
            ).encode(),
            headers={"x-trace-id": "trace-001"},
        )
        self.assertEqual(payload["schema"], "oc.chat.v1")
        self.assertEqual(payload["subject"], "oc.chat.to.worker-a")
        self.assertEqual(payload["trace_id"], "trace-001")
        self.assertEqual(payload["timestamp"], 1700000000.0)
        self.assertEqual(payload["ts"], 1700000000.0)


class DualWriteTest(unittest.IsolatedAsyncioTestCase):
    async def test_publish_result_to_subjects_dual_writes(self):
        bus = FakeBus()
        store = FakeStore()
        result = TaskResult(
            task_id="t-1", node_id="worker-a", exit_code=0, summary="ok", artifacts=[]
        )

        await publish_result_to_subjects(
            bus=bus,
            store=store,
            subjects=["openclaw.result.v1", "op.result.controller"],
            result=result,
        )

        self.assertEqual(
            [s for s, _ in bus.published],
            ["openclaw.result.v1", "op.result.controller"],
        )
        self.assertEqual(
            [s for _, s, _ in store.rows],
            ["openclaw.result.v1", "op.result.controller"],
        )
        for _, payload in bus.published:
            decoded = json.loads(payload.decode())
            self.assertEqual(decoded["task_id"], "t-1")


if __name__ == "__main__":
    unittest.main()
