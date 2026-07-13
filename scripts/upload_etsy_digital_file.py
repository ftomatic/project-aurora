"""Upload final PNG digital files to the latest partial Etsy draft only."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_digital_file_service import (  # noqa: E402
    EtsyDigitalFileService,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyCompleteDraftResult,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def _load_partial_result(memory: MemoryManager) -> EtsyCompleteDraftResult:
    stored = memory.load_etsy_complete_draft_result()
    if stored.get("status") != "PARTIAL_FAILURE":
        raise RuntimeError("Latest complete draft result is not PARTIAL_FAILURE.")
    listing_id = stored.get("etsy_listing_id")
    if not isinstance(listing_id, str) or not listing_id.strip():
        raise RuntimeError("Latest partial result does not include etsy_listing_id.")
    return EtsyCompleteDraftResult(
        etsy_listing_id=listing_id,
        draft_url=stored.get("draft_url"),
        draft_created=bool(stored.get("draft_created")),
        images_uploaded=int(stored.get("images_uploaded", 0)),
        image_count=int(stored.get("image_count", 0)),
        digital_file_uploaded=bool(stored.get("digital_file_uploaded")),
        digital_file_path=stored.get("digital_file_path"),
        price=float(stored.get("price", 1.99)),
        status=str(stored.get("status")),
        completed_stages=tuple(stored.get("completed_stages", ())),
        failed_stage=stored.get("failed_stage"),
        warnings=tuple(stored.get("warnings", ())),
        errors=tuple(stored.get("errors", ())),
    )


def main() -> None:
    """Upload only the four final PNG digital files for the existing draft."""
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
        current = _load_partial_result(memory)
        upload_result = EtsyDigitalFileService(
            config=config,
            memory=memory,
        ).upload_digital_files(
            listing_id=current.etsy_listing_id,
            final_images_dir=final_images_dir,
        )
    except RuntimeError as error:
        print("ETSY DIGITAL FILE UPLOAD")
        print("")
        print("Status")
        print("FAILED")
        print("")
        print("Reason")
        print(error)
        raise SystemExit(1) from error

    updated = replace(
        current,
        status="SUCCESS" if upload_result.uploaded else "PARTIAL_FAILURE",
        digital_file_uploaded=upload_result.uploaded,
        digital_file_path=str(final_images_dir),
        failed_stage=None if upload_result.uploaded else "digital_file_upload",
        errors=upload_result.errors,
        warnings=upload_result.warnings,
        completed_stages=(
            tuple(current.completed_stages) + ("digital_file_uploaded",)
            if upload_result.uploaded
            else tuple(current.completed_stages)
        ),
    )
    memory.save_etsy_complete_draft_result(updated)

    print("ETSY DIGITAL FILE UPLOAD")
    print("")
    print("Listing ID")
    print(current.etsy_listing_id)
    print("")
    print("Files Found")
    print(upload_result.files_found)
    print("")
    print("Files Uploaded")
    print(upload_result.files_uploaded)
    print("")
    print("Failed")
    print(upload_result.failed)
    print("")
    print("Status")
    print(upload_result.status)
    if upload_result.errors:
        print("")
        print("Errors")
        for error in upload_result.errors:
            print(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
