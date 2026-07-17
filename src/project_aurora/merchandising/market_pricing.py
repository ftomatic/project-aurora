"""Live market pricing research models and Etsy provider."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Protocol
from urllib.parse import quote

from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.storage.memory_manager import MemoryManager


LIVE_ETSY_MARKET = "LIVE_ETSY_MARKET"
MARKET_PRICING_COLLECTION = "market_pricing_research"


@dataclass(frozen=True, slots=True)
class ComparableListing:
    """One comparable Etsy listing used for market pricing."""

    title: str
    price: float
    url: str = ""
    bestseller: bool = False
    review_count: int = 0
    rating: float = 0.0
    popularity_signal: float = 0.0
    bundle_size: int | None = None
    commercial_use: bool | None = None
    product_type: str = ""
    niche: str = ""
    audience: str = ""
    artistic_category: str = ""
    similarity_score: int = 0
    source: str = "etsy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "price": self.price,
            "url": self.url,
            "bestseller": self.bestseller,
            "review_count": self.review_count,
            "rating": self.rating,
            "popularity_signal": self.popularity_signal,
            "bundle_size": self.bundle_size,
            "commercial_use": self.commercial_use,
            "product_type": self.product_type,
            "niche": self.niche,
            "audience": self.audience,
            "artistic_category": self.artistic_category,
            "similarity_score": self.similarity_score,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComparableListing":
        return cls(
            title=str(data.get("title", "")),
            price=float(data.get("price", 0.0)),
            url=str(data.get("url", "")),
            bestseller=bool(data.get("bestseller", False)),
            review_count=int(data.get("review_count", 0) or 0),
            rating=float(data.get("rating", 0.0) or 0.0),
            popularity_signal=float(data.get("popularity_signal", 0.0) or 0.0),
            bundle_size=_optional_int(data.get("bundle_size")),
            commercial_use=_optional_bool(data.get("commercial_use")),
            product_type=str(data.get("product_type", "")),
            niche=str(data.get("niche", "")),
            audience=str(data.get("audience", "")),
            artistic_category=str(data.get("artistic_category", "")),
            similarity_score=int(data.get("similarity_score", 0) or 0),
            source=str(data.get("source", "etsy")),
        )


@dataclass(frozen=True, slots=True)
class MarketPricingResearch:
    """Comparable market set and derived pricing statistics."""

    product_name: str
    product_type: str
    category: str
    keywords: tuple[str, ...]
    listings_compared: int
    market_low: float
    market_median: float
    market_high: float
    top_seller_median: float
    premium_seller_median: float
    competition_level: str
    suggested_launch_price: float
    suggested_mature_price: float
    pricing_confidence: int
    pricing_strategy: str
    reason: str
    source: str
    comparables: tuple[ComparableListing, ...]
    cache_key: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "product_type": self.product_type,
            "category": self.category,
            "keywords": list(self.keywords),
            "listings_compared": self.listings_compared,
            "market_low": self.market_low,
            "market_median": self.market_median,
            "market_high": self.market_high,
            "top_seller_median": self.top_seller_median,
            "premium_seller_median": self.premium_seller_median,
            "competition_level": self.competition_level,
            "suggested_launch_price": self.suggested_launch_price,
            "suggested_mature_price": self.suggested_mature_price,
            "pricing_confidence": self.pricing_confidence,
            "pricing_strategy": self.pricing_strategy,
            "reason": self.reason,
            "source": self.source,
            "comparables": [item.to_dict() for item in self.comparables],
            "cache_key": self.cache_key,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketPricingResearch":
        return cls(
            product_name=str(data["product_name"]),
            product_type=str(data["product_type"]),
            category=str(data["category"]),
            keywords=tuple(str(item) for item in data.get("keywords", ())),
            listings_compared=int(data["listings_compared"]),
            market_low=float(data["market_low"]),
            market_median=float(data["market_median"]),
            market_high=float(data["market_high"]),
            top_seller_median=float(data["top_seller_median"]),
            premium_seller_median=float(data["premium_seller_median"]),
            competition_level=str(data["competition_level"]),
            suggested_launch_price=float(data["suggested_launch_price"]),
            suggested_mature_price=float(data["suggested_mature_price"]),
            pricing_confidence=int(data["pricing_confidence"]),
            pricing_strategy=str(data["pricing_strategy"]),
            reason=str(data["reason"]),
            source=str(data["source"]),
            comparables=tuple(
                ComparableListing.from_dict(item)
                for item in data.get("comparables", ())
                if isinstance(item, dict)
            ),
            cache_key=str(data["cache_key"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )


class MarketPricingProvider(Protocol):
    """Provider interface for live market pricing research."""

    def research_pricing(
        self,
        *,
        product_name: str,
        product_type: str,
        category: str,
        keywords: tuple[str, ...],
        bundle_size: int,
        target_buyer: str = "",
        artistic_category: str = "",
    ) -> MarketPricingResearch | None:
        """Return market pricing evidence, or None when unavailable."""


class EtsyMarketPricingProvider:
    """Research comparable active Etsy listings through the Open API."""

    def __init__(
        self,
        client: EtsyClient,
        memory: MemoryManager | None = None,
        cache_ttl_hours: int = 24,
        minimum_comparables: int = 3,
    ) -> None:
        self._client = client
        self._memory = memory
        self._cache_ttl = timedelta(hours=cache_ttl_hours)
        self._minimum_comparables = minimum_comparables

    def research_pricing(
        self,
        *,
        product_name: str,
        product_type: str,
        category: str,
        keywords: tuple[str, ...],
        bundle_size: int,
        target_buyer: str = "",
        artistic_category: str = "",
    ) -> MarketPricingResearch | None:
        """Search Etsy and return a comparable market set."""
        cache_key = pricing_cache_key(product_type, category, keywords or tuple(product_name.split()))
        cached = self._load_cached(cache_key)
        if cached is not None:
            return cached

        query = _search_query(product_name, product_type, category, keywords)
        response = self._client.get_json(
            f"/listings/active?keywords={quote(query)}&limit=100"
        )
        raw_results = response.get("results", ())
        if not isinstance(raw_results, list):
            return None
        comparables = tuple(
            sorted(
                (
                    comparable
                    for item in raw_results
                    if isinstance(item, dict)
                    for comparable in (
                        comparable_from_etsy_record(
                            item,
                            product_name=product_name,
                            product_type=product_type,
                            category=category,
                            keywords=keywords,
                            bundle_size=bundle_size,
                            target_buyer=target_buyer,
                            artistic_category=artistic_category,
                        ),
                    )
                    if comparable is not None
                ),
                key=lambda item: (-item.similarity_score, -item.popularity_signal, item.price),
            )
        )
        if len(comparables) < self._minimum_comparables:
            return None
        research = build_market_research(
            product_name=product_name,
            product_type=product_type,
            category=category,
            keywords=keywords,
            comparables=comparables,
            cache_key=cache_key,
        )
        self._save_cached(research)
        return research

    def _load_cached(self, cache_key: str) -> MarketPricingResearch | None:
        if self._memory is None:
            return None
        try:
            record = self._memory.load_record(MARKET_PRICING_COLLECTION, cache_key)
        except FileNotFoundError:
            return None
        research = MarketPricingResearch.from_dict(record)
        if datetime.now() - research.created_at > self._cache_ttl:
            return None
        return research

    def _save_cached(self, research: MarketPricingResearch) -> None:
        if self._memory is None:
            return
        self._memory.save_record(
            MARKET_PRICING_COLLECTION,
            research.cache_key,
            research.to_dict(),
        )


def build_market_research(
    *,
    product_name: str,
    product_type: str,
    category: str,
    keywords: tuple[str, ...],
    comparables: tuple[ComparableListing, ...],
    cache_key: str,
) -> MarketPricingResearch:
    """Calculate market pricing statistics from comparable listings."""
    prices = sorted(item.price for item in comparables)
    top_prices = [
        item.price
        for item in comparables
        if item.bestseller or item.review_count >= 100 or item.popularity_signal >= 80
    ]
    premium_prices = [
        item.price
        for item in comparables
        if item.rating >= 4.8 and item.review_count >= 50
    ]
    market_median = float(median(prices))
    top_median = float(median(top_prices or prices))
    premium_median = float(median(premium_prices or top_prices or prices))
    competition = _competition_level(comparables)
    if competition == "High":
        launch = market_median * 0.94
        strategy = "competitive_launch"
        reason = "Strong competition. Launch slightly below median using comparable Etsy evidence."
    elif competition == "Low":
        launch = min(top_median, market_median * 1.04)
        strategy = "market_confident_launch"
        reason = "Lower competition. Launch near market median using comparable Etsy evidence."
    else:
        launch = market_median * 0.96
        strategy = "balanced_market_launch"
        reason = "Moderate competition. Launch just below median from comparable Etsy listings."
    mature = max(launch, min(premium_median, top_median * 1.02))
    return MarketPricingResearch(
        product_name=product_name,
        product_type=product_type,
        category=category,
        keywords=keywords,
        listings_compared=len(comparables),
        market_low=_money(prices[0]),
        market_median=_money(market_median),
        market_high=_money(prices[-1]),
        top_seller_median=_money(top_median),
        premium_seller_median=_money(premium_median),
        competition_level=competition,
        suggested_launch_price=_money(launch),
        suggested_mature_price=_money(mature),
        pricing_confidence=min(98, 72 + len(comparables)),
        pricing_strategy=strategy,
        reason=reason,
        source=LIVE_ETSY_MARKET,
        comparables=comparables,
        cache_key=cache_key,
    )


def comparable_from_etsy_record(
    record: dict[str, Any],
    *,
    product_name: str,
    product_type: str,
    category: str,
    keywords: tuple[str, ...],
    bundle_size: int,
    target_buyer: str = "",
    artistic_category: str = "",
) -> ComparableListing | None:
    """Convert an Etsy listing record into a comparable when it is relevant."""
    title = str(record.get("title") or "")
    description = str(record.get("description") or "")
    text = f"{title} {description}".casefold()
    price = _price_from_record(record)
    if price <= 0:
        return None
    expected_key = product_type_key(product_name, product_type, category)
    actual_key = product_type_key(title, str(record.get("product_type", "")), str(record.get("category", "")))
    if actual_key != expected_key:
        return None
    if _contains_unrelated_product_type(text, expected_key):
        return None
    expected_tokens = _important_tokens(product_name, category, keywords)
    actual_tokens = _expanded_market_tokens(set(_tokens(title)))
    niche_score = _token_overlap_score(expected_tokens, actual_tokens)
    if niche_score < 15:
        return None
    actual_bundle_size = _bundle_size_from_text(text)
    if actual_bundle_size and bundle_size >= 4:
        ratio = actual_bundle_size / max(1, bundle_size)
        if ratio < 0.35 or ratio > 3.0:
            return None
    audience_score = _token_overlap_score(set(_tokens(target_buyer)), set(_tokens(text))) if target_buyer else 0
    art_score = _token_overlap_score(set(_tokens(artistic_category)), set(_tokens(text))) if artistic_category else 0
    similarity = min(100, 55 + niche_score + min(10, audience_score) + min(10, art_score))
    if similarity < 70:
        return None
    review_count = int(record.get("num_favorers") or record.get("review_count") or record.get("reviews") or 0)
    rating = float(record.get("rating") or record.get("shop_average_rating") or 0.0)
    bestseller = bool(record.get("bestseller") or record.get("is_bestseller"))
    popularity = min(100.0, review_count / 3 + (10 if bestseller else 0) + max(0.0, rating - 4.0) * 10)
    return ComparableListing(
        title=title,
        price=price,
        url=str(record.get("url") or record.get("listing_url") or ""),
        bestseller=bestseller,
        review_count=review_count,
        rating=rating,
        popularity_signal=round(popularity, 2),
        bundle_size=actual_bundle_size,
        commercial_use=("commercial" in text or "commercial use" in text),
        product_type=expected_key,
        niche=" ".join(sorted(_important_tokens(product_name, category, keywords))),
        audience=target_buyer,
        artistic_category=artistic_category,
        similarity_score=similarity,
    )


def pricing_cache_key(product_type: str, subcategory: str, keywords: tuple[str, ...]) -> str:
    """Return a stable 24-hour market pricing cache key."""
    keyword_part = "_".join(sorted({slugify(item) for item in keywords if item.strip()}))
    return "_".join(
        item
        for item in (
            slugify(product_type),
            slugify(subcategory),
            keyword_part,
        )
        if item
    )[:180]


def product_type_key(product_name: str, product_type: str, category: str) -> str:
    """Normalize a product into a broad comparable product-type key."""
    text = f"{product_name} {product_type} {category}".casefold()
    if "digital paper" in text or "scrapbook paper" in text or "pattern" in text:
        return "digital paper"
    if "clipart" in text or "clip art" in text or "graphics" in text:
        return "clipart"
    if "sticker" in text:
        return "sticker sheet"
    if "wall art" in text or "poster" in text or "print" in text:
        return "wall art"
    if "invitation" in text:
        return "invitation"
    if "tag" in text:
        return "gift tags"
    if "stationery" in text or "bridal shower" in text:
        return "stationery"
    return slugify(product_type or category)


def slugify(value: str) -> str:
    """Return a safe lowercase slug."""
    return "_".join(_tokens(value))


def _search_query(product_name: str, product_type: str, category: str, keywords: tuple[str, ...]) -> str:
    query_tokens = list(dict.fromkeys((*_tokens(product_name), *_tokens(product_type), *_tokens(category), *keywords)))
    return " ".join(str(token).replace("_", " ") for token in query_tokens[:8])


def _price_from_record(record: dict[str, Any]) -> float:
    price = record.get("price")
    if isinstance(price, dict):
        amount = price.get("amount")
        divisor = price.get("divisor") or 1
        if amount is not None:
            return _money(float(amount) / float(divisor))
    if isinstance(price, int | float | str):
        try:
            return _money(float(str(price).replace("$", "")))
        except ValueError:
            return 0.0
    return 0.0


def _bundle_size_from_text(text: str) -> int | None:
    matches = re.findall(r"\b(\d{1,3})\s*(?:png|papers|patterns|sheets|prints|files|clipart|images)\b", text)
    if not matches:
        return None
    return max(int(match) for match in matches)


def _contains_unrelated_product_type(text: str, expected_key: str) -> bool:
    groups = {
        "digital paper": ("wall art", "poster", "clipart", "sticker", "invitation"),
        "clipart": ("wall art", "poster", "digital paper", "invitation"),
        "wall art": ("clipart", "digital paper", "sticker sheet", "invitation"),
        "sticker sheet": ("wall art", "digital paper", "invitation"),
        "invitation": ("wall art", "clipart", "digital paper", "sticker"),
    }
    return any(term in text for term in groups.get(expected_key, ()))


def _important_tokens(product_name: str, category: str, keywords: tuple[str, ...]) -> set[str]:
    stop = {"digital", "printable", "bundle", "set", "png", "art", "paper", "clipart", "wall", "the"}
    return {
        token
        for token in (*_tokens(product_name), *_tokens(category), *tuple(_tokens(" ".join(keywords))))
        if token not in stop and len(token) > 2
    }


def _expanded_market_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    synonym_groups = (
        {"woodland", "forest"},
        {"winter", "christmas", "holiday"},
        {"baby", "nursery"},
        {"floral", "flower", "botanical"},
    )
    for group in synonym_groups:
        if expanded & group:
            expanded.update(group)
    return expanded


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^a-z0-9]+", value.casefold()) if token)


def _token_overlap_score(expected: set[str], actual: set[str]) -> int:
    if not expected:
        return 0
    return int((len(expected & actual) / len(expected)) * 35)


def _competition_level(comparables: tuple[ComparableListing, ...]) -> str:
    if len(comparables) >= 30:
        return "High"
    if len(comparables) >= 10:
        return "Moderate"
    return "Low"


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _money(value: float) -> float:
    return round(value + 1e-9, 2)
