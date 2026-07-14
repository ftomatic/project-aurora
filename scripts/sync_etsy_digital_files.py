"""Idempotently sync final PNG digital files to an existing Etsy draft."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_digital_file_service import (  # noqa: E402
    EtsyDigitalFileService,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyDigitalFileUploadResult,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def _load_listing_id(memory: MemoryManager) -> str:
    """Load the latest existing Etsy draft listing id from memory."""
    loaders = (
        memory.load_etsy_complete_draft_result,
        memory.load_etsy_digital_file_upload_result,
        memory.load_etsy_draft_result,
    )
    for loader in loaders:
        try:
            stored = loader()
        except FileNotFoundError:
            continue
        listing_id = stored.get("etsy_listing_id")
        if isinstance(listing_id, str) and listing_id.strip():
            return listing_id.strip()
    raise RuntimeError("No existing Etsy listing ID was found in Aurora memory.")


def _metadata_records(
    result: EtsyDigitalFileUploadResult,
    key: str,
) -> list[dict[str, object]]:
    records = result.metadata.get(key, ())
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _total_present(result: EtsyDigitalFileUploadResult) -> int:
    total = result.metadata.get("total_present")
    if isinstance(total, int):
        return total
    return len(_metadata_records(result, "already_present")) + result.files_uploaded


def _print_errors(result: EtsyDigitalFileUploadResult) -> None:
    errors = list(result.errors)
    for attempt in result.attempts:
        for error in attempt.errors:
            errors.append(f"{attempt.filename}: {error}")
    if not errors:
        return
    print("")
    print("Errors")
    for error in errors:
        print(error)


def main() -> None:
    """Sync missing digital download files without creating a new listing."""
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
        listing_id = _load_listing_id(memory)
        result = EtsyDigitalFileService(
            config=config,
            memory=memory,
        ).sync_digital_files(
            listing_id=listing_id,
            final_images_dir=final_images_dir,
        )
    except RuntimeError as error:
        print("ETSY DIGITAL FILE SYNC")
        print("")
        print("Status")
        print("FAILED")
        print("")
        print("Errors")
        print(error)
        raise SystemExit(1) from error

    already_present = _metadata_records(result, "already_present")

    print("ETSY DIGITAL FILE SYNC")
    print("")
    print("Listing ID")
    print(result.etsy_listing_id)
    print("")
    print("Expected Files")
    print(result.files_found)
    print("")
    print("Already Present")
    print(len(already_present))
    print("")
    print("Uploaded Now")
    print(result.files_uploaded)
    print("")
    print("Failed")
    print(result.failed)
    print("")
    print("Total Present")
    print(_total_present(result))
    print("")
    print("Status")
    print(result.status)
    _print_errors(result)
    if result.status != "SUCCESS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
