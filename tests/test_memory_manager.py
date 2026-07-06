"""Tests for the Project Aurora memory layer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.core.agent_result import AgentResult  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from project_aurora.storage.storage_interface import (  # noqa: E402
    StorageInterface,
)
from project_aurora.strategy.product_plan import (  # noqa: E402
    BundleItem,
    ProductPlan,
)


class CSVStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = CSVStorage(base_path=Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_storage_interface_is_implemented(self) -> None:
        self.assertIsInstance(self.storage, StorageInterface)

    def test_save_load_exists_list_and_delete(self) -> None:
        self.storage.save("research", "latest", {"selected": "A"})

        self.assertTrue(self.storage.exists("research", "latest"))
        self.assertEqual(
            self.storage.load("research", "latest"),
            {"selected": "A"},
        )
        self.assertEqual(self.storage.list("research"), ("latest",))

        self.storage.delete("research", "latest")

        self.assertFalse(self.storage.exists("research", "latest"))

    def test_overwrite_replaces_existing_record(self) -> None:
        self.storage.save("strategy", "latest", {"priority": "Medium"})
        self.storage.save("strategy", "latest", {"priority": "High"})

        self.assertEqual(
            self.storage.load("strategy", "latest"),
            {"priority": "High"},
        )

    def test_missing_data_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.storage.load("missing", "latest")


class MemoryManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=Path(self.temp_dir.name))
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_memory_manager_saves_and_loads_research(self) -> None:
        self.memory.save_research(
            {
                "production_selection": {
                    "best_product": {
                        "name": "Strawberry Birthday Party Printable"
                    }
                }
            }
        )

        loaded = self.memory.load_research()

        self.assertEqual(
            loaded["production_selection"]["best_product"]["name"],
            "Strawberry Birthday Party Printable",
        )

    def test_memory_manager_saves_and_loads_strategy_dataclass(self) -> None:
        plan = ProductPlan(
            selected_product="Strawberry Birthday Party Printable",
            product_type="Party Printable Bundle",
            collection_name="Summer Strawberry Birthday Collection",
            asset_count=36,
            bundle_structure=(
                BundleItem(quantity=8, name="invitations"),
                BundleItem(quantity=6, name="digital papers"),
            ),
            target_buyer="Parents planning summer parties",
            positioning="Cute strawberry printable party bundle",
            expansion_ideas=("Matching thank-you cards",),
            estimated_commercial_potential="High",
            production_priority="High",
            ceo_summary="Today the studio should produce...",
        )

        self.memory.save_strategy(plan)
        loaded = self.memory.load_strategy()

        self.assertEqual(
            loaded["collection_name"],
            "Summer Strawberry Birthday Collection",
        )
        self.assertEqual(loaded["bundle_structure"][0]["quantity"], 8)

    def test_memory_manager_saves_agent_result(self) -> None:
        now = datetime.now()
        result = AgentResult(
            agent_name="Morning Research Agent",
            status="SUCCESS",
            started_at=now,
            finished_at=now,
            execution_time=0.1,
            confidence=0.95,
            summary="Research complete.",
            output={"selected": "Strawberry"},
            next_agent="Product Strategy Agent",
        )

        key = self.memory.save_agent_result(result, result_id="morning")

        self.assertEqual(key, "morning")
        loaded = self.memory._storage.load("agent_results", "morning")  # noqa: SLF001
        self.assertEqual(loaded["agent_name"], "Morning Research Agent")
        self.assertEqual(loaded["confidence"], 0.95)

    def test_memory_summary_reports_counts_and_health(self) -> None:
        self.memory.save_research({"status": "ok"})
        self.memory.save_strategy(
            {"collection_name": "Summer Strawberry Birthday Collection"}
        )

        summary = self.memory.memory_summary()

        self.assertEqual(summary.research_reports_stored, 1)
        self.assertEqual(summary.production_plans, 1)
        self.assertEqual(
            summary.last_production,
            "Summer Strawberry Birthday Collection",
        )
        self.assertEqual(summary.memory_health, "Healthy")
        self.assertIn("AURORA MEMORY", summary.render())

    def test_memory_manager_missing_research_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.memory.load_research()


if __name__ == "__main__":
    unittest.main()
