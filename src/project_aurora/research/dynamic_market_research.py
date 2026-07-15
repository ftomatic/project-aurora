"""Provider-based market research for Aurora daily planning."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MarketSignal:
    """Normalized market signal used for daily product planning."""

    trend_phrase: str
    product_type: str
    estimated_demand: float
    estimated_competition: float
    seasonal_timing: str
    target_customer: str
    recommended_style: str
    keywords: tuple[str, ...]
    source: str
    collected_at: datetime
    confidence_score: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "keywords", tuple(self.keywords))


@dataclass(frozen=True, slots=True)
class ProviderUnavailable:
    """Unavailable research provider detail."""

    provider: str
    reason: str


@dataclass(frozen=True, slots=True)
class DynamicResearchReport:
    """Research output consumed by Sprint 22 dynamic planning."""

    signals: tuple[MarketSignal, ...]
    providers_used: tuple[str, ...]
    providers_unavailable: tuple[ProviderUnavailable, ...]
    collected_at: datetime = field(default_factory=datetime.now)


class MarketResearchProvider(Protocol):
    """Market research provider boundary."""

    @property
    def provider_name(self) -> str:
        """Return provider name."""

    def collect(self) -> tuple[MarketSignal, ...]:
        """Collect normalized market signals."""


class SeasonalCalendarProvider:
    """Deterministic seasonal and holiday signal provider."""

    provider_name = "Seasonal Calendar"

    def collect(self) -> tuple[MarketSignal, ...]:
        today = date.today()
        holidays = _upcoming_holiday_phrases(today)
        signals: list[MarketSignal] = []
        for index, phrase in enumerate(holidays):
            signals.append(
                MarketSignal(
                    trend_phrase=phrase,
                    product_type="party printable",
                    estimated_demand=0.82 - index * 0.02,
                    estimated_competition=0.34 + index * 0.03,
                    seasonal_timing=f"{30 * (index + 1)} day window",
                    target_customer="parents, teachers, crafters, digital printable buyers",
                    recommended_style=_style_for_phrase(phrase),
                    keywords=tuple(phrase.casefold().split()) + ("printable", "clipart"),
                    source=self.provider_name,
                    collected_at=datetime.now(),
                    confidence_score=0.88 - index * 0.02,
                )
            )
        return tuple(signals)


class HistoricalProductsProvider:
    """Local historical trend provider based on Aurora product themes."""

    provider_name = "Aurora History"

    def collect(self) -> tuple[MarketSignal, ...]:
        phrases = (
            "woodland baby animals",
            "strawberry birthday party",
            "fairy garden clipart",
            "vintage christmas tags",
            "cottagecore digital paper",
        )
        return tuple(
            MarketSignal(
                trend_phrase=phrase,
                product_type="clipart" if "party" not in phrase else "party printable",
                estimated_demand=0.78,
                estimated_competition=0.42,
                seasonal_timing="evergreen",
                target_customer="parents, teachers, crafters, digital printable buyers",
                recommended_style=_style_for_phrase(phrase),
                keywords=tuple(phrase.split()) + ("commercial", "download"),
                source=self.provider_name,
                collected_at=datetime.now(),
                confidence_score=0.76,
            )
            for phrase in phrases
        )


class ConfiguredExternalProvider:
    """Unavailable-by-default external provider placeholder."""

    def __init__(self, provider_name: str, required_env: str) -> None:
        self._provider_name = provider_name
        self._required_env = required_env

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def collect(self) -> tuple[MarketSignal, ...]:
        if not os.getenv(self._required_env):
            raise RuntimeError(f"{self._required_env} is not configured.")
        return ()


class DynamicMarketResearchEngine:
    """Collect daily market research from configured providers."""

    def __init__(self, providers: tuple[MarketResearchProvider, ...] | None = None) -> None:
        self._providers = providers or (
            SeasonalCalendarProvider(),
            HistoricalProductsProvider(),
            ConfiguredExternalProvider("Etsy API Signals", "ETSY_ACCESS_TOKEN"),
            ConfiguredExternalProvider("Google Trends", "AURORA_GOOGLE_TRENDS_ENABLED"),
            ConfiguredExternalProvider("Pinterest Trends", "AURORA_PINTEREST_TRENDS_ENABLED"),
        )

    def run(self) -> DynamicResearchReport:
        """Collect all available signals and unavailable-provider details."""
        signals: list[MarketSignal] = []
        used: list[str] = []
        unavailable: list[ProviderUnavailable] = []
        for provider in self._providers:
            try:
                provider_signals = provider.collect()
            except RuntimeError as error:
                unavailable.append(
                    ProviderUnavailable(provider=provider.provider_name, reason=str(error))
                )
                continue
            if provider_signals:
                used.append(provider.provider_name)
                signals.extend(provider_signals)
            else:
                unavailable.append(
                    ProviderUnavailable(
                        provider=provider.provider_name,
                        reason="Provider configured but returned no signals.",
                    )
                )
        return DynamicResearchReport(
            signals=tuple(signals),
            providers_used=tuple(used),
            providers_unavailable=tuple(unavailable),
        )


def _upcoming_holiday_phrases(today: date) -> tuple[str, ...]:
    seasonal = (
        (date(today.year, 2, 14), "valentine classroom cards"),
        (date(today.year, 3, 17), "st patricks day clipart"),
        (date(today.year, 4, 12), "spring bunny party"),
        (date(today.year, 7, 4), "summer berry celebration"),
        (date(today.year, 10, 31), "cute halloween party"),
        (date(today.year, 12, 25), "vintage christmas printable"),
    )
    windows = (30, 60, 90)
    phrases: list[str] = []
    for days in windows:
        target = today + timedelta(days=days)
        best = min(
            seasonal,
            key=lambda item: abs((item[0].replace(year=target.year) - target).days),
        )
        phrases.append(best[1])
    return tuple(dict.fromkeys(phrases))


def _style_for_phrase(phrase: str) -> str:
    lowered = phrase.casefold()
    if "christmas" in lowered:
        return "Vintage Christmas"
    if "halloween" in lowered:
        return "Cute Halloween"
    if "baby" in lowered or "bunny" in lowered:
        return "Pastel Nursery"
    if "berry" in lowered or "strawberry" in lowered:
        return "Storybook Watercolor"
    return "Soft Cottagecore"
