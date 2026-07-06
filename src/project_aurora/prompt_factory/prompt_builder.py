"""Prompt builders for Aurora prompt packages."""

from __future__ import annotations

from project_aurora.production.queue_item import ProductionQueueItem
from project_aurora.prompt_factory.prompt_package import PromptPackage
from project_aurora.prompt_factory.prompt_templates import (
    NEGATIVE_PROMPT_LINES,
    PromptTemplate,
    get_templates,
    select_template_names,
)


class PromptBuilder:
    """Build deterministic creative prompts from production queue items."""

    def build_package(self, item: ProductionQueueItem) -> PromptPackage:
        """Return a prompt package for a production queue item."""
        template_names = select_template_names(
            product_name=item.product_name,
            product_category=item.product_category,
            content_type=item.content_type,
        )
        templates = get_templates(template_names)
        style = " ".join(template.name for template in templates)
        theme = self._theme_from_product(item.product_name)
        collection = self._collection_from_item(item)
        keywords = self._keywords(item, theme)

        return PromptPackage(
            product_name=item.product_name,
            collection=collection,
            theme=theme,
            style=style,
            target_platforms=(item.platform,),
            image_prompt=self._image_prompt(item, theme, templates),
            negative_prompt="\n".join(NEGATIVE_PROMPT_LINES),
            mockup_prompt=self._mockup_prompt(item, collection),
            listing_title_prompt=self._listing_title_prompt(item, collection),
            listing_description_prompt=self._listing_description_prompt(
                item,
                collection,
            ),
            seo_prompt=self._seo_prompt(item, keywords),
            pinterest_prompt=self._pinterest_prompt(item, collection),
            instagram_prompt=self._instagram_prompt(item, collection),
            tiktok_prompt=self._tiktok_prompt(item, collection),
            keywords=keywords,
            notes=f"Generated from production queue item {item.id}.",
            created_at=item.updated_at,
        )

    @staticmethod
    def _theme_from_product(product_name: str) -> str:
        words = product_name.split()
        if len(words) <= 2:
            return product_name
        return " ".join(words[:2])

    @staticmethod
    def _collection_from_item(item: ProductionQueueItem) -> str:
        marker = "Collection:"
        if marker in item.prompt:
            after_marker = item.prompt.split(marker, maxsplit=1)[1]
            collection = after_marker.split(".", maxsplit=1)[0].strip()
            if collection:
                return collection
        if "Collection" in item.product_name:
            return item.product_name
        return f"{item.product_name} Collection"

    @staticmethod
    def _image_prompt(
        item: ProductionQueueItem,
        theme: str,
        templates: tuple[PromptTemplate, ...],
    ) -> str:
        descriptors: list[str] = []
        for template in templates:
            descriptors.extend(template.descriptors)

        primary_template = templates[0]
        prompt_parts = (
            f"A whimsical {theme.lower()} design for {item.product_name}",
            *descriptors,
            primary_template.lighting,
            "highly detailed",
            primary_template.atmosphere,
            primary_template.finish,
        )
        return ",\n".join(prompt_parts) + "."

    @staticmethod
    def _mockup_prompt(
        item: ProductionQueueItem,
        collection: str,
    ) -> str:
        return (
            f"Create a clean product mockup concept for {collection} on "
            f"{item.platform}, showing the {item.product_category} clearly "
            "with bright natural light and no distracting props."
        )

    @staticmethod
    def _listing_title_prompt(
        item: ProductionQueueItem,
        collection: str,
    ) -> str:
        return (
            f"Write an Etsy-ready listing title for {collection}, emphasizing "
            f"{item.product_name}, printable use, buyer intent, and clear "
            "search terms."
        )

    @staticmethod
    def _listing_description_prompt(
        item: ProductionQueueItem,
        collection: str,
    ) -> str:
        return (
            f"Write a polished listing description for {collection}. Explain "
            f"what is included in the {item.product_category}, who it is for, "
            "how buyers can use it, and why it feels special."
        )

    @staticmethod
    def _seo_prompt(
        item: ProductionQueueItem,
        keywords: tuple[str, ...],
    ) -> str:
        return (
            f"Create SEO copy for {item.product_name} using these keywords: "
            f"{', '.join(keywords)}. Keep the tone clear, warm, and "
            "buyer-focused."
        )

    @staticmethod
    def _pinterest_prompt(
        item: ProductionQueueItem,
        collection: str,
    ) -> str:
        return (
            f"Write a Pinterest pin description for {collection} that uses "
            f"{item.product_name} naturally and encourages party planners and "
            "creative buyers to save the idea."
        )

    @staticmethod
    def _instagram_prompt(
        item: ProductionQueueItem,
        collection: str,
    ) -> str:
        return (
            f"Write an Instagram caption for {collection} with a friendly "
            "studio voice, concise benefit-led copy, and relevant hashtags."
        )

    @staticmethod
    def _tiktok_prompt(
        item: ProductionQueueItem,
        collection: str,
    ) -> str:
        return (
            f"Write a short TikTok video script for {collection}: opening "
            "hook, three quick visual beats, and a gentle call to action."
        )

    @staticmethod
    def _keywords(
        item: ProductionQueueItem,
        theme: str,
    ) -> tuple[str, ...]:
        normalized_theme = theme.lower()
        return (
            item.product_name.lower(),
            item.product_category.lower(),
            normalized_theme,
            f"{normalized_theme} printable",
            f"{normalized_theme} party",
            item.platform.lower(),
        )
