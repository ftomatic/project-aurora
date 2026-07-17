"""Market-aware deterministic pricing for Aurora products."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from project_aurora.merchandising.market_pricing import (
    LIVE_ETSY_MARKET,
    MarketPricingProvider,
)


CONFIGURED_FALLBACK = "CONFIGURED_FALLBACK"


@dataclass(frozen=True, slots=True)
class PricingResult:
    """Resolved price range and launch price for one product."""

    market_low: float
    market_median: float
    market_high: float
    recommended_price: float
    launch_price: float
    mature_price: float
    pricing_strategy: str
    reason: str
    evidence: tuple[str, ...]
    confidence: int
    source: str = CONFIGURED_FALLBACK
    listings_compared: int = 0
    top_seller_median: float = 0.0
    premium_seller_median: float = 0.0
    competition_level: str = ""
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_low": self.market_low,
            "market_median": self.market_median,
            "market_high": self.market_high,
            "recommended_price": self.recommended_price,
            "launch_price": self.launch_price,
            "mature_price": self.mature_price,
            "pricing_strategy": self.pricing_strategy,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "source": self.source,
            "listings_compared": self.listings_compared,
            "top_seller_median": self.top_seller_median,
            "premium_seller_median": self.premium_seller_median,
            "competition_level": self.competition_level,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PricingRange:
    """Configured market price range."""

    low: float
    median: float
    high: float


class PricingEngine:
    """Resolve product-specific launch pricing without live market claims."""

    def __init__(
        self,
        config_path: Path | None = None,
        ranges: dict[str, PricingRange] | None = None,
        market_provider: MarketPricingProvider | None = None,
        minimum_margin: float = 1.0,
        commercial_license_premium: float = 0.5,
        minimum_live_comparables: int = 3,
    ) -> None:
        self._market_provider = market_provider
        self._minimum_live_comparables = minimum_live_comparables
        if ranges is not None:
            self._ranges = ranges
            self._minimum_margin = minimum_margin
            self._premium = commercial_license_premium
            return
        config = _load_pricing_config(
            config_path
            or Path(__file__).resolve().parents[3] / "config" / "pricing.yaml"
        )
        self._ranges = config["ranges"]
        self._minimum_margin = float(config["minimum_margin"])
        self._premium = float(config["commercial_license_premium"])
        self._minimum_live_comparables = int(config.get("minimum_live_comparables", minimum_live_comparables))

    def resolve_price(
        self,
        *,
        product_name: str,
        product_type: str,
        category: str,
        bundle_size: int,
        image_count: int,
        commercial_license: bool,
        competition_level: str,
        demand_score: float,
        confidence_score: float,
        production_cost: float = 0.0,
        target_buyer: str = "",
        artistic_category: str = "",
        keywords: tuple[str, ...] = (),
    ) -> PricingResult:
        """Return the launch price for a production job."""
        live_result = self._resolve_live_market_price(
            product_name=product_name,
            product_type=product_type,
            category=category,
            bundle_size=bundle_size,
            target_buyer=target_buyer,
            artistic_category=artistic_category,
            keywords=keywords,
        )
        if live_result is not None:
            return live_result
        key = _pricing_key(product_name, product_type, category)
        if key not in self._ranges:
            raise RuntimeError(f"No configured pricing range for product type: {product_type or category}.")
        price_range = self._ranges[key]
        score = max(0.0, min(1.0, (demand_score or confidence_score or 0.75)))
        if "high" in competition_level.casefold():
            score -= 0.12
        elif "low" in competition_level.casefold():
            score += 0.08
        if bundle_size >= 8 or image_count >= 8:
            score += 0.08
        if commercial_license:
            score += 0.04
        score = max(0.0, min(1.0, score))
        recommended = price_range.low + (price_range.high - price_range.low) * score
        if commercial_license:
            recommended += self._premium
        floor = production_cost + self._minimum_margin
        recommended = max(recommended, floor)
        mature = min(price_range.high, recommended + 0.75)
        launch = min(mature, max(price_range.low, recommended - 0.50))
        return PricingResult(
            market_low=price_range.low,
            market_median=price_range.median,
            market_high=price_range.high,
            recommended_price=_money(recommended),
            launch_price=_money(launch),
            mature_price=_money(mature),
            pricing_strategy="value_based_launch",
            reason=(
                f"Configured fallback range for {key}; adjusted for demand, "
                f"competition, bundle value, and commercial license."
            ),
            evidence=(f"pricing_range:{key}", "source:configured_fallback"),
            confidence=86,
            source=CONFIGURED_FALLBACK,
            listings_compared=0,
            top_seller_median=0.0,
            premium_seller_median=0.0,
            competition_level=competition_level,
        )

    def _resolve_live_market_price(
        self,
        *,
        product_name: str,
        product_type: str,
        category: str,
        bundle_size: int,
        target_buyer: str,
        artistic_category: str,
        keywords: tuple[str, ...],
    ) -> PricingResult | None:
        if self._market_provider is None:
            return None
        try:
            research = self._market_provider.research_pricing(
                product_name=product_name,
                product_type=product_type,
                category=category,
                keywords=keywords,
                bundle_size=bundle_size,
                target_buyer=target_buyer,
                artistic_category=artistic_category,
            )
        except Exception:
            return None
        if research is None or research.listings_compared < self._minimum_live_comparables:
            return None
        return PricingResult(
            market_low=research.market_low,
            market_median=research.market_median,
            market_high=research.market_high,
            recommended_price=research.market_median,
            launch_price=research.suggested_launch_price,
            mature_price=research.suggested_mature_price,
            pricing_strategy=research.pricing_strategy,
            reason=research.reason,
            evidence=(
                f"source:{LIVE_ETSY_MARKET}",
                f"listings_compared:{research.listings_compared}",
                f"cache_key:{research.cache_key}",
            ),
            confidence=research.pricing_confidence,
            source=LIVE_ETSY_MARKET,
            listings_compared=research.listings_compared,
            top_seller_median=research.top_seller_median,
            premium_seller_median=research.premium_seller_median,
            competition_level=research.competition_level,
        )


def _pricing_key(product_name: str, product_type: str, category: str) -> str:
    lowered = f"{product_name} {product_type} {category}".casefold()
    if "nursery" in lowered and ("wall art" in lowered or "art" in lowered):
        return "nursery art set"
    if "wall art" in lowered or "poster" in lowered or "print" in lowered:
        return "printable wall art"
    if "sticker" in lowered:
        return "sticker sheet"
    if "digital paper" in lowered or "paper" in lowered or "pattern" in lowered:
        return "digital paper"
    if "gift tag" in lowered or "tag" in lowered:
        return "gift tags"
    if "scrapbook" in lowered or "journal" in lowered:
        return "scrapbook kit"
    if "stationery" in lowered or "recipe card" in lowered or "bridal shower" in lowered:
        return "stationery"
    if "clipart" in lowered or "graphics" in lowered:
        return "clipart bundle"
    return product_type.casefold().strip() or category.casefold().strip()


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


def _load_pricing_config(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {
        "minimum_margin": 1.0,
        "commercial_license_premium": 0.5,
        "minimum_live_comparables": 3,
        "ranges": {},
    }
    current_key = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("minimum_margin:"):
            values["minimum_margin"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("commercial_license_premium:"):
            values["commercial_license_premium"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("minimum_live_comparables:"):
            values["minimum_live_comparables"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            current_key = line.strip().removesuffix(":")
            values["ranges"][current_key] = {}
        elif line.startswith("    ") and current_key:
            key, raw = line.strip().split(":", 1)
            values["ranges"][current_key][key] = float(raw.strip())
    values["ranges"] = {
        key: PricingRange(
            low=float(record["low"]),
            median=float(record["median"]),
            high=float(record["high"]),
        )
        for key, record in values["ranges"].items()
    }
    return values
