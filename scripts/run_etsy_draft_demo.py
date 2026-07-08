"""Run Aurora Etsy draft creation demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_draft_service import (  # noqa: E402
    EtsyDraftService,
)
from project_aurora.listing.listing_package import (  # noqa: E402
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


SAMPLE_PRODUCT_DATA = {
    "product_name": "Summer Strawberry Birthday Collection",
    "product_type": "Party Printable Bundle",
    "target_buyer": "Parents planning girls' summer birthday parties",
}


def main() -> None:
    """Create a mock Etsy draft result from local Aurora data."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    config = EtsyConfig.from_file(PROJECT_ROOT / "config" / "etsy.yaml")
    seo_package = SEOEngine(memory=memory).run(SAMPLE_PRODUCT_DATA)
    listing_package = ListingPackage(
        product_name="Summer Strawberry Birthday Collection",
        collection_name="Summer Strawberry Birthday Collection",
        listing_status=READY_FOR_ETSY_DRAFT,
        seo_package_id="latest",
        prompt_package_id="latest",
        approved_mockup_files=("mockup_01.png",),
        approved_generated_image_files=("asset_01.png",),
    )
    result = EtsyDraftService(config=config, memory=memory).create_draft(
        listing_package=listing_package,
        seo_package=seo_package,
    )
    api_called = bool(result.metadata.get("api_called"))
    validation = "PASS" if not result.errors else "FAIL"
    missing = tuple(result.metadata.get("missing", ()))

    print("ETSY DRAFT SERVICE")
    print("")
    print("Mode")
    print("Mock" if config.is_mock_mode else "Live")
    if result.status == "CONFIGURATION_REQUIRED" and not config.is_mock_mode:
        print("")
        print("Status")
        print(result.status)
        print("")
        print("Missing")
        for field_name in missing:
            print(field_name)
        print("")
        print("Etsy API")
        print("Not called")
        return
    print("")
    print("Listing")
    print(listing_package.product_name)
    print("")
    print("Status")
    print(listing_package.listing_status)
    print("")
    print("Etsy API")
    print("Called" if api_called else "Not called")
    print("")
    print("Validation")
    print(validation)


if __name__ == "__main__":
    main()
