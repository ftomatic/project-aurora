"""Tests for the complete Etsy draft creation workflow."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_complete_draft_service import (  # noqa: E402
    EtsyCompleteDraftService,
)
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_listing_mapper import (  # noqa: E402
    EtsyDraftListingPayload,
)
from project_aurora.integrations.etsy.etsy_result import EtsyDraftResult  # noqa: E402
from project_aurora.seo.description_builder import (  # noqa: E402
    RAINBOW_MILK_STUDIO_DESCRIPTION,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeCompleteEtsyClient(EtsyClient):
    def __init__(
        self,
        config: EtsyConfig,
        fail_stage: str | None = None,
    ) -> None:
        super().__init__(config)
        self.fail_stage = fail_stage
        self.draft_calls = 0
        self.image_uploads: list[tuple[str, str, int]] = []
        self.digital_uploads: list[tuple[str, str]] = []
        self.payloads: list[EtsyDraftListingPayload] = []

    def create_draft_listing(
        self,
        payload: EtsyDraftListingPayload,
    ) -> EtsyDraftResult:
        self.draft_calls += 1
        self.payloads.append(payload)
        if self.fail_stage == "draft":
            return EtsyDraftResult(
                status="FAILED",
                etsy_listing_id=None,
                draft_url=None,
                errors=("Draft failed.",),
            )
        return EtsyDraftResult(
            status="DRAFT_CREATED",
            etsy_listing_id="123456789",
            draft_url="https://www.etsy.com/listing/123456789",
        )

    def upload_listing_image(
        self,
        listing_id: str,
        image_path: Path,
        rank: int,
    ) -> dict[str, object]:
        if self.fail_stage == "image":
            raise RuntimeError("Image upload failed.")
        self.image_uploads.append((listing_id, image_path.name, rank))
        return {"listing_image_id": rank}

    def upload_listing_digital_file(
        self,
        listing_id: str,
        file_path: Path,
    ) -> dict[str, object]:
        if self.fail_stage == "digital":
            raise RuntimeError("Digital upload failed.")
        self.digital_uploads.append((listing_id, file_path.name))
        return {"file_id": "file-1"}


def write_final_png(path: Path, color: tuple[int, int, int, int]) -> None:
    Image.new("RGBA", (3600, 3600), color).save(
        path,
        format="PNG",
        dpi=(300, 300),
    )


class CompleteEtsyDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.final_images_dir = self.base_path / "final_product_images"
        self.downloads_dir = self.base_path / "digital_downloads"
        self.final_images_dir.mkdir()
        for index in range(1, 5):
            write_final_png(
                self.final_images_dir
                / f"strawberry_birthday_party_printable_{index:02d}.png",
                (255, index * 20, 0, 255),
            )
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )
        self.config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="fake_keystring",
            shared_secret="fake_shared_secret",
            access_token="fake_token",
            taxonomy_id=1250,
            default_price=1.99,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_complete_draft_success(self) -> None:
        client = FakeCompleteEtsyClient(self.config)

        result = EtsyCompleteDraftService(
            config=self.config,
            memory=self.memory,
            final_images_dir=self.final_images_dir,
            digital_downloads_dir=self.downloads_dir,
            client=client,
        ).run()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.etsy_listing_id, "123456789")
        self.assertTrue(result.draft_created)
        self.assertEqual(result.images_uploaded, 4)
        self.assertEqual(result.image_count, 4)
        self.assertTrue(result.digital_file_uploaded)
        self.assertEqual(client.draft_calls, 1)
        self.assertEqual([upload[2] for upload in client.image_uploads], [1, 2, 3, 4])
        self.assertEqual(len(client.digital_uploads), 1)
        payload = client.payloads[0].to_dict()
        self.assertEqual(payload["type"], "download")
        self.assertEqual(payload["price"], 1.99)
        self.assertEqual(payload["quantity"], 999)
        self.assertEqual(payload["taxonomy_id"], 1250)
        self.assertEqual(payload["description"], RAINBOW_MILK_STUDIO_DESCRIPTION)
        self.assertEqual(len(payload["tags"]), 13)
        self.assertNotIn("shipping_profile_id", payload)
        self.assertNotIn("processing_profile_id", payload)
        with ZipFile(result.digital_file_path or "", "r") as archive:
            self.assertEqual(len(archive.namelist()), 4)
        saved = self.memory.load_etsy_complete_draft_result()
        self.assertEqual(saved["status"], "SUCCESS")
        self.assertEqual(saved["etsy_listing_id"], "123456789")

    def test_partial_failure_after_image_upload_does_not_create_second_draft(self) -> None:
        client = FakeCompleteEtsyClient(self.config, fail_stage="image")

        result = EtsyCompleteDraftService(
            config=self.config,
            memory=self.memory,
            final_images_dir=self.final_images_dir,
            digital_downloads_dir=self.downloads_dir,
            client=client,
        ).run()

        self.assertEqual(result.status, "PARTIAL_FAILURE")
        self.assertEqual(result.etsy_listing_id, "123456789")
        self.assertEqual(result.failed_stage, "image_upload")
        self.assertEqual(client.draft_calls, 1)
        self.assertEqual(client.digital_uploads, [])

    def test_partial_failure_after_digital_upload_preserves_listing_id(self) -> None:
        client = FakeCompleteEtsyClient(self.config, fail_stage="digital")

        result = EtsyCompleteDraftService(
            config=self.config,
            memory=self.memory,
            final_images_dir=self.final_images_dir,
            digital_downloads_dir=self.downloads_dir,
            client=client,
        ).run()

        self.assertEqual(result.status, "PARTIAL_FAILURE")
        self.assertEqual(result.etsy_listing_id, "123456789")
        self.assertEqual(result.failed_stage, "digital_file_upload")
        self.assertEqual(result.images_uploaded, 4)
        self.assertEqual(client.draft_calls, 1)

    def test_requires_explicit_live_mode_before_api_calls(self) -> None:
        config = EtsyConfig(mode="mock")
        client = FakeCompleteEtsyClient(config)

        result = EtsyCompleteDraftService(
            config=config,
            memory=self.memory,
            final_images_dir=self.final_images_dir,
            digital_downloads_dir=self.downloads_dir,
            client=client,
        ).run()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertEqual(result.failed_stage, "configuration")
        self.assertEqual(client.draft_calls, 0)

    def test_client_uploads_digital_file_as_multipart(self) -> None:
        zip_path = self.downloads_dir / "download.zip"
        self.downloads_dir.mkdir()
        zip_path.write_bytes(b"zip-bytes")
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            return FakeResponse({"file_id": 1})

        response = EtsyClient(
            config=self.config,
            urlopen=fake_urlopen,
        ).upload_listing_digital_file(
            listing_id="123456789",
            file_path=zip_path,
        )

        self.assertEqual(response["file_id"], 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("/shops/shop/listings/123456789/files", calls[0].full_url)
        self.assertIn("multipart/form-data", calls[0].headers["Content-type"])
        self.assertIn(b'name="file"; filename="download.zip"', calls[0].data)


if __name__ == "__main__":
    unittest.main()
