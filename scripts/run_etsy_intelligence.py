"""Run Aurora's read-only Etsy Intelligence Agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.etsy_intelligence.agent import EtsyIntelligenceAgent  # noqa: E402
from project_aurora.etsy_intelligence.reporting import render_intelligence_report  # noqa: E402
from project_aurora.etsy_intelligence.shop_reader import EtsyShopReader  # noqa: E402
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only Etsy intelligence.")
    parser.add_argument("--read-only", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    parse_args(argv)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    try:
        config = EtsyConfig.from_environment(
            PROJECT_ROOT / "config" / "etsy.yaml",
            PROJECT_ROOT / "config" / "aurora.local.env",
        )
        client = EtsyClient(config) if not config.is_mock_mode else None
    except Exception:
        client = None
    report = EtsyIntelligenceAgent(
        memory=memory,
        shop_reader=EtsyShopReader(client),
    ).run()
    print(render_intelligence_report(report))


if __name__ == "__main__":
    main()
