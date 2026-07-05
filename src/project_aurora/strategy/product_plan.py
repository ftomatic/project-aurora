"""Product strategy plan models and rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BundleItem:
    """A planned asset group inside a product bundle."""

    quantity: int
    name: str


@dataclass(frozen=True, slots=True)
class ProductPlan:
    """A production-ready product strategy plan."""

    selected_product: str
    product_type: str
    collection_name: str
    asset_count: int
    bundle_structure: tuple[BundleItem, ...]
    target_buyer: str
    positioning: str
    expansion_ideas: tuple[str, ...]
    estimated_commercial_potential: str
    production_priority: str
    ceo_summary: str

    def render(self) -> str:
        """Return a plain-text strategy plan for console output."""
        bundle_lines = [
            f"- {item.quantity} {item.name}"
            for item in self.bundle_structure
        ]
        expansion_lines = [f"- {idea}" for idea in self.expansion_ideas]

        return "\n\n".join(
            (
                "PROJECT AURORA - PRODUCT STRATEGY PLAN\n"
                "======================================",
                f"CEO Summary:\n{self.ceo_summary}",
                f"Selected Product:\n{self.selected_product}",
                f"Product Type:\n{self.product_type}",
                f"Collection:\n{self.collection_name}",
                f"Number of Assets to Create:\n{self.asset_count}",
                "Bundle Structure:\n" + "\n".join(bundle_lines),
                f"Target Buyer:\n{self.target_buyer}",
                f"Positioning:\n{self.positioning}",
                "Expansion Ideas:\n" + "\n".join(expansion_lines),
                "Estimated Commercial Potential:\n"
                f"{self.estimated_commercial_potential}",
                f"Production Priority:\n{self.production_priority}",
            )
        )
