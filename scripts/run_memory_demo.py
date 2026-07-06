"""Demonstrate the Project Aurora memory layer."""

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
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Save and reload Aurora research and strategy memory records."""
    logger = logging.getLogger("project_aurora.memory_demo")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)

    paths = MorningResearchPaths(
        shop_csv=PROJECT_ROOT / "data" / "research" / "sample_shop.csv",
        market_trends_csv=(
            PROJECT_ROOT / "data" / "research" / "sample_market_trends.csv"
        ),
    )
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )

    morning_report = MorningResearchAgent(logger=logger).build_report(paths)
    memory.save_research(morning_report)
    loaded_research = memory.load_research()

    strategy_plan = ProductStrategyAgent(logger=logger).build_plan(
        morning_report
    )
    memory.save_strategy(strategy_plan)
    loaded_strategy = memory.load_strategy()

    memory.save_production_queue(
        tuple(
            item["name"]
            for item in loaded_strategy.get("bundle_structure", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        )
    )

    if loaded_research and loaded_strategy:
        print(memory.memory_summary().render())


if __name__ == "__main__":
    main()
