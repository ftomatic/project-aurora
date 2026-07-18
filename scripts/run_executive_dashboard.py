"""Run Aurora's Executive AI Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.executive.dashboard_engine import (  # noqa: E402
    ExecutiveDashboardEngine,
    render_dashboard,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Print the executive dashboard."""
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    dashboard = ExecutiveDashboardEngine(memory=memory).build()
    print(render_dashboard(dashboard))


if __name__ == "__main__":
    main()
