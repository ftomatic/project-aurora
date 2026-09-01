"""Prepare 25 active Etsy listings for Pinterest's bulk-import tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.pinterest.bulk_export import (  # noqa: E402
    PinterestBulkExporter,
    daily_publish_dates,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "aurora" / "pinterest_bulk"
DEFAULT_BOARD = "RainbowMilkStudio Digital Downloads"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--board", default=DEFAULT_BOARD)
    parser.add_argument(
        "--schedule-day",
        help="Schedule 10 Pins on YYYY-MM-DD at 9 AM, 1 PM and 6 PM Eastern.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    load_local_env(PROJECT_ROOT / "config" / "aurora.local.env")
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    missing = config.validate_for_api(is_digital=True)
    if missing:
        raise SystemExit("Missing Etsy configuration: " + ", ".join(missing))
    publish_dates = (
        daily_publish_dates(args.schedule_day, args.count)
        if args.schedule_day
        else ()
    )
    result = PinterestBulkExporter(
        client=EtsyClient(config),
        output_dir=DEFAULT_OUTPUT_DIR,
        board=args.board,
    ).export(count=args.count, publish_dates=publish_dates)
    print("PINTEREST BULK UPLOAD")
    print("")
    print("Pins Prepared")
    print(result.pins_prepared)
    print("")
    print("Board")
    print(args.board)
    print("")
    print("CSV")
    print(result.csv_path)
    print("")
    print("Previously Prepared Skipped")
    print(result.skipped_prepared)
    print("")
    print("Status")
    print("READY_FOR_PINTEREST_IMPORT" if result.pins_prepared else "NO_NEW_LISTINGS")


if __name__ == "__main__":
    main()
