"""Safely fix supported Etsy listing defaults on an existing draft."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_listing_mapper import (  # noqa: E402
    AI_DISCLOSURE_API_FIELD,
    DEFAULT_AI_DISCLOSURE,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def load_existing_listing_id(memory: MemoryManager) -> str:
    """Load the latest existing Etsy listing id without creating a listing."""
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


def validate_live_config(config: EtsyConfig) -> tuple[str, ...]:
    """Return missing config values required for a live listing update."""
    missing: list[str] = []
    if config.is_mock_mode:
        missing.append("AURORA_ETSY_MODE=live")
    if not config.shop_id:
        missing.append("ETSY_SHOP_ID")
    if not config.client_id:
        missing.append("ETSY_CLIENT_ID")
    if not config.shared_secret:
        missing.append("ETSY_SHARED_SECRET")
    if not config.access_token:
        missing.append("ETSY_ACCESS_TOKEN")
    return tuple(missing)


def main() -> None:
    """Update only supported Etsy default fields on the existing draft."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    config = EtsyConfig.from_file(PROJECT_ROOT / "config" / "etsy.yaml")

    try:
        listing_id = load_existing_listing_id(memory)
        missing = validate_live_config(config)
        if missing:
            raise RuntimeError(
                "Missing Etsy configuration: " + ", ".join(missing) + "."
            )
        response = EtsyClient(config).update_listing_renewal_default(listing_id)
    except RuntimeError as error:
        print("ETSY LISTING DEFAULTS FIX")
        print("")
        print("Status")
        print("FAILED")
        print("")
        print("Error")
        print(error)
        raise SystemExit(1) from error

    print("ETSY LISTING DEFAULTS FIX")
    print("")
    print("Listing ID")
    print(listing_id)
    print("")
    print("AI Disclosure")
    if AI_DISCLOSURE_API_FIELD is None:
        print("MANUAL_REQUIRED")
        print("")
        print("Expected AI Disclosure")
        print(DEFAULT_AI_DISCLOSURE)
        print("")
        print("AI Disclosure Reason")
        print("Etsy Open API does not expose a verified update field for this setting.")
    else:
        print(response.get(AI_DISCLOSURE_API_FIELD, "UNKNOWN"))
    print("")
    print("Renewal")
    print(response.get("should_auto_renew", "UNKNOWN"))
    print("")
    print("Listing Status")
    print(response.get("state", "draft"))
    print("")
    print("Status")
    print("PARTIAL_SUCCESS" if AI_DISCLOSURE_API_FIELD is None else "SUCCESS")


if __name__ == "__main__":
    main()
