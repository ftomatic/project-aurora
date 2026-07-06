"""Local file storage for Aurora memory records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from project_aurora.storage.storage_interface import StorageInterface


class CSVStorage(StorageInterface):
    """Store structured Aurora data as JSON files under a local data root."""

    def __init__(self, base_path: Path | None = None) -> None:
        self._base_path = base_path or Path("data") / "aurora"

    @property
    def base_path(self) -> Path:
        """Return the root path used for local storage."""
        return self._base_path

    def save(
        self,
        collection: str,
        key: str,
        data: Mapping[str, Any],
    ) -> None:
        """Save a JSON-serializable record under collection/key."""
        path = self._record_path(collection, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as output_file:
            json.dump(data, output_file, indent=2, sort_keys=True)

    def load(self, collection: str, key: str) -> dict[str, Any]:
        """Load a record from collection/key."""
        path = self._record_path(collection, key)
        if not path.exists():
            raise FileNotFoundError(
                f"No stored record found for {collection}/{key}."
            )

        with path.open("r", encoding="utf-8") as input_file:
            loaded = json.load(input_file)

        if not isinstance(loaded, dict):
            raise ValueError(f"Stored record {collection}/{key} is invalid.")
        return loaded

    def exists(self, collection: str, key: str) -> bool:
        """Return whether collection/key exists."""
        return self._record_path(collection, key).exists()

    def delete(self, collection: str, key: str) -> None:
        """Delete collection/key if it exists."""
        path = self._record_path(collection, key)
        if path.exists():
            path.unlink()

    def list(self, collection: str) -> tuple[str, ...]:
        """Return keys stored in a collection."""
        collection_path = self._collection_path(collection)
        if not collection_path.exists():
            return ()

        return tuple(
            sorted(path.stem for path in collection_path.glob("*.json"))
        )

    def _record_path(self, collection: str, key: str) -> Path:
        return self._collection_path(collection) / f"{self._clean_name(key)}.json"

    def _collection_path(self, collection: str) -> Path:
        return self._base_path / self._clean_name(collection)

    @staticmethod
    def _clean_name(value: str) -> str:
        cleaned = value.strip().replace(" ", "_")
        if not cleaned:
            raise ValueError("Storage names cannot be empty.")
        if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
            raise ValueError(f"Invalid storage name: {value!r}.")
        return cleaned

