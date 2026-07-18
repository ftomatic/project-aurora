"""Tests for Sprint 40 AI COO."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.ai_coo import AICOOEngine  # noqa: E402
from project_aurora.ai_coo.coo_engine import render_daily_business_plan  # noqa: E402
from project_aurora.ai_coo.seasonal_calendar import current_calendar_focus, merchandising_calendar  # noqa: E402
from project_aurora.business_intelligence import (  # noqa: E402
    BusinessIntelligenceEngine,
    ListingRecord,
    PerformanceMetrics,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    FAILED,
    READY,
    ProductionQueueManager,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class AICOOTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        self._seed_queue()
        self._seed_dashboard_memory()
        self._seed_bi()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_queue(self) -> None:
        for index in range(3):
            self.queue.add_job(
                priority="High",
                product_name=f"Evergreen Clipart {index}",
                category="clipart",
                style="Watercolor",
                seasonal_theme="Evergreen" if index == 0 else "Christmas",
                keywords=("evergreen", "clipart"),
                confidence_score=0.9,
                estimated_competition="Moderate",
                estimated_demand="High",
                estimated_revenue=160 - index * 10,
                status=READY,
            )
        self.queue.add_job(
            priority="Medium",
            product_name="Failed Merchant QA Product",
            category="wall art",
            style="Flat Vector",
            seasonal_theme="Seasonal",
            keywords=("failed",),
            confidence_score=0.82,
            estimated_competition="High",
            estimated_demand="Moderate",
            estimated_revenue=80,
            status=FAILED,
        )

    def _seed_dashboard_memory(self) -> None:
        today = datetime.now().isoformat()
        self.memory.save_record(
            "production_reports",
            "draft-1",
            {
                "job_id": "draft-1",
                "product": "Draft Product",
                "style": "Watercolor",
                "draft_id": "etsy-1",
                "images": 4,
                "downloads": 4,
                "success": True,
                "created_at": today,
                "metadata": {"price": 2.49},
            },
        )
        self.memory.save_record(
            "collection_plans",
            "woodland",
            {
                "collection": "Woodland Nursery",
                "products": ["Clipart", "Digital Paper"],
                "roadmap": {
                    "products_planned": ["Clipart", "Digital Paper", "Wall Art", "Milestone Cards"],
                    "products_completed": ["Clipart"],
                    "products_remaining": ["Digital Paper", "Wall Art", "Milestone Cards"],
                    "estimated_collection_revenue": 260,
                },
                "collection_score": {
                    "cross_sell_potential": 94,
                    "brand_consistency": 92,
                    "total": 91,
                },
            },
        )
        self.memory.save_record(
            "merchant_preflight",
            "failed",
            {"status": "PREFLIGHT_FAILED", "merchant_qa_status": "FAIL"},
        )
        self.memory.save_record("seo", "weak", {"seo_score": 72})
        self.memory.save_record("image_qa", "thumb", {"results": [{"overall_score": 70}]})
        for index, score in enumerate((96, 91, 88), start=1):
            self.memory.save_record(
                "opportunity_scores",
                f"opp-{index}",
                {
                    "opportunity_id": f"opp-{index}",
                    "product": f"Opportunity {index}",
                    "opportunity_score": score,
                    "expected_revenue": 120,
                    "trend_velocity_score": 90 if index == 1 else 70,
                },
            )

    def _seed_bi(self) -> None:
        bi = BusinessIntelligenceEngine(
            memory=self.memory,
            minimum_confidence=75,
            minimum_sample_size=2,
        )
        for index in range(3):
            listing = ListingRecord(
                listing_id=f"listing-{index}",
                product_name=f"Woodland Listing {index}",
                collection_id="Woodland Nursery",
                blueprint="storybook",
                creation_date=datetime(2026, 7, 1),
                publish_date=datetime(2026, 7, 2),
                price=5.99,
                discounts=(),
                marketplace="Etsy",
                status="PUBLISHED",
                category="clipart",
                style="Watercolor",
                bundle_size=24,
                thumbnail_layout="lifestyle",
            )
            bi.record_listing(listing)
            bi.record_performance(
                listing.listing_id,
                PerformanceMetrics(
                    views=100,
                    favorites=20,
                    orders=8,
                    revenue=48,
                    refunds=0,
                    downloads=8,
                    traffic_source="Etsy Search",
                ),
                research_score=90,
                creative_score=92,
                thumbnail_score=88,
                seo_score=86,
                merchant_qa=100,
            )

    def engine(self, **overrides: int) -> AICOOEngine:
        values = {
            "image_generation_budget": 1,
            "api_usage_budget": 4,
            "publishing_capacity": 1,
            "review_time_minutes": 60,
        }
        values.update(overrides)
        return AICOOEngine(
            memory=self.memory,
            queue_manager=self.queue,
            business_intelligence=BusinessIntelligenceEngine(
                memory=self.memory,
                minimum_confidence=75,
                minimum_sample_size=2,
            ),
            **values,
        )

    def test_daily_business_plan_created(self) -> None:
        plan = self.engine().create_daily_plan(date(2026, 7, 18))

        self.assertEqual(plan.plan_date.isoformat(), "2026-07-18")
        self.assertTrue(plan.production_goals)
        self.assertTrue(plan.publishing_goals)
        self.assertTrue(plan.collection_goals)
        self.assertTrue(plan.research_goals)
        self.assertTrue(plan.improvement_goals)
        self.assertTrue(plan.selected_tasks)
        self.assertTrue(self.memory.load_record("ai_coo_daily_plans", "latest"))

    def test_priority_engine_scores_high_value_tasks_first(self) -> None:
        plan = self.engine(image_generation_budget=2, publishing_capacity=2).create_daily_plan(date(2026, 7, 18))
        scores = [task.priority_score for task in plan.selected_tasks]

        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertIn(
            plan.selected_tasks[0].category,
            {"Collections", "Publishing", "Improvement", "Production", "Research"},
        )

    def test_workload_optimization_avoids_overload(self) -> None:
        plan = self.engine(image_generation_budget=1, api_usage_budget=2, publishing_capacity=1, review_time_minutes=40).create_daily_plan(date(2026, 7, 18))

        self.assertFalse(plan.resource_plan.overloaded)
        self.assertLessEqual(plan.resource_plan.selected_image_tasks, 1)
        self.assertLessEqual(plan.resource_plan.selected_api_tasks, 2)
        self.assertLessEqual(plan.resource_plan.selected_publishing_tasks, 1)
        self.assertLessEqual(plan.resource_plan.selected_review_minutes, 40)

    def test_seasonal_calendar_focus(self) -> None:
        events = merchandising_calendar()
        july_focus = {event.name for event in current_calendar_focus(7)}

        self.assertIn("Christmas", {event.name for event in events})
        self.assertIn("Halloween", {event.name for event in events})
        self.assertIn("Halloween", july_focus)
        self.assertIn("Christmas", july_focus)

    def test_backlog_management(self) -> None:
        plan = self.engine(image_generation_budget=1, api_usage_budget=1, publishing_capacity=1, review_time_minutes=20).create_daily_plan(date(2026, 7, 18))
        backlog = plan.backlog.to_dict()

        self.assertIn("collections", backlog)
        self.assertIn("products", backlog)
        self.assertIn("experiments", backlog)
        self.assertIn("research", backlog)
        self.assertIn("marketing", backlog)
        self.assertIn("technical_debt", backlog)

    def test_business_risks_identified(self) -> None:
        plan = self.engine().create_daily_plan(date(2026, 7, 18))
        risk_types = {risk.risk_type for risk in plan.business_risks}

        self.assertIn("Collection imbalance", risk_types)
        self.assertIn("Price inconsistency", risk_types)
        self.assertIn("Low category diversity", risk_types)

    def test_executive_report_and_business_journal(self) -> None:
        plan = self.engine().create_daily_plan(date(2026, 7, 18))
        report = plan.executive_report.render()
        journal = self.memory.list_records("business_journal")

        self.assertIn("Completed Yesterday", report)
        self.assertIn("Today's Plan", report)
        self.assertIn("Risks", report)
        self.assertIn("Opportunities", report)
        self.assertIn("Recommendations", report)
        self.assertGreater(plan.executive_report.confidence, 50)
        self.assertTrue(journal)

    def test_render_daily_business_plan(self) -> None:
        plan = self.engine().create_daily_plan(date(2026, 7, 18))
        rendered = render_daily_business_plan(plan)

        self.assertIn("AI COO DAILY BUSINESS PLAN", rendered)
        self.assertIn("Production Goals", rendered)
        self.assertIn("Publishing Goals", rendered)
        self.assertIn("Resources", rendered)
        self.assertIn("Status\nSUCCESS", rendered)


if __name__ == "__main__":
    unittest.main()
