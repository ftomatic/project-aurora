"""Resolve whether Aurora can professionally create a product."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "supported": self.supported,
            "reason": self.reason,
            "max_words_allowed": self.max_words_allowed,
            "generated_at": self.generated_at.isoformat(),
        }


class ProductCapabilityResolver:
    """Classify products before paid generation."""

    def __init__(self, maximum_short_text_words: int = 5) -> None:
        self._maximum_short_text_words = maximum_short_text_words

    def resolve(self, product_name: str, product_type: str, category: str) -> ProductCapabilityResult:
        lowered = f"{product_name} {product_type} {category}".casefold()
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
            )
        if any(term in lowered for term in (
            "wall art",
            "clipart",
            "digital paper",
            "pattern",
            "botanical print",
            "nursery",
            "scrapbook",
            "journaling paper",
            "gift tags",
            "stationery",
        )):
            return ProductCapabilityResult(
                mode=IMAGE_ONLY,
                supported=True,
                reason="Product can be produced as image-first commercial PNG assets.",
                max_words_allowed=self._maximum_short_text_words,
            )
        word_count = len([word for word in product_name.split() if word.strip()])
        if word_count <= self._maximum_short_text_words:
            return ProductCapabilityResult(
                mode=IMAGE_WITH_SHORT_TEXT,
                supported=True,
                reason="Product contains only short verified text.",
                max_words_allowed=self._maximum_short_text_words,
            )
        return ProductCapabilityResult(
            mode=UNSUPPORTED,
            supported=False,
            reason="No safe product capability mapping exists.",
            max_words_allowed=self._maximum_short_text_words,
        )
