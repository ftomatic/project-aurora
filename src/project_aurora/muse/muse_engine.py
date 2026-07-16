"""Muse style selection engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_aurora.muse.art_direction import ArtDirection
from project_aurora.muse.style_library import MuseStyleLibrary
from project_aurora.muse.style_memory import StyleMemory
from project_aurora.muse.style_profile import MuseStyleProfile
from project_aurora.muse.style_settings import StyleSettings
from project_aurora.storage.memory_manager import MemoryManager


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class StyleCandidateScore:
    """One scored style candidate."""

    style_name: str
    score: int
    reason: str


class MuseEngine:
    """Choose the best artistic direction for a product."""

    def __init__(
        self,
        library: MuseStyleLibrary | None = None,
        settings: StyleSettings | None = None,
        memory: MemoryManager | None = None,
        style_memory: StyleMemory | None = None,
    ) -> None:
        self._library = library or MuseStyleLibrary.from_file(PROJECT_ROOT / "config" / "style_library.yaml")
        self._settings = settings or StyleSettings.from_file(PROJECT_ROOT / "config" / "style_settings.yaml")
        self._memory = memory
        self._style_memory = style_memory or StyleMemory(memory=memory)

    @property
    def styles(self) -> tuple[MuseStyleProfile, ...]:
        """Return available styles."""
        return self._library.profiles

    def style_profile(self, style_name: str) -> MuseStyleProfile:
        """Return a style profile by name."""
        return self._library.get(style_name)

    def select_style(
        self,
        product: str,
        audience: str = "",
        season: str = "",
        competition: str = "",
        current_portfolio: tuple[str, ...] = (),
        historical_products: tuple[str, ...] = (),
        product_type: str = "",
    ) -> ArtDirection:
        """Research and select an art direction using deterministic scoring."""
        scores = tuple(
            self._score_style(
                profile,
                product=product,
                audience=audience,
                season=season,
                competition=competition,
                current_portfolio=current_portfolio,
                historical_products=historical_products,
                product_type=product_type,
            )
            for profile in self._library.profiles
        )
        ranked = tuple(sorted(scores, key=lambda item: item.score, reverse=True))
        best = ranked[0]
        profile = self._library.get(best.style_name)
        direction = ArtDirection(
            product_name=product,
            recommended_style=profile.name,
            confidence=best.score,
            reason=best.reason,
            palette=", ".join(profile.typical_color_palette),
            rendering_method=profile.rendering_method,
            composition=_composition_for_product(product, product_type),
            mood=_mood_for_product(product, season),
            trend_score=profile.trend_score,
            portfolio_diversity=_portfolio_diversity(best.style_name, current_portfolio, self._settings.maximum_style_reuse),
            alternative_styles=tuple((item.style_name, item.score) for item in ranked[1:4]),
        )
        if direction.confidence < self._settings.minimum_style_confidence:
            return direction
        self._style_memory.remember(product, direction.recommended_style)
        if self._memory is not None:
            self._memory.save_record("muse_art_directions", _slug(product), direction)
        return direction

    def _score_style(
        self,
        profile: MuseStyleProfile,
        product: str,
        audience: str,
        season: str,
        competition: str,
        current_portfolio: tuple[str, ...],
        historical_products: tuple[str, ...],
        product_type: str,
    ) -> StyleCandidateScore:
        haystack = f"{product} {product_type}".casefold()
        score = 20 + int(profile.commercial_appeal * 0.25) + int(profile.trend_score * 0.25)
        product_matches = _count_matches(haystack, profile.products_it_fits)
        audience_matches = _count_matches(audience.casefold(), profile.target_audience)
        season_matches = _count_matches(season.casefold(), profile.seasonality)
        avoid_matches = _count_matches(haystack, profile.avoid_using_with)
        score += product_matches * 18
        score += audience_matches * 8
        score += season_matches * self._settings.season_weight
        score -= avoid_matches * 30
        reuse_count = sum(1 for style in current_portfolio if style.casefold() == profile.name.casefold())
        reuse_count += self._style_memory.count_recent_style(profile.name)
        if reuse_count >= self._settings.maximum_style_reuse:
            score -= self._settings.style_rotation_weight * (reuse_count - self._settings.maximum_style_reuse + 1)
        if any(profile.name.casefold() in item.casefold() for item in historical_products):
            score -= 6
        if competition.casefold() == "high":
            score += 3 if profile.commercial_appeal >= 88 else -3
        score = max(0, min(100, score))
        reason = (
            f"Fits {product} with {product_matches} product match(es), "
            f"trend score {profile.trend_score}, reuse count {reuse_count}."
        )
        return StyleCandidateScore(profile.name, score, reason)


def _count_matches(text: str, values: tuple[str, ...]) -> int:
    return sum(1 for value in values if value.casefold() in text)


def _composition_for_product(product: str, product_type: str) -> str:
    lowered = f"{product} {product_type}".casefold()
    if "paper" in lowered or "pattern" in lowered:
        return "Seamless pattern layout"
    if "invitation" in lowered:
        return "Elegant centered stationery layout"
    if "sticker" in lowered:
        return "Sticker sheet with clear individual icons"
    if "clipart" in lowered or "mushroom" in lowered:
        return "Individual isolated elements"
    return "Centered printable art composition"


def _mood_for_product(product: str, season: str) -> str:
    lowered = f"{product} {season}".casefold()
    if "dark academia" in lowered:
        return "Moody scholarly"
    if "wedding" in lowered:
        return "Romantic elegant"
    if "coastal" in lowered:
        return "Breezy seaside"
    if "autumn" in lowered or "mushroom" in lowered:
        return "Cozy woodland"
    if "teacher" in lowered:
        return "Bright classroom"
    return "Commercially polished"


def _portfolio_diversity(style: str, current_portfolio: tuple[str, ...], maximum_reuse: int) -> str:
    count = sum(1 for item in current_portfolio if item.casefold() == style.casefold())
    return "Healthy" if count < maximum_reuse else "Overused"


def _slug(value: str) -> str:
    return "_".join(part for part in value.casefold().replace("-", " ").split() if part)
