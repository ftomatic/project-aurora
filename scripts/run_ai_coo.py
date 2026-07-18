"""Run Aurora AI COO daily operating planner."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.ai_coo import AICOOEngine  # noqa: E402
from project_aurora.ai_coo.coo_engine import render_daily_business_plan  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Create and print today's AI COO plan."""
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    plan = AICOOEngine(memory=memory).create_daily_plan()
    print(render_daily_business_plan(plan))


if __name__ == "__main__":
    main()
