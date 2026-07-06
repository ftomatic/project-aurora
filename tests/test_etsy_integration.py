"""Tests for Aurora Etsy draft integration."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_draft_service import (  # noqa: E402
    EtsyDraftService,
)
from project_aurora.integrations.etsy.etsy_listing_mapper import (  # noqa: E402
    EtsyListingMapper,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyDraftResult,
)
from project_aurora.listing.listing_package import (  # noqa: E402
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


PRODUCT_DATA = {
    "product_name": "Summer Strawberry Birthday Collection",
    "product_type": "Party Printable Bundle",
    "target_buyer": "Parents planning girls' summer birthday parties",
}


def make_listing_package() -> ListingPackage:
    return ListingPackage(
        product_name="Summer Strawberry Birthday Collection",
        collection_name="Summer Strawberry Birthday Collection",
        listing_status=READY_FOR_ETSY_DRAFT,
        seo_package_id="latest",
        prompt_package_id="latest",
        approved_mockup_files=("mockup_01.png",),
        approved_generated_image_files=("asset_01.png",),
    )


class EtsyIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=Path(self.temp_dir.name))
        )
        self.config = EtsyConfig(mode="mock")
        self.seo_package = SEOEngine().build_package(PRODUCT_DATA)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_config_loads_environment_safe_defaults(self) -> None:
        config = EtsyConfig.from_file(Path("missing_etsy.yaml"))

        self.assertEqual(config.mode, "mock")
        self.assertTrue(config.is_mock_mode)

    def test_listing_mapper_creates_draft_payload(self) -> None:
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(),
            seo_package=self.seo_package,
            config=self.config,
        )

        self.assertEqual(payload.title, self.seo_package.title)
        self.assertEqual(len(payload.tags), 13)
        self.assertTrue(payload.is_digital)
        self.assertEqual(payload.who_made, "i_did")
        self.assertEqual(payload.to_dict()["state"], "draft")

    def test_payload_validation_passes(self) -> None:
        mapper = EtsyListingMapper()
        payload = mapper.map_to_draft(
            listing_package=make_listing_package(),
            seo_package=self.seo_package,
            config=self.config,
        )

        self.assertEqual(mapper.validate_payload(payload), ())

    def test_mock_client_does_not_call_etsy_api(self) -> None:
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(),
            seo_package=self.seo_package,
            config=self.config,
        )

        result = EtsyClient(self.config).create_draft_listing(payload)

        self.assertEqual(result.status, "READY_FOR_ETSY_DRAFT")
        self.assertFalse(result.metadata["api_called"])
        self.assertEqual(result.etsy_listing_id, None)

    def test_draft_service_saves_result_to_memory(self) -> None:
        result = EtsyDraftService(
            config=self.config,
            memory=self.memory,
        ).create_draft(
            listing_package=make_listing_package(),
            seo_package=self.seo_package,
        )

        saved = self.memory.load_etsy_draft_result()

        self.assertIsInstance(result, EtsyDraftResult)
        self.assertEqual(saved["status"], "READY_FOR_ETSY_DRAFT")
        self.assertEqual(saved["metadata"]["api_called"], False)

    def test_real_mode_requires_credentials(self) -> None:
        config = EtsyConfig(mode="live")
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(),
            seo_package=self.seo_package,
            config=config,
        )

        result = EtsyClient(config).create_draft_listing(payload)

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertTrue(result.errors)
        self.assertFalse(result.metadata["api_called"])


if __name__ == "__main__":
    unittest.main()
