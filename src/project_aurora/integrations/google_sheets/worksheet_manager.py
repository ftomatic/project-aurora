"""Worksheet management for Aurora Command Center."""

from __future__ import annotations

from dataclasses import dataclass

from project_aurora.integrations.google_sheets.sheets_client import SheetsClient


REQUIRED_WORKSHEETS: tuple[str, ...] = (
    "Dashboard",
    "Research",
    "Strategy",
    "Production Queue",
    "Prompt Packages",
    "Image Generation",
    "Image QA",
    "Mockups",
    "SEO",
    "Listings",
    "Workflow",
    "Logs",
)


@dataclass(frozen=True, slots=True)
class WorksheetInitializationResult:
    """Worksheet initialization metadata."""

    spreadsheet_id: str
    created: tuple[str, ...]
    existing: tuple[str, ...]


class WorksheetManager:
    """Ensure required Aurora worksheets exist."""

    def __init__(self, client: SheetsClient) -> None:
        self._client = client

    def ensure_workbook(
        self,
        workbook_name: str,
        spreadsheet_id: str | None = None,
    ) -> str:
        """Return a workbook id, creating it when needed."""
        return self._client.get_or_create_workbook(
            title=workbook_name,
            spreadsheet_id=spreadsheet_id,
        )

    def ensure_worksheets(
        self,
        spreadsheet_id: str,
        worksheet_titles: tuple[str, ...] = REQUIRED_WORKSHEETS,
    ) -> WorksheetInitializationResult:
        """Create missing worksheets and return initialization metadata."""
        existing = self._client.get_worksheet_titles(spreadsheet_id)
        existing_set = set(existing)
        created: list[str] = []

        for title in worksheet_titles:
            if title not in existing_set:
                self._client.add_worksheet(spreadsheet_id, title)
                created.append(title)
                existing_set.add(title)

        return WorksheetInitializationResult(
            spreadsheet_id=spreadsheet_id,
            created=tuple(created),
            existing=existing,
        )
