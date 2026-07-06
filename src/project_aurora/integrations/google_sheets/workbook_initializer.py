"""Workbook initialization for Aurora Command Center."""

from __future__ import annotations

from dataclasses import dataclass

from project_aurora.integrations.google_sheets.sheets_client import SheetsClient
from project_aurora.integrations.google_sheets.worksheet_manager import (
    REQUIRED_WORKSHEETS,
    WorksheetInitializationResult,
    WorksheetManager,
)


@dataclass(frozen=True, slots=True)
class WorkbookInitialization:
    """Workbook initialization result."""

    workbook_name: str
    spreadsheet_id: str
    worksheets: WorksheetInitializationResult


class WorkbookInitializer:
    """Create/open the Aurora workbook and required worksheets."""

    def __init__(self, client: SheetsClient) -> None:
        self._worksheet_manager = WorksheetManager(client)

    def initialize(
        self,
        workbook_name: str,
        spreadsheet_id: str | None = None,
    ) -> WorkbookInitialization:
        """Initialize workbook and worksheets."""
        resolved_spreadsheet_id = self._worksheet_manager.ensure_workbook(
            workbook_name=workbook_name,
            spreadsheet_id=spreadsheet_id,
        )
        worksheets = self._worksheet_manager.ensure_worksheets(
            spreadsheet_id=resolved_spreadsheet_id,
            worksheet_titles=REQUIRED_WORKSHEETS,
        )
        return WorkbookInitialization(
            workbook_name=workbook_name,
            spreadsheet_id=resolved_spreadsheet_id,
            worksheets=worksheets,
        )
