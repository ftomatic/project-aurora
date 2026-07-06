"""Abstract storage interface for Aurora operational memory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class StorageInterface(ABC):
    """Define durable storage operations for structured Aurora data."""

    @abstractmethod
    def save(
        self,
        collection: str,
        key: str,
        data: Mapping[str, Any],
    ) -> None:
        """Save structured data under a collection and key."""

    @abstractmethod
    def load(self, collection: str, key: str) -> dict[str, Any]:
        """Load structured data for a collection and key."""

    @abstractmethod
    def exists(self, collection: str, key: str) -> bool:
        """Return whether a stored record exists."""

    @abstractmethod
    def delete(self, collection: str, key: str) -> None:
        """Delete a stored record if it exists."""

    @abstractmethod
    def list(self, collection: str) -> tuple[str, ...]:
        """Return stored keys for a collection."""

