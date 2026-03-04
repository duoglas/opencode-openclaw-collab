import unittest

from ocbridge.bridge_daemon import DEFAULT_DISPATCH_SUBJECTS, DEFAULT_RESULT_SUBJECTS


class E2EMinimalChainTest(unittest.TestCase):
    def test_end_to_end_subject_names_present(self):
        self.assertIn("openclaw.dispatch.v1", DEFAULT_DISPATCH_SUBJECTS)
        self.assertIn("op.task.home", DEFAULT_DISPATCH_SUBJECTS)
        self.assertIn("openclaw.result.v1", DEFAULT_RESULT_SUBJECTS)
        self.assertIn("op.result.controller", DEFAULT_RESULT_SUBJECTS)


if __name__ == "__main__":
    unittest.main()
