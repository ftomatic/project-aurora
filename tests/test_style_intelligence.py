"""Tests for Aurora Style Intelligence Engine."""

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
from project_aurora.creative.collection_plan import CollectionPlan  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from project_aurora.style_intelligence.style_engine import (  # noqa: E402
    StyleEngine,
)
from project_aurora.style_intelligence.style_library_builder import (  # noqa: E402
    StyleLibraryBuilder,
)
from project_aurora.style_intelligence.style_profile import (  # noqa: E402
    StyleProfile,
)
from project_aurora.style_intelligence.style_selector import (  # noqa: E402
    StyleSelector,
)


PROFILE_PATH = (
    PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
)


def make_collection_plan() -> CollectionPlan:
    return CollectionPlan(
        collection_name="Strawberry Birthday",
        theme="Storybook Watercolor",
        season="Summer",
        target_customer="Parents planning girls' summer birthday parties",
        art_style="Storybook Watercolor Cottagecore",
        primary_palette=("berry red", "blush pink", "cream"),
        secondary_palette=("sage", "warm yellow"),
        recommended_products=("Invitation", "Cupcake Toppers", "Favor Tags"),
        master_assets=("Main Strawberry Girl", "Berry Pattern"),
        shared_elements=("strawberries", "flowers", "ribbons"),
        cross_sell_products=("Matching Clipart",),
        upsell_products=("Deluxe Party Bundle",),
        estimated_revenue=120.0,
        estimated_generation_cost=0.62,
        priority="High",
    )


def make_trend_research() -> dict[str, str]:
    return {
        "theme": "strawberry birthday storybook watercolor summer party",
        "audience": "parents digital printable buyers",
        "product": "party printable",
    }


class StyleIntelligenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = ProjectProfileLoader().load(PROFILE_PATH)

    def test_style_profile_dataclass(self) -> None:
        style = StyleProfile(
            style_id="test_style",
            style_name="Test Style",
            description="A broad test style.",
            visual_characteristics=("soft", "friendly"),
            color_palette=("cream", "sage"),
            brush_style="soft watercolor",
            line_style="clean linework",
            lighting="warm light",
            composition="centered",
            texture="paper grain",
            recommended_products=("party printable",),
            recommended_seasons=("Summer",),
            recommended_audiences=("parents",),
            confidence=0.9,
        )

        self.assertEqual(style.style_id, "test_style")
        self.assertEqual(style.confidence, 0.9)

    def test_library_builder_creates_seed_styles(self) -> None:
        profiles = StyleLibraryBuilder().build_seed_library()

        self.assertEqual(len(profiles), 10)
        self.assertIn(
            "Storybook Watercolor",
            [profile.style_name for profile in profiles],
        )
        for profile in profiles:
            self.assertTrue(profile.description)
            self.assertTrue(profile.visual_characteristics)
            self.assertTrue(profile.color_palette)

    def test_style_selector_selects_storybook_watercolor(self) -> None:
        selection = StyleSelector().select(
            project_profile=self.profile,
            trend_research=make_trend_research(),
            collection_plan=make_collection_plan(),
            style_profiles=StyleLibraryBuilder().build_seed_library(),
        )

        self.assertEqual(selection.style_profile.style_name, "Storybook Watercolor")
        self.assertEqual(selection.confidence, 0.96)
        self.assertIn("Highest fit", selection.reason)

    def test_style_engine_saves_profiles_to_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = MemoryManager(storage=CSVStorage(base_path=Path(temp_dir)))
            result = StyleEngine(memory=memory).run(
                project_profile=self.profile,
                trend_research=make_trend_research(),
                collection_plan=make_collection_plan(),
            )

            self.assertEqual(result.styles_available, 10)
            self.assertEqual(len(result.saved_style_ids), 10)
            self.assertIn("storybook_watercolor", memory.list_style_profiles())
            saved = memory.load_style_profile("storybook_watercolor")
            self.assertEqual(saved["style_name"], "Storybook Watercolor")

    def test_selection_requires_profiles(self) -> None:
        with self.assertRaises(ValueError):
            StyleSelector().select(
                project_profile=self.profile,
                trend_research=make_trend_research(),
                collection_plan=make_collection_plan(),
                style_profiles=(),
            )


if __name__ == "__main__":
    unittest.main()
