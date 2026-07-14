"""Retry failed Etsy digital file uploads for the latest draft only."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_digital_file_service import (  # noqa: E402
    EtsyDigitalFileService,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyDigitalFileUploadAttempt,
    EtsyDigitalFileUploadResult,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def _load_latest_partial_upload(
    memory: MemoryManager,
) -> EtsyDigitalFileUploadResult:
    stored = memory.load_etsy_digital_file_upload_result()
    status = str(stored.get("status", "")).upper()
    if status != "PARTIAL_FAILURE":
        raise RuntimeError(
            "Latest digital-file upload result is not PARTIAL_FAILURE."
        )
    listing_id = stored.get("etsy_listing_id")
    if not isinstance(listing_id, str) or not listing_id.strip():
        raise RuntimeError("Latest partial upload does not include etsy_listing_id.")
    attempts = tuple(
        _attempt_from_record(record)
        for record in stored.get("attempts", ())
        if isinstance(record, dict)
    )
    return EtsyDigitalFileUploadResult(
        status=status,
        etsy_listing_id=listing_id,
        digital_file_path=stored.get("digital_file_path"),
        uploaded=bool(stored.get("uploaded")),
        files_found=int(stored.get("files_found", 0)),
        files_uploaded=int(stored.get("files_uploaded", 0)),
        failed=int(stored.get("failed", 0)),
        attempts=attempts,
        errors=tuple(stored.get("errors", ())),
        warnings=tuple(stored.get("warnings", ())),
        metadata=dict(stored.get("metadata", {})),
    )


def _attempt_from_record(record: dict[str, Any]) -> EtsyDigitalFileUploadAttempt:
    return EtsyDigitalFileUploadAttempt(
        filename=str(record.get("filename", "")),
        rank=int(record.get("rank", 0)),
        status=str(record.get("status", "FAILED")),
        etsy_file_id=(
            str(record["etsy_file_id"])
            if record.get("etsy_file_id") is not None
            else None
        ),
        errors=tuple(str(error) for error in record.get("errors", ())),
        metadata=dict(record.get("metadata", {})),
    )


def _records_from_metadata(
    result: EtsyDigitalFileUploadResult,
    key: str,
) -> list[dict[str, object]]:
    records = result.metadata.get(key, ())
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _print_named_records(
    label: str,
    records: list[dict[str, object]],
) -> None:
    print(label)
    print(len(records))
    for record in records:
        filename = record.get("filename")
        if isinstance(filename, str) and filename:
            extra = record.get("etsy_file_id")
            suffix = f" ({extra})" if extra else ""
            print(f"- {filename}{suffix}")
    print("")


def _print_retry_names(result: EtsyDigitalFileUploadResult) -> None:
    retrying = result.metadata.get("retrying", ())
    retry_names = [name for name in retrying if isinstance(name, str)]
    print("Retrying")
    print(len(retry_names))
    for filename in retry_names:
        print(f"- {filename}")
    print("")


def _print_errors(result: EtsyDigitalFileUploadResult) -> None:
    errors: list[str] = list(result.errors)
    for warning in result.warnings:
        errors.append(warning)
    for attempt in result.attempts:
        errors.extend(attempt.errors)
    for record in _records_from_metadata(result, "previous_failed"):
        for error in record.get("errors", ()):
            if isinstance(error, str):
                errors.append(f"{record.get('filename')}: {error}")
    deduped = tuple(dict.fromkeys(error for error in errors if error))

    print("Error")
    if not deduped:
        print("None")
        return
    for error in deduped:
        print(error)


def main() -> None:
    """Retry only failed or missing Etsy digital files."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    config = EtsyConfig.from_file(PROJECT_ROOT / "config" / "etsy.yaml")
    final_images_dir = (
        PROJECT_ROOT
        / "data"
        / "aurora"
        / "final_product_images"
    )
    try:
        previous = _load_latest_partial_upload(memory)
        result = EtsyDigitalFileService(
            config=config,
            memory=memory,
        ).retry_failed_digital_files(
            listing_id=previous.etsy_listing_id,
            final_images_dir=final_images_dir,
            previous_result=previous,
        )
    except RuntimeError as error:
        print("ETSY DIGITAL FILE RETRY")
        print("")
        print("Status")
        print("FAILED")
        print("")
        print("Error")
        print(error)
        raise SystemExit(1) from error

    print("ETSY DIGITAL FILE RETRY")
    print("")
    print("Listing ID")
    print(result.etsy_listing_id)
    print("")
    _print_named_records(
        "Already Uploaded",
        _records_from_metadata(result, "already_uploaded"),
    )
    _print_retry_names(result)
    _print_named_records(
        "Uploaded",
        _records_from_metadata(result, "uploaded"),
    )
    print("Failed")
    print(result.failed)
    print("")
    _print_errors(result)
    print("")
    print("Status")
    print(result.status)
    if result.status != "SUCCESS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
