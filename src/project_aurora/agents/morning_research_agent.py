"""Morning research agent for RainbowMilkStudio product planning."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from pathlib import Path

from project_aurora.core.logger import get_logger
from project_aurora.research.market_analyzer import MarketAnalyzer
from project_aurora.research.recommendation_engine import (
    RecommendationEngine,
    ResearchReport,
)
from project_aurora.research.report_generator import ReportGenerator
from project_aurora.research.shop_analyzer import ShopAnalyzer


@dataclass(frozen=True, slots=True)
class MorningResearchPaths:
    """Input paths for the morning research workflow."""

    shop_csv: Path
    market_trends_csv: Path


class MorningResearchAgent:
    """Generate a daily local research report for product planning."""

    def __init__(
        self,
        shop_analyzer: ShopAnalyzer | None = None,
        market_analyzer: MarketAnalyzer | None = None,
        recommendation_engine: RecommendationEngine | None = None,
        report_generator: ReportGenerator | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._shop_analyzer = shop_analyzer or ShopAnalyzer()
        self._market_analyzer = market_analyzer or MarketAnalyzer()
        self._recommendation_engine = (
            recommendation_engine or RecommendationEngine()
        )
        self._report_generator = report_generator or ReportGenerator()
        self._logger = logger or get_logger(__name__)

    def build_report(self, paths: MorningResearchPaths) -> ResearchReport:
        """Analyze local CSV inputs and return a research report."""
        self._logger.info("Loading shop data from %s", paths.shop_csv)
        products = self._shop_analyzer.load_products(paths.shop_csv)
        shop_summary = self._shop_analyzer.summarize(products)

        self._logger.info(
            "Loading market trends from %s",
            paths.market_trends_csv,
        )
        market_trends = self._market_analyzer.load_trends(
            paths.market_trends_csv
        )
        market_summary = self._market_analyzer.summarize(market_trends)

        self._logger.info("Scoring product opportunities")
        return self._recommendation_engine.build_report(
            shop_summary=shop_summary,
            market_trends=market_trends,
            seasonal_opportunities=market_summary.seasonal_opportunities,
            competition_estimate=market_summary.competition_estimate,
        )

    def render_report(self, paths: MorningResearchPaths) -> str:
        """Return the rendered morning research report."""
        report = self.build_report(paths)
        rendered_report = self._report_generator.render(report)
        self._logger.info("Morning research report generated")
        return rendered_report
