"""Aurora Prompt Factory service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_aurora.production.queue_item import ProductionQueueItem
from project_aurora.prompt_factory.prompt_builder import PromptBuilder
from project_aurora.prompt_factory.prompt_package import PromptPackage
from project_aurora.storage.memory_manager import MemoryManager


@dataclass(frozen=True, slots=True)
class PromptFactoryResult:
    """Result metadata for a prompt factory run."""

    packages: tuple[PromptPackage, ...]
    saved_package_ids: tuple[str, ...]


class PromptFactory:
    """Transform production queue items into prompt packages."""

    APPROVED_STATUSES: frozenset[str] = frozenset({"pending", "in_progress"})

    def __init__(
        self,
        memory: MemoryManager,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self._memory = memory
        self._prompt_builder = prompt_builder or PromptBuilder()

    def run(self, queue_id: str = "latest") -> PromptFactoryResult:
        """Read production queue items and save generated prompt packages."""
        queue_data = self._memory.load_production_queue(queue_id)
        items = self._queue_items_from_memory(queue_data)
        packages = tuple(
            self._prompt_builder.build_package(item)
            for item in items
            if item.status in self.APPROVED_STATUSES
        )
        saved_ids = tuple(
            self._memory.save_prompt_package(
                prompt_package=package,
                package_id=self._package_id(index, package),
            )
            for index, package in enumerate(packages, start=1)
        )
        return PromptFactoryResult(
            packages=packages,
            saved_package_ids=saved_ids,
        )

    @staticmethod
    def _queue_items_from_memory(
        queue_data: dict[str, Any],
    ) -> tuple[ProductionQueueItem, ...]:
        raw_items = queue_data.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("Production queue memory record has no items.")
        return tuple(
            ProductionQueueItem.from_dict(item)
            for item in raw_items
            if isinstance(item, dict)
        )

    @staticmethod
    def _package_id(index: int, package: PromptPackage) -> str:
        product_slug = (
            package.product_name.casefold()
            .replace(" ", "_")
            .replace("/", "_")
        )
        platform_slug = "_".join(
            platform.casefold() for platform in package.target_platforms
        )
        return f"{index:02d}_{product_slug}_{platform_slug}"
