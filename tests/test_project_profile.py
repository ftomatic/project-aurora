"""Tests for Aurora project profiles."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.profile_loader import (  # noqa: E402
    ProjectProfileLoader,
)
from project_aurora.config.project_profile import ProjectProfile  # noqa: E402


PROFILE_PATH = (
    PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
)


class ProjectProfileTest(unittest.TestCase):
    def test_loads_rainbow_milk_studio_profile(self) -> None:
        profile = ProjectProfileLoader().load(PROFILE_PATH)

        self.assertIsInstance(profile, ProjectProfile)
        self.assertEqual(profile.project_id, "rainbow_milk_studio")
        self.assertEqual(profile.brand_name, "RainbowMilkStudio")
        self.assertEqual(profile.marketplace, "Etsy")
        self.assertEqual(profile.default_ai_provider, "openai")
        self.assertEqual(profile.default_price, 1.99)
        self.assertEqual(
            profile.etsy_listing_defaults["ai_disclosure"],
            "It’s created with help from an AI generator.",
        )
        self.assertEqual(
            profile.etsy_listing_defaults["renewal_option"],
            "automatic",
        )
        self.assertEqual(profile.etsy_listing_defaults["quantity"], 999)
        self.assertEqual(profile.etsy_listing_defaults["price"], 1.99)
        self.assertTrue(profile.etsy_listing_defaults["should_auto_renew"])

    def test_profile_includes_allowed_products_and_platforms(self) -> None:
        profile = ProjectProfileLoader().load(PROFILE_PATH)

        self.assertIn("party printable", profile.allowed_product_types)
        self.assertIn("clipart", profile.allowed_product_types)
        self.assertIn("Etsy", profile.allowed_platforms)
        self.assertIn("Shopify", profile.allowed_platforms)

    def test_profile_includes_retention_policy(self) -> None:
        profile = ProjectProfileLoader().load(PROFILE_PATH)

        self.assertEqual(
            profile.retention_policy["generated_images"],
            "delete_after_publish",
        )
        self.assertEqual(profile.retention_policy["seo_packages"], "keep")
        self.assertIn(
            "Generated images delete after publish",
            profile.retention_summary(),
        )

    def test_missing_profile_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            ProjectProfileLoader().load(Path("missing_profile.yaml"))

    def test_invalid_profile_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "bad.yaml"
            profile_path.write_text(
                "project_id: bad\n"
                "brand_name: \n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                ProjectProfileLoader().load(profile_path)


if __name__ == "__main__":
    unittest.main()
