"""Tests for Sprint 29 live Etsy market pricing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.merchandising.market_pricing import (  # noqa: E402
    LIVE_ETSY_MARKET,
    EtsyMarketPricingProvider,
    MarketPricingResearch,
    build_market_research,
    comparable_from_etsy_record,
)
from project_aurora.merchandising.pricing_engine import (  # noqa: E402
    CONFIGURED_FALLBACK,
    PricingEngine,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class FakeEtsyClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[str] = []

    def get_json(self, path: str) -> dict[str, object]:
        self.calls.append(path)
        return self.response


def etsy_listing(
    title: str,
    price: float,
    *,
    reviews: int = 10,
    rating: float = 4.8,
    bestseller: bool = False,
) -> dict[str, object]:
    return {
        "title": title,
        "price": price,
        "review_count": reviews,
        "rating": rating,
        "bestseller": bestseller,
        "url": f"https://example.test/{title.replace(' ', '-')}",
    }


class LiveMarketPricingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(
            CSVStorage(base_path=Path(self.temp_dir.name) / "memory")
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_successful_live_pricing_uses_etsy_market_evidence(self) -> None:
        client = FakeEtsyClient(
            {
                "results": [
                    etsy_listing("Winter Woodland Digital Paper 12 PNG Papers", 3.99, reviews=18),
                    etsy_listing("Christmas Woodland Digital Paper 10 Pattern Bundle", 4.99, reviews=210, bestseller=True),
                    etsy_listing("Forest Animal Digital Paper 12 Scrapbook Papers", 5.49, reviews=90),
                    etsy_listing("Woodland Scrapbook Paper 8 Digital Papers", 6.49, reviews=65),
                    etsy_listing("Winter Pattern Bundle Woodland Digital Paper", 4.49, reviews=40),
                ]
            }
        )
        provider = EtsyMarketPricingProvider(client=client, memory=self.memory)
        result = PricingEngine(market_provider=provider).resolve_price(
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            bundle_size=12,
            image_count=4,
            commercial_license=True,
            competition_level="Medium",
            demand_score=0.9,
            confidence_score=0.9,
            keywords=("winter", "woodland", "digital", "paper"),
            target_buyer="crafters scrapbook buyers",
            artistic_category="watercolor woodland",
        )

        self.assertEqual(result.source, LIVE_ETSY_MARKET)
        self.assertEqual(result.listings_compared, 5)
        self.assertEqual(result.market_low, 3.99)
        self.assertEqual(result.market_high, 6.49)
        self.assertEqual(result.market_median, 4.99)
        self.assertNotEqual(result.launch_price, 1.99)
        self.assertIn("comparable Etsy", result.reason)

    def test_fallback_pricing_when_etsy_research_fails(self) -> None:
        class BrokenProvider:
            def research_pricing(self, **_kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("Etsy unavailable")

        result = PricingEngine(market_provider=BrokenProvider()).resolve_price(
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            bundle_size=12,
            image_count=4,
            commercial_license=True,
            competition_level="Medium",
            demand_score=0.8,
            confidence_score=0.8,
        )

        self.assertEqual(result.source, CONFIGURED_FALLBACK)
        self.assertEqual(result.listings_compared, 0)
        self.assertNotEqual(result.launch_price, 1.99)

    def test_cached_pricing_avoids_repeated_etsy_requests(self) -> None:
        client = FakeEtsyClient(
            {
                "results": [
                    etsy_listing("Winter Woodland Digital Paper 12 PNG Papers", 3.99),
                    etsy_listing("Christmas Woodland Digital Paper 10 Pattern Bundle", 4.99),
                    etsy_listing("Forest Animal Digital Paper 12 Scrapbook Papers", 5.49),
                ]
            }
        )
        provider = EtsyMarketPricingProvider(client=client, memory=self.memory)

        first = provider.research_pricing(
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland", "digital", "paper"),
            bundle_size=12,
        )
        second = provider.research_pricing(
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland", "digital", "paper"),
            bundle_size=12,
        )

        self.assertIsInstance(first, MarketPricingResearch)
        self.assertIsInstance(second, MarketPricingResearch)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(first.cache_key, second.cache_key)

    def test_similar_product_matching_accepts_relevant_digital_paper(self) -> None:
        comparable = comparable_from_etsy_record(
            etsy_listing("Christmas Woodland Digital Paper 12 Scrapbook Papers", 4.99),
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland", "digital", "paper"),
            bundle_size=12,
        )

        self.assertIsNotNone(comparable)
        self.assertGreaterEqual(comparable.similarity_score, 70)

    def test_unrelated_listing_is_rejected(self) -> None:
        wall_art = comparable_from_etsy_record(
            etsy_listing("Winter Woodland Wall Art Printable Poster", 7.99),
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland", "digital", "paper"),
            bundle_size=12,
        )
        clipart = comparable_from_etsy_record(
            etsy_listing("Woodland Animal Clipart PNG Bundle", 6.99),
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland", "digital", "paper"),
            bundle_size=12,
        )

        self.assertIsNone(wall_art)
        self.assertIsNone(clipart)

    def test_launch_price_differs_by_market_conditions(self) -> None:
        low_market = build_market_research(
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland"),
            comparables=tuple(
                comparable_from_etsy_record(
                    etsy_listing(f"Winter Woodland Digital Paper {index} 12 Papers", price),
                    product_name="Winter Woodland Digital Paper",
                    product_type="digital paper",
                    category="digital paper",
                    keywords=("winter", "woodland", "digital", "paper"),
                    bundle_size=12,
                )
                for index, price in enumerate((2.99, 3.49, 3.99), start=1)
            ),
            cache_key="low",
        )
        high_market = build_market_research(
            product_name="Winter Woodland Digital Paper",
            product_type="digital paper",
            category="digital paper",
            keywords=("winter", "woodland"),
            comparables=tuple(
                comparable_from_etsy_record(
                    etsy_listing(f"Winter Woodland Digital Paper {index} 12 Papers", price),
                    product_name="Winter Woodland Digital Paper",
                    product_type="digital paper",
                    category="digital paper",
                    keywords=("winter", "woodland", "digital", "paper"),
                    bundle_size=12,
                )
                for index, price in enumerate((5.99, 6.49, 6.99), start=1)
            ),
            cache_key="high",
        )

        self.assertNotEqual(
            low_market.suggested_launch_price,
            high_market.suggested_launch_price,
        )


if __name__ == "__main__":
    unittest.main()
