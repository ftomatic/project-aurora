"""Review Aurora Collection Intelligence output."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.collections.collection_engine import (  # noqa: E402
    CollectionIntelligenceEngine,
    render_collection_merchant_report,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Print selected collection plan."""
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    plan = CollectionIntelligenceEngine(memory=memory).run()

    print(render_collection_merchant_report(plan))


if __name__ == "__main__":
    main()
