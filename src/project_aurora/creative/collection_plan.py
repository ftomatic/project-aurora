"""Collection plan model for Aurora Creative Director."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    """Complete creative plan for one product collection."""

    collection_name: str
    theme: str
    season: str
    target_customer: str
    art_style: str
    primary_palette: tuple[str, ...]
    secondary_palette: tuple[str, ...]
    recommended_products: tuple[str, ...]
    master_assets: tuple[str, ...]
    shared_elements: tuple[str, ...]
    cross_sell_products: tuple[str, ...]
    upsell_products: tuple[str, ...]
    estimated_revenue: float
    estimated_generation_cost: float
    priority: str

    def __post_init__(self) -> None:
        required_values = {
            "collection_name": self.collection_name,
            "theme": self.theme,
            "season": self.season,
            "target_customer": self.target_customer,
            "art_style": self.art_style,
            "priority": self.priority,
        }
        for field_name, value in required_values.items():
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
        if self.estimated_revenue < 0:
            raise ValueError("estimated_revenue cannot be negative.")
        if self.estimated_generation_cost < 0:
            raise ValueError("estimated_generation_cost cannot be negative.")

        object.__setattr__(
            self,
            "primary_palette",
            tuple(self.primary_palette),
        )
        object.__setattr__(
            self,
            "secondary_palette",
            tuple(self.secondary_palette),
        )
        object.__setattr__(
            self,
            "recommended_products",
            tuple(self.recommended_products),
        )
        object.__setattr__(self, "master_assets", tuple(self.master_assets))
        object.__setattr__(self, "shared_elements", tuple(self.shared_elements))
        object.__setattr__(
            self,
            "cross_sell_products",
            tuple(self.cross_sell_products),
        )
        object.__setattr__(
            self,
            "upsell_products",
            tuple(self.upsell_products),
        )

    @property
    def status(self) -> str:
        """Return image generation readiness status."""
        return "READY FOR IMAGE GENERATION"
