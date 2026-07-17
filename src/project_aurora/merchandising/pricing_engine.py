"""Market-aware deterministic pricing for Aurora products."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


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
        minimum_margin: float = 1.0,
        commercial_license_premium: float = 0.5,
    ) -> None:
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
    ) -> PricingResult:
        """Return the launch price for a production job."""
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
