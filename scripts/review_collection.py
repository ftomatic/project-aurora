"""Review Aurora Collection Intelligence output."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.collections.collection_engine import CollectionIntelligenceEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Print selected collection plan."""
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    plan = CollectionIntelligenceEngine(memory=memory).run()

    print("COLLECTION REVIEW")
    print("")
    print("Collection")
    print(plan.collection.name)
    print("")
    print("Why Chosen")
    print(plan.why_chosen)
    print("")
    print("Products")
    for product in plan.products:
        print(product.subject)
    print("")
    print("Master Style")
    print(plan.art_direction.master_style)
    print("")
    print("Palette")
    for color in plan.art_direction.palette:
        print(color)
    print("")
    print("Expected Cross Sales")
    for suggestion in plan.cross_sell.bundle_suggestions:
        print(suggestion)
    print("")
    print("Commercial Score")
    print(plan.score.commercial_score)


if __name__ == "__main__":
    main()
