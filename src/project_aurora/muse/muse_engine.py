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
from project_aurora.style.proven_winner_memory import ProvenWinnerMemory
from project_aurora.style.style_registry import MarketStyle, StyleRegistry
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
        style_registry: StyleRegistry | None = None,
        proven_winner_memory: ProvenWinnerMemory | None = None,
    ) -> None:
        self._library = library or MuseStyleLibrary.from_file(PROJECT_ROOT / "config" / "style_library.yaml")
        self._settings = settings or StyleSettings.from_file(PROJECT_ROOT / "config" / "style_settings.yaml")
        self._memory = memory
        self._style_memory = style_memory or StyleMemory(memory=memory)
        self._style_registry = style_registry or StyleRegistry.from_config()
        self._proven_winners = proven_winner_memory or ProvenWinnerMemory.from_config()

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
        category = _category_for(product, product_type)
        market_scores = self._score_market_styles(
            product=product,
            category=category,
            audience=audience,
            season=season,
            competition=competition,
            current_portfolio=current_portfolio,
            product_type=product_type,
        )
        if market_scores:
            best_market = market_scores[0]
            style = self._style_registry.get(best_market.style_name)
            direction = _direction_from_market_style(
                product=product,
                category=category,
                style=style,
                score=best_market,
                alternatives=market_scores[1:4],
            )
            if direction.confidence >= self._settings.minimum_style_confidence:
                self._style_memory.remember(product, direction.recommended_style)
                if self._memory is not None:
                    self._memory.save_record("muse_art_directions", _slug(product), direction)
            return direction

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
            background_treatment="clean printable background",
            lighting="style-appropriate lighting",
            texture=profile.texture if hasattr(profile, "texture") else "",
            typography_direction="none unless product type requires it",
            mood=_mood_for_product(product, season),
            trend_score=profile.trend_score,
            portfolio_diversity=_portfolio_diversity(best.style_name, current_portfolio, self._settings.maximum_style_reuse),
            category=category,
            rendering_family=profile.rendering_method,
            commercial_rationale=best.reason,
            alternative_styles=tuple((item.style_name, item.score) for item in ranked[1:4]),
        )
        if direction.confidence < self._settings.minimum_style_confidence:
            return direction
        self._style_memory.remember(product, direction.recommended_style)
        if self._memory is not None:
            self._memory.save_record("muse_art_directions", _slug(product), direction)
        return direction

    def select_batch(
        self,
        products: tuple[dict[str, str], ...],
    ) -> tuple[ArtDirection, ...]:
        """Select styles for a batch while enforcing hard diversity rules."""
        selected: list[ArtDirection] = []
        for product in products:
            direction = self.select_style(
                product=product["product"],
                audience=product.get("audience", ""),
                season=product.get("season", ""),
                competition=product.get("competition", ""),
                current_portfolio=tuple(item.recommended_style for item in selected),
                product_type=product.get("product_type", ""),
            )
            if not _batch_rule_allows((*selected, direction)):
                direction = self._replacement_direction(product, tuple(selected), direction)
            selected.append(direction)
        return tuple(selected)

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

    def _score_market_styles(
        self,
        product: str,
        category: str,
        audience: str,
        season: str,
        competition: str,
        current_portfolio: tuple[str, ...],
        product_type: str,
    ) -> tuple[StyleCandidateScore, ...]:
        playbook_styles = self._style_registry.playbook_for_category(category)
        scores: list[StyleCandidateScore] = []
        for rank, style in enumerate(playbook_styles):
            score, reason = self._score_market_style(
                style,
                rank=rank,
                product=product,
                category=category,
                audience=audience,
                season=season,
                competition=competition,
                current_portfolio=current_portfolio,
                product_type=product_type,
            )
            scores.append(StyleCandidateScore(style.style_id, score, reason))
        return tuple(sorted(scores, key=lambda item: item.score, reverse=True))

    def _score_market_style(
        self,
        style: MarketStyle,
        rank: int,
        product: str,
        category: str,
        audience: str,
        season: str,
        competition: str,
        current_portfolio: tuple[str, ...],
        product_type: str,
    ) -> tuple[int, str]:
        haystack = f"{product} {category} {product_type} {audience}".casefold()
        score = 42 + max(0, 18 - rank * 4)
        score += int(style.commercial_appeal_score * 0.16)
        score += int(style.current_trend_score * 0.12)
        score += int(style.historical_performance_score * 0.08)
        if any(_normalize(item) in haystack for item in style.best_fit_categories):
            score += 16
        if any(_normalize(item) in haystack for item in style.avoid_categories):
            score -= 35
        if season and season.casefold() in haystack:
            score += self._settings.season_weight // 2
        reuse_count = sum(1 for item in current_portfolio if item.casefold() == style.name.casefold())
        diversity_penalty = max(0, reuse_count - self._settings.maximum_style_reuse + 1) * style.recent_use_penalty
        score -= diversity_penalty
        proven_boost, evidence = self._proven_winners.influence_for(category, style.style_id)
        score += proven_boost
        if competition.casefold() == "high" and style.commercial_appeal_score >= 88:
            score += 4
        score = max(0, min(100, score))
        reason = (
            f"Category playbook fit for {category}; commercial appeal "
            f"{style.commercial_appeal_score}, trend {style.current_trend_score}, "
            f"proven winner: {evidence}, diversity penalty {diversity_penalty}."
        )
        return score, reason

    def _replacement_direction(
        self,
        product: dict[str, str],
        selected: tuple[ArtDirection, ...],
        rejected: ArtDirection,
    ) -> ArtDirection:
        category = _category_for(product["product"], product.get("product_type", ""))
        for score in self._score_market_styles(
            product=product["product"],
            category=category,
            audience=product.get("audience", ""),
            season=product.get("season", ""),
            competition=product.get("competition", ""),
            current_portfolio=tuple(item.recommended_style for item in selected),
            product_type=product.get("product_type", ""),
        )[1:]:
            style = self._style_registry.get(score.style_name)
            candidate = _direction_from_market_style(
                product=product["product"],
                category=category,
                style=style,
                score=score,
                alternatives=(),
            )
            if _batch_rule_allows((*selected, candidate)):
                return candidate
        return rejected


def _count_matches(text: str, values: tuple[str, ...]) -> int:
    return sum(1 for value in values if value.casefold() in text)


def _direction_from_market_style(
    product: str,
    category: str,
    style: MarketStyle,
    score: StyleCandidateScore,
    alternatives: tuple[StyleCandidateScore, ...],
) -> ArtDirection:
    evidence = _extract_evidence(score.reason)
    diversity_penalty = _extract_penalty(score.reason)
    return ArtDirection(
        product_name=product,
        recommended_style=style.name,
        confidence=score.score,
        reason=score.reason,
        palette=style.palette_guidance,
        rendering_method=style.rendering_family,
        composition=_composition_template_for_category(category, style.composition_template),
        mood=_mood_for_product(product, category),
        trend_score=style.current_trend_score,
        portfolio_diversity="Healthy" if diversity_penalty == 0 else "Penalty Applied",
        category=category,
        rendering_family=style.rendering_family,
        background_treatment=style.background_treatment,
        lighting=style.lighting_guidance,
        texture=style.texture_guidance,
        typography_direction=style.typography_guidance,
        commercial_rationale=score.reason,
        proven_winner_evidence_used=evidence,
        diversity_penalty_applied=diversity_penalty,
        dominant_palette_family=style.dominant_palette_family,
        texture_family=style.texture_family,
        negative_style_constraints=style.negative_prompt_directives,
        alternative_styles=tuple((item.style_name, item.score) for item in alternatives),
    )


def _category_for(product: str, product_type: str) -> str:
    haystack = f"{product} {product_type}".casefold()
    if "coastal" in haystack and ("wall art" in haystack or "print" in haystack):
        return "coastal wall art"
    if "teacher" in haystack or "classroom" in haystack:
        return "teacher printables"
    if "wedding" in haystack:
        return "wedding"
    if "invitation" in haystack:
        return "invitations"
    if "sticker" in haystack:
        return "sticker sheets"
    if "digital paper" in haystack or "paper" in haystack:
        return "digital paper"
    if "kitchen" in haystack:
        return "kitchen wall art"
    if "dark academia" in haystack:
        return "dark academia"
    if "nursery" in haystack or "baby" in haystack:
        return "nursery"
    if "christmas" in haystack or "halloween" in haystack or "holiday" in haystack:
        return "seasonal holiday"
    if "clipart" in haystack:
        return "clipart"
    if "wall art" in haystack:
        return "wall art"
    return product_type or "clipart"


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _extract_evidence(reason: str) -> str:
    marker = "proven winner: "
    if marker not in reason:
        return "none"
    value = reason.split(marker, maxsplit=1)[1].split(", diversity penalty", maxsplit=1)[0]
    return value.strip() or "none"


def _extract_penalty(reason: str) -> int:
    marker = "diversity penalty "
    if marker not in reason:
        return 0
    raw = reason.rsplit(marker, maxsplit=1)[-1].rstrip(".")
    return int(raw) if raw.isdigit() else 0


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


def _composition_template_for_category(category: str, fallback: str) -> str:
    lowered = category.casefold()
    if "clipart" in lowered:
        return "isolated elements on transparent or clean white background"
    if "wall art" in lowered:
        return "finished artwork with listing mockup-ready composition"
    if "invitation" in lowered or "wedding" in lowered:
        return "complete invitation layout with typography hierarchy"
    if "sticker" in lowered or "teacher" in lowered:
        return "grid or clustered sticker layout with clear cuttable shapes"
    if "digital paper" in lowered:
        return "seamless pattern presentation with tiled preview"
    return fallback


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


def _batch_rule_allows(directions: tuple[ArtDirection, ...]) -> bool:
    dimensions = (
        "rendering_family",
        "background_treatment",
        "composition",
        "dominant_palette_family",
        "texture_family",
    )
    for dimension in dimensions:
        counts: dict[str, int] = {}
        for direction in directions:
            value = str(getattr(direction, dimension, "")).casefold()
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
            if counts[value] > 2:
                return False
    return True


def _slug(value: str) -> str:
    return "_".join(part for part in value.casefold().replace("-", " ").split() if part)
