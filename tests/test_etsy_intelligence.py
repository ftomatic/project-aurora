"""Tests for read-only Etsy Intelligence Agent."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.etsy_intelligence.agent import EtsyIntelligenceAgent  # noqa: E402
from project_aurora.etsy_intelligence.duplicate_detector import DuplicateDetector  # noqa: E402
from project_aurora.etsy_intelligence.intelligence_models import (  # noqa: E402
    READ_ONLY,
    UNAVAILABLE,
    ListingSnapshot,
)
from project_aurora.etsy_intelligence.pricing_analyzer import PricingAnalyzer  # noqa: E402
from project_aurora.etsy_intelligence.reporting import render_intelligence_report  # noqa: E402
from project_aurora.etsy_intelligence.shop_reader import EtsyShopReader  # noqa: E402
from project_aurora.merchandising.pricing_engine import DEFAULT_LISTING_PRICE  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.upload_approved_product import main as upload_approved_main  # noqa: E402


class FakeEtsyClient:
    def __init__(self) -> None:
        self.write_called = False

    def list_shop_draft_listings(self) -> tuple[dict[str, object], ...]:
        return (
            {
                "listing_id": 111,
                "title": "Woodland Nursery Clipart PNG Bundle",
                "state": "draft",
                "price": {"amount": 249, "divisor": 100},
                "tags": ["woodland clipart", "nursery art"],
                "taxonomy_id": 119,
                "is_digital": True,
            },
            {
                "listing_id": 222,
                "title": "Teacher Classroom Printable Decor",
                "state": "draft",
                "price": {"amount": 249, "divisor": 100},
                "tags": ["teacher printable", "classroom decor"],
                "taxonomy_id": 119,
                "is_digital": True,
            },
        )

    def update_listing_fields(self, *_args: object, **_kwargs: object) -> None:
        self.write_called = True


class EtsyIntelligenceTest(unittest.TestCase):
    def test_missing_metric_marked_unavailable_not_fabricated(self) -> None:
        shop, listings, warnings = EtsyShopReader(FakeEtsyClient()).read()
        self.assertEqual(shop.draft_listings, 2)
        self.assertEqual(listings[0].views, UNAVAILABLE)
        self.assertFalse(warnings)

    def test_low_sample_size_produces_low_confidence(self) -> None:
        report = EtsyIntelligenceAgent(
            memory=_memory(),
            shop_reader=EtsyShopReader(FakeEtsyClient()),
        ).run()
        self.assertTrue(any(item.confidence < 50 for item in report.shop_learnings))

    def test_duplicate_product_detected(self) -> None:
        listing = ListingSnapshot(
            listing_id="111",
            title="Woodland Nursery Clipart PNG Bundle",
            state="draft",
            price=2.49,
            tags=("woodland clipart", "nursery art"),
            taxonomy_id="119",
            is_digital=True,
            image_count=4,
        )
        assessment = DuplicateDetector().assess("Woodland Nursery Clipart PNG Bundle", (listing,))
        self.assertIn(assessment.decision, {"SKIP_DUPLICATE", "CREATE_WITH_DIFFERENTIATION"})
        self.assertGreaterEqual(assessment.similarity_score, 60)

    def test_fixed_price_is_not_overridden(self) -> None:
        listing = ListingSnapshot(
            listing_id="111",
            title="Premium Expensive Bundle",
            state="draft",
            price=19.99,
            tags=(),
            taxonomy_id="119",
            is_digital=True,
            image_count=4,
        )
        evidence = PricingAnalyzer().analyze((listing,))
        self.assertIn(f"${DEFAULT_LISTING_PRICE:.2f}", evidence.summary)
        self.assertIn("ANALYSIS_ONLY", evidence.summary)

    def test_read_only_agent_performs_no_etsy_writes_and_saves_report(self) -> None:
        client = FakeEtsyClient()
        memory = _memory()
        report = EtsyIntelligenceAgent(
            memory=memory,
            shop_reader=EtsyShopReader(client),
        ).run()
        self.assertEqual(report.mode, READ_ONLY)
        self.assertFalse(report.writes_performed)
        self.assertFalse(client.write_called)
        self.assertIn("latest", memory.list_records("etsy_intelligence_reports"))

    def test_intelligence_report_works_with_partial_data(self) -> None:
        report = EtsyIntelligenceAgent(
            memory=_memory(),
            shop_reader=EtsyShopReader(None),
        ).run()
        rendered = render_intelligence_report(report)
        self.assertIn("ETSY INTELLIGENCE", rendered)
        self.assertIn("Writes Performed\nNO", rendered)
        self.assertTrue(report.warnings)

    def test_upload_approved_product_requires_approval(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            upload_approved_main(["--job-id", "missing-job"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_upload_approved_product_invokes_resume_only_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = MemoryManager(storage=CSVStorage(base_path=Path(temp_dir)))
            memory.save_record("human_product_approvals", "job-1", {"job_id": "job-1"})
            with (
                patch("scripts.upload_approved_product.PROJECT_ROOT", Path(temp_dir)),
                patch("scripts.upload_approved_product.MemoryManager", return_value=memory),
                patch("scripts.upload_approved_product.ProductionQueueManager"),
                patch("scripts.upload_approved_product.subprocess.run") as run,
            ):
                run.return_value.returncode = 0
                with self.assertRaises(SystemExit) as raised:
                    upload_approved_main(["--job-id", "job-1"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--upload", run.call_args.args[0])


def _memory() -> MemoryManager:
    temp_dir = tempfile.TemporaryDirectory()
    memory = MemoryManager(storage=CSVStorage(base_path=Path(temp_dir.name)))
    memory._test_temp_dir = temp_dir  # type: ignore[attr-defined]
    return memory


if __name__ == "__main__":
    unittest.main()
