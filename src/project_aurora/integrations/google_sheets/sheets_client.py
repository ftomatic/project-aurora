"""Google Sheets client adapter for Aurora Command Center."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


class SheetsClient(Protocol):
    """Small client surface used by Aurora Sheets sync."""

    def get_or_create_workbook(
        self,
        title: str,
        spreadsheet_id: str | None = None,
    ) -> str:
        """Return a spreadsheet id, creating the workbook when needed."""

    def get_worksheet_titles(self, spreadsheet_id: str) -> tuple[str, ...]:
        """Return worksheet titles for a spreadsheet."""

    def add_worksheet(self, spreadsheet_id: str, title: str) -> None:
        """Create a worksheet."""

    def update_values(
        self,
        spreadsheet_id: str,
        worksheet_title: str,
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        """Replace worksheet values."""

    def append_values(
        self,
        spreadsheet_id: str,
        worksheet_title: str,
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        """Append worksheet values."""


@dataclass(frozen=True, slots=True)
class GoogleSheetsConfig:
    """Runtime configuration for Google Sheets sync."""

    workbook_name: str
    spreadsheet_id: str | None
    credentials_file: Path | None

    @classmethod
    def from_file(cls, path: Path) -> "GoogleSheetsConfig":
        """Load minimal YAML config without external parser dependencies."""
        values: dict[str, str] = {}
        if path.exists():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = line.split(":", maxsplit=1)
                cleaned = value.strip().strip("\"'")
                values[key.strip()] = cleaned

        workbook_name = values.get("workbook_name", "Aurora Command Center")
        spreadsheet_id = values.get("spreadsheet_id") or os.getenv(
            "AURORA_GOOGLE_SHEETS_SPREADSHEET_ID"
        )
        credentials_value = values.get("credentials_file") or os.getenv(
            "AURORA_GOOGLE_SERVICE_ACCOUNT_FILE"
        )
        credentials_file = Path(credentials_value) if credentials_value else None
        return cls(
            workbook_name=workbook_name,
            spreadsheet_id=spreadsheet_id,
            credentials_file=credentials_file,
        )


class GoogleSheetsClient:
    """Official Google Sheets API client wrapper."""

    def __init__(self, credentials_file: Path | None = None) -> None:
        self._service = self._build_service(credentials_file)

    def get_or_create_workbook(
        self,
        title: str,
        spreadsheet_id: str | None = None,
    ) -> str:
        """Return configured spreadsheet id or create a new workbook."""
        if spreadsheet_id:
            return spreadsheet_id

        body = {"properties": {"title": title}}
        response = (
            self._service.spreadsheets()
            .create(body=body, fields="spreadsheetId")
            .execute()
        )
        return str(response["spreadsheetId"])

    def get_worksheet_titles(self, spreadsheet_id: str) -> tuple[str, ...]:
        """Return current worksheet titles."""
        response = (
            self._service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id)
            .execute()
        )
        sheets = response.get("sheets", [])
        return tuple(
            str(sheet["properties"]["title"])
            for sheet in sheets
            if "properties" in sheet and "title" in sheet["properties"]
        )

    def add_worksheet(self, spreadsheet_id: str, title: str) -> None:
        """Add a worksheet if missing."""
        body = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "gridProperties": {
                                "rowCount": 1000,
                                "columnCount": 26,
                            },
                        }
                    }
                }
            ]
        }
        (
            self._service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )

    def update_values(
        self,
        spreadsheet_id: str,
        worksheet_title: str,
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        """Clear and replace worksheet values."""
        range_name = f"{worksheet_title}!A:Z"
        self._service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            body={},
        ).execute()
        self._service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{worksheet_title}!A1",
            valueInputOption="RAW",
            body={"values": [list(row) for row in rows]},
        ).execute()

    def append_values(
        self,
        spreadsheet_id: str,
        worksheet_title: str,
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        """Append rows to a worksheet."""
        self._service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{worksheet_title}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [list(row) for row in rows]},
        ).execute()

    @staticmethod
    def _build_service(credentials_file: Path | None) -> Any:
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as error:
            raise RuntimeError(
                "Google Sheets sync requires google-api-python-client, "
                "google-auth, and google-auth-oauthlib."
            ) from error

        resolved_credentials = credentials_file or Path(
            os.environ.get("AURORA_GOOGLE_SERVICE_ACCOUNT_FILE", "")
        )
        if not str(resolved_credentials):
            raise RuntimeError(
                "Set AURORA_GOOGLE_SERVICE_ACCOUNT_FILE or credentials_file "
                "in config/google_sheets.yaml."
            )
        if not resolved_credentials.exists():
            raise FileNotFoundError(
                f"Google credentials file not found: {resolved_credentials}."
            )

        credentials = Credentials.from_service_account_file(
            str(resolved_credentials),
            scopes=SCOPES,
        )
        return build("sheets", "v4", credentials=credentials)
