"""Tests for Aurora Etsy draft listing package model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.listing.listing_package import (  # noqa: E402
    CLEANUP_NOT_STARTED,
    READY_FOR_ETSY_DRAFT,
    RETENTION_KEEP_METADATA_DELETE_LOCAL_TEMP,
    ListingPackage,
)


class ListingPackageTest(unittest.TestCase):
    def test_listing_package_is_ready_for_etsy_draft(self) -> None:
        package = ListingPackage(
            product_name="Summer Strawberry Birthday Collection",
            collection_name="Summer Strawberry Birthday Collection",
            listing_status=READY_FOR_ETSY_DRAFT,
            seo_package_id="latest",
            prompt_package_id="01_strawberry_birthday_party_printable_etsy",
            approved_mockup_files=("mockup_01.png",),
            approved_generated_image_files=("asset_01.png",),
            price=5.99,
        )

        self.assertEqual(package.listing_status, READY_FOR_ETSY_DRAFT)
        self.assertEqual(package.price, 5.99)
        self.assertEqual(package.etsy_listing_id, None)
        self.assertEqual(package.posted_at, None)
        self.assertEqual(package.local_asset_cleanup_status, CLEANUP_NOT_STARTED)
        self.assertEqual(
            package.local_files_retention_policy,
            RETENTION_KEEP_METADATA_DELETE_LOCAL_TEMP,
        )
        self.assertEqual(package.status_history[0].status, READY_FOR_ETSY_DRAFT)

    def test_listing_package_rejects_review_status(self) -> None:
        with self.assertRaises(ValueError):
            ListingPackage(
                product_name="Summer Strawberry Birthday Collection",
                collection_name="Summer Strawberry Birthday Collection",
                listing_status="READY_FOR_REVIEW",
                seo_package_id="latest",
                prompt_package_id="latest",
                approved_mockup_files=(),
                approved_generated_image_files=(),
            )

    def test_listing_package_rejects_missing_price(self) -> None:
        with self.assertRaises(ValueError):
            ListingPackage(
                product_name="Summer Strawberry Birthday Collection",
                collection_name="Summer Strawberry Birthday Collection",
                listing_status=READY_FOR_ETSY_DRAFT,
                seo_package_id="latest",
                prompt_package_id="latest",
                approved_mockup_files=(),
                approved_generated_image_files=(),
            )


if __name__ == "__main__":
    unittest.main()
