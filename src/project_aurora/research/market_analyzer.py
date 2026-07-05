"""Analyze local market trend sample data."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


COMPETITION_WEIGHTS: dict[str, int] = {
    "low": 3,
    "medium": 2,
    "high": 1,
}


@dataclass(frozen=True, slots=True)
class MarketTrend:
    """A market opportunity represented in local trend data."""

    product_type: str
    theme: str
    season: str
    demand_score: int
    competition_level: str
    trend_notes: str

    @property
    def competition_weight(self) -> int:
        """Return a numeric weight for the competition estimate."""
        return COMPETITION_WEIGHTS[self.competition_level.casefold()]


@dataclass(frozen=True, slots=True)
class MarketSummary:
    """Summary of local market trend opportunities."""

    trend_count: int
    average_demand_score: float
    top_seasons: tuple[tuple[str, int], ...]
    top_themes: tuple[tuple[str, int], ...]
    competition_estimate: tuple[tuple[str, int], ...]
    seasonal_opportunities: tuple[MarketTrend, ...]


class MarketAnalyzer:
    """Load and summarize local market trend CSV data."""

    def load_trends(self, csv_path: Path) -> tuple[MarketTrend, ...]:
        """Return market trends loaded from a CSV file."""
        with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            return tuple(self._row_to_trend(row) for row in reader)

    def summarize(self, trends: tuple[MarketTrend, ...]) -> MarketSummary:
        """Return a market summary for the provided trends."""
        if not trends:
            return MarketSummary(
                trend_count=0,
                average_demand_score=0.0,
                top_seasons=(),
                top_themes=(),
                competition_estimate=(),
                seasonal_opportunities=(),
            )

        season_counts = Counter(trend.season for trend in trends)
        theme_counts = Counter(trend.theme for trend in trends)
        competition_counts = Counter(
            trend.competition_level for trend in trends
        )
        average_demand = (
            sum(trend.demand_score for trend in trends) / len(trends)
        )

        seasonal_opportunities = tuple(
            sorted(
                trends,
                key=lambda trend: (
                    trend.demand_score,
                    trend.competition_weight,
                ),
                reverse=True,
            )[:5]
        )

        return MarketSummary(
            trend_count=len(trends),
            average_demand_score=round(average_demand, 2),
            top_seasons=tuple(season_counts.most_common(5)),
            top_themes=tuple(theme_counts.most_common(5)),
            competition_estimate=tuple(competition_counts.most_common()),
            seasonal_opportunities=seasonal_opportunities,
        )

    @staticmethod
    def _row_to_trend(row: dict[str, str]) -> MarketTrend:
        return MarketTrend(
            product_type=row["product_type"].strip(),
            theme=row["theme"].strip(),
            season=row["season"].strip(),
            demand_score=int(row["demand_score"]),
            competition_level=row["competition_level"].strip().lower(),
            trend_notes=row["trend_notes"].strip(),
        )
