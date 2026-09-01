"""Tests for Aurora generation-family strategy."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.generation_strategy import (  # noqa: E402
    GENERATION_MODE_BOTANICAL,
    GENERATION_MODE_CHARACTERS,
    GENERATION_MODE_CLIPART,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_ORIGINAL,
    GENERATION_MODE_STORYBOOK,
    GENERATION_MODE_WEDDING,
    GenerationStrategyConfig,
    GenerationStrategyResolver,
    listing_family_for_generation_mode,
    normalize_generation_mode,
)


class GenerationStrategyTest(unittest.TestCase):
    def test_normalizes_cli_modes(self) -> None:
        self.assertEqual(normalize_generation_mode("storybook"), GENERATION_MODE_STORYBOOK)
        self.assertEqual(normalize_generation_mode("digital-paper"), GENERATION_MODE_DIGITAL_PAPER)
        self.assertEqual(normalize_generation_mode("digital_paper"), GENERATION_MODE_DIGITAL_PAPER)
        self.assertEqual(normalize_generation_mode("wedding"), GENERATION_MODE_WEDDING)
        self.assertEqual(normalize_generation_mode("original"), GENERATION_MODE_ORIGINAL)

    def test_loads_generation_mix_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "generation_mix.yaml"
            path.write_text(
                "generation_mix:\n"
                "  storybook: 50\n"
                "  clipart: 25\n"
                "  characters: 10\n"
                "  botanical: 10\n"
                "  digital_paper: 5\n",
                encoding="utf-8",
            )

            config = GenerationStrategyConfig.from_file(path)

        self.assertEqual(config.mix[GENERATION_MODE_STORYBOOK], 50)
        self.assertEqual(config.mix[GENERATION_MODE_DIGITAL_PAPER], 5)

    def test_explicit_override_wins(self) -> None:
        decision = GenerationStrategyResolver().resolve(
            product_name="Rabbit Tea Party Watercolor Clipart",
            requested_mode="botanical",
        )

        self.assertEqual(decision.generation_mode, GENERATION_MODE_BOTANICAL)
        self.assertEqual(decision.listing_family, GENERATION_MODE_CLIPART)

    def test_auto_uses_brand_storybook_terms(self) -> None:
        decision = GenerationStrategyResolver().resolve(
            product_name="Rabbit Garden Tea Party Watercolor Clipart",
            product_category="watercolor animal collection",
        )

        self.assertEqual(decision.generation_mode, GENERATION_MODE_STORYBOOK)
        self.assertEqual(decision.listing_family, GENERATION_MODE_STORYBOOK)

    def test_auto_detects_other_supported_families(self) -> None:
        resolver = GenerationStrategyResolver()

        self.assertEqual(
            resolver.resolve(product_name="Woodland Character Bundle").generation_mode,
            GENERATION_MODE_CHARACTERS,
        )
        self.assertEqual(
            resolver.resolve(product_name="Vintage Botanical Elements").generation_mode,
            GENERATION_MODE_BOTANICAL,
        )
        self.assertEqual(
            resolver.resolve(product_name="Sage Botanical Digital Paper").generation_mode,
            GENERATION_MODE_DIGITAL_PAPER,
        )
        self.assertEqual(
            resolver.resolve(product_name="French Country Wedding Menu").generation_mode,
            GENERATION_MODE_WEDDING,
        )

    def test_auto_back_to_school_uses_transparent_character_family(self) -> None:
        decision = GenerationStrategyResolver().resolve(
            product_name="Bright Back to School Kids Clipart",
            product_category="classroom elements",
        )

        self.assertEqual(decision.generation_mode, GENERATION_MODE_CHARACTERS)
        self.assertEqual(decision.listing_family, GENERATION_MODE_CLIPART)

    def test_listing_family_mapping(self) -> None:
        self.assertEqual(
            listing_family_for_generation_mode(GENERATION_MODE_STORYBOOK),
            GENERATION_MODE_STORYBOOK,
        )
        self.assertEqual(
            listing_family_for_generation_mode(GENERATION_MODE_BOTANICAL),
            GENERATION_MODE_CLIPART,
        )
        self.assertEqual(
            listing_family_for_generation_mode(GENERATION_MODE_ORIGINAL),
            GENERATION_MODE_STORYBOOK,
        )


if __name__ == "__main__":
    unittest.main()
