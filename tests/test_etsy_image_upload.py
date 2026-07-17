"""Tests for uploading generated images to an Etsy draft listing."""

from __future__ import annotations

import json
from io import BytesIO
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_image_upload_service import (  # noqa: E402
    EtsyImageUploadService,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyDraftResult,
    EtsyImageUploadAttempt,
    EtsyImageUploadResult,
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


def make_visible_png_bytes(color: tuple[int, int, int, int] = (255, 0, 0, 255)) -> bytes:
    output = BytesIO()
    Image.new("RGBA", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


class EtsyImageUploadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )
        self.images_dir = self.base_path / "final_product_images"
        self.images_dir.mkdir()
        self.config = EtsyConfig(
            mode="live",
            shop_id="shop-id",
            client_id="fake_keystring",
            shared_secret="fake_shared_secret",
            access_token="fake_token",
        )
        self.memory.save_etsy_draft_result(
            EtsyDraftResult(
                status="DRAFT_CREATED",
                etsy_listing_id="123456789",
                draft_url="https://www.etsy.com/listing/123456789",
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_upload_attempt_dataclass(self) -> None:
        attempt = EtsyImageUploadAttempt(
            image_path="asset.png",
            rank=1,
            status="success",
            etsy_image_id="image-1",
        )

        self.assertEqual(attempt.status, "SUCCESS")
        self.assertEqual(attempt.etsy_image_id, "image-1")

    def test_upload_result_dataclass(self) -> None:
        result = EtsyImageUploadResult(
            status="success",
            etsy_listing_id="123",
            images_found=1,
            images_uploaded=1,
            failed=0,
        )

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.images_uploaded, 1)

    def test_client_uploads_listing_image_as_multipart(self) -> None:
        image_path = self.images_dir / "strawberry_01.png"
        image_path.write_bytes(make_visible_png_bytes())
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return FakeResponse({"listing_image_id": 456})

        response = EtsyClient(
            config=self.config,
            urlopen=fake_urlopen,
        ).upload_listing_image(
            listing_id="123456789",
            image_path=image_path,
            rank=1,
        )

        self.assertEqual(response["listing_image_id"], 456)
        self.assertEqual(len(calls), 1)
        api_request = calls[0][0]
        self.assertIn(
            "/shops/shop-id/listings/123456789/images",
            api_request.full_url,
        )
        self.assertIn("multipart/form-data", api_request.headers["Content-type"])
        self.assertEqual(
            api_request.headers["X-api-key"],
            "fake_keystring:fake_shared_secret",
        )
        self.assertIn(b'name="rank"', api_request.data)
        self.assertIn(b"name=\"image\"; filename=\"strawberry_01.png\"", api_request.data)
        self.assertIn(b"\x89PNG", api_request.data)

    def test_client_lists_listing_images_without_shop_path(self) -> None:
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return FakeResponse(
                {
                    "results": [
                        {"listing_image_id": 1, "rank": 1},
                    ]
                }
            )

        response = EtsyClient(
            config=self.config,
            urlopen=fake_urlopen,
        ).list_listing_images("123456789")

        self.assertEqual(response, ({"listing_image_id": 1, "rank": 1},))
        self.assertEqual(len(calls), 1)
        self.assertIn("/listings/123456789/images", calls[0][0].full_url)
        self.assertNotIn("/shops/shop-id/listings/123456789/images", calls[0][0].full_url)

    def test_service_uploads_sorted_png_images_to_latest_draft(self) -> None:
        (self.images_dir / "b.png").write_bytes(make_visible_png_bytes())
        (self.images_dir / "a.png").write_bytes(make_visible_png_bytes())
        (self.images_dir / "c.png").write_bytes(make_visible_png_bytes())
        (self.images_dir / "d.png").write_bytes(make_visible_png_bytes())
        (self.images_dir / "empty.png").write_bytes(b"")
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            return FakeResponse({"listing_image_id": len(calls)})

        result = EtsyImageUploadService(
            config=self.config,
            memory=self.memory,
            images_dir=self.images_dir,
            client=EtsyClient(config=self.config, urlopen=fake_urlopen),
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.etsy_listing_id, "123456789")
        self.assertEqual(result.images_found, 4)
        self.assertEqual(result.images_uploaded, 4)
        self.assertEqual(result.failed, 0)
        self.assertEqual([attempt.rank for attempt in result.attempts], [1, 2, 3, 4])
        upload_calls = [call for call in calls if call.data is not None]
        self.assertEqual(len(upload_calls), 4)
        self.assertIn(b'filename="a.png"', upload_calls[0].data)
        self.assertIn(b'filename="b.png"', upload_calls[1].data)
        saved = self.memory.load_etsy_image_upload_result()
        self.assertEqual(saved["status"], "SUCCESS")
        self.assertEqual(saved["images_uploaded"], 4)

    def test_service_requires_exactly_four_images(self) -> None:
        for index in range(5):
            (self.images_dir / f"asset_{index:02d}.png").write_bytes(
                make_visible_png_bytes()
            )
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            return FakeResponse({"listing_image_id": len(calls)})

        result = EtsyImageUploadService(
            config=self.config,
            memory=self.memory,
            images_dir=self.images_dir,
            client=EtsyClient(config=self.config, urlopen=fake_urlopen),
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertEqual(result.images_found, 5)
        self.assertEqual(result.images_uploaded, 0)
        self.assertEqual(calls, [])
        self.assertIn("Exactly 4", result.errors[0])

    def test_service_validates_before_calling_etsy(self) -> None:
        (self.images_dir / "a.png").write_bytes(make_visible_png_bytes())
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            return FakeResponse({"listing_image_id": 1})

        result = EtsyImageUploadService(
            config=EtsyConfig(mode="live"),
            memory=self.memory,
            images_dir=self.images_dir,
            client=EtsyClient(config=EtsyConfig(mode="live"), urlopen=fake_urlopen),
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertEqual(result.images_uploaded, 0)
        self.assertEqual(calls, [])
        self.assertIn("ETSY_SHOP_ID", result.errors[0])
        self.assertIn("ETSY_CLIENT_ID", result.errors[0])
        self.assertIn("ETSY_SHARED_SECRET", result.errors[0])
        self.assertIn("ETSY_ACCESS_TOKEN", result.errors[0])

    def test_service_rejects_generated_images_folder(self) -> None:
        wrong_dir = self.base_path / "generated_images"
        wrong_dir.mkdir()
        for index in range(4):
            (wrong_dir / f"asset_{index:02d}.png").write_bytes(
                make_visible_png_bytes()
            )

        result = EtsyImageUploadService(
            config=self.config,
            memory=self.memory,
            images_dir=wrong_dir,
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertIn("final_product_images", result.errors[0])

    def test_service_requires_latest_listing_id(self) -> None:
        self.memory.save_etsy_draft_result(
            EtsyDraftResult(
                status="DRAFT_CREATED",
                etsy_listing_id=None,
                draft_url=None,
            )
        )
        (self.images_dir / "a.png").write_bytes(make_visible_png_bytes())

        result = EtsyImageUploadService(
            config=self.config,
            memory=self.memory,
            images_dir=self.images_dir,
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertIn("etsy_listing_id", result.errors[0])

    def test_service_requires_successful_latest_draft(self) -> None:
        self.memory.save_etsy_draft_result(
            EtsyDraftResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id="123456789",
                draft_url=None,
            )
        )
        (self.images_dir / "a.png").write_bytes(make_visible_png_bytes())

        result = EtsyImageUploadService(
            config=self.config,
            memory=self.memory,
            images_dir=self.images_dir,
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertIn("not successful", result.errors[0])

    def test_service_blocks_invalid_pngs_before_calling_etsy(self) -> None:
        (self.images_dir / "bad.png").write_bytes(b"not-a-real-png")
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            return FakeResponse({"listing_image_id": 1})

        result = EtsyImageUploadService(
            config=self.config,
            memory=self.memory,
            images_dir=self.images_dir,
            client=EtsyClient(config=self.config, urlopen=fake_urlopen),
        ).upload_latest_draft_images()

        self.assertEqual(result.status, "CONFIGURATION_REQUIRED")
        self.assertEqual(calls, [])
        self.assertTrue(any("INVALID_IMAGE" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
