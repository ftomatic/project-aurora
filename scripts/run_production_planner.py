"""Run Aurora Sprint 19 production planning."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.product_planner import ProductPlanner  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionQueueManager,
)
from project_aurora.style_intelligence.style_library_builder import (  # noqa: E402
    StyleLibraryBuilder,
)


def mock_research_output() -> dict[str, object]:
    """Return local Morning Research-shaped input for planner demo."""
    return {
        "recommendations": (
            {
                "name": "Woodland Baby Animals",
                "category": "Digital Clipart",
                "theme": "Woodland Baby Animals",
                "season": "Evergreen",
                "demand_score": 9,
                "competition_level": "low",
                "revenue_potential": "high",
                "score": 112,
            },
            {
                "name": "Strawberry Birthday Party",
                "category": "Party Printable",
                "theme": "Strawberry Birthday",
                "season": "Summer",
                "demand_score": 9,
                "competition_level": "medium",
                "revenue_potential": "high",
                "score": 107,
            },
            {
                "name": "Fairy Garden Clipart",
                "category": "Digital Clipart",
                "theme": "Fairy Garden",
                "season": "Spring",
                "demand_score": 8,
                "competition_level": "low",
                "revenue_potential": "high",
                "score": 104,
            },
            {
                "name": "Vintage Christmas Gift Tags",
                "category": "Printable Gift Tags",
                "theme": "Vintage Christmas",
                "season": "Christmas",
                "demand_score": 8,
                "competition_level": "medium",
                "revenue_potential": "medium",
                "score": 92,
            },
            {
                "name": "Cottagecore Digital Paper",
                "category": "Digital Paper Pack",
                "theme": "Cottagecore Florals",
                "season": "Spring",
                "demand_score": 7,
                "competition_level": "low",
                "revenue_potential": "medium",
                "score": 90,
            },
        )
    }


def main() -> None:
    """Create dynamic production jobs from local planner inputs."""
    queue_path = (
        PROJECT_ROOT
        / "data"
        / "aurora"
        / "production_queue"
        / "queue.json"
    )
    queue_manager = ProductionQueueManager(queue_path=queue_path)
    jobs = ProductPlanner(queue_manager=queue_manager).plan(
        research_output=mock_research_output(),
        style_output=StyleLibraryBuilder().build_seed_library(),
        top_n=5,
    )

    print("PRODUCTION PLAN")
    print("")
    print("Jobs Created")
    print(len(jobs))
    print("")
    for index, job in enumerate(jobs, start=1):
        print(f"{index}.")
        print(job.product_name)
        print("")
        print("Confidence")
        print(f"{int(round(job.confidence_score * 100))}%")
        print("")
        print("Style")
        print(job.style)
        print("")
        print("Demand")
        print(job.estimated_demand)
        print("")
        print("Competition")
        print(job.estimated_competition)
        print("")
    print("Queue Saved")
    print("data/aurora/production_queue/queue.json")


if __name__ == "__main__":
    main()
