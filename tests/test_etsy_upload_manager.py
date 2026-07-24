"""Tests for resilient Etsy upload checkpoint handling."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_upload_manager import (  # noqa: E402
    EtsyUploadManager,
    EtsyUploadPolicy,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class EtsyUploadManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )
        self.file_path = self.base_path / "printable_wall_art_11x14.jpg"
        self.file_path.write_bytes(b"fake image bytes")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_broken_pipe_exception_is_retried(self) -> None:
        calls = 0
        waits: list[float] = []

        def uploader() -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise BrokenPipeError(32, "Broken pipe")
            return {"listing_file_id": "file-1"}

        checkpoint = EtsyUploadManager(
            memory=self.memory,
            policy=EtsyUploadPolicy(max_attempts=2, backoff_seconds=(0,)),
            sleeper=waits.append,
        ).upload_one(
            listing_id="listing-1",
            job_id="job-1",
            upload_type="digital_file",
            file_path=self.file_path,
            rank=1,
            uploader=uploader,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(waits, [0])
        self.assertEqual(checkpoint.status, "SUCCESS")
        self.assertEqual(checkpoint.etsy_resource_id, "file-1")
        self.assertEqual(checkpoint.attempts, 2)

    def test_wrapped_broken_pipe_message_is_retried(self) -> None:
        calls = 0

        def uploader() -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("Etsy API request failed: [Errno 32] Broken pipe")
            return {"listing_file_id": "file-2"}

        checkpoint = EtsyUploadManager(
            memory=self.memory,
            policy=EtsyUploadPolicy(max_attempts=2, backoff_seconds=(0,)),
            sleeper=lambda _seconds: None,
        ).upload_one(
            listing_id="listing-1",
            job_id="job-1",
            upload_type="digital_file",
            file_path=self.file_path,
            rank=1,
            uploader=uploader,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(checkpoint.status, "SUCCESS")
        self.assertEqual(checkpoint.etsy_resource_id, "file-2")


if __name__ == "__main__":
    unittest.main()
