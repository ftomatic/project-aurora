"""Tests for Pinterest bulk export without Pinterest API calls."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from project_aurora.integrations.pinterest.bulk_export import (
    PinterestBulkExporter,
    daily_publish_dates,
)


class FakeEtsyReader:
    def __init__(self, count: int = 30) -> None:
        self.listings = tuple(
            {
                "listing_id": str(index),
                "title": f"Rabbit Garden Watercolor Collection {index}",
                "tags": ["rabbit art", "storybook", "watercolor"],
                "creation_timestamp": index,
                "url": f"https://www.etsy.com/listing/{index}",
            }
            for index in range(1, count + 1)
        )

    def list_shop_active_listings(self):  # type: ignore[no-untyped-def]
        return self.listings

    def list_listing_images(self, listing_id: str):  # type: ignore[no-untyped-def]
        return (
            {
                "rank": 1,
                "url_fullxfull": f"https://i.etsystatic.com/{listing_id}.jpg",
            },
        )


class PinterestBulkExporterTest(unittest.TestCase):
    def test_exports_25_newest_active_listings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            result = PinterestBulkExporter(FakeEtsyReader(), output).export(25)

            self.assertEqual(result.pins_prepared, 25)
            self.assertEqual(result.listing_ids[0], "30")
            with Path(result.csv_path).open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 25)
            self.assertEqual(rows[0]["Pinterest board"], "RainbowMilkStudio Digital Downloads")
            self.assertEqual(rows[0]["Link"], "https://www.etsy.com/listing/30")
            self.assertTrue(rows[0]["Media URL"].endswith("30.jpg"))
            self.assertLessEqual(len(rows[0]["Title"]), 100)
            self.assertLessEqual(len(rows[0]["Description"]), 500)

    def test_rerun_skips_manifest_listings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            exporter = PinterestBulkExporter(FakeEtsyReader(count=3), output)
            first = exporter.export(2)
            second = exporter.export(2)

            self.assertEqual(first.listing_ids, ("3", "2"))
            self.assertEqual(second.listing_ids, ("1",))
            manifest = json.loads(Path(second.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["pins"]), 3)

    def test_listing_without_public_image_is_skipped(self) -> None:
        reader = FakeEtsyReader(count=1)
        reader.list_listing_images = lambda listing_id: ()  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as temp_dir:
            result = PinterestBulkExporter(reader, Path(temp_dir)).export(1)

        self.assertEqual(result.pins_prepared, 0)
        self.assertEqual(result.skipped_without_images, 1)

    def test_copy_uses_distinct_pinterest_keywords(self) -> None:
        reader = FakeEtsyReader(count=1)
        reader.listings = (
            {
                "listing_id": "1",
                "title": "Fox Garden Watercolor Clipart",
                "tags": [
                    "fox garden",
                    "garden watercolor",
                    "watercolor clipart",
                    "fox garden",
                    "clipart",
                ],
                "creation_timestamp": 1,
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = PinterestBulkExporter(reader, Path(temp_dir)).export(1)
            with Path(result.csv_path).open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

        self.assertEqual(row["Keywords"].count("fox garden"), 1)
        self.assertNotIn("fox garden, fox garden", row["Keywords"])
        self.assertIn("Save this Pin", row["Description"])

    def test_daily_schedule_distributes_three_three_four(self) -> None:
        dates = daily_publish_dates("2026-08-28", 10)

        self.assertEqual(len(dates), 10)
        self.assertEqual(len(set(dates[:3])), 1)
        self.assertEqual(len(set(dates[3:6])), 1)
        self.assertEqual(len(set(dates[6:])), 1)
        self.assertNotEqual(dates[0], dates[3])
        self.assertNotEqual(dates[3], dates[6])


if __name__ == "__main__":
    unittest.main()
