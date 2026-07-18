"""Run Aurora Business Intelligence demo/report."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.business_intelligence import BusinessIntelligenceEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Print BI learning summary from local memory."""
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    engine = BusinessIntelligenceEngine(memory=memory)
    records = engine.performance_records()
    patterns = engine.discover_patterns()
    recommendations = engine.generate_recommendations()
    insights = engine.executive_insights()
    proposals = engine.propose_strategy_adjustments()

    print("BUSINESS INTELLIGENCE")
    print("")
    print("Listings Tracked")
    print(len(records))
    print("")
    print("Patterns Discovered")
    print(len(patterns))
    for pattern in patterns[:5]:
        print(f"- {pattern.observation} ({pattern.confidence:.0f}% confidence)")
    print("")
    print("Recommendations")
    print(len(recommendations))
    for recommendation in recommendations[:5]:
        print(f"- {recommendation.recommendation} ({recommendation.confidence:.0f}% confidence)")
    print("")
    print("Executive Insights")
    print(f"Top Performing Style: {insights.top_performing_style}")
    print(f"Fastest Growing Category: {insights.fastest_growing_category}")
    print(f"Highest Revenue Collection: {insights.highest_revenue_collection}")
    print("")
    print("Learning Proposals")
    print(sum(1 for proposal in proposals if proposal.approved_for_application))
    print("")
    print("Status")
    print("SUCCESS")


if __name__ == "__main__":
    main()
