"""Collection Intelligence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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

    @property
    def total(self) -> int:
        """Return weighted average score."""
        values = (
            self.trend_score,
            self.commercial_score,
            self.seasonality,
            100 - self.competition,
            self.portfolio_fit,
            self.cross_sell_potential,
            self.evergreen_score,
            self.average_confidence,
        )
        return round(sum(values) / len(values))


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


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    """Complete collection-first production plan."""

    collection: CollectionOpportunity
    score: CollectionScore
    art_direction: CollectionArtDirection
    products: tuple[CollectionProduct, ...]
    cross_sell: CrossSellPlan
    why_chosen: str
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.products:
            raise ValueError("Collection plan must include products.")
        object.__setattr__(self, "products", tuple(self.products))

    @property
    def collection_name(self) -> str:
        """Return collection name."""
        return self.collection.name
