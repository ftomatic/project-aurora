"""Collection planning engine for Aurora Creative Director."""

from __future__ import annotations

from typing import Any

from project_aurora.config.project_profile import ProjectProfile
from project_aurora.creative.art_direction import ArtDirection
from project_aurora.creative.collection_plan import CollectionPlan


class CollectionEngine:
    """Build collection plans from research, strategy, and profile context."""

    PRODUCT_LINEUP: tuple[str, ...] = (
        "Invitation",
        "Cupcake Toppers",
        "Favor Tags",
        "Welcome Sign",
        "Water Bottle Labels",
        "Party Banner",
        "Thank You Cards",
        "Gift Tags",
        "Cake Topper",
        "Party Circles",
    )
    MASTER_ASSETS: tuple[str, ...] = (
        "Main Strawberry Girl",
        "Berry Pattern",
        "Watercolor Background",
        "Floral Accent Pack",
    )
    SUPPORTING_MASTER_ASSETS: tuple[str, ...] = (
        "Ribbon Set",
        "Strawberry Cluster",
        "Cake Accent",
    )
    CROSS_SELLS: tuple[str, ...] = (
        "Matching Baby Shower",
        "Matching Nursery",
        "Matching Clipart",
        "Matching Digital Paper",
    )
    UPSELLS: tuple[str, ...] = (
        "Editable Invitation Upgrade",
        "Deluxe Party Decor Bundle",
        "Matching Thank You Card Set",
        "Pinterest Launch Graphics",
        "Instagram Promo Graphics",
    )

    def build_plan(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        project_profile: ProjectProfile,
    ) -> CollectionPlan:
        """Return a complete deterministic collection plan."""
        collection_name = self._collection_name(strategy)
        theme = self._theme(strategy, research)
        season = self._season(strategy, research)
        art_direction = self._art_direction(theme, project_profile)
        recommended_products = self._recommended_products(strategy)
        master_assets = self._master_assets(strategy)
        generation_cost = self.estimate_generation_cost(master_assets)
        estimated_revenue = self.estimate_revenue(
            recommended_products=recommended_products,
            upsell_products=self.UPSELLS,
            default_price=project_profile.default_price,
        )

        return CollectionPlan(
            collection_name=collection_name,
            theme=theme,
            season=season,
            target_customer=str(
                strategy.get("target_buyer")
                or project_profile.target_customer
            ),
            art_style=art_direction.art_style,
            primary_palette=art_direction.primary_palette,
            secondary_palette=art_direction.secondary_palette,
            recommended_products=recommended_products,
            master_assets=master_assets,
            shared_elements=art_direction.shared_elements,
            cross_sell_products=self.CROSS_SELLS,
            upsell_products=self.UPSELLS,
            estimated_revenue=estimated_revenue,
            estimated_generation_cost=generation_cost,
            priority=str(strategy.get("production_priority", "High")),
        )

    @classmethod
    def estimate_revenue(
        cls,
        recommended_products: tuple[str, ...],
        upsell_products: tuple[str, ...],
        default_price: float,
    ) -> float:
        """Estimate collection revenue potential."""
        base_bundle_value = default_price * len(recommended_products)
        upsell_value = len(upsell_products) * 8.0
        return round(base_bundle_value + upsell_value, 2)

    @staticmethod
    def estimate_generation_cost(master_assets: tuple[str, ...]) -> float:
        """Estimate image generation cost for master assets."""
        return round(len(master_assets) * 0.155, 2)

    @classmethod
    def _recommended_products(cls, strategy: dict[str, Any]) -> tuple[str, ...]:
        if "Party Printable" in str(strategy.get("product_type", "")):
            return cls.PRODUCT_LINEUP
        return cls.PRODUCT_LINEUP[:6]

    @classmethod
    def _master_assets(cls, strategy: dict[str, Any]) -> tuple[str, ...]:
        asset_count = int(strategy.get("asset_count", 36) or 36)
        if asset_count >= 36:
            return cls.MASTER_ASSETS
        return cls.MASTER_ASSETS[:3]

    @staticmethod
    def _collection_name(strategy: dict[str, Any]) -> str:
        collection = str(
            strategy.get("collection_name")
            or strategy.get("selected_product")
            or "Aurora Collection"
        )
        return collection.replace(" Collection", "")

    @staticmethod
    def _theme(
        strategy: dict[str, Any],
        research: dict[str, Any],
    ) -> str:
        positioning = str(strategy.get("positioning", "")).casefold()
        if "watercolor" in positioning or "strawberry" in positioning:
            return "Storybook Watercolor"
        recommendation = research.get("production_selection", {})
        best_product = recommendation.get("best_product", {})
        if isinstance(best_product, dict) and best_product.get("theme"):
            return str(best_product["theme"])
        return "Storybook Watercolor"

    @staticmethod
    def _season(
        strategy: dict[str, Any],
        research: dict[str, Any],
    ) -> str:
        collection = str(strategy.get("collection_name", "")).casefold()
        if "summer" in collection:
            return "Summer"
        recommendation = research.get("production_selection", {})
        best_product = recommendation.get("best_product", {})
        if isinstance(best_product, dict) and best_product.get("season"):
            return str(best_product["season"])
        return "Evergreen"

    @staticmethod
    def _art_direction(
        theme: str,
        project_profile: ProjectProfile,
    ) -> ArtDirection:
        style = "Storybook Watercolor"
        if "cottagecore" in project_profile.brand_style:
            style = "Storybook Watercolor Cottagecore"
        return ArtDirection(
            art_style=style,
            primary_palette=(
                "strawberry red",
                "soft blush pink",
                "cream white",
                "leaf green",
            ),
            secondary_palette=(
                "butter yellow",
                "sky blue",
                "warm peach",
            ),
            shared_elements=(
                "strawberries",
                "summer flowers",
                "gingham ribbon",
                "watercolor leaves",
                "storybook sparkle accents",
            ),
        )
