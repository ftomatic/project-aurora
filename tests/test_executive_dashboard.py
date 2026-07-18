"""Tests for Sprint 37 Executive AI Dashboard."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.executive.dashboard_engine import (  # noqa: E402
    ExecutiveDashboardEngine,
    render_dashboard,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    FAILED,
    READY,
    ProductionQueueManager,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class ExecutiveDashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        self._seed_queue()
        self._seed_memory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_queue(self) -> None:
        self.queue.add_job(
            priority="High",
            product_name="Woodland Nursery Clipart",
            category="clipart",
            style="Whimsical Storybook",
            seasonal_theme="Evergreen",
            keywords=("woodland", "nursery", "clipart"),
            confidence_score=0.94,
            estimated_competition="Moderate",
            estimated_demand="High",
            estimated_revenue=180,
            status=READY,
        )
        self.queue.add_job(
            priority="High",
            product_name="Boho Teacher Decor",
            category="wall art",
            style="Boho",
            seasonal_theme="Back To School",
            keywords=("boho", "teacher", "decor"),
            confidence_score=0.91,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=140,
        )
        self.queue.add_job(
            priority="Medium",
            product_name="Weak SEO Stickers",
            category="sticker sheet",
            style="Flat Vector",
            seasonal_theme="Seasonal",
            keywords=("teacher", "stickers"),
            confidence_score=0.86,
            estimated_competition="High",
            estimated_demand="Moderate",
            estimated_revenue=80,
            status=FAILED,
        )

    def _seed_memory(self) -> None:
        today = datetime.now().isoformat()
        self.memory.save_record(
            "production_reports",
            "job-1",
            {
                "job_id": "job-1",
                "product": "Woodland Nursery Clipart",
                "style": "Whimsical Storybook",
                "draft_id": "etsy-1",
                "images": 4,
                "downloads": 4,
                "time": 20,
                "success": True,
                "created_at": today,
                "metadata": {"price": 6.99},
            },
        )
        self.memory.save_record(
            "production_reports",
            "job-2",
            {
                "job_id": "job-2",
                "product": "Weak SEO Stickers",
                "style": "Flat Vector",
                "draft_id": "",
                "images": 0,
                "downloads": 0,
                "time": 4,
                "success": False,
                "failed_stage": "seo_generation",
                "created_at": today,
            },
        )
        for index, score in enumerate((96, 91, 88), start=1):
            self.memory.save_record(
                "opportunity_scores",
                f"opp-{index}",
                {
                    "opportunity_id": f"opp-{index}",
                    "product": f"Opportunity {index}",
                    "opportunity_score": score,
                    "expected_revenue": 100 + index * 20,
                    "trend_velocity_score": 90 if index == 1 else 70,
                    "selection_outcome": "CANDIDATE",
                },
            )
        self.memory.save_record(
            "creative_briefs",
            "brief-1",
            {
                "style_id": "whimsical_storybook",
                "palette_id": "woodland",
                "moodboard_id": "woodland_mood",
                "creative_score": {"overall_creative_score": 92},
            },
        )
        self.memory.save_record(
            "merchant_preflight",
            "job-1",
            {"status": "READY_FOR_ETSY_DRAFT", "merchant_qa_status": "PASS"},
        )
        self.memory.save_record(
            "merchant_preflight",
            "job-2",
            {"status": "PREFLIGHT_FAILED", "merchant_qa_status": "FAIL"},
        )
        self.memory.save_record("seo", "job-1", {"seo_score": 86})
        self.memory.save_record("seo", "job-2", {"seo_score": 62})
        self.memory.save_record(
            "image_qa",
            "job-1",
            {"results": [{"overall_score": 72}, {"overall_score": 74}]},
        )
        self.memory.save_record(
            "collection_plans",
            "woodland_nursery",
            {
                "collection": "Woodland Nursery",
                "products": ["Clipart", "Digital Paper", "Wall Art"],
                "roadmap": {
                    "products_planned": ["Clipart", "Digital Paper", "Wall Art", "Milestone Cards"],
                    "products_completed": ["Clipart", "Digital Paper"],
                    "products_remaining": ["Wall Art", "Milestone Cards"],
                    "estimated_collection_revenue": 240,
                },
                "collection_score": {
                    "cross_sell_potential": 94,
                    "brand_consistency": 92,
                    "total": 91,
                },
            },
        )

    def dashboard(self):
        return ExecutiveDashboardEngine(memory=self.memory, queue_manager=self.queue).build()

    def test_dashboard_metrics(self) -> None:
        dashboard = self.dashboard()

        self.assertEqual(dashboard.executive_summary.products_generated_today, 1)
        self.assertEqual(dashboard.executive_summary.drafts_pending_review, 1)
        self.assertEqual(dashboard.executive_summary.collections_active, 1)
        self.assertEqual(dashboard.executive_summary.products_waiting, 2)
        self.assertEqual(dashboard.executive_summary.average_opportunity_score, 91.67)
        self.assertEqual(dashboard.quality_metrics.creative_score, 92)
        self.assertEqual(dashboard.quality_metrics.merchant_qa, 50)
        self.assertGreater(dashboard.business_metrics.expected_monthly_revenue, 0)

    def test_pipeline_summary(self) -> None:
        dashboard = self.dashboard()
        pipeline = dashboard.production_pipeline

        self.assertEqual(pipeline.opportunity, 3)
        self.assertEqual(pipeline.creative, 1)
        self.assertEqual(pipeline.production, 1)
        self.assertEqual(pipeline.qa, 1)
        self.assertEqual(pipeline.etsy_draft, 1)
        self.assertIn("Products Waiting", pipeline.bottlenecks)

    def test_shop_health(self) -> None:
        dashboard = self.dashboard()

        self.assertEqual(dashboard.shop_health.products_per_category["clipart"], 1)
        self.assertEqual(dashboard.shop_health.products_per_collection["Woodland Nursery"], 3)
        self.assertEqual(dashboard.shop_health.seasonal_vs_evergreen["Evergreen"], 1)
        self.assertEqual(dashboard.shop_health.portfolio_diversity, "Growing")

    def test_quality_metrics_and_alerts(self) -> None:
        dashboard = self.dashboard()
        alert_types = {alert.alert_type for alert in dashboard.alerts}

        self.assertEqual(dashboard.quality_metrics.seo_score, 74)
        self.assertEqual(dashboard.quality_metrics.thumbnail_score, 73)
        self.assertGreater(dashboard.quality_metrics.reject_rate, 0)
        self.assertIn("Collection incomplete", alert_types)
        self.assertIn("Low thumbnail score", alert_types)
        self.assertIn("Weak SEO", alert_types)
        self.assertIn("Poor merchant QA", alert_types)
        self.assertIn("Trend emerging", alert_types)

    def test_top_opportunities(self) -> None:
        dashboard = self.dashboard()

        self.assertEqual(len(dashboard.top_opportunities), 3)
        self.assertEqual(dashboard.top_opportunities[0].rank, 1)
        self.assertEqual(dashboard.top_opportunities[0].score, 96)
        self.assertEqual(dashboard.top_opportunities[0].product, "Opportunity 1")

    def test_collection_health(self) -> None:
        dashboard = self.dashboard()
        row = dashboard.collection_health[0]

        self.assertEqual(row.collection_name, "Woodland Nursery")
        self.assertEqual(row.completion_percent, 50)
        self.assertEqual(row.products, 4)
        self.assertEqual(row.revenue_estimate, 240)
        self.assertEqual(row.cross_sell_score, 94)
        self.assertEqual(row.brand_consistency, 92)

    def test_daily_report_and_render(self) -> None:
        dashboard = self.dashboard()
        rendered = render_dashboard(dashboard)

        self.assertIn("What happened yesterday", dashboard.daily_report)
        self.assertIn("What Aurora plans today", dashboard.daily_report)
        self.assertIn("Business risks", dashboard.daily_report)
        self.assertIn("Business opportunities", dashboard.daily_report)
        self.assertIn("Recommended actions", dashboard.daily_report)
        self.assertIn("AURORA EXECUTIVE DASHBOARD", rendered)
        self.assertIn("PRODUCTION PIPELINE", rendered)
        self.assertIn("TOP OPPORTUNITIES", rendered)
        self.assertTrue(self.memory.load_record("executive_dashboards", "latest"))


if __name__ == "__main__":
    unittest.main()
