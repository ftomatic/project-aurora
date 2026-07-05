"""Run the Project Aurora product strategy agent."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.agents.morning_research_agent import (  # noqa: E402
    MorningResearchAgent,
    MorningResearchPaths,
)
from project_aurora.agents.product_strategy_agent import (  # noqa: E402
    ProductStrategyAgent,
)


def main() -> None:
    """Generate and print today's local product strategy plan."""
    logger = logging.getLogger("project_aurora.product_strategy")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)

    paths = MorningResearchPaths(
        shop_csv=PROJECT_ROOT / "data" / "research" / "sample_shop.csv",
        market_trends_csv=(
            PROJECT_ROOT / "data" / "research" / "sample_market_trends.csv"
        ),
    )
    morning_agent = MorningResearchAgent(logger=logger)
    morning_report = morning_agent.build_report(paths)
    strategy_agent = ProductStrategyAgent(logger=logger)

    print(strategy_agent.render_plan(morning_report))


if __name__ == "__main__":
    main()
