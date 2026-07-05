"""Convert morning research output into product strategy plans."""

from __future__ import annotations

from project_aurora.research.recommendation_engine import (
    ProductRecommendation,
    ResearchReport,
)
from project_aurora.strategy.product_plan import BundleItem, ProductPlan


class ProductStrategyEngine:
    """Build production-ready plans from local Morning Research reports."""

    def build_plan(self, report: ResearchReport) -> ProductPlan:
        """Return a strategy plan for the top Morning Research selection."""
        recommendation = report.production_selection.best_product
        bundle_structure = self._bundle_structure(recommendation.category)
        asset_count = sum(item.quantity for item in bundle_structure)
        product_type = self._product_type(recommendation.category)
        collection_name = self._collection_name(recommendation)
        priority = self._production_priority(recommendation)

        return ProductPlan(
            selected_product=recommendation.name,
            product_type=product_type,
            collection_name=collection_name,
            asset_count=asset_count,
            bundle_structure=bundle_structure,
            target_buyer=self._target_buyer(recommendation),
            positioning=self._positioning(recommendation, product_type),
            expansion_ideas=self._expansion_ideas(report, recommendation),
            estimated_commercial_potential=(
                self._commercial_potential(recommendation)
            ),
            production_priority=priority,
            ceo_summary=self._ceo_summary(
                recommendation=recommendation,
                product_type=product_type,
                asset_count=asset_count,
                priority=priority,
            ),
        )

    @staticmethod
    def _product_type(category: str) -> str:
        if category == "Party Printable":
            return "Party Printable Bundle"
        if category == "Digital Paper Pack":
            return "Digital Paper Bundle"
        if category == "Digital Clipart":
            return "Digital Clipart Bundle"
        return category

    @staticmethod
    def _bundle_structure(category: str) -> tuple[BundleItem, ...]:
        structures: dict[str, tuple[BundleItem, ...]] = {
            "Party Printable": (
                BundleItem(quantity=8, name="invitations"),
                BundleItem(quantity=8, name="cupcake toppers"),
                BundleItem(quantity=8, name="favor tags"),
                BundleItem(quantity=6, name="thank-you cards"),
                BundleItem(quantity=6, name="digital papers"),
            ),
            "Digital Clipart": (
                BundleItem(quantity=12, name="transparent PNG graphics"),
                BundleItem(quantity=12, name="SVG graphics"),
                BundleItem(quantity=6, name="coordinating patterns"),
            ),
            "Digital Paper Pack": (
                BundleItem(quantity=12, name="seamless digital papers"),
                BundleItem(quantity=6, name="solid coordinate papers"),
                BundleItem(quantity=4, name="bonus texture papers"),
            ),
            "Printable Planner": (
                BundleItem(quantity=8, name="planner pages"),
                BundleItem(quantity=4, name="habit trackers"),
                BundleItem(quantity=4, name="weekly layouts"),
                BundleItem(quantity=4, name="sticker sheets"),
            ),
            "Sticker Sheet": (
                BundleItem(quantity=16, name="kiss-cut sticker designs"),
                BundleItem(quantity=4, name="mini accent stickers"),
                BundleItem(quantity=2, name="printable sheet layouts"),
            ),
            "Printable Gift Tags": (
                BundleItem(quantity=12, name="gift tag designs"),
                BundleItem(quantity=4, name="label designs"),
                BundleItem(quantity=4, name="wraparound tags"),
            ),
        }
        return structures.get(
            category,
            (
                BundleItem(quantity=8, name="core printable assets"),
                BundleItem(quantity=4, name="bonus coordinating assets"),
            ),
        )

    @staticmethod
    def _collection_name(recommendation: ProductRecommendation) -> str:
        return f"{recommendation.season} {recommendation.theme} Collection"

    @staticmethod
    def _target_buyer(recommendation: ProductRecommendation) -> str:
        theme = recommendation.theme.lower()
        season = recommendation.season.lower()
        category = recommendation.category

        if category == "Party Printable":
            return f"Parents planning {season} {theme} parties"
        if category == "Printable Planner":
            return f"Organized buyers preparing for {season} routines"
        if category == "Digital Clipart":
            return f"Small creative sellers designing {theme} products"
        if category == "Digital Paper Pack":
            return f"Crafters and sellers needing {theme} pattern assets"
        if category == "Sticker Sheet":
            return f"Sticker lovers and planners drawn to {theme} designs"
        if category == "Printable Gift Tags":
            return f"Gift givers packaging {theme} presents"
        return f"Buyers looking for {theme} {category.lower()} products"

    @staticmethod
    def _positioning(
        recommendation: ProductRecommendation,
        product_type: str,
    ) -> str:
        theme = recommendation.theme.lower()
        season = recommendation.season.lower()
        product = product_type.lower()

        if recommendation.category == "Party Printable":
            return f"Cute {theme} printable party bundle for {season} events"
        if recommendation.category in {"Digital Clipart", "Digital Paper Pack"}:
            return f"Commercially useful {theme} {product} for creators"
        return f"Polished {theme} {product} for {season} shopping moments"

    @staticmethod
    def _expansion_ideas(
        report: ResearchReport,
        selected: ProductRecommendation,
    ) -> tuple[str, ...]:
        ideas: list[str] = [
            f"{selected.theme} matching thank-you set",
            f"{selected.theme} social listing mockups",
        ]

        for recommendation in report.recommendations:
            if recommendation == selected:
                continue
            idea = (
                f"{recommendation.theme} {recommendation.category} follow-up"
            )
            if idea not in ideas:
                ideas.append(idea)
            if len(ideas) == 5:
                break

        return tuple(ideas)

    @staticmethod
    def _commercial_potential(
        recommendation: ProductRecommendation,
    ) -> str:
        if (
            recommendation.score >= 115
            and recommendation.revenue_potential == "high"
        ):
            potential = "High"
        elif recommendation.score >= 90:
            potential = "Medium"
        else:
            potential = "Emerging"

        return (
            f"{potential} - score {recommendation.score}, "
            f"{recommendation.revenue_potential} revenue potential, "
            f"{recommendation.competition_level} competition"
        )

    @staticmethod
    def _production_priority(recommendation: ProductRecommendation) -> str:
        if (
            recommendation.score >= 115
            and recommendation.ip_safety == "high"
        ):
            return "High"
        if recommendation.score >= 90:
            return "Medium"
        return "Low"

    @staticmethod
    def _ceo_summary(
        recommendation: ProductRecommendation,
        product_type: str,
        asset_count: int,
        priority: str,
    ) -> str:
        return (
            "Today the studio should produce "
            f"{recommendation.name} as a {product_type}, creating "
            f"{asset_count} assets with {priority.lower()} production priority."
        )
