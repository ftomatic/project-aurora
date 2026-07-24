"""Resolve whether Aurora can professionally create a product."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
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

    def __init__(
        self,
        maximum_short_text_words: int = 5,
        specification_library: Any | None = None,
    ) -> None:
        self._maximum_short_text_words = maximum_short_text_words
        self._specification_library = specification_library

    def resolve(
        self,
        product_name: str,
        product_type: str,
        category: str,
        assets_dir: Path | None = None,
    ) -> ProductCapabilityResult:
        lowered = f"{product_name} {product_type} {category}".casefold()
        if any(term in lowered for term in (
            "shower games",
            "worksheet",
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
        spec = self._resolve_spec(category=category, product_name=product_name)
        if spec is not None:
            blocked = self._blocked_by_spec(spec, lowered, assets_dir)
            if blocked is not None:
                return blocked
            return ProductCapabilityResult(
                mode=IMAGE_ONLY,
                supported=True,
                reason="Product requirements fit the current image production pipeline.",
                max_words_allowed=self._maximum_short_text_words,
                requires_zip_package=str(getattr(spec, "packaging", "")).casefold() == "zip",
                required_deliverable_count=int(spec.bundle_size),
                requires_layout_engine=False,
            )
        if any(term in lowered for term in (
            "wall art",
            "clipart",
            "digital paper",
            "planner",
            "junk journal",
            "journal kit",
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

    def _resolve_spec(self, category: str, product_name: str) -> Any | None:
        if self._specification_library is not None:
            library = self._specification_library
        else:
            from project_aurora.production.merchant_specification import (
                MerchantSpecificationLibrary,
            )

            library = MerchantSpecificationLibrary()
        try:
            return library.resolve(category, product_name)
        except RuntimeError:
            return None

    def _blocked_by_spec(
        self,
        spec: Any,
        lowered_product: str,
        assets_dir: Path | None,
    ) -> ProductCapabilityResult | None:
        bundle_size = int(getattr(spec, "bundle_size", 0))
        requires_zip = str(getattr(spec, "packaging", "")).casefold() == "zip"
        requires_layout = (
            "sticker" in lowered_product
            and (
                "sheet" in lowered_product
                or any(
                    "sheet" in str(value).casefold()
                    or "layout" in str(value).casefold()
                    or "template" in str(value).casefold()
                    for value in (
                        *getattr(spec, "preview_requirements", ()),
                        *getattr(spec, "qa_requirements", ()),
                        *getattr(spec, "thumbnail_rules", ()),
                    )
                )
            )
        )
        if bundle_size > 20:
            return ProductCapabilityResult(
                mode=UNSUPPORTED,
                supported=False,
                reason=(
                    f"{getattr(spec, 'category', 'Product')} requires "
                    f"{bundle_size} deliverable files; current limit is 20."
                ),
                max_words_allowed=self._maximum_short_text_words,
                requires_zip_package=False,
                required_deliverable_count=bundle_size,
                requires_layout_engine=requires_layout,
            )
        if requires_layout:
            from project_aurora.production.layout_template_engine import (
                layout_template_exists,
            )

            if layout_template_exists(assets_dir):
                return None
            return ProductCapabilityResult(
                mode=TEMPLATE_REQUIRED,
                supported=False,
                reason="Sticker sheet requires a layout/template engine before paid image generation.",
                max_words_allowed=self._maximum_short_text_words,
                requires_zip_package=False,
                required_deliverable_count=bundle_size,
                requires_layout_engine=True,
            )
        if requires_zip:
            return ProductCapabilityResult(
                mode=UNSUPPORTED,
                supported=False,
                reason=(
                    f"{getattr(spec, 'category', 'Product')} requires a ZIP package; "
                    "standard daily production only supports non-ZIP four-image products."
                ),
                max_words_allowed=self._maximum_short_text_words,
                requires_zip_package=True,
                required_deliverable_count=bundle_size,
                requires_layout_engine=requires_layout,
            )
        return None
