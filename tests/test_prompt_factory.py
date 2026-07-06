"""Tests for Aurora Prompt Factory."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.production_queue import (  # noqa: E402
    ProductionQueue,
)
from project_aurora.prompt_factory.prompt_builder import PromptBuilder  # noqa: E402
from project_aurora.prompt_factory.prompt_factory import (  # noqa: E402
    PromptFactory,
)
from project_aurora.prompt_factory.prompt_package import (  # noqa: E402
    PromptPackage,
)
from project_aurora.prompt_factory.prompt_templates import (  # noqa: E402
    NEGATIVE_PROMPT_LINES,
    select_template_names,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from project_aurora.strategy.product_plan import (  # noqa: E402
    BundleItem,
    ProductPlan,
)


def make_strategy() -> ProductPlan:
    return ProductPlan(
        selected_product="Strawberry Birthday Party Printable",
        product_type="Party Printable Bundle",
        collection_name="Summer Strawberry Birthday Collection",
        asset_count=36,
        bundle_structure=(BundleItem(quantity=8, name="invitations"),),
        target_buyer="Parents planning summer birthday parties",
        positioning="Cute cottagecore strawberry printable party bundle",
        expansion_ideas=("Matching thank-you set",),
        estimated_commercial_potential="High",
        production_priority="High",
        ceo_summary="Today the studio should produce...",
    )


class PromptFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(storage=CSVStorage(base_path=self.base_path))
        self.queue = ProductionQueue(
            queue_dir=self.base_path / "production_queue"
        )
        self.items = self.queue.create_queue_from_strategy(make_strategy())
        self.queue.save_queue(self.items)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_prompt_package_dataclass(self) -> None:
        package = PromptBuilder().build_package(self.items[0])

        self.assertIsInstance(package, PromptPackage)
        self.assertEqual(
            package.product_name,
            "Strawberry Birthday Party Printable",
        )
        self.assertEqual(
            package.collection,
            "Summer Strawberry Birthday Collection",
        )
        self.assertIn("Etsy", package.target_platforms)

    def test_template_selection(self) -> None:
        selected = select_template_names(
            product_name="Strawberry Birthday Party Printable",
            product_category="Party Printable Bundle",
            content_type="product_listing",
        )

        self.assertEqual(selected, ("Storybook", "Watercolor"))

    def test_image_prompt_generation(self) -> None:
        package = PromptBuilder().build_package(self.items[0])

        self.assertIn("storybook illustration", package.image_prompt)
        self.assertIn("soft watercolor", package.image_prompt)
        self.assertIn("commercial clipart", package.image_prompt)
        self.assertTrue(package.image_prompt.endswith("."))

    def test_negative_prompt_generation(self) -> None:
        package = PromptBuilder().build_package(self.items[0])

        for line in NEGATIVE_PROMPT_LINES:
            self.assertIn(line, package.negative_prompt)
        self.assertIn("No watermark", package.negative_prompt)

    def test_prompt_factory_saves_packages_to_memory(self) -> None:
        result = PromptFactory(memory=self.memory).run()

        self.assertEqual(len(result.packages), len(self.items))
        self.assertEqual(len(result.saved_package_ids), len(self.items))
        saved_ids = self.memory.list_prompt_packages()
        self.assertEqual(len(saved_ids), len(self.items))
        saved_package = self.memory.load_prompt_package(saved_ids[0])
        self.assertIn("image_prompt", saved_package)
        self.assertIn("seo_prompt", saved_package)


if __name__ == "__main__":
    unittest.main()
