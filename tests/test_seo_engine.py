"""Tests for Aurora SEO and Keyword Engine."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.seo.description_builder import (  # noqa: E402
    DescriptionBuilder,
    RAINBOW_MILK_STUDIO_DESCRIPTION,
)
from project_aurora.seo.keyword_engine import KeywordEngine  # noqa: E402
from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from project_aurora.seo.seo_package import SEOPackage  # noqa: E402
from project_aurora.seo.title_builder import TitleBuilder  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


SAMPLE_PRODUCT_DATA = {
    "product_name": "Summer Strawberry Birthday Collection",
    "product_type": "Party Printable Bundle",
    "target_buyer": "Parents planning girls' summer birthday parties",
}


class SEOEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=Path(self.temp_dir.name))
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_keyword_engine_generates_thirteen_etsy_tags(self) -> None:
        tags = KeywordEngine().build_tags(
            product_name=SAMPLE_PRODUCT_DATA["product_name"],
            product_type=SAMPLE_PRODUCT_DATA["product_type"],
            target_buyer=SAMPLE_PRODUCT_DATA["target_buyer"],
        )

        self.assertEqual(len(tags), 13)
        self.assertIn("strawberry party", tags)
        self.assertTrue(all(len(tag) <= 20 for tag in tags))

    def test_title_builder_generates_expected_title(self) -> None:
        title = TitleBuilder().build_title(
            product_name=SAMPLE_PRODUCT_DATA["product_name"],
            product_type=SAMPLE_PRODUCT_DATA["product_type"],
            keywords=(),
        )

        self.assertIn("Summer Strawberry Birthday Collection", title)
        self.assertNotIn("Cupcake Toppers", title)
        self.assertLessEqual(len(title), 140)

    def test_description_builder_returns_required_description(self) -> None:
        description = DescriptionBuilder().build_description(
            product_name=SAMPLE_PRODUCT_DATA["product_name"],
            product_type=SAMPLE_PRODUCT_DATA["product_type"],
            target_buyer=SAMPLE_PRODUCT_DATA["target_buyer"],
            buyer_use_case="Parents planning parties",
            product_positioning="Cute strawberry printable bundle",
            tags=("strawberry party", "birthday printable"),
        )

        self.assertEqual(description, RAINBOW_MILK_STUDIO_DESCRIPTION)
        self.assertIn("4 high-quality 300 DPI PNG files", description)
        self.assertIn("3600 × 3600 pixels", description)

    def test_seo_engine_builds_package(self) -> None:
        package = SEOEngine().build_package(SAMPLE_PRODUCT_DATA)

        self.assertIsInstance(package, SEOPackage)
        self.assertEqual(
            package.product_name,
            "Summer Strawberry Birthday Collection",
        )
        self.assertEqual(len(package.tags), 13)
        self.assertGreaterEqual(package.seo_score, 90)
        self.assertEqual(package.description, RAINBOW_MILK_STUDIO_DESCRIPTION)
        self.assertEqual(package.warnings, ())

    def test_seo_engine_saves_package_to_memory(self) -> None:
        package = SEOEngine(memory=self.memory).run(SAMPLE_PRODUCT_DATA)

        saved = self.memory.load_seo_package()

        self.assertEqual(saved["product_name"], package.product_name)
        self.assertEqual(saved["seo_score"], package.seo_score)
        self.assertEqual(len(saved["tags"]), 13)

    def test_seo_engine_warns_on_long_tags_or_title(self) -> None:
        warnings = SEOEngine._warnings(
            title="x" * 141,
            tags=(
                "this tag is definitely too long",
                "short",
            )
            + tuple(f"tag {index}" for index in range(11)),
        )

        self.assertTrue(any("Title" in warning for warning in warnings))
        self.assertTrue(any("Tags exceed" in warning for warning in warnings))

    def test_missing_product_data_raises(self) -> None:
        with self.assertRaises(ValueError):
            SEOEngine().build_package({"product_name": "Missing Fields"})


if __name__ == "__main__":
    unittest.main()
