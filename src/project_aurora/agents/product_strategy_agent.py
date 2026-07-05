"""Product strategy agent for Project Aurora."""

from __future__ import annotations

from logging import Logger

from project_aurora.core.logger import get_logger
from project_aurora.research.recommendation_engine import ResearchReport
from project_aurora.strategy.product_plan import ProductPlan
from project_aurora.strategy.product_strategy_engine import (
    ProductStrategyEngine,
)


class ProductStrategyAgent:
    """Create a product strategy plan from Morning Research output."""

    def __init__(
        self,
        strategy_engine: ProductStrategyEngine | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._strategy_engine = strategy_engine or ProductStrategyEngine()
        self._logger = logger or get_logger(__name__)

    def build_plan(self, morning_report: ResearchReport) -> ProductPlan:
        """Return a production-ready strategy plan."""
        self._logger.info("Building product strategy plan")
        return self._strategy_engine.build_plan(morning_report)

    def render_plan(self, morning_report: ResearchReport) -> str:
        """Return the rendered product strategy plan."""
        plan = self.build_plan(morning_report)
        self._logger.info("Product strategy plan generated")
        return plan.render()
