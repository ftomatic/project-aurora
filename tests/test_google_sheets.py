"""Tests for Aurora Google Sheets Command Center sync."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.google_sheets.dashboard_builder import (  # noqa: E402
    DashboardBuilder,
)
from project_aurora.integrations.google_sheets.sheets_client import (  # noqa: E402
    GoogleSheetsConfig,
)
from project_aurora.integrations.google_sheets.sheets_sync import (  # noqa: E402
    SheetsSync,
)
from project_aurora.integrations.google_sheets.worksheet_manager import (  # noqa: E402
    REQUIRED_WORKSHEETS,
    WorksheetManager,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class FakeSheetsClient:
    def __init__(self) -> None:
        self.spreadsheet_id = "fake-spreadsheet"
        self.worksheets: set[str] = {"Dashboard"}
        self.updated: dict[str, tuple[tuple[Any, ...], ...]] = {}

    def get_or_create_workbook(
        self,
        title: str,
        spreadsheet_id: str | None = None,
    ) -> str:
        return spreadsheet_id or self.spreadsheet_id

    def get_worksheet_titles(self, spreadsheet_id: str) -> tuple[str, ...]:
        return tuple(sorted(self.worksheets))

    def add_worksheet(self, spreadsheet_id: str, title: str) -> None:
        self.worksheets.add(title)

    def update_values(
        self,
        spreadsheet_id: str,
        worksheet_title: str,
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        self.updated[worksheet_title] = rows

    def append_values(
        self,
        spreadsheet_id: str,
        worksheet_title: str,
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        existing = self.updated.get(worksheet_title, ())
        self.updated[worksheet_title] = (*existing, *rows)


class GoogleSheetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(storage=CSVStorage(base_path=self.base_path))
        self.client = FakeSheetsClient()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def seed_memory(self) -> None:
        self.memory.save_research(
            {
                "production_selection": {
                    "best_product": {
                        "name": "Strawberry Birthday Party Printable"
                    },
                    "product_type": "Party Printable Bundle",
                },
                "recommendations": [{"name": "A"}, {"name": "B"}],
            }
        )
        self.memory.save_strategy(
            {
                "selected_product": "Strawberry Birthday Party Printable",
                "collection_name": "Summer Strawberry Birthday Collection",
                "asset_count": 36,
                "production_priority": "High",
                "estimated_commercial_potential": "High",
            }
        )
        self.memory.save_production_queue(
            [
                {
                    "id": "item-1",
                    "product_name": "Summer Strawberry Birthday Collection",
                    "platform": "Etsy",
                    "content_type": "product_listing",
                    "priority": "High",
                    "status": "pending",
                }
            ]
        )
        self.memory.save_prompt_package(
            {
                "product_name": "Summer Strawberry Birthday Collection",
                "collection": "Summer Strawberry Birthday Collection",
                "style": "Storybook Watercolor",
                "target_platforms": ["Etsy"],
            }
        )
        self.memory.save_image_result(
            {
                "provider": "Mock Provider",
                "status": "SUCCESS",
                "generated_files": ["asset_01.png", "asset_02.png"],
            }
        )
        self.memory.save_image_qa_results(
            [
                {
                    "asset_name": "asset_01.png",
                    "status": "PASS",
                    "overall_score": 100,
                    "recommended_action": "Approve",
                    "review_required": False,
                }
            ]
        )
        self.memory.save_seo_package(
            {
                "product_name": "Summer Strawberry Birthday Collection",
                "title": "Strawberry Birthday Party Printable Bundle",
                "seo_score": 100,
            }
        )

    def test_configuration_loads_yaml(self) -> None:
        config_path = self.base_path / "google_sheets.yaml"
        config_path.write_text(
            "workbook_name: Aurora Command Center\n"
            "spreadsheet_id: abc123\n"
            "credentials_file: config/google_credentials.local.json\n",
            encoding="utf-8",
        )

        config = GoogleSheetsConfig.from_file(config_path)

        self.assertEqual(config.workbook_name, "Aurora Command Center")
        self.assertEqual(config.spreadsheet_id, "abc123")
        self.assertEqual(
            str(config.credentials_file),
            "config/google_credentials.local.json",
        )

    def test_worksheet_creation(self) -> None:
        manager = WorksheetManager(self.client)

        result = manager.ensure_worksheets("fake-spreadsheet")

        self.assertIn("Research", result.created)
        self.assertTrue(set(REQUIRED_WORKSHEETS).issubset(self.client.worksheets))

    def test_dashboard_population(self) -> None:
        self.seed_memory()
        builder = DashboardBuilder(self.memory)

        rows = builder.dashboard_rows(builder.load_snapshot())

        self.assertIn(("Prompt Packages", 1), rows)
        self.assertIn(("Images Generated", 2), rows)
        self.assertIn(("QA Approved", 1), rows)
        self.assertIn(("SEO Packages", 1), rows)

    def test_memory_reading(self) -> None:
        self.seed_memory()
        snapshot = DashboardBuilder(self.memory).load_snapshot()

        self.assertIsNotNone(snapshot.research)
        self.assertIsNotNone(snapshot.strategy)
        self.assertEqual(len(snapshot.prompt_packages), 1)
        self.assertEqual(len(snapshot.seo_packages), 1)

    def test_synchronization(self) -> None:
        self.seed_memory()
        config = GoogleSheetsConfig(
            workbook_name="Aurora Command Center",
            spreadsheet_id="fake-spreadsheet",
            credentials_file=None,
        )

        result = SheetsSync(
            memory=self.memory,
            client=self.client,
            config=config,
        ).run()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.workbook_name, "Aurora Command Center")
        self.assertIn("Dashboard", self.client.updated)
        self.assertIn("Production Queue", self.client.updated)
        self.assertIn("SEO", self.client.updated)


if __name__ == "__main__":
    unittest.main()
