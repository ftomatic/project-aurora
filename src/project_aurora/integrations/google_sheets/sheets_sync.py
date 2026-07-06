"""One-way Aurora Memory to Google Sheets synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from project_aurora.integrations.google_sheets.dashboard_builder import (
    DashboardBuilder,
)
from project_aurora.integrations.google_sheets.sheets_client import (
    GoogleSheetsConfig,
    SheetsClient,
)
from project_aurora.integrations.google_sheets.workbook_initializer import (
    WorkbookInitializer,
)
from project_aurora.storage.memory_manager import MemoryManager


@dataclass(frozen=True, slots=True)
class SheetsSyncResult:
    """Result of a Google Sheets sync."""

    workbook_name: str
    spreadsheet_id: str
    worksheets_created: tuple[str, ...]
    worksheets_synced: tuple[str, ...]
    status: str
    synced_at: datetime


class SheetsSync:
    """Synchronize Aurora Memory into Google Sheets."""

    def __init__(
        self,
        memory: MemoryManager,
        client: SheetsClient,
        config: GoogleSheetsConfig,
    ) -> None:
        self._memory = memory
        self._client = client
        self._config = config
        self._dashboard_builder = DashboardBuilder(memory)
        self._workbook_initializer = WorkbookInitializer(client)

    def run(self) -> SheetsSyncResult:
        """Run a one-way Memory to Sheets sync."""
        workbook = self._workbook_initializer.initialize(
            workbook_name=self._config.workbook_name,
            spreadsheet_id=self._config.spreadsheet_id,
        )
        snapshot = self._dashboard_builder.load_snapshot()
        rows_by_sheet = self._dashboard_builder.build_workbook_rows(snapshot)

        for worksheet_title, rows in rows_by_sheet.items():
            self._client.update_values(
                spreadsheet_id=workbook.spreadsheet_id,
                worksheet_title=worksheet_title,
                rows=rows,
            )

        return SheetsSyncResult(
            workbook_name=workbook.workbook_name,
            spreadsheet_id=workbook.spreadsheet_id,
            worksheets_created=workbook.worksheets.created,
            worksheets_synced=tuple(rows_by_sheet),
            status="SUCCESS",
            synced_at=datetime.now(),
        )
