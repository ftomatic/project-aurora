"""Tests for Sprint 39 Business Intelligence and Learning Engine."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.business_intelligence import (  # noqa: E402
    ABTestExperiment,
    BusinessIntelligenceEngine,
    ListingRecord,
    PerformanceMetrics,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class BusinessIntelligenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(CSVStorage(base_path=Path(self.temp_dir.name)))
        self.engine = BusinessIntelligenceEngine(
            memory=self.memory,
            minimum_confidence=80,
            minimum_sample_size=3,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def listing(
        self,
        listing_id: str,
        *,
        style: str,
        category: str,
        collection: str,
        price: float = 5.99,
        bundle_size: int = 12,
        thumbnail: str = "grid",
        blueprint: str = "storybook",
    ) -> ListingRecord:
        return ListingRecord(
            listing_id=listing_id,
            product_name=f"{collection} {category} {listing_id}",
            collection_id=collection,
            blueprint=blueprint,
            creation_date=datetime(2026, 7, 1),
            publish_date=datetime(2026, 7, 2),
            price=price,
            discounts=(),
            marketplace="Etsy",
            status="PUBLISHED",
            category=category,
            style=style,
            bundle_size=bundle_size,
            thumbnail_layout=thumbnail,
        )

    def record(
        self,
        listing_id: str,
        *,
        style: str = "Watercolor",
        category: str = "wall art",
        collection: str = "Woodland Nursery",
        views: int = 100,
        favorites: int = 20,
        orders: int = 8,
        revenue: float = 48,
        bundle_size: int = 12,
        thumbnail: str = "lifestyle",
    ) -> None:
        listing = self.listing(
            listing_id,
            style=style,
            category=category,
            collection=collection,
            bundle_size=bundle_size,
            thumbnail=thumbnail,
        )
        self.engine.record_listing(listing)
        self.engine.record_performance(
            listing_id,
            PerformanceMetrics(
                views=views,
                favorites=favorites,
                orders=orders,
                revenue=revenue,
                refunds=0,
                downloads=orders,
                traffic_source="Etsy Search",
            ),
            research_score=91,
            creative_score=92,
            thumbnail_score=88,
            seo_score=85,
            merchant_qa=100,
        )

    def seed_performance(self) -> None:
        self.record("w1", style="Watercolor", category="wall art", collection="Woodland Nursery", orders=10, revenue=80, favorites=30, bundle_size=24)
        self.record("w2", style="Watercolor", category="clipart", collection="Woodland Nursery", orders=8, revenue=72, favorites=28, bundle_size=24)
        self.record("w3", style="Watercolor", category="digital paper", collection="Woodland Nursery", orders=7, revenue=60, favorites=25, bundle_size=24)
        self.record("f1", style="Flat Vector", category="floral clipart", collection="Generic Floral", orders=2, revenue=12, favorites=5, bundle_size=12, thumbnail="flat")
        self.record("f2", style="Flat Vector", category="floral clipart", collection="Generic Floral", orders=1, revenue=6, favorites=3, bundle_size=12, thumbnail="flat")

    def test_performance_metrics_recorded(self) -> None:
        self.record("listing-1")

        saved = self.memory.load_record("business_performance", "listing-1")
        score = self.memory.load_record("business_score_evolution", "listing-1")

        self.assertEqual(saved["metrics"]["views"], 100)
        self.assertEqual(saved["metrics"]["orders"], 8)
        self.assertEqual(saved["metrics"]["conversion_rate"], 8)
        self.assertEqual(saved["metrics"]["average_order_value"], 6)
        self.assertGreater(score["performance_score"], 0)

    def test_historical_metrics_preserved(self) -> None:
        listing = self.listing("listing-2", style="Watercolor", category="clipart", collection="Woodland")
        self.engine.record_listing(listing)
        self.engine.record_performance("listing-2", PerformanceMetrics(views=100, favorites=10, orders=4, revenue=20, refunds=0, downloads=4, traffic_source="Etsy"))
        self.engine.record_performance("listing-2", PerformanceMetrics(views=200, favorites=30, orders=12, revenue=72, refunds=0, downloads=12, traffic_source="Etsy"))

        history = self.memory.list_records("business_performance_history")
        latest = self.memory.load_record("business_performance", "listing-2")

        self.assertEqual(len(history), 2)
        self.assertEqual(latest["metrics"]["orders"], 12)

    def test_pattern_discovery(self) -> None:
        self.seed_performance()

        patterns = self.engine.discover_patterns()
        observations = " ".join(pattern.observation for pattern in patterns)

        self.assertIn("Watercolor", observations)
        self.assertTrue(any("Larger bundles" in pattern.observation for pattern in patterns))
        self.assertTrue(self.memory.list_records("business_patterns"))

    def test_ab_test_winner(self) -> None:
        experiment = ABTestExperiment(
            experiment_id="thumb-test",
            listing_id="listing-1",
            hypothesis="Lifestyle mockups increase favorites.",
            variant_a="Grid thumbnail",
            variant_b="Lifestyle thumbnail",
            metric="favorites",
            variant_a_value=10,
            variant_b_value=18,
            sample_size=30,
        )

        self.engine.create_experiment(experiment)
        evaluated = self.engine.evaluate_experiment("thumb-test")

        self.assertEqual(evaluated.winner, "B")
        self.assertEqual(evaluated.status, "COMPLETE")
        self.assertGreater(evaluated.confidence, 80)

    def test_recommendations_generated(self) -> None:
        self.seed_performance()

        recommendations = self.engine.generate_recommendations()
        text = " ".join(item.recommendation for item in recommendations)

        self.assertIn("Increase Watercolor products", text)
        self.assertIn("Create more Woodland Nursery collection extensions", text)
        self.assertTrue(all(item.supporting_evidence for item in recommendations))

    def test_learning_updates_only_above_confidence_threshold(self) -> None:
        self.seed_performance()

        proposals = self.engine.propose_strategy_adjustments()

        self.assertTrue(any(proposal.approved_for_application for proposal in proposals))
        self.assertTrue(
            all(
                not proposal.approved_for_application
                or (proposal.confidence >= 80 and proposal.sample_size >= 3)
                for proposal in proposals
            )
        )

    def test_learning_does_not_apply_with_low_sample_size(self) -> None:
        engine = BusinessIntelligenceEngine(
            memory=self.memory,
            minimum_confidence=80,
            minimum_sample_size=10,
        )
        self.seed_performance()

        proposals = engine.propose_strategy_adjustments()

        self.assertTrue(proposals)
        self.assertTrue(all(not proposal.approved_for_application for proposal in proposals))

    def test_collection_analytics_and_executive_insights(self) -> None:
        self.seed_performance()

        analytics = self.engine.collection_analytics()
        insights = self.engine.executive_insights()

        self.assertEqual(analytics[0].collection_id, "Woodland Nursery")
        self.assertGreater(analytics[0].revenue, 0)
        self.assertEqual(insights.top_performing_style, "Watercolor")
        self.assertEqual(insights.highest_revenue_collection, "Woodland Nursery")
        self.assertTrue(self.memory.load_record("business_executive_insights", "latest"))


if __name__ == "__main__":
    unittest.main()
