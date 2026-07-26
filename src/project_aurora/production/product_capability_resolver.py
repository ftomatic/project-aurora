"""Resolve whether Aurora can professionally create a product."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from project_aurora.production.watercolor_scope import resolve_watercolor_scope


IMAGE_ONLY = "IMAGE_ONLY"
IMAGE_WITH_SHORT_TEXT = "IMAGE_WITH_SHORT_TEXT"
TEMPLATE_REQUIRED = "TEMPLATE_REQUIRED"
UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class ProductCapabilityResult:
    """Capability classification for a production job."""

    mode: str
    supported: bool
    reason: str
    max_words_allowed: int = 5
    requires_zip_package: bool = False
    required_deliverable_count: int = 0
    requires_layout_engine: bool = False
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "supported": self.supported,
            "reason": self.reason,
            "max_words_allowed": self.max_words_allowed,
            "requires_zip_package": self.requires_zip_package,
            "required_deliverable_count": self.required_deliverable_count,
            "requires_layout_engine": self.requires_layout_engine,
            "generated_at": self.generated_at.isoformat(),
        }


class ProductCapabilityResolver:
    """Classify products before paid generation."""

    def __init__(self, maximum_short_text_words: int = 5) -> None:
        self._maximum_short_text_words = maximum_short_text_words

    def resolve(self, product_name: str, product_type: str, category: str) -> ProductCapabilityResult:
        lowered = f"{product_name} {product_type} {category}".casefold()
        scope = resolve_watercolor_scope(product_name, category or product_type)
        if not scope.supported:
            return ProductCapabilityResult(
                mode=UNSUPPORTED,
                supported=False,
                reason=scope.reason,
                max_words_allowed=self._maximum_short_text_words,
            )
        if any(term in lowered for term in (
            "shower games",
            "worksheet",
            "planner",
            "calendar",
            "flashcard",
            "checklist",
            "form",
            "recipe card",
            "game",
        )):
            return ProductCapabilityResult(
                mode=TEMPLATE_REQUIRED,
                supported=False,
                reason="Product requires a template/text engine before paid image generation.",
                max_words_allowed=self._maximum_short_text_words,
                requires_layout_engine=True,
            )
        return ProductCapabilityResult(
            mode=IMAGE_ONLY,
            supported=True,
            reason=scope.reason,
            max_words_allowed=self._maximum_short_text_words,
            requires_zip_package=True,
            required_deliverable_count=4,
        )
