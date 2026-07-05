"""Render morning research reports for the console."""

from __future__ import annotations

from project_aurora.research.recommendation_engine import ResearchReport


class ReportGenerator:
    """Format research report data for terminal output."""

    def render(self, report: ResearchReport) -> str:
        """Return a beautiful plain-text console report."""
        sections = [
            self._title(),
            self._shop_summary(report),
            self._market_trends(report),
            self._seasonal_opportunities(report),
            self._competition_estimate(report),
            self._production_selection(report),
            self._recommendations(report),
            self._future_collections(report),
        ]
        return "\n\n".join(sections)

    @staticmethod
    def _title() -> str:
        return "\n".join(
            (
                "PROJECT AURORA - MORNING RESEARCH REPORT",
                "=" * 48,
                "RainbowMilkStudio product opportunity scan",
            )
        )

    @staticmethod
    def _shop_summary(report: ResearchReport) -> str:
        summary = report.shop_summary
        categories = ", ".join(
            f"{name} ({count})" for name, count in summary.top_categories
        )
        themes = ", ".join(
            f"{name} ({count})" for name, count in summary.top_themes
        )

        return "\n".join(
            (
                "Current Shop Summary",
                "-" * 20,
                f"Products reviewed: {summary.product_count}",
                f"Total sample sales: {summary.total_sales}",
                f"Average price: ${summary.average_price:.2f}",
                f"Average rating: {summary.average_rating:.2f}",
                f"Top categories: {categories}",
                f"Top themes: {themes}",
            )
        )

    @staticmethod
    def _market_trends(report: ResearchReport) -> str:
        rows = [
            (
                trend.product_type,
                trend.theme,
                trend.season,
                str(trend.demand_score),
                trend.competition_level,
            )
            for trend in report.market_trends
        ]
        return "\n".join(
            (
                "Market Trends",
                "-" * 13,
                _table(
                    ("Product Type", "Theme", "Season", "Demand", "Competition"),
                    rows,
                ),
            )
        )

    @staticmethod
    def _seasonal_opportunities(report: ResearchReport) -> str:
        lines = [
            (
                f"- {trend.season}: {trend.theme} {trend.product_type} "
                f"(demand {trend.demand_score}/10, "
                f"{trend.competition_level} competition)"
            )
            for trend in report.seasonal_opportunities
        ]
        return "\n".join(("Seasonal Opportunities", "-" * 24, *lines))

    @staticmethod
    def _competition_estimate(report: ResearchReport) -> str:
        lines = [
            f"- {level.title()}: {count} "
            f"{_pluralize(count, 'opportunity', 'opportunities')}"
            for level, count in report.competition_estimate
        ]
        return "\n".join(("Competition Estimate", "-" * 20, *lines))

    @staticmethod
    def _production_selection(report: ResearchReport) -> str:
        selection = report.production_selection
        queue_lines = [
            f"- {item}" for item in selection.production_queue
        ]
        return "\n".join(
            (
                "Selected for Production Today",
                "-" * 29,
                f"Today's Best Product: {selection.best_product.name}",
                f"Today's Backup Product: {selection.backup_product.name}",
                (
                    "Today's Collection Expansion: "
                    f"{selection.collection_expansion}"
                ),
                f"Today's Product Type: {selection.product_type}",
                f"Why this was selected: {selection.selection_reason}",
                "Move into Production Queue:",
                *queue_lines,
            )
        )

    @staticmethod
    def _recommendations(report: ResearchReport) -> str:
        lines = ["Top 10 Recommended Products", "-" * 27]
        for index, recommendation in enumerate(report.recommendations, start=1):
            lines.extend(
                (
                    f"{index}. {recommendation.name}",
                    (
                        f"   Score: {recommendation.score} | "
                        f"Season: {recommendation.season} | "
                        f"Competition: {recommendation.competition_level}"
                    ),
                    (
                        "   Signals: "
                        f"Revenue {recommendation.revenue_potential} | "
                        f"Ease {recommendation.ease_of_production} | "
                        f"IP safety {recommendation.ip_safety}"
                    ),
                    f"   Reasoning: {recommendation.reasoning}",
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _future_collections(report: ResearchReport) -> str:
        lines = [
            f"- {collection}" for collection in report.future_collections
        ]
        return "\n".join(("Future Collection Suggestions", "-" * 29, *lines))


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [
        max(len(row[index]) for row in (headers, *rows))
        for index in range(len(headers))
    ]
    header_row = " | ".join(
        value.ljust(widths[index]) for index, value in enumerate(headers)
    )
    separator = "-+-".join("-" * width for width in widths)
    body = [
        " | ".join(
            value.ljust(widths[index]) for index, value in enumerate(row)
        )
        for row in rows
    ]
    return "\n".join((header_row, separator, *body))


def _pluralize(count: int, singular: str, plural: str) -> str:
    if count == 1:
        return singular
    return plural
