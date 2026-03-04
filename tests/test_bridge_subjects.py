import json
import unittest

from ocbridge.bridge_daemon import parse_subject_list, resolve_subjects, publish_result_to_subjects
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
        self.assertEqual(parse_subject_list(raw), ["openclaw.dispatch.v1", "op.task.home"])

    def test_resolve_subjects_merges_csv_and_legacy_single(self):
        merged = resolve_subjects("openclaw.result.v1,op.result.controller", "oc.task.result")
        self.assertEqual(
            merged,
            ["openclaw.result.v1", "op.result.controller", "oc.task.result"],
        )


class DualWriteTest(unittest.IsolatedAsyncioTestCase):
    async def test_publish_result_to_subjects_dual_writes(self):
        bus = FakeBus()
        store = FakeStore()
        result = TaskResult(task_id="t-1", node_id="worker-a", exit_code=0, summary="ok", artifacts=[])

        await publish_result_to_subjects(
            bus=bus,
            store=store,
            subjects=["openclaw.result.v1", "op.result.controller"],
            result=result,
        )

        self.assertEqual([s for s, _ in bus.published], ["openclaw.result.v1", "op.result.controller"])
        self.assertEqual([s for _, s, _ in store.rows], ["openclaw.result.v1", "op.result.controller"])
        for _, payload in bus.published:
            decoded = json.loads(payload.decode())
            self.assertEqual(decoded["task_id"], "t-1")


if __name__ == "__main__":
    unittest.main()
