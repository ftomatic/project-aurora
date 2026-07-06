"""Prompt package models for Aurora creative production."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptPackage:
    """All production prompts needed for one product."""

    product_name: str
    collection: str
    theme: str
    style: str
    target_platforms: tuple[str, ...]
    image_prompt: str
    negative_prompt: str
    mockup_prompt: str
    listing_title_prompt: str
    listing_description_prompt: str
    seo_prompt: str
    pinterest_prompt: str
    instagram_prompt: str
    tiktok_prompt: str
    keywords: tuple[str, ...]
    notes: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable prompt package."""
        return {
            "product_name": self.product_name,
            "collection": self.collection,
            "theme": self.theme,
            "style": self.style,
            "target_platforms": list(self.target_platforms),
            "image_prompt": self.image_prompt,
            "negative_prompt": self.negative_prompt,
            "mockup_prompt": self.mockup_prompt,
            "listing_title_prompt": self.listing_title_prompt,
            "listing_description_prompt": self.listing_description_prompt,
            "seo_prompt": self.seo_prompt,
            "pinterest_prompt": self.pinterest_prompt,
            "instagram_prompt": self.instagram_prompt,
            "tiktok_prompt": self.tiktok_prompt,
            "keywords": list(self.keywords),
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    def render_summary(self) -> str:
        """Return a compact prompt package summary."""
        return "\n\n".join(
            (
                f"Product\n{self.product_name}",
                f"Collection\n{self.collection}",
                f"Prompt Style\n{self.style}",
                f"Platforms\n{', '.join(self.target_platforms)}",
                "Assets Generated\n"
                "Image Prompt, Negative Prompt, SEO Prompt, Pinterest Prompt, "
                "Instagram Prompt, TikTok Prompt",
            )
        )
