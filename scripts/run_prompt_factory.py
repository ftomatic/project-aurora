"""Run Aurora's local Prompt Factory."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.production_queue import (  # noqa: E402
    ProductionQueue,
)
from project_aurora.prompt_factory.prompt_factory import (  # noqa: E402
    PromptFactory,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_production_queue import make_sample_strategy  # noqa: E402


def ensure_sample_queue() -> None:
    """Create local sample production queue data for the demo."""
    queue = ProductionQueue(
        queue_dir=PROJECT_ROOT / "data" / "aurora" / "production_queue"
    )
    items = queue.create_queue_from_strategy(make_sample_strategy())
    queue.save_queue(items)


def main() -> None:
    """Generate prompt packages from local production queue memory."""
    ensure_sample_queue()
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    result = PromptFactory(memory=memory).run()
    package = result.packages[0]

    print("PROMPT FACTORY")
    print("")
    print("Production Item")
    print(package.collection)
    print("")
    print("Prompt Style")
    print(package.style)
    print("")
    print("Prompt Package")
    print("Generated")
    print("")
    print("Assets")
    print("Image Prompt")
    print("Negative Prompt")
    print("SEO Prompt")
    print("Pinterest Prompt")
    print("Instagram Prompt")
    print("TikTok Prompt")
    print("")
    print("Status")
    print("SUCCESS")


if __name__ == "__main__":
    main()
