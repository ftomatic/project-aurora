"""Upload generated Aurora PNG images to the latest Etsy draft listing."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_image_upload_service import (  # noqa: E402
    EtsyImageUploadService,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Upload images to the latest saved Etsy draft listing."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    config = EtsyConfig.from_file(PROJECT_ROOT / "config" / "etsy.yaml")
    service = EtsyImageUploadService(
        config=config,
        memory=memory,
        images_dir=PROJECT_ROOT / "data" / "aurora" / "generated_images",
    )
    try:
        result = service.upload_latest_draft_images()
    except RuntimeError as error:
        print("ETSY IMAGE UPLOAD")
        print("")
        print("Status")
        print("FAILED")
        print("")
        print("Reason")
        print(error)
        raise SystemExit(1) from error

    print("ETSY IMAGE UPLOAD")
    print("")
    print("Listing ID")
    print(result.etsy_listing_id or "")
    print("")
    print("Images Found")
    print(result.images_found)
    print("")
    print("Images Uploaded")
    print(result.images_uploaded)
    print("")
    print("Failed")
    print(result.failed)
    print("")
    print("Status")
    print(result.status)
    if result.errors:
        print("")
        print("Errors")
        for error in result.errors:
            print(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
