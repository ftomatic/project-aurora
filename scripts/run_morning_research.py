"""Run the Project Aurora morning research agent."""

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


def main() -> None:
    """Generate and print the morning research report."""
    logger = logging.getLogger("project_aurora.morning_research")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)

    paths = MorningResearchPaths(
        shop_csv=PROJECT_ROOT / "data" / "research" / "sample_shop.csv",
        market_trends_csv=(
            PROJECT_ROOT / "data" / "research" / "sample_market_trends.csv"
        ),
    )
    agent = MorningResearchAgent(logger=logger)
    print(agent.render_report(paths))


if __name__ == "__main__":
    main()
