"""Create product recommendations from shop and market analysis."""

from __future__ import annotations

from dataclasses import dataclass

from project_aurora.research.market_analyzer import MarketTrend
from project_aurora.research.shop_analyzer import ShopSummary


@dataclass(frozen=True, slots=True)
class ProductRecommendation:
    """A scored product opportunity for RainbowMilkStudio."""

    name: str
    category: str
    theme: str
    season: str
    score: int
    competition_level: str
    revenue_potential: str
    ease_of_production: str
    ip_safety: str
    reasoning: str


@dataclass(frozen=True, slots=True)
class ProductionSelection:
    """Today's automated product selection decision."""

    best_product: ProductRecommendation
    backup_product: ProductRecommendation
    collection_expansion: str
    product_type: str
    selection_reason: str
    production_queue: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """Complete morning research report data."""

    shop_summary: ShopSummary
    market_trends: tuple[MarketTrend, ...]
    seasonal_opportunities: tuple[MarketTrend, ...]
    competition_estimate: tuple[tuple[str, int], ...]
    recommendations: tuple[ProductRecommendation, ...]
    production_selection: ProductionSelection
    future_collections: tuple[str, ...]


class RecommendationEngine:
    """Score opportunities by comparing shop coverage to market demand."""

    def build_report(
        self,
        shop_summary: ShopSummary,
        market_trends: tuple[MarketTrend, ...],
        seasonal_opportunities: tuple[MarketTrend, ...],
        competition_estimate: tuple[tuple[str, int], ...],
    ) -> ResearchReport:
        """Return a complete research report from analyzed inputs."""
        recommendations = self.recommend(shop_summary, market_trends)
        production_selection = self.select_for_production(recommendations)
        return ResearchReport(
            shop_summary=shop_summary,
            market_trends=market_trends,
            seasonal_opportunities=seasonal_opportunities,
            competition_estimate=competition_estimate,
            recommendations=recommendations,
            production_selection=production_selection,
            future_collections=self.suggest_collections(recommendations),
        )

    def recommend(
        self,
        shop_summary: ShopSummary,
        market_trends: tuple[MarketTrend, ...],
        limit: int = 10,
    ) -> tuple[ProductRecommendation, ...]:
        """Return the top scored product recommendations."""
        recommendations = tuple(
            self._recommend_from_trend(shop_summary, trend)
            for trend in market_trends
        )
        return tuple(
            sorted(
                recommendations,
                key=lambda item: (item.score, item.name),
                reverse=True,
            )[:limit]
        )

    def suggest_collections(
        self,
        recommendations: tuple[ProductRecommendation, ...],
    ) -> tuple[str, ...]:
        """Return future collection ideas from the best opportunities."""
        seen: set[str] = set()
        collections: list[str] = []

        for recommendation in recommendations:
            collection = (
                f"{recommendation.season} {recommendation.theme} Collection"
            )
            if collection not in seen:
                seen.add(collection)
                collections.append(collection)

        return tuple(collections[:5])

    def select_for_production(
        self,
        recommendations: tuple[ProductRecommendation, ...],
    ) -> ProductionSelection:
        """Choose today's production focus from scored opportunities."""
        if len(recommendations) < 2:
            raise ValueError("At least two recommendations are required.")

        best_product = recommendations[0]
        backup_product = recommendations[1]
        collection_expansion = (
            f"{best_product.season} {best_product.theme} Collection"
        )
        production_queue = (
            best_product.name,
            backup_product.name,
            collection_expansion,
        )

        selection_reason = (
            f"{best_product.name} is today's strongest production choice "
            f"because it combines a score of {best_product.score}, "
            f"{best_product.revenue_potential} revenue potential, "
            f"{best_product.ease_of_production} production ease, "
            f"{best_product.ip_safety} IP safety, and "
            f"{best_product.competition_level} competition. "
            f"The selection balances shop fit, trend strength, seasonal "
            f"timing, product gap coverage, revenue potential, production "
            f"ease, and IP safety."
        )

        return ProductionSelection(
            best_product=best_product,
            backup_product=backup_product,
            collection_expansion=collection_expansion,
            product_type=best_product.category,
            selection_reason=selection_reason,
            production_queue=production_queue,
        )

    def _recommend_from_trend(
        self,
        shop_summary: ShopSummary,
        trend: MarketTrend,
    ) -> ProductRecommendation:
        category_gap = trend.product_type not in shop_summary.covered_categories
        theme_gap = trend.theme not in shop_summary.covered_themes
        season_gap = trend.season not in shop_summary.covered_seasons

        gap_bonus = (
            (18 if category_gap else 4)
            + (14 if theme_gap else 3)
            + (8 if season_gap else 2)
        )
        demand_points = trend.demand_score * 8
        competition_points = trend.competition_weight * 6
        ease_of_production = self._ease_of_production(trend.product_type)
        revenue_potential = self._revenue_potential(
            trend.demand_score,
            trend.product_type,
        )
        ip_safety = self._ip_safety(trend.theme)
        score = (
            demand_points
            + competition_points
            + gap_bonus
            + self._ease_points(ease_of_production)
            + self._revenue_points(revenue_potential)
            + self._ip_safety_points(ip_safety)
        )

        reasons = [
            f"demand score {trend.demand_score}/10",
            f"{trend.competition_level} competition",
            f"{revenue_potential} revenue potential",
            f"{ease_of_production} production ease",
            f"{ip_safety} IP safety",
        ]
        if category_gap:
            reasons.append("fills a product-type gap")
        else:
            reasons.append("extends an existing product type")
        if theme_gap:
            reasons.append("adds a new theme")
        else:
            reasons.append("builds on a proven shop theme")
        if season_gap:
            reasons.append("opens a new seasonal lane")
        reasons.append(trend.trend_notes)

        return ProductRecommendation(
            name=f"{trend.theme} {trend.product_type}",
            category=trend.product_type,
            theme=trend.theme,
            season=trend.season,
            score=score,
            competition_level=trend.competition_level,
            revenue_potential=revenue_potential,
            ease_of_production=ease_of_production,
            ip_safety=ip_safety,
            reasoning="; ".join(reasons),
        )

    @staticmethod
    def _ease_of_production(product_type: str) -> str:
        easy_types = {
            "Digital Clipart",
            "Digital Paper Pack",
            "Printable Gift Tags",
            "Printable Planner",
            "Sticker Sheet",
        }
        if product_type in easy_types:
            return "high"
        if product_type == "Party Printable":
            return "medium"
        return "medium"

    @staticmethod
    def _revenue_potential(demand_score: int, product_type: str) -> str:
        premium_types = {
            "Digital Clipart",
            "Digital Paper Pack",
            "Party Printable",
            "Printable Planner",
        }
        if demand_score >= 8 and product_type in premium_types:
            return "high"
        if demand_score >= 7:
            return "medium"
        return "low"

    @staticmethod
    def _ip_safety(theme: str) -> str:
        unsafe_terms = ("disney", "pokemon", "barbie", "taylor swift")
        normalized_theme = theme.casefold()
        if any(term in normalized_theme for term in unsafe_terms):
            return "low"
        return "high"

    @staticmethod
    def _ease_points(ease_of_production: str) -> int:
        return {"high": 10, "medium": 6, "low": 0}[ease_of_production]

    @staticmethod
    def _revenue_points(revenue_potential: str) -> int:
        return {"high": 12, "medium": 7, "low": 2}[revenue_potential]

    @staticmethod
    def _ip_safety_points(ip_safety: str) -> int:
        return {"high": 10, "medium": 5, "low": -20}[ip_safety]
