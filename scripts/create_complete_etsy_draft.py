"""Create one complete Etsy draft for the current RainbowMilkStudio product."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_complete_draft_service import (  # noqa: E402
    EtsyCompleteDraftService,
    PRODUCT_DATA,
)
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def confirm_live_creation(config: EtsyConfig) -> bool:
    """Require explicit confirmation before creating a live Etsy draft."""
    if config.is_mock_mode:
        return False
    print("Type CREATE to continue")
    try:
        confirmation = input("> ").strip()
    except EOFError:
        return False
    return confirmation == "CREATE"


def main() -> None:
    """Run the complete Etsy draft creation workflow."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    config = EtsyConfig.from_file(PROJECT_ROOT / "config" / "etsy.yaml")
    if not confirm_live_creation(config):
        print("COMPLETE ETSY DRAFT")
        print("")
        print("Status")
        print("CONFIRMATION_REQUIRED")
        raise SystemExit(1)

    result = EtsyCompleteDraftService(
        config=config,
        memory=memory,
        final_images_dir=PROJECT_ROOT / "data" / "aurora" / "final_product_images",
        digital_downloads_dir=PROJECT_ROOT / "data" / "aurora" / "digital_downloads",
    ).run()

    print("COMPLETE ETSY DRAFT")
    print("")
    print("Listing")
    print(PRODUCT_DATA["product_name"])
    print("")
    print("Price")
    print("$1.99")
    print("")
    print("Draft Created")
    print("YES" if result.draft_created else "NO")
    print("")
    print("Images Uploaded")
    print(result.images_uploaded)
    print("")
    print("Digital File Uploaded")
    print("YES" if result.digital_file_uploaded else "NO")
    print("")
    print("Listing Status")
    print("DRAFT")
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
