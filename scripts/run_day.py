"""Run the Project Aurora daily workflow."""

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
from project_aurora.core.workflow_orchestrator import (  # noqa: E402
    WorkflowOrchestrator,
)


def main() -> None:
    """Execute Aurora's local agent sequence and print the CEO briefing."""
    logger = logging.getLogger("project_aurora.workflow")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)

    paths = MorningResearchPaths(
        shop_csv=PROJECT_ROOT / "data" / "research" / "sample_shop.csv",
        market_trends_csv=(
            PROJECT_ROOT / "data" / "research" / "sample_market_trends.csv"
        ),
    )
    orchestrator = WorkflowOrchestrator(logger=logger)
    briefing = orchestrator.run_day(
        morning_agent=MorningResearchAgent(logger=logger),
        strategy_agent=ProductStrategyAgent(logger=logger),
        paths=paths,
    )
    print(briefing)


if __name__ == "__main__":
    main()
