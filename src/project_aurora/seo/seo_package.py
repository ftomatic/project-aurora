"""SEO package model for Etsy listing preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SEOPackage:
    """Deterministic Etsy SEO assets for one product."""

    product_name: str
    product_type: str
    target_buyer: str
    title: str
    tags: tuple[str, ...]
    description: str
    keywords: tuple[str, ...]
    buyer_use_case: str
    product_positioning: str
    seo_score: int
    job_id: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)
    generated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("Product name cannot be empty.")
        if not self.product_type.strip():
            raise ValueError("Product type cannot be empty.")
        if len(self.tags) != 13:
            raise ValueError("Etsy SEO packages must include exactly 13 tags.")
        if not 0 <= self.seo_score <= 100:
            raise ValueError("SEO score must be between 0 and 100.")

        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "keywords", tuple(self.keywords))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.generated_at is None:
            object.__setattr__(self, "generated_at", self.created_at)

    @property
    def status(self) -> str:
        """Return package status for CLI display."""
        if self.seo_score >= 80:
            return "SUCCESS"
        if self.seo_score >= 65:
            return "WARNING"
        return "NEEDS REVIEW"
