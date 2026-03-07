import os
import tempfile
import unittest
from pathlib import Path

from ocbridge.logging_utils import setup_rotating_logger


class LoggingRotationTest(unittest.TestCase):
    def test_rotating_file_handler_creates_backup(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "logs" / "ocbridge.log"
            os.environ["OCBRIDGE_LOG_PATH"] = str(log_path)
            os.environ["OCBRIDGE_LOG_MAX_BYTES"] = "256"
            os.environ["OCBRIDGE_LOG_BACKUP_COUNT"] = "2"

            logger, resolved = setup_rotating_logger("ocbridge.test.rotation")
            self.assertEqual(resolved, str(log_path))

            for i in range(120):
                logger.info("line %s %s", i, "x" * 40)

            self.assertTrue(log_path.exists())
            rotated = Path(str(log_path) + ".1")
            self.assertTrue(rotated.exists())


if __name__ == "__main__":
    unittest.main()
