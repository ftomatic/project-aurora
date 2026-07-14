"""Central memory manager for Aurora agents."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from project_aurora.core.agent_result import AgentResult
from project_aurora.storage.csv_storage import CSVStorage
from project_aurora.storage.storage_interface import StorageInterface


@dataclass(frozen=True, slots=True)
class MemorySummary:
    """Summary of Aurora's current local memory state."""

    research_reports_stored: int
    production_plans: int
    last_production: str
    memory_health: str

    def render(self) -> str:
        """Return a plain-text memory summary."""
        return "\n\n".join(
            (
                "AURORA MEMORY",
                "Research Reports Stored\n"
                f"{self.research_reports_stored}",
                f"Production Plans\n{self.production_plans}",
                f"Last Production\n{self.last_production}",
                f"Memory Health\n{self.memory_health}",
            )
        )


class MemoryManager:
    """Single entry point for Aurora operational reads and writes."""

    RESEARCH_COLLECTION = "research_reports"
    STRATEGY_COLLECTION = "production_plans"
    AGENT_RESULT_COLLECTION = "agent_results"
    PRODUCTION_QUEUE_COLLECTION = "production_queue"
    PROMPT_PACKAGE_COLLECTION = "prompt_packages"
    PROMPT_RECIPE_COLLECTION = "prompt_recipes"
    STYLE_PROFILE_COLLECTION = "style_profiles"
    IMAGE_RESULT_COLLECTION = "image_results"
    IMAGE_QA_COLLECTION = "image_qa"
    SEO_COLLECTION = "seo"
    LISTING_COLLECTION = "listings"
    ETSY_DRAFT_COLLECTION = "etsy_drafts"
    ETSY_IMAGE_UPLOAD_COLLECTION = "etsy_image_uploads"
    ETSY_DIGITAL_FILE_UPLOAD_COLLECTION = "etsy_digital_file_uploads"
    ETSY_COMPLETE_DRAFT_COLLECTION = "etsy_complete_drafts"

    def __init__(self, storage: StorageInterface | None = None) -> None:
        self._storage = storage or CSVStorage()

    def save_agent_result(
        self,
        result: AgentResult,
        result_id: str | None = None,
    ) -> str:
        """Save an orchestrated agent result and return its memory key."""
        key = result_id or self._timestamped_key(result.agent_name)
        self._storage.save(
            self.AGENT_RESULT_COLLECTION,
            key,
            self._to_record(result),
        )
        return key

    def save_research(
        self,
        research: Any,
        report_id: str = "latest",
    ) -> str:
        """Save a Morning Research output record."""
        self._storage.save(
            self.RESEARCH_COLLECTION,
            report_id,
            self._to_record(research),
        )
        return report_id

    def load_research(self, report_id: str = "latest") -> dict[str, Any]:
        """Load a stored Morning Research output record."""
        return self._storage.load(self.RESEARCH_COLLECTION, report_id)

    def save_strategy(
        self,
        strategy: Any,
        plan_id: str = "latest",
    ) -> str:
        """Save a Product Strategy output record."""
        self._storage.save(
            self.STRATEGY_COLLECTION,
            plan_id,
            self._to_record(strategy),
        )
        return plan_id

    def load_strategy(self, plan_id: str = "latest") -> dict[str, Any]:
        """Load a stored Product Strategy output record."""
        return self._storage.load(self.STRATEGY_COLLECTION, plan_id)

    def save_production_queue(
        self,
        queue_items: tuple[str, ...] | list[str],
        queue_id: str = "latest",
    ) -> str:
        """Save the current production queue."""
        self._storage.save(
            self.PRODUCTION_QUEUE_COLLECTION,
            queue_id,
            {"items": list(queue_items)},
        )
        return queue_id

    def load_production_queue(
        self,
        queue_id: str = "latest",
    ) -> dict[str, Any]:
        """Load the current production queue."""
        return self._storage.load(self.PRODUCTION_QUEUE_COLLECTION, queue_id)

    def save_prompt_package(
        self,
        prompt_package: Any,
        package_id: str = "latest",
    ) -> str:
        """Save a prompt package record."""
        self._storage.save(
            self.PROMPT_PACKAGE_COLLECTION,
            package_id,
            self._to_record(prompt_package),
        )
        return package_id

    def load_prompt_package(
        self,
        package_id: str = "latest",
    ) -> dict[str, Any]:
        """Load a prompt package record."""
        return self._storage.load(self.PROMPT_PACKAGE_COLLECTION, package_id)

    def list_prompt_packages(self) -> tuple[str, ...]:
        """Return stored prompt package keys."""
        return self._storage.list(self.PROMPT_PACKAGE_COLLECTION)

    def save_prompt_recipe(
        self,
        prompt_recipe: Any,
        recipe_id: str = "latest",
    ) -> str:
        """Save a Prompt Factory 2.0 recipe record."""
        self._storage.save(
            self.PROMPT_RECIPE_COLLECTION,
            recipe_id,
            self._to_record(prompt_recipe),
        )
        return recipe_id

    def load_prompt_recipe(
        self,
        recipe_id: str = "latest",
    ) -> dict[str, Any]:
        """Load a Prompt Factory 2.0 recipe record."""
        return self._storage.load(self.PROMPT_RECIPE_COLLECTION, recipe_id)

    def save_style_profile(
        self,
        style_profile: Any,
        style_id: str,
    ) -> str:
        """Save a reusable style profile."""
        self._storage.save(
            self.STYLE_PROFILE_COLLECTION,
            style_id,
            self._to_record(style_profile),
        )
        return style_id

    def load_style_profile(self, style_id: str) -> dict[str, Any]:
        """Load a reusable style profile."""
        return self._storage.load(self.STYLE_PROFILE_COLLECTION, style_id)

    def list_style_profiles(self) -> tuple[str, ...]:
        """Return stored style profile ids."""
        return self._storage.list(self.STYLE_PROFILE_COLLECTION)

    def save_image_result(
        self,
        image_result: Any,
        result_id: str = "latest",
    ) -> str:
        """Save an image generation result record."""
        self._storage.save(
            self.IMAGE_RESULT_COLLECTION,
            result_id,
            self._to_record(image_result),
        )
        return result_id

    def load_image_result(
        self,
        result_id: str = "latest",
    ) -> dict[str, Any]:
        """Load an image generation result record."""
        return self._storage.load(self.IMAGE_RESULT_COLLECTION, result_id)

    def save_image_qa_results(
        self,
        qa_results: Any,
        result_id: str = "latest",
    ) -> str:
        """Save image QA result records."""
        self._storage.save(
            self.IMAGE_QA_COLLECTION,
            result_id,
            self._to_record({"results": qa_results}),
        )
        return result_id

    def load_image_qa_results(
        self,
        result_id: str = "latest",
    ) -> dict[str, Any]:
        """Load image QA result records."""
        return self._storage.load(self.IMAGE_QA_COLLECTION, result_id)

    def save_seo_package(
        self,
        seo_package: Any,
        package_id: str = "latest",
    ) -> str:
        """Save an SEO package record."""
        self._storage.save(
            self.SEO_COLLECTION,
            package_id,
            self._to_record(seo_package),
        )
        return package_id

    def load_seo_package(
        self,
        package_id: str = "latest",
    ) -> dict[str, Any]:
        """Load an SEO package record."""
        return self._storage.load(self.SEO_COLLECTION, package_id)

    def list_records(self, collection: str) -> tuple[str, ...]:
        """Return stored record keys for a memory collection."""
        return self._storage.list(collection)

    def load_record(self, collection: str, record_id: str) -> dict[str, Any]:
        """Load a stored record from any memory collection."""
        return self._storage.load(collection, record_id)

    def save_etsy_draft_result(
        self,
        etsy_result: Any,
        result_id: str = "latest",
    ) -> str:
        """Save an Etsy draft creation result."""
        self._storage.save(
            self.ETSY_DRAFT_COLLECTION,
            result_id,
            self._to_record(etsy_result),
        )
        return result_id

    def load_etsy_draft_result(
        self,
        result_id: str = "latest",
    ) -> dict[str, Any]:
        """Load an Etsy draft creation result."""
        return self._storage.load(self.ETSY_DRAFT_COLLECTION, result_id)

    def save_etsy_image_upload_result(
        self,
        upload_result: Any,
        result_id: str = "latest",
    ) -> str:
        """Save an Etsy listing image upload result."""
        self._storage.save(
            self.ETSY_IMAGE_UPLOAD_COLLECTION,
            result_id,
            self._to_record(upload_result),
        )
        return result_id

    def load_etsy_image_upload_result(
        self,
        result_id: str = "latest",
    ) -> dict[str, Any]:
        """Load an Etsy listing image upload result."""
        return self._storage.load(
            self.ETSY_IMAGE_UPLOAD_COLLECTION,
            result_id,
        )

    def save_etsy_digital_file_upload_result(
        self,
        upload_result: Any,
        result_id: str = "latest",
    ) -> str:
        """Save an Etsy digital file upload result."""
        self._storage.save(
            self.ETSY_DIGITAL_FILE_UPLOAD_COLLECTION,
            result_id,
            self._to_record(upload_result),
        )
        return result_id

    def load_etsy_digital_file_upload_result(
        self,
        result_id: str = "latest",
    ) -> dict[str, Any]:
        """Load an Etsy digital file upload result."""
        return self._storage.load(
            self.ETSY_DIGITAL_FILE_UPLOAD_COLLECTION,
            result_id,
        )

    def save_etsy_complete_draft_result(
        self,
        complete_result: Any,
        result_id: str = "latest",
    ) -> str:
        """Save a complete Etsy draft workflow result."""
        self._storage.save(
            self.ETSY_COMPLETE_DRAFT_COLLECTION,
            result_id,
            self._to_record(complete_result),
        )
        return result_id

    def load_etsy_complete_draft_result(
        self,
        result_id: str = "latest",
    ) -> dict[str, Any]:
        """Load a complete Etsy draft workflow result."""
        return self._storage.load(self.ETSY_COMPLETE_DRAFT_COLLECTION, result_id)

    def memory_summary(self) -> MemorySummary:
        """Return a summary of stored Aurora memory."""
        research_count = len(self._storage.list(self.RESEARCH_COLLECTION))
        plan_count = len(self._storage.list(self.STRATEGY_COLLECTION))
        last_production = self._last_production_name()
        memory_health = "Healthy"
        if research_count == 0 or plan_count == 0:
            memory_health = "Needs Data"

        return MemorySummary(
            research_reports_stored=research_count,
            production_plans=plan_count,
            last_production=last_production,
            memory_health=memory_health,
        )

    def _last_production_name(self) -> str:
        if not self._storage.exists(self.STRATEGY_COLLECTION, "latest"):
            return "None"

        latest_strategy = self.load_strategy()
        collection_name = latest_strategy.get("collection_name")
        if isinstance(collection_name, str) and collection_name:
            return collection_name
        selected_product = latest_strategy.get("selected_product")
        if isinstance(selected_product, str) and selected_product:
            return selected_product
        return "Unknown"

    @classmethod
    def _timestamped_key(cls, name: str) -> str:
        normalized_name = name.casefold().replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{normalized_name}_{timestamp}"

    @classmethod
    def _to_record(cls, value: Any) -> dict[str, Any]:
        plain_value = cls._to_plain_data(value)
        if isinstance(plain_value, dict):
            return plain_value
        return {"value": plain_value}

    @classmethod
    def _to_plain_data(cls, value: Any) -> Any:
        if is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: cls._to_plain_data(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, Mapping):
            return {
                str(key): cls._to_plain_data(item)
                for key, item in value.items()
            }
        if isinstance(value, tuple | list | set | frozenset):
            return [cls._to_plain_data(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value
