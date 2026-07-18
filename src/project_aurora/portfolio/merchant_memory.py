"""Merchant-minded portfolio memory and duplicate intelligence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from project_aurora.research.market_opportunity import MarketOpportunity


EXACT_DUPLICATE = "EXACT_DUPLICATE"
SAME_CONCEPT = "SAME_CONCEPT"
SAME_THEME_DIFFERENT_CATEGORY = "SAME_THEME_DIFFERENT_CATEGORY"
SEASONAL_REFRESH = "SEASONAL_REFRESH"
COMMERCIAL_VARIANT = "COMMERCIAL_VARIANT"
DIFFERENT = "DIFFERENT"


@dataclass(frozen=True, slots=True)
class MerchantMemoryRecord:
    """Production memory fingerprint used by Atlas."""

    product_concept: str
    theme: str
    style: str
    category: str
    bundle_size: int
    target_audience: str
    season: str
    primary_colors: tuple[str, ...] = field(default_factory=tuple)
    keywords: tuple[str, ...] = field(default_factory=tuple)
    creation_date: datetime = field(default_factory=datetime.now)
    similarity_fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "primary_colors", tuple(self.primary_colors))
        object.__setattr__(self, "keywords", tuple(self.keywords))
        if not self.similarity_fingerprint:
            object.__setattr__(self, "similarity_fingerprint", fingerprint_for_record(self))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe merchant memory."""
        return {
            "product_concept": self.product_concept,
            "theme": self.theme,
            "style": self.style,
            "category": self.category,
            "bundle_size": self.bundle_size,
            "target_audience": self.target_audience,
            "season": self.season,
            "primary_colors": list(self.primary_colors),
            "keywords": list(self.keywords),
            "creation_date": self.creation_date.isoformat(),
            "similarity_fingerprint": self.similarity_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SimilarityAssessment:
    """Decision-quality duplicate assessment."""

    score: int
    duplicate_class: str
    allowed: bool
    reason: str
    matched_product: str = ""
    suggested_alternatives: tuple[str, ...] = field(default_factory=tuple)
    suggested_style: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe assessment."""
        return {
            "similarity": self.score,
            "duplicate_class": self.duplicate_class,
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_product": self.matched_product,
            "suggested_alternatives": list(self.suggested_alternatives),
            "suggested_style": self.suggested_style,
        }


def record_from_opportunity(opportunity: MarketOpportunity) -> MerchantMemoryRecord:
    """Create a memory fingerprint from a selected opportunity."""
    return MerchantMemoryRecord(
        product_concept=opportunity.keyword,
        theme=opportunity.primary_niche,
        style=opportunity.recommended_artistic_style,
        category=opportunity.product_type,
        bundle_size=_bundle_size(opportunity.product_type, opportunity.keyword),
        target_audience=opportunity.target_audience,
        season=opportunity.season,
        keywords=tuple(_tokens(opportunity.keyword)),
    )


def analyze_similarity(
    opportunity: MarketOpportunity,
    records: tuple[MerchantMemoryRecord, ...],
    seasonal_cooldown_days: int = 90,
) -> SimilarityAssessment:
    """Return the strongest merchant duplicate assessment."""
    if not records:
        return SimilarityAssessment(0, DIFFERENT, True, "No related merchant memory.")
    candidate = record_from_opportunity(opportunity)
    assessments = tuple(
        _compare(candidate, record, seasonal_cooldown_days)
        for record in records
    )
    return max(assessments, key=lambda item: item.score)


def fingerprint_for_record(record: MerchantMemoryRecord) -> str:
    """Return a stable product fingerprint."""
    parts = (
        record.product_concept,
        record.theme,
        record.style,
        record.category,
        str(record.bundle_size),
        record.target_audience,
        record.season,
        " ".join(record.primary_colors),
        " ".join(record.keywords),
    )
    return "|".join(_normalize(part) for part in parts)


def alternatives_for(opportunity: MarketOpportunity) -> tuple[str, str, str]:
    """Return three nearby opportunities for a rejected product."""
    tokens = [token.title() for token in _tokens(opportunity.keyword) if token not in _STOPWORDS]
    theme = " ".join(tokens[:2]) if tokens else opportunity.primary_niche
    return (
        f"{theme} Alphabet Posters",
        f"{opportunity.primary_niche} Clipart",
        f"{theme} Digital Paper",
    )


def _compare(
    candidate: MerchantMemoryRecord,
    existing: MerchantMemoryRecord,
    seasonal_cooldown_days: int,
) -> SimilarityAssessment:
    score = similarity_score(candidate, existing)
    meaningful_difference = _meaningful_difference(candidate, existing)
    if _seasonal_refresh(candidate, existing):
        allowed = datetime.now() - existing.creation_date >= timedelta(days=seasonal_cooldown_days)
        return SimilarityAssessment(
            max(score, 65),
            SEASONAL_REFRESH,
            allowed,
            (
                "Seasonal refresh cooldown satisfied."
                if allowed
                else f"Seasonal refresh requires {seasonal_cooldown_days} days between similar products."
            ),
            existing.product_concept,
            alternatives_for_record(candidate),
            _suggested_style(existing.style),
        )
    if _exact_duplicate(candidate, existing):
        return SimilarityAssessment(
            100,
            EXACT_DUPLICATE,
            False,
            "Exact duplicate: same title, keywords, product type, style, and bundle.",
            existing.product_concept,
            alternatives_for_record(candidate),
            _suggested_style(existing.style),
        )
    if _same_theme_different_category(candidate, existing):
        return SimilarityAssessment(
            min(score, 60),
            SAME_THEME_DIFFERENT_CATEGORY,
            True,
            "Same theme but different product category; commercially useful cross-sell.",
            existing.product_concept,
        )
    if score >= 81:
        allowed = meaningful_difference
        return SimilarityAssessment(
            score,
            COMMERCIAL_VARIANT if allowed else EXACT_DUPLICATE,
            allowed,
            (
                "Very similar concept allowed because style, audience, palette, bundle, or positioning differs."
                if allowed
                else "Nearly identical to recent merchant memory."
            ),
            existing.product_concept,
            alternatives_for_record(candidate),
            _suggested_style(existing.style),
        )
    if score >= 61:
        return SimilarityAssessment(
            score,
            COMMERCIAL_VARIANT if meaningful_difference else SAME_CONCEPT,
            True,
            "Related concept; allowed with differentiated execution.",
            existing.product_concept,
        )
    if score >= 31:
        return SimilarityAssessment(
            score,
            SAME_CONCEPT,
            True,
            "Related but safely differentiated.",
            existing.product_concept,
        )
    return SimilarityAssessment(score, DIFFERENT, True, "Different product opportunity.", existing.product_concept)


def similarity_score(left: MerchantMemoryRecord, right: MerchantMemoryRecord) -> int:
    """Return 0-100 merchant similarity score."""
    if _exact_duplicate(left, right):
        return 100
    title = _text_similarity(left.product_concept, right.product_concept)
    keyword = _set_similarity(set(left.keywords), set(right.keywords))
    theme = 1.0 if _normalize(left.theme) == _normalize(right.theme) else 0.0
    category = 1.0 if _normalize(left.category) == _normalize(right.category) else 0.0
    style = 1.0 if _normalize(left.style) == _normalize(right.style) else 0.0
    audience = 1.0 if _normalize(left.target_audience) == _normalize(right.target_audience) else 0.0
    bundle = 1.0 if left.bundle_size == right.bundle_size else 0.0
    return round(
        (title * 0.32 + keyword * 0.20 + theme * 0.14 + category * 0.12 + style * 0.10 + audience * 0.06 + bundle * 0.04)
        * 100
    )


def alternatives_for_record(record: MerchantMemoryRecord) -> tuple[str, str, str]:
    fake = _FakeOpportunity(record.product_concept, record.theme)
    return alternatives_for(fake)  # type: ignore[arg-type]


def _exact_duplicate(left: MerchantMemoryRecord, right: MerchantMemoryRecord) -> bool:
    return (
        _normalize(left.product_concept) == _normalize(right.product_concept)
        and _normalize(left.category) == _normalize(right.category)
        and _normalize(left.style) == _normalize(right.style)
        and left.bundle_size == right.bundle_size
        and (not left.keywords or not right.keywords or bool(set(left.keywords) & set(right.keywords)))
    )


def _same_theme_different_category(left: MerchantMemoryRecord, right: MerchantMemoryRecord) -> bool:
    return (
        _shared_theme(left, right)
        and _normalize(left.category) != _normalize(right.category)
    )


def _seasonal_refresh(left: MerchantMemoryRecord, right: MerchantMemoryRecord) -> bool:
    seasonal = {"christmas", "halloween", "easter", "thanksgiving", "valentine", "mother", "father"}
    return bool(set(left.keywords) & seasonal and set(right.keywords) & seasonal and _shared_theme(left, right))


def _meaningful_difference(left: MerchantMemoryRecord, right: MerchantMemoryRecord) -> bool:
    return any(
        (
            _normalize(left.style) != _normalize(right.style),
            _normalize(left.target_audience) != _normalize(right.target_audience),
            _normalize(left.category) != _normalize(right.category),
            left.bundle_size != right.bundle_size,
            set(left.primary_colors) != set(right.primary_colors),
        )
    )


def _shared_theme(left: MerchantMemoryRecord, right: MerchantMemoryRecord) -> bool:
    return bool((set(left.keywords) & set(right.keywords)) or _normalize(left.theme) == _normalize(right.theme))


def _suggested_style(existing_style: str) -> str:
    if "watercolor" in existing_style.casefold():
        return "Vintage Botanical"
    if "vintage" in existing_style.casefold():
        return "Storybook Watercolor"
    return "Soft Cottagecore"


def _bundle_size(product_type: str, product_name: str) -> int:
    match = re.search(r"\b(\d{1,3})\b", product_name)
    if match:
        return int(match.group(1))
    lowered = product_type.casefold()
    if "digital paper" in lowered:
        return 12
    if "clipart" in lowered:
        return 8
    return 4


def _text_similarity(left: str, right: str) -> float:
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if left_norm == right_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _set_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _normalize(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^a-z0-9]+", value.casefold()) if token)


_STOPWORDS = {
    "art",
    "back",
    "bundle",
    "digital",
    "paper",
    "printable",
    "product",
    "png",
    "school",
    "set",
    "stickers",
    "sticker",
    "to",
    "wall",
    "clipart",
}


class _FakeOpportunity:
    def __init__(self, keyword: str, primary_niche: str) -> None:
        self.keyword = keyword
        self.primary_niche = primary_niche
