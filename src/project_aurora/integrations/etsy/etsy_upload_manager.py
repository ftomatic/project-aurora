"""Resilient Etsy upload manager with checkpoints."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime
from http.client import RemoteDisconnected
from pathlib import Path
from time import sleep
from typing import Any, Callable
from urllib.error import HTTPError, URLError

from project_aurora.storage.memory_manager import MemoryManager


TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class EtsyUploadPolicy:
    """Retry policy for Etsy uploads."""

    max_attempts: int = 4
    backoff_seconds: tuple[int, ...] = (5, 15, 30)
    delay_between_files_seconds: int = 0
    timeout_seconds: int = 60


@dataclass(frozen=True, slots=True)
class EtsyUploadCheckpoint:
    """Per-file upload checkpoint."""

    listing_id: str
    job_id: str
    filename: str
    upload_type: str
    etsy_resource_id: str | None
    rank: int
    status: str
    attempts: int
    completed_at: datetime
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "job_id": self.job_id,
            "filename": self.filename,
            "upload_type": self.upload_type,
            "etsy_resource_id": self.etsy_resource_id,
            "rank": self.rank,
            "status": self.status,
            "attempts": self.attempts,
            "completed_at": self.completed_at.isoformat(),
            "error": self.error,
        }


class EtsyUploadManager:
    """Upload Etsy files one-at-a-time with transient retry handling."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        policy: EtsyUploadPolicy | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._memory = memory
        self._policy = policy or EtsyUploadPolicy()
        self._sleeper = sleeper

    def upload_one(
        self,
        *,
        listing_id: str,
        job_id: str,
        upload_type: str,
        file_path: Path,
        rank: int,
        uploader: Callable[[], dict[str, Any]],
    ) -> EtsyUploadCheckpoint:
        """Upload one file and save a checkpoint immediately."""
        last_error = ""
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                response = uploader()
            except Exception as error:  # noqa: BLE001 - classified below.
                last_error = str(error)
                if not _is_transient_upload_error(error) or attempt >= self._policy.max_attempts:
                    checkpoint = EtsyUploadCheckpoint(
                        listing_id=listing_id,
                        job_id=job_id,
                        filename=file_path.name,
                        upload_type=upload_type,
                        etsy_resource_id=None,
                        rank=rank,
                        status="FAILED",
                        attempts=attempt,
                        completed_at=datetime.now(),
                        error=last_error,
                    )
                    self._save(checkpoint)
                    return checkpoint
                wait = self._wait_for_attempt(attempt)
                _print_upload_retry(file_path, attempt + 1, self._policy.max_attempts, last_error, wait)
                self._sleeper(wait)
                continue
            resource_id = (
                response.get("listing_image_id")
                or response.get("image_id")
                or response.get("listing_file_id")
                or response.get("file_id")
                or response.get("digital_file_id")
            )
            checkpoint = EtsyUploadCheckpoint(
                listing_id=listing_id,
                job_id=job_id,
                filename=file_path.name,
                upload_type=upload_type,
                etsy_resource_id=str(resource_id) if resource_id is not None else None,
                rank=rank,
                status="SUCCESS",
                attempts=attempt,
                completed_at=datetime.now(),
            )
            self._save(checkpoint)
            return checkpoint
        raise AssertionError("unreachable upload retry state")

    def delay_between_files(self) -> None:
        if self._policy.delay_between_files_seconds > 0:
            self._sleeper(self._policy.delay_between_files_seconds)

    def _wait_for_attempt(self, attempt: int) -> int:
        index = min(max(0, attempt - 1), len(self._policy.backoff_seconds) - 1)
        return self._policy.backoff_seconds[index]

    def _save(self, checkpoint: EtsyUploadCheckpoint) -> None:
        if self._memory is None:
            return
        key = f"{checkpoint.listing_id}_{checkpoint.upload_type}_{checkpoint.rank}_{checkpoint.filename}"
        self._memory.save_record("etsy_upload_checkpoints", key, checkpoint.to_dict())


def _is_transient_upload_error(error: Exception) -> bool:
    if isinstance(error, (RemoteDisconnected, ConnectionResetError, TimeoutError, socket.timeout)):
        return True
    if isinstance(error, HTTPError):
        return error.code in TRANSIENT_HTTP_CODES
    if isinstance(error, URLError):
        return True
    text = str(error).casefold()
    return any(
        marker in text
        for marker in (
            "remote end closed connection",
            "remote disconnected",
            "timed out",
            "http 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
        )
    )


def _print_upload_retry(
    file_path: Path,
    attempt: int,
    max_attempts: int,
    reason: str,
    wait: int,
) -> None:
    print("UPLOAD RETRY")
    print("")
    print("File")
    print(file_path.name)
    print("")
    print("Attempt")
    print(f"{attempt} of {max_attempts}")
    print("")
    print("Reason")
    print(reason)
    print("")
    print("Waiting")
    print(f"{wait} seconds")
