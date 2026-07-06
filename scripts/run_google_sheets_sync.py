"""Run Aurora Command Center Google Sheets sync."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.google_sheets.sheets_client import (  # noqa: E402
    GoogleSheetsClient,
    GoogleSheetsConfig,
)
from project_aurora.integrations.google_sheets.sheets_sync import (  # noqa: E402
    SheetsSync,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Synchronize Aurora Memory to Google Sheets."""
    config = GoogleSheetsConfig.from_file(
        PROJECT_ROOT / "config" / "google_sheets.yaml"
    )
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    try:
        client = GoogleSheetsClient(credentials_file=config.credentials_file)
        result = SheetsSync(memory=memory, client=client, config=config).run()
    except (FileNotFoundError, RuntimeError) as error:
        print("AURORA COMMAND CENTER")
        print("")
        print("Google Sheets Connected")
        print("No")
        print("")
        print("Status")
        print("CONFIGURATION_REQUIRED")
        print("")
        print("Reason")
        print(error)
        raise SystemExit(1) from error

    print("AURORA COMMAND CENTER")
    print("")
    print("Google Sheets Connected")
    print("")
    print("Workbook")
    print(result.workbook_name)
    print("")
    print("Worksheets")
    print("Created")
    print("")
    print("Synchronization")
    print("Completed")
    print("")
    print("Status")
    print(result.status)


if __name__ == "__main__":
    main()
