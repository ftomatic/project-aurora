"""Collection Intelligence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class CollectionOpportunity:
    """A researched collection opportunity."""

    name: str
    theme: str
    audience: str
    season: str
    aesthetics: tuple[str, ...]
    customer_intent: str
    complementary_products: tuple[str, ...]
    source: str = "Athena Local Collection Research"

    def __post_init__(self) -> None:
        for field_name in ("name", "theme", "audience", "season", "customer_intent"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} cannot be empty.")
        object.__setattr__(self, "aesthetics", tuple(self.aesthetics))
        object.__setattr__(self, "complementary_products", tuple(self.complementary_products))


@dataclass(frozen=True, slots=True)
class CollectionScore:
    """Commercial score dimensions for a collection."""

    trend_score: int
    commercial_score: int
    seasonality: int
    competition: int
    portfolio_fit: int
    cross_sell_potential: int
    evergreen_score: int
    average_confidence: int
    expansion_potential: int = 0
    brand_consistency: int = 0
    revenue_potential: int = 0

    @property
    def total(self) -> int:
        """Return weighted average score."""
        values = (
            self.commercial_score,
            self.portfolio_fit,
            self.expansion_potential or self.cross_sell_potential,
            self.cross_sell_potential,
            self.brand_consistency or self.average_confidence,
            self.revenue_potential or self.commercial_score,
            self.trend_score,
            self.seasonality,
            100 - self.competition,
            self.evergreen_score,
            self.average_confidence,
        )
        return round(sum(values) / len(values))


@dataclass(frozen=True, slots=True)
class CollectionBlueprint:
    """Commercial identity blueprint for a coordinated Etsy collection."""

    theme_name: str
    target_audience: str
    visual_identity: str
    primary_colors: tuple[str, ...]
    secondary_colors: tuple[str, ...]
    typography_style: str
    illustration_style: str
    mood: tuple[str, ...]
    season: str
    commercial_positioning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme_name": self.theme_name,
            "target_audience": self.target_audience,
            "visual_identity": self.visual_identity,
            "primary_colors": list(self.primary_colors),
            "secondary_colors": list(self.secondary_colors),
            "typography_style": self.typography_style,
            "illustration_style": self.illustration_style,
            "mood": list(self.mood),
            "season": self.season,
            "commercial_positioning": self.commercial_positioning,
        }


@dataclass(frozen=True, slots=True)
class CollectionArtDirection:
    """Muse art direction for a whole collection."""

    master_style: str
    palette: tuple[str, ...]
    rendering: str
    mood: tuple[str, ...]
    typography: str
    composition_rules: tuple[str, ...]
    consistency_rules: tuple[str, ...]
    variation_rules: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.master_style.strip():
            raise ValueError("master_style cannot be empty.")
        object.__setattr__(self, "palette", tuple(self.palette))
        object.__setattr__(self, "mood", tuple(self.mood))
        object.__setattr__(self, "composition_rules", tuple(self.composition_rules))
        object.__setattr__(self, "consistency_rules", tuple(self.consistency_rules))
        object.__setattr__(self, "variation_rules", tuple(self.variation_rules))


@dataclass(frozen=True, slots=True)
class CollectionProduct:
    """One product planned inside a coordinated collection."""

    product_name: str
    subject: str
    product_type: str
    keywords: tuple[str, ...]
    status: str = "PLANNED"

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("product_name cannot be empty.")
        if not self.subject.strip():
            raise ValueError("subject cannot be empty.")
        if not self.product_type.strip():
            raise ValueError("product_type cannot be empty.")
        object.__setattr__(self, "keywords", tuple(self.keywords))


@dataclass(frozen=True, slots=True)
class CrossSellPlan:
    """Merchant Brain cross-sell suggestions."""

    related_products: tuple[str, ...]
    collection_links: tuple[str, ...]
    bundle_suggestions: tuple[str, ...]
    future_collection_ideas: tuple[str, ...]
    matching_products: tuple[str, ...] = ()
    matching_collections: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CollectionRoadmap:
    """Track planned, completed, and remaining collection products."""

    collection_name: str
    products_planned: tuple[str, ...]
    products_completed: tuple[str, ...]
    products_remaining: tuple[str, ...]
    estimated_collection_revenue: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection": self.collection_name,
            "products_planned": list(self.products_planned),
            "products_completed": list(self.products_completed),
            "products_remaining": list(self.products_remaining),
            "estimated_collection_revenue": self.estimated_collection_revenue,
        }


@dataclass(frozen=True, slots=True)
class ShopHealth:
    """Collection-level shop health summary."""

    collections_active: int
    collections_growing: int
    collections_completed: int
    largest_collection: str
    revenue_concentration: str
    collection_diversity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "collections_active": self.collections_active,
            "collections_growing": self.collections_growing,
            "collections_completed": self.collections_completed,
            "largest_collection": self.largest_collection,
            "revenue_concentration": self.revenue_concentration,
            "collection_diversity": self.collection_diversity,
        }


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    """Complete collection-first production plan."""

    collection: CollectionOpportunity
    score: CollectionScore
    art_direction: CollectionArtDirection
    products: tuple[CollectionProduct, ...]
    cross_sell: CrossSellPlan
    why_chosen: str
    blueprint: CollectionBlueprint | None = None
    roadmap: CollectionRoadmap | None = None
    shop_health: ShopHealth | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.products:
            raise ValueError("Collection plan must include products.")
        object.__setattr__(self, "products", tuple(self.products))

    @property
    def collection_name(self) -> str:
        """Return collection name."""
        return self.collection.name
