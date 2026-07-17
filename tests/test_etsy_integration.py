"""Tests for Aurora Etsy draft integration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_draft_service import (  # noqa: E402
    EtsyDraftService,
)
from project_aurora.integrations.etsy.etsy_listing_mapper import (  # noqa: E402
    AI_DISCLOSURE_API_FIELD,
    DEFAULT_AI_DISCLOSURE,
    EtsyListingMapper,
    RENEWAL_API_FIELD,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyDraftResult,
)
from project_aurora.seo.description_builder import (  # noqa: E402
    DOWNLOAD_DISCLAIMER_SECTION,
    PURCHASE_SECTION,
    RAINBOW_MILK_STUDIO_DESCRIPTION,
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


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeTokenManager:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_if_needed(self, force: bool = False):  # type: ignore[no-untyped-def]
        self.calls += 1
        return type(
            "Refresh",
            (),
            {"refreshed": True, "status": "REFRESHED"},
        )()


def make_listing_package(
    image_files: tuple[str, ...] = ("mockup_01.png",),
) -> ListingPackage:
    return ListingPackage(
        product_name="Summer Strawberry Birthday Collection",
        collection_name="Summer Strawberry Birthday Collection",
        listing_status=READY_FOR_ETSY_DRAFT,
        seo_package_id="latest",
        prompt_package_id="latest",
        approved_mockup_files=image_files,
        approved_generated_image_files=("asset_01.png",),
        price=5.99,
    )


def make_physical_listing_package(
    image_files: tuple[str, ...] = ("mockup_01.png",),
) -> ListingPackage:
    return ListingPackage(
        product_name="Summer Strawberry Birthday Collection",
        collection_name="Summer Strawberry Birthday Collection",
        listing_status=READY_FOR_ETSY_DRAFT,
        seo_package_id="latest",
        prompt_package_id="latest",
        approved_mockup_files=image_files,
        approved_generated_image_files=("asset_01.png",),
        is_digital_download=False,
        price=5.99,
    )


class EtsyIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=Path(self.temp_dir.name))
        )
        self.config = EtsyConfig(mode="mock")
        self.seo_package = SEOEngine().build_package(PRODUCT_DATA)
        self.final_image_files = self._create_final_image_files()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_final_image_files(self) -> tuple[str, ...]:
        image_dir = Path(self.temp_dir.name) / "final_product_images"
        image_dir.mkdir()
        paths: list[str] = []
        for index in range(1, 5):
            path = image_dir / f"strawberry_birthday_party_printable_{index:02d}.png"
            Image.new("RGBA", (3600, 3600), (255, index * 20, 0, 255)).save(
                path,
                format="PNG",
                dpi=(300, 300),
            )
            paths.append(str(path))
        return tuple(paths)

    def test_config_loads_environment_safe_defaults(self) -> None:
        config = EtsyConfig.from_file(Path("missing_etsy.yaml"))

        self.assertEqual(config.mode, "mock")
        self.assertTrue(config.is_mock_mode)

    def test_listing_mapper_creates_draft_payload(self) -> None:
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=self.config,
        )

        self.assertEqual(payload.title, self.seo_package.title)
        self.assertEqual(len(payload.tags), 13)
        self.assertTrue(payload.is_digital)
        self.assertEqual(payload.listing_type, "download")
        self.assertEqual(payload.price, 5.99)
        self.assertEqual(payload.quantity, 999)
        self.assertNotEqual(payload.description, RAINBOW_MILK_STUDIO_DESCRIPTION)
        self.assertIn(PURCHASE_SECTION, payload.description)
        self.assertIn(DOWNLOAD_DISCLAIMER_SECTION, payload.description)
        self.assertIn("FREE COMMERCIAL LICENSE", payload.description)
        self.assertEqual(payload.who_made, "i_did")
        self.assertEqual(payload.when_made, "made_to_order")
        self.assertEqual(payload.ai_disclosure, DEFAULT_AI_DISCLOSURE)
        self.assertTrue(payload.should_auto_renew)
        self.assertEqual(payload.to_dict()["state"], "draft")

    def test_digital_listing_payload_uses_download_type(self) -> None:
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=self.config,
        )
        payload_data = payload.to_dict()

        self.assertEqual(payload_data["type"], "download")
        self.assertEqual(payload_data["quantity"], 999)
        self.assertEqual(payload_data["price"], 5.99)
        self.assertEqual(payload_data["who_made"], "i_did")
        self.assertEqual(payload_data["when_made"], "made_to_order")
        self.assertEqual(payload_data[RENEWAL_API_FIELD], True)
        self.assertNotIn("ai_generated_summary", payload_data)
        self.assertNotIn("is_ai_generated", payload_data)
        self.assertIsNone(AI_DISCLOSURE_API_FIELD)
        self.assertNotIn("shipping_profile_id", payload_data)
        self.assertNotIn("processing_profile_id", payload_data)

    def test_listing_package_digital_flag_maps_to_physical_type(self) -> None:
        config = EtsyConfig(
            mode="live",
            taxonomy_id=123,
            processing_profile_id=456,
            shipping_profile_id=789,
        )

        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_physical_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=config,
        )
        payload_data = payload.to_dict()

        self.assertFalse(payload.is_digital)
        self.assertEqual(payload_data["type"], "physical")
        self.assertEqual(payload_data["shipping_profile_id"], 789)

    def test_payload_validation_passes(self) -> None:
        mapper = EtsyListingMapper()
        payload = mapper.map_to_draft(
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=self.config,
        )

        self.assertEqual(mapper.validate_payload(payload), ())

    def test_mock_client_does_not_call_etsy_api(self) -> None:
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(self.final_image_files),
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
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
        )

        saved = self.memory.load_etsy_draft_result()

        self.assertIsInstance(result, EtsyDraftResult)
        self.assertEqual(saved["status"], "READY_FOR_ETSY_DRAFT")
        self.assertEqual(saved["metadata"]["api_called"], False)

    def test_real_mode_requires_credentials(self) -> None:
        config = EtsyConfig(mode="live")
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=config,
        )

        result = EtsyClient(config).create_draft_listing(payload)

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertTrue(result.errors)
        self.assertFalse(result.metadata["api_called"])
        self.assertIn("ETSY_SHARED_SECRET", result.metadata["missing"])
        self.assertIn("taxonomy_id", result.metadata["missing"])

    def test_live_digital_listing_does_not_require_processing_profile(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="client",
            shared_secret="secret",
            access_token="token",
            taxonomy_id=123,
            processing_profile_id=None,
        )

        self.assertEqual(config.validate_for_api(is_digital=True), ())

    def test_live_physical_listing_requires_processing_profile(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="client",
            shared_secret="secret",
            access_token="token",
            taxonomy_id=123,
            processing_profile_id=None,
        )

        self.assertEqual(
            config.validate_for_api(is_digital=False),
            ("processing_profile_id", "shipping_profile_id"),
        )

    def test_draft_service_stops_before_client_when_live_config_missing(self) -> None:
        class ExplodingClient(EtsyClient):
            def create_draft_listing(self, payload):  # type: ignore[no-untyped-def]
                raise AssertionError("Etsy client should not be called.")

        result = EtsyDraftService(
            config=EtsyConfig(mode="live"),
            memory=self.memory,
            client=ExplodingClient(EtsyConfig(mode="live")),
        ).create_draft(
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
        )

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertFalse(result.metadata["api_called"])

    def test_physical_config_validation_requires_profiles(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="client",
            shared_secret="secret",
            access_token="token",
            taxonomy_id=123,
        )
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_physical_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=config,
        )

        self.assertEqual(
            config.validate_for_api(is_digital=payload.is_digital),
            ("processing_profile_id", "shipping_profile_id"),
        )

    def test_expired_etsy_token_refreshes_and_retries_once(self) -> None:
        calls = []
        token_manager = FakeTokenManager()

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            if len(calls) == 1:
                raise HTTPError(
                    api_request.full_url,
                    401,
                    "Unauthorized",
                    {},
                    BytesIO(b'{"error":"invalid_token","error_description":"access token expired"}'),
                )
            return FakeResponse({"ok": True})

        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="client",
            shared_secret="secret",
            access_token="expired",
            taxonomy_id=123,
        )

        with patch(
            "project_aurora.integrations.etsy.etsy_client.EtsyConfig.from_environment",
            return_value=config,
        ):
            result = EtsyClient(
                config,
                urlopen=fake_urlopen,
                token_manager=token_manager,
            ).get_json("/shops/shop")

        self.assertEqual(result["ok"], True)
        self.assertEqual(token_manager.calls, 1)
        self.assertEqual(len(calls), 2)

    def test_physical_payload_validation_requires_shipping_profile(self) -> None:
        config = EtsyConfig(
            mode="live",
            taxonomy_id=123,
            processing_profile_id=456,
            shipping_profile_id=None,
        )
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_physical_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=config,
        )

        self.assertIn(
            "shipping_profile_id is required for physical listings.",
            EtsyListingMapper().validate_payload(payload),
        )

    def test_live_client_sends_keystring_and_shared_secret_header(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="fake_keystring",
            shared_secret="fake_shared_secret",
            access_token="fake_access_token",
            taxonomy_id=123,
            api_base_url="https://example.test/v3/application",
        )
        payload = EtsyListingMapper().map_to_draft(
            listing_package=make_listing_package(self.final_image_files),
            seo_package=self.seo_package,
            config=config,
        )
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return FakeResponse({"listing_id": 987654})

        result = EtsyClient(
            config=config,
            urlopen=fake_urlopen,
        ).create_draft_listing(payload)

        self.assertEqual(result.status, "DRAFT_CREATED")
        self.assertEqual(len(calls), 1)
        headers = calls[0][0].headers
        self.assertEqual(
            headers["X-api-key"],
            "fake_keystring:fake_shared_secret",
        )
        self.assertEqual(
            headers["Authorization"],
            "Bearer fake_access_token",
        )
        self.assertIn("/shops/shop/listings", calls[0][0].full_url)

    def test_live_client_updates_only_automatic_renewal_field(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="fake_keystring",
            shared_secret="fake_shared_secret",
            access_token="fake_access_token",
            taxonomy_id=123,
            api_base_url="https://example.test/v3/application",
        )
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return FakeResponse(
                {
                    "listing_id": 987654,
                    "should_auto_renew": True,
                    "state": "draft",
                    "title": "unchanged",
                }
            )

        response = EtsyClient(
            config=config,
            urlopen=fake_urlopen,
        ).update_listing_renewal_default("987654")

        self.assertEqual(response["should_auto_renew"], True)
        self.assertEqual(len(calls), 1)
        api_request = calls[0][0]
        self.assertEqual(api_request.get_method(), "PATCH")
        self.assertIn("/shops/shop/listings/987654", api_request.full_url)
        payload = json.loads(api_request.data.decode("utf-8"))
        self.assertEqual(payload, {"should_auto_renew": True})
        self.assertNotIn("title", payload)
        self.assertNotIn("description", payload)
        self.assertNotIn("tags", payload)
        self.assertNotIn("price", payload)
        self.assertNotIn("image_ids", payload)
        self.assertNotIn("digital_files", payload)

    def test_live_client_lists_only_shop_draft_listings(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="fake_keystring",
            shared_secret="fake_shared_secret",
            access_token="fake_access_token",
            taxonomy_id=123,
            api_base_url="https://example.test/v3/application",
        )
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return FakeResponse(
                {
                    "results": [
                        {"listing_id": 1, "state": "draft"},
                        {"listing_id": 2, "state": "active"},
                        {"listing_id": 3, "state": "draft"},
                    ]
                }
            )

        drafts = EtsyClient(
            config=config,
            urlopen=fake_urlopen,
        ).list_shop_draft_listings()

        self.assertEqual(
            tuple(item["listing_id"] for item in drafts),
            (1, 3),
        )
        self.assertEqual(len(calls), 1)
        self.assertIn(
            "/shops/shop/listings?state=draft&limit=100",
            calls[0][0].full_url,
        )


if __name__ == "__main__":
    unittest.main()
