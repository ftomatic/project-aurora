"""SEO and keyword engine for Project Aurora."""

from __future__ import annotations

from typing import Any

from project_aurora.seo.description_builder import DescriptionBuilder
from project_aurora.seo.keyword_engine import KeywordEngine
from project_aurora.seo.seo_package import SEOPackage
from project_aurora.seo.title_builder import TitleBuilder
from project_aurora.storage.memory_manager import MemoryManager


class SEOEngine:
    """Generate Etsy-ready SEO packages from local product data."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        keyword_engine: KeywordEngine | None = None,
        title_builder: TitleBuilder | None = None,
        description_builder: DescriptionBuilder | None = None,
    ) -> None:
        self._memory = memory
        self._keyword_engine = keyword_engine or KeywordEngine()
        self._title_builder = title_builder or TitleBuilder()
        self._description_builder = description_builder or DescriptionBuilder()

    def build_package(
        self,
        product_data: dict[str, Any],
    ) -> SEOPackage:
        """Return an Etsy-ready SEO package."""
        product_name = self._get_value(product_data, "product_name")
        product_type = self._get_value(product_data, "product_type")
        target_buyer = self._get_value(product_data, "target_buyer")
        buyer_use_case = self._buyer_use_case(target_buyer)
        product_positioning = self._product_positioning(
            product_name,
            product_type,
        )
        keywords = self._keyword_engine.build_keywords(
            product_name,
            product_type,
            target_buyer,
        )
        tags = self._keyword_engine.build_tags(
            product_name,
            product_type,
            target_buyer,
        )
        title = self._title_builder.build_title(
            product_name,
            product_type,
            keywords,
        )
        description = self._description_builder.build_description(
            product_name=product_name,
            product_type=product_type,
            target_buyer=target_buyer,
            buyer_use_case=buyer_use_case,
            product_positioning=product_positioning,
            tags=tags,
        )
        warnings = self._warnings(title, tags)
        score = self._score(title, tags, description, warnings)

        return SEOPackage(
            product_name=product_name,
            product_type=product_type,
            target_buyer=target_buyer,
            title=title,
            tags=tags,
            description=description,
            keywords=keywords,
            buyer_use_case=buyer_use_case,
            product_positioning=product_positioning,
            seo_score=score,
            warnings=warnings,
        )

    def run(
        self,
        product_data: dict[str, Any],
        package_id: str = "latest",
    ) -> SEOPackage:
        """Build and save an SEO package."""
        package = self.build_package(product_data)
        if self._memory is not None:
            self._memory.save_seo_package(package, package_id=package_id)
        return package

    @staticmethod
    def _get_value(product_data: dict[str, Any], field_name: str) -> str:
        value = product_data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"SEO product field is required: {field_name}.")
        return value.strip()

    @staticmethod
    def _buyer_use_case(target_buyer: str) -> str:
        return (
            f"{target_buyer} who want coordinated invitations, cupcake toppers, "
            "favor tags, thank-you cards, and party decor without starting from "
            "scratch"
        )

    @staticmethod
    def _product_positioning(
        product_name: str,
        product_type: str,
    ) -> str:
        return (
            f"Cute cottagecore strawberry {product_type.lower()} for summer "
            f"birthday celebrations, centered on {product_name}."
        )

    @staticmethod
    def _warnings(title: str, tags: tuple[str, ...]) -> tuple[str, ...]:
        warnings: list[str] = []
        if len(title) > 140:
            warnings.append("Title is longer than Etsy's 140-character limit.")
        long_tags = tuple(tag for tag in tags if len(tag) > 20)
        if long_tags:
            warnings.append(
                "Tags exceed Etsy's 20-character limit: "
                f"{', '.join(long_tags)}."
            )
        if len(tags) != 13:
            warnings.append("Etsy listings should include exactly 13 tags.")
        return tuple(warnings)

    @staticmethod
    def _score(
        title: str,
        tags: tuple[str, ...],
        description: str,
        warnings: tuple[str, ...],
    ) -> int:
        score = 72
        if "Strawberry" in title and "Birthday" in title:
            score += 8
        if len(tags) == 13:
            score += 8
        if all(len(tag) <= 20 for tag in tags):
            score += 5
        if len(description) >= 300:
            score += 4
        if "Digital download" in description:
            score += 3
        score -= len(warnings) * 6
        return max(0, min(100, score))
