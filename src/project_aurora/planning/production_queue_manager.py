"""Persistent production job queue for Aurora planning."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


READY = "READY"
IN_PROGRESS = "IN_PROGRESS"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"

SUPPORTED_JOB_STATUSES = {
    READY,
    IN_PROGRESS,
    COMPLETED,
    FAILED,
    SKIPPED,
}


@dataclass(frozen=True, slots=True)
class ProductionJob:
    """A planned product production job, not a finished product."""

    id: str
    priority: str
    product_name: str
    category: str
    style: str
    seasonal_theme: str
    keywords: tuple[str, ...]
    confidence_score: float
    estimated_competition: str
    estimated_demand: str
    estimated_revenue: float
    created_at: datetime = field(default_factory=datetime.now)
    status: str = READY

    def __post_init__(self) -> None:
        for field_name in (
            "id",
            "priority",
            "product_name",
            "category",
            "style",
            "seasonal_theme",
            "estimated_competition",
            "estimated_demand",
        ):
            value = str(getattr(self, field_name))
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
        normalized_status = self.status.strip().upper()
        if normalized_status not in SUPPORTED_JOB_STATUSES:
            raise ValueError(f"Unsupported job status: {self.status}.")
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("confidence_score must be between 0 and 1.")
        if self.estimated_revenue < 0:
            raise ValueError("estimated_revenue cannot be negative.")
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "keywords", tuple(self.keywords))

    def with_status(self, status: str) -> "ProductionJob":
        """Return this job with an updated status."""
        return replace(self, status=status)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe job data."""
        return {
            "id": self.id,
            "priority": self.priority,
            "product_name": self.product_name,
            "category": self.category,
            "style": self.style,
            "seasonal_theme": self.seasonal_theme,
            "keywords": list(self.keywords),
            "confidence_score": self.confidence_score,
            "estimated_competition": self.estimated_competition,
            "estimated_demand": self.estimated_demand,
            "estimated_revenue": self.estimated_revenue,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductionJob":
        """Create a production job from persisted JSON data."""
        created_at = data.get("created_at")
        return cls(
            id=str(data["id"]),
            priority=str(data["priority"]),
            product_name=str(data["product_name"]),
            category=str(data["category"]),
            style=str(data["style"]),
            seasonal_theme=str(data["seasonal_theme"]),
            keywords=tuple(str(value) for value in data.get("keywords", ())),
            confidence_score=float(data["confidence_score"]),
            estimated_competition=str(data["estimated_competition"]),
            estimated_demand=str(data["estimated_demand"]),
            estimated_revenue=float(data["estimated_revenue"]),
            created_at=(
                datetime.fromisoformat(str(created_at))
                if created_at
                else datetime.now()
            ),
            status=str(data.get("status", READY)),
        )


class ProductionQueueManager:
    """Manage and persist Aurora production planning jobs."""

    def __init__(
        self,
        queue_path: Path | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._queue_path = (
            queue_path
            or Path("data") / "aurora" / "production_queue" / "queue.json"
        )
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._jobs = self._load_jobs()

    @property
    def queue_path(self) -> Path:
        """Return the queue JSON path."""
        return self._queue_path

    def add_job(
        self,
        *,
        priority: str,
        product_name: str,
        category: str,
        style: str,
        seasonal_theme: str,
        keywords: tuple[str, ...],
        confidence_score: float,
        estimated_competition: str,
        estimated_demand: str,
        estimated_revenue: float,
        status: str = READY,
    ) -> ProductionJob:
        """Add and persist a production job, preventing duplicate products."""
        if self._contains_product(product_name):
            raise ValueError(f"Production job already exists: {product_name}.")
        job = ProductionJob(
            id=self._id_factory(),
            priority=priority,
            product_name=product_name,
            category=category,
            style=style,
            seasonal_theme=seasonal_theme,
            keywords=keywords,
            confidence_score=confidence_score,
            estimated_competition=estimated_competition,
            estimated_demand=estimated_demand,
            estimated_revenue=estimated_revenue,
            status=status,
        )
        self._jobs = self._sorted_jobs((*self._jobs, job))
        self._save()
        return job

    def add_existing_job(self, job: ProductionJob) -> ProductionJob:
        """Persist a prebuilt job, preventing duplicate products."""
        if self._contains_product(job.product_name):
            raise ValueError(f"Production job already exists: {job.product_name}.")
        self._jobs = self._sorted_jobs((*self._jobs, job))
        self._save()
        return job

    def remove_job(self, job_id: str) -> None:
        """Remove a job by id and persist the queue."""
        jobs = tuple(job for job in self._jobs if job.id != job_id)
        if len(jobs) == len(self._jobs):
            raise ValueError(f"Production job not found: {job_id}.")
        self._jobs = jobs
        self._save()

    def mark_in_progress(self, job_id: str) -> ProductionJob:
        """Mark a job in progress."""
        return self._mark_status(job_id, IN_PROGRESS)

    def mark_completed(self, job_id: str) -> ProductionJob:
        """Mark a job completed."""
        return self._mark_status(job_id, COMPLETED)

    def mark_failed(self, job_id: str) -> ProductionJob:
        """Mark a job failed."""
        return self._mark_status(job_id, FAILED)

    def next_ready_job(self) -> ProductionJob | None:
        """Return the highest-confidence ready job."""
        for job in self._sorted_jobs(self._jobs):
            if job.status == READY:
                return job
        return None

    def list_jobs(self) -> tuple[ProductionJob, ...]:
        """Return jobs in deterministic production order."""
        return self._sorted_jobs(self._jobs)

    def product_names(self) -> set[str]:
        """Return normalized product names already in the queue."""
        return {_normalize_product_name(job.product_name) for job in self._jobs}

    def _mark_status(self, job_id: str, status: str) -> ProductionJob:
        updated: list[ProductionJob] = []
        changed_job: ProductionJob | None = None
        for job in self._jobs:
            if job.id == job_id:
                changed_job = job.with_status(status)
                updated.append(changed_job)
            else:
                updated.append(job)
        if changed_job is None:
            raise ValueError(f"Production job not found: {job_id}.")
        self._jobs = self._sorted_jobs(tuple(updated))
        self._save()
        return changed_job

    def _load_jobs(self) -> tuple[ProductionJob, ...]:
        if not self._queue_path.exists():
            return ()
        try:
            payload = json.loads(self._queue_path.read_text(encoding="utf-8"))
            items = payload.get("jobs")
            if not isinstance(items, list):
                return ()
            return self._sorted_jobs(
                tuple(
                    ProductionJob.from_dict(item)
                    for item in items
                    if isinstance(item, dict)
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return ()

    def _save(self) -> None:
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at": datetime.now().isoformat(),
            "job_count": len(self._jobs),
            "jobs": [job.to_dict() for job in self._sorted_jobs(self._jobs)],
        }
        self._queue_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _contains_product(self, product_name: str) -> bool:
        normalized = _normalize_product_name(product_name)
        return any(
            _normalize_product_name(job.product_name) == normalized
            for job in self._jobs
        )

    @staticmethod
    def _sorted_jobs(jobs: tuple[ProductionJob, ...]) -> tuple[ProductionJob, ...]:
        return tuple(
            sorted(
                jobs,
                key=lambda job: (
                    -job.confidence_score,
                    -job.estimated_revenue,
                    job.product_name.casefold(),
                    job.created_at.isoformat(),
                    job.id,
                ),
            )
        )


def _normalize_product_name(value: str) -> str:
    return " ".join(value.casefold().strip().split())
