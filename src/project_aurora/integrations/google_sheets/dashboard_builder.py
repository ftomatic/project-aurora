"""Build worksheet rows from Aurora Memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from project_aurora.storage.memory_manager import MemoryManager


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    """Memory records used for command center sync."""

    research: dict[str, Any] | None
    strategy: dict[str, Any] | None
    production_queue: dict[str, Any] | None
    prompt_packages: tuple[dict[str, Any], ...]
    image_generation: dict[str, Any] | None
    image_qa: dict[str, Any] | None
    seo_packages: tuple[dict[str, Any], ...]
    listings: tuple[dict[str, Any], ...]
    workflow: tuple[dict[str, Any], ...]


class DashboardBuilder:
    """Convert Aurora Memory into Google Sheets row payloads."""

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def load_snapshot(self) -> MemorySnapshot:
        """Read latest Aurora Memory records for dashboard sync."""
        return MemorySnapshot(
            research=self._load_optional("research_reports", "latest"),
            strategy=self._load_optional("production_plans", "latest"),
            production_queue=self._load_optional("production_queue", "latest"),
            prompt_packages=self._load_all("prompt_packages"),
            image_generation=self._load_optional("image_results", "latest"),
            image_qa=self._load_optional("image_qa", "latest"),
            seo_packages=self._load_all("seo"),
            listings=self._load_all("listings"),
            workflow=self._load_all("agent_results"),
        )

    def build_workbook_rows(
        self,
        snapshot: MemorySnapshot,
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        """Return rows for every Aurora worksheet."""
        return {
            "Dashboard": self.dashboard_rows(snapshot),
            "Research": self.research_rows(snapshot.research),
            "Strategy": self.strategy_rows(snapshot.strategy),
            "Production Queue": self.production_queue_rows(
                snapshot.production_queue
            ),
            "Prompt Packages": self.prompt_package_rows(
                snapshot.prompt_packages
            ),
            "Image Generation": self.image_generation_rows(
                snapshot.image_generation
            ),
            "Image QA": self.image_qa_rows(snapshot.image_qa),
            "Mockups": self.mockup_rows(),
            "SEO": self.seo_rows(snapshot.seo_packages),
            "Listings": self.listing_rows(snapshot.listings),
            "Workflow": self.workflow_rows(snapshot.workflow),
            "Logs": self.log_rows("Prepared memory snapshot for sync."),
        }

    def dashboard_rows(
        self,
        snapshot: MemorySnapshot,
    ) -> tuple[tuple[Any, ...], ...]:
        """Build dashboard key/value rows."""
        strategy = snapshot.strategy or {}
        image_generation = snapshot.image_generation or {}
        image_qa = snapshot.image_qa or {}
        production_queue = snapshot.production_queue or {}
        qa_results = image_qa.get("results", [])

        images_generated = len(image_generation.get("generated_files", []))
        qa_approved = sum(
            1
            for result in qa_results
            if isinstance(result, dict) and result.get("status") == "PASS"
        )
        prompt_count = len(snapshot.prompt_packages)
        seo_count = len(snapshot.seo_packages)
        listings_ready = sum(
            1
            for listing in snapshot.listings
            if listing.get("listing_status") == "READY_FOR_ETSY_DRAFT"
        )
        next_stage = "SEO" if seo_count == 0 else "Listings"

        return (
            ("Metric", "Value"),
            ("Last Run", datetime.now().isoformat(timespec="seconds")),
            ("Workflow Status", "READY"),
            ("Research Status", "AVAILABLE" if snapshot.research else "MISSING"),
            ("Strategy Status", "AVAILABLE" if strategy else "MISSING"),
            ("Prompt Packages", prompt_count),
            ("Images Generated", images_generated),
            ("QA Approved", qa_approved),
            ("Mockups", 0),
            ("SEO Packages", seo_count),
            ("Listings Ready", listings_ready),
            (
                "Current Production Collection",
                strategy.get("collection_name", ""),
            ),
            (
                "Commercial Potential",
                strategy.get("estimated_commercial_potential", ""),
            ),
            ("Next Stage", next_stage),
            ("Production Queue Items", len(production_queue.get("items", []))),
        )

    @staticmethod
    def research_rows(record: dict[str, Any] | None) -> tuple[tuple[Any, ...], ...]:
        """Build latest research rows."""
        if not record:
            return (("Field", "Value"), ("Status", "No research memory found"))
        selection = record.get("production_selection", {})
        best = selection.get("best_product", {})
        return (
            ("Field", "Value"),
            ("Best Product", best.get("name", "")),
            ("Product Type", selection.get("product_type", "")),
            ("Recommendations", len(record.get("recommendations", []))),
        )

    @staticmethod
    def strategy_rows(record: dict[str, Any] | None) -> tuple[tuple[Any, ...], ...]:
        """Build latest strategy rows."""
        if not record:
            return (("Field", "Value"), ("Status", "No strategy memory found"))
        return (
            ("Field", "Value"),
            ("Selected Product", record.get("selected_product", "")),
            ("Collection", record.get("collection_name", "")),
            ("Asset Count", record.get("asset_count", "")),
            ("Priority", record.get("production_priority", "")),
            (
                "Commercial Potential",
                record.get("estimated_commercial_potential", ""),
            ),
        )

    @staticmethod
    def production_queue_rows(
        record: dict[str, Any] | None,
    ) -> tuple[tuple[Any, ...], ...]:
        """Build production queue rows."""
        rows: list[tuple[Any, ...]] = [
            ("ID", "Product", "Platform", "Content Type", "Priority", "Status")
        ]
        for item in (record or {}).get("items", []):
            if isinstance(item, dict):
                rows.append(
                    (
                        item.get("id", ""),
                        item.get("product_name", ""),
                        item.get("platform", ""),
                        item.get("content_type", ""),
                        item.get("priority", ""),
                        item.get("status", ""),
                    )
                )
        return tuple(rows)

    @staticmethod
    def prompt_package_rows(
        records: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[Any, ...], ...]:
        """Build prompt package rows."""
        rows: list[tuple[Any, ...]] = [
            ("Product", "Collection", "Style", "Platforms")
        ]
        for record in records:
            rows.append(
                (
                    record.get("product_name", ""),
                    record.get("collection", ""),
                    record.get("style", ""),
                    ", ".join(record.get("target_platforms", [])),
                )
            )
        return tuple(rows)

    @staticmethod
    def image_generation_rows(
        record: dict[str, Any] | None,
    ) -> tuple[tuple[Any, ...], ...]:
        """Build generated image rows."""
        rows: list[tuple[Any, ...]] = [("Provider", "Generated File", "Status")]
        if not record:
            return tuple(rows)
        provider = record.get("provider", "")
        status = record.get("status", "")
        for generated_file in record.get("generated_files", []):
            rows.append((provider, generated_file, status))
        return tuple(rows)

    @staticmethod
    def image_qa_rows(record: dict[str, Any] | None) -> tuple[tuple[Any, ...], ...]:
        """Build image QA rows."""
        rows: list[tuple[Any, ...]] = [
            ("Asset", "Status", "Score", "Action", "Review Required")
        ]
        for result in (record or {}).get("results", []):
            if isinstance(result, dict):
                rows.append(
                    (
                        result.get("asset_name", ""),
                        result.get("status", ""),
                        result.get("overall_score", ""),
                        result.get("recommended_action", ""),
                        result.get("review_required", ""),
                    )
                )
        return tuple(rows)

    @staticmethod
    def mockup_rows() -> tuple[tuple[Any, ...], ...]:
        """Build mockup rows for future memory records."""
        return (("Mockup", "Status"), ("Mockup sync", "Pending"))

    @staticmethod
    def seo_rows(records: tuple[dict[str, Any], ...]) -> tuple[tuple[Any, ...], ...]:
        """Build SEO rows."""
        rows: list[tuple[Any, ...]] = [("Product", "Title", "Score", "Status")]
        for record in records:
            status = "SUCCESS" if int(record.get("seo_score", 0)) >= 80 else "WARNING"
            rows.append(
                (
                    record.get("product_name", ""),
                    record.get("title", ""),
                    record.get("seo_score", ""),
                    status,
                )
            )
        return tuple(rows)

    @staticmethod
    def listing_rows(
        records: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[Any, ...], ...]:
        """Build listing rows."""
        rows: list[tuple[Any, ...]] = [
            ("Product", "Status", "Etsy Listing ID", "Cleanup Status")
        ]
        for record in records:
            rows.append(
                (
                    record.get("product_name", ""),
                    record.get("listing_status", ""),
                    record.get("etsy_listing_id", ""),
                    record.get("local_asset_cleanup_status", ""),
                )
            )
        return tuple(rows)

    @staticmethod
    def workflow_rows(
        records: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[Any, ...], ...]:
        """Build workflow history rows."""
        rows: list[tuple[Any, ...]] = [
            ("Agent", "Status", "Execution Time", "Confidence")
        ]
        for record in records:
            rows.append(
                (
                    record.get("agent_name", ""),
                    record.get("status", ""),
                    record.get("execution_time", ""),
                    record.get("confidence", ""),
                )
            )
        return tuple(rows)

    @staticmethod
    def log_rows(message: str) -> tuple[tuple[Any, ...], ...]:
        """Build sync log rows."""
        return (
            ("Timestamp", "Message"),
            (datetime.now().isoformat(timespec="seconds"), message),
        )

    def _load_optional(
        self,
        collection: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        try:
            return self._memory.load_record(collection, record_id)
        except FileNotFoundError:
            return None

    def _load_all(self, collection: str) -> tuple[dict[str, Any], ...]:
        records: list[dict[str, Any]] = []
        for key in self._memory.list_records(collection):
            try:
                records.append(self._memory.load_record(collection, key))
            except FileNotFoundError:
                continue
        return tuple(records)
