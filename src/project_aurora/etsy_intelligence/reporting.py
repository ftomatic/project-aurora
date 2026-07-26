"""Console report rendering for Etsy Intelligence."""

from __future__ import annotations

from project_aurora.etsy_intelligence.intelligence_models import EtsyIntelligenceReport


def render_intelligence_report(report: EtsyIntelligenceReport) -> str:
    """Render a readable read-only intelligence report."""
    shop = report.shop_snapshot
    opportunities = "\n".join(
        "\n".join(
            (
                item.product_concept,
                f"Score: {item.opportunity_score}",
                f"Duplicate Risk: {item.duplicate_risk}",
                f"Differentiation: {item.recommended_differentiation}",
                f"Confidence: {item.confidence}%",
                "",
            )
        )
        for item in report.top_opportunities
    ).strip() or "None"
    learnings = "\n".join(f"- {item.summary} (confidence {item.confidence}%)" for item in report.shop_learnings)
    availability = "\n".join(
        f"- {item.field_name}: {item.status} ({item.reason})"
        for item in shop.data_availability
    )
    actions = "\n".join(f"- {item}" for item in report.recommended_actions)
    warnings = "\n".join(f"- {item}" for item in report.warnings) if report.warnings else "None"
    return "\n\n".join(
        (
            "ETSY INTELLIGENCE",
            "Mode\n" + report.mode,
            "ETSY SHOP HEALTH",
            f"Active Listings\n{shop.active_listings}",
            f"Draft Listings\n{shop.draft_listings}",
            "Categories\n" + (", ".join(shop.categories) if shop.categories else "None"),
            "Data Availability\n" + availability,
            "TOP OPPORTUNITIES\n" + opportunities,
            "SHOP LEARNINGS\n" + learnings,
            "RECOMMENDED ACTIONS\n" + actions,
            "Warnings\n" + warnings,
            f"Writes Performed\n{'YES' if report.writes_performed else 'NO'}",
            "Status\nSUCCESS",
        )
    )
