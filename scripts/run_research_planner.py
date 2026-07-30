"""Run Athena research and Atlas production portfolio planning."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_cost_estimator import (  # noqa: E402
    ImageCostEstimate,
    ImageCostEstimator,
)
from project_aurora.brand_profile import load_brand_profile, score_brand_fit  # noqa: E402
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionQueueManager,
)
from project_aurora.production.watercolor_scope import resolve_watercolor_scope  # noqa: E402
from project_aurora.portfolio.atlas_portfolio_manager import (  # noqa: E402
    AtlasPortfolioManager,
    AtlasPortfolioPlan,
)
from project_aurora.research.athena_market_intelligence import (  # noqa: E402
    AthenaMarketIntelligence,
    AthenaResearchReport,
)
from project_aurora.research.market_opportunity import MarketOpportunity  # noqa: E402
from project_aurora.research.research_config import ResearchPlannerConfig  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
RESEARCH_CONFIG_PATH = PROJECT_ROOT / "config" / "research.yaml"
OPENAI_CONFIG_PATH = PROJECT_ROOT / "config" / "openai.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Aurora research planner.")
    parser.add_argument("--auto-approve", action="store_true")
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Pause for operator approval before queue handoff.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of production jobs required for this planner run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run research-first planning and optional Forge handoff."""
    args = parse_args(argv)
    config = ResearchPlannerConfig.from_file(RESEARCH_CONFIG_PATH)
    if args.count is not None:
        if args.count < 1:
            raise ValueError("--count must be at least 1.")
        config = replace(config, daily_products=args.count)
    queue_manager = ProductionQueueManager(queue_path=QUEUE_PATH)
    research = AthenaMarketIntelligence(candidate_count=config.candidate_count).run()
    provider_status = tuple(
        {
            "provider": status.provider,
            "priority": status.priority,
            "status": status.status,
            "detail": status.detail,
            "opportunities": status.opportunities,
        }
        for status in research.provider_statuses
    )
    atlas = AtlasPortfolioManager(config=config, queue_manager=queue_manager)
    brand_candidates = build_brand_profile_portfolio_candidates(
        research.opportunities,
        target_count=max(config.daily_products * 2, 10),
    )
    plan = atlas.build_portfolio(
        brand_candidates,
        provider_status=provider_status,
    )
    atlas.save_report(plan)
    estimate = estimate_image_cost(config.daily_products)
    print_research_planner_output(research, plan, estimate)
    print_quality_gate(plan)
    if not plan.quality_gate_passed:
        print_blocked_reasons(plan)
        return
    print("")
    approved = True
    if args.require_approval and not args.auto_approve:
        print("Awaiting Approval")
        approved = request_production_approval(
            plan,
            estimate,
            input,
        )
    else:
        print("Approval Mode")
        print("AUTO")
    if not approved:
        print("")
        print("Status")
        print("AWAITING_APPROVAL")
        return
    created = handoff_to_forge(plan, queue_manager)
    print("")
    print("Forge Handoff")
    print(f"{created} jobs queued")
    print("")
    print("Status")
    print("APPROVED")


def estimate_image_cost(product_count: int) -> ImageCostEstimate:
    """Estimate image cost for the approved portfolio."""
    image_config = ImageProviderConfig.from_file(OPENAI_CONFIG_PATH)
    return ImageCostEstimator().estimate(
        provider=image_config.provider,
        quality=image_config.quality,
        number_of_images=product_count * image_config.number_of_images,
    )


def recovery_watercolor_opportunities() -> tuple[MarketOpportunity, ...]:
    """Return fresh approved-scope opportunities for emergency recovery runs."""
    specs = (
        (
            "Mouse Bakery Watercolor Clipart",
            "storybook animals",
            "cottage bakery animals",
            "crafters and nursery buyers",
            "Evergreen",
            "signature_storybook_animal_collection",
            "Whimsical Storybook",
        ),
        (
            "Fox Garden Watercolor Clipart",
            "woodland animals",
            "garden animal clipart",
            "cottagecore printable buyers",
            "Spring",
            "watercolor_woodland_collection",
            "Storybook Watercolor",
        ),
        (
            "Rabbit Tea Party Watercolor Clipart",
            "baby animals",
            "tea party animal clipart",
            "parents and crafters",
            "Summer",
            "watercolor_animal_collection",
            "Loose Watercolor",
        ),
        (
            "Bear Picnic Watercolor Clipart",
            "woodland nursery",
            "picnic animal clipart",
            "nursery decor buyers",
            "Fall",
            "watercolor_animal_collection",
            "Cottagecore",
        ),
        (
            "Cottage Mushroom Botanical Clipart",
            "botanical",
            "mushroom botanical clipart",
            "junk journal and craft buyers",
            "Autumn",
            "watercolor_botanical_collection",
            "Vintage Botanical",
        ),
    )
    return tuple(
        MarketOpportunity(
            keyword=keyword,
            primary_niche=niche,
            subcategory=subcategory,
            target_audience=audience,
            season=season,
            product_type=product_type,
            recommended_artistic_style=style,
            trend_score=91 - index,
            competition_score=34 + index,
            commercial_potential=92 - index,
            confidence=93 - index,
            research_sources=("Aurora Recovery Scope", "Seasonal Calendar"),
        )
        for index, (
            keyword,
            niche,
            subcategory,
            audience,
            season,
            product_type,
            style,
        ) in enumerate(specs)
    )


def build_brand_profile_portfolio_candidates(
    research_opportunities: tuple[MarketOpportunity, ...],
    *,
    target_count: int = 10,
) -> tuple[MarketOpportunity, ...]:
    """Build Atlas input from RainbowMilkStudio brand-fit opportunities."""
    profile = load_brand_profile()
    pool = _dedupe_opportunities(
        research_opportunities
        + brand_profile_opportunities(profile)
        + recovery_watercolor_opportunities()
    )
    accepted: list[MarketOpportunity] = []
    filtered: list[tuple[MarketOpportunity, str]] = []
    for opportunity in pool:
        scope = resolve_watercolor_scope(
            opportunity.keyword,
            opportunity.product_type,
            opportunity.recommended_artistic_style,
        )
        if not scope.supported:
            filtered.append((opportunity, scope.reason))
            continue
        brand_score = score_brand_fit(
            opportunity.keyword,
            opportunity.product_type,
            opportunity.recommended_artistic_style,
            profile=profile,
        )
        if not brand_score.accepted:
            filtered.append(
                (
                    opportunity,
                    f"{brand_score.reason} Brand score {brand_score.score}.",
                )
            )
            continue
        accepted.append(_with_canonical_scope(opportunity, scope.canonical_product_type))
    accepted = sorted(
        accepted,
        key=lambda item: (
            -score_brand_fit(
                item.keyword,
                item.product_type,
                item.recommended_artistic_style,
                profile=profile,
            ).score,
            -item.confidence,
            -item.trend_score,
            item.keyword.casefold(),
        ),
    )
    print_brand_candidate_diagnostics(accepted, filtered)
    return tuple(accepted[:target_count])


def brand_profile_opportunities(profile: dict[str, object]) -> tuple[MarketOpportunity, ...]:
    """Create fresh product ideas from the persisted RainbowMilkStudio brand profile."""
    animals = _profile_terms(profile, "popular_animals")
    themes = _profile_terms(profile, "popular_themes")
    pairings = (
        (animals[0], themes[0], "signature_storybook_animal_collection", "Whimsical Storybook"),
        (animals[1], themes[1], "watercolor_animal_collection", "Storybook Watercolor"),
        (animals[2], themes[2], "watercolor_woodland_collection", "Loose Watercolor"),
        (animals[3], themes[3], "watercolor_animal_collection", "Cottagecore"),
        (animals[4], themes[4], "watercolor_animal_collection", "Soft Nursery"),
        ("mushroom", "cottagecore", "watercolor_botanical_collection", "Vintage Botanical"),
        ("fox", "woodland homes", "signature_storybook_animal_collection", "Whimsical Storybook"),
        ("rabbit", "gardening", "watercolor_seasonal_collection", "Storybook Watercolor"),
    )
    opportunities: list[MarketOpportunity] = []
    for index, (subject, theme, product_type, style) in enumerate(pairings):
        keyword = f"{subject.title()} {theme.title()} Watercolor Clipart"
        opportunities.append(
            MarketOpportunity(
                keyword=keyword,
                primary_niche=f"{subject.title()} {theme.title()}",
                subcategory=f"{theme} woodland clipart",
                target_audience="crafters and nursery buyers",
                season=_season_for_theme(theme),
                product_type=product_type,
                recommended_artistic_style=style,
                trend_score=96 - index,
                competition_score=30 + index,
                commercial_potential=96 - index,
                confidence=96 - index,
                research_sources=("RainbowMilkStudio Brand Profile",),
            )
        )
    return tuple(opportunities)


def print_brand_candidate_diagnostics(
    accepted: list[MarketOpportunity],
    filtered: list[tuple[MarketOpportunity, str]],
) -> None:
    """Print explicit planner decision diagnostics before Atlas selection."""
    print("")
    print("Planner Candidate Diagnostics")
    print("Products Selected For Portfolio Input")
    print(len(accepted))
    for opportunity in accepted[:10]:
        print(f"- {opportunity.keyword.title()}")
    print("")
    print("Products Filtered")
    print(len(filtered))
    for opportunity, reason in filtered:
        print(f"- {opportunity.keyword.title()}: {reason}")


def _profile_terms(profile: dict[str, object], key: str) -> tuple[str, ...]:
    value = profile.get(key)
    if not isinstance(value, list | tuple):
        value = ()
    fallback = {
        "popular_animals": ("rabbit", "fox", "mouse", "bear", "hedgehog"),
        "popular_themes": ("tea party", "baking", "gardening", "reading", "nursery"),
    }[key]
    terms = tuple(str(term).strip().casefold() for term in value if str(term).strip())
    return (terms + fallback)[:5]


def _season_for_theme(theme: str) -> str:
    text = theme.casefold()
    if "garden" in text:
        return "Spring"
    if "tea" in text or "picnic" in text:
        return "Summer"
    if "mushroom" in text or "cottage" in text:
        return "Autumn"
    return "Evergreen"


def _dedupe_opportunities(
    opportunities: tuple[MarketOpportunity, ...],
) -> tuple[MarketOpportunity, ...]:
    seen: set[str] = set()
    deduped: list[MarketOpportunity] = []
    for opportunity in opportunities:
        key = opportunity.keyword.casefold().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(opportunity)
    return tuple(deduped)


def _with_canonical_scope(
    opportunity: MarketOpportunity,
    canonical_product_type: str,
) -> MarketOpportunity:
    if opportunity.product_type == canonical_product_type:
        return opportunity
    return MarketOpportunity(
        keyword=opportunity.keyword,
        primary_niche=opportunity.primary_niche,
        subcategory=opportunity.subcategory,
        target_audience=opportunity.target_audience,
        season=opportunity.season,
        product_type=canonical_product_type,
        recommended_artistic_style=opportunity.recommended_artistic_style,
        trend_score=opportunity.trend_score,
        competition_score=opportunity.competition_score,
        commercial_potential=opportunity.commercial_potential,
        confidence=opportunity.confidence,
        research_sources=opportunity.research_sources,
        id=opportunity.id,
        created_at=opportunity.created_at,
    )


def request_production_approval(
    plan: AtlasPortfolioPlan,
    estimate: ImageCostEstimate,
    input_fn: Callable[[str], str],
) -> bool:
    """Ask for explicit production approval."""
    if not plan.quality_gate_passed:
        return False
    print("")
    print("Today's Portfolio")
    for index, opportunity in enumerate(plan.selected, start=1):
        print(f"{index}. {opportunity.keyword.title()}")
    print("")
    print("Average Confidence")
    print(f"{plan.average_confidence:.0f}%")
    print("")
    print("Estimated Image Cost")
    print(estimate.render())
    print("")
    response = input_fn("Type APPROVE to continue\n")
    return response.strip() == "APPROVE"


def print_quality_gate(plan: AtlasPortfolioPlan) -> None:
    """Print the explicit quality gate state."""
    gate = plan.quality_gate
    print("")
    print("QUALITY GATE")
    print("")
    print("Required Products")
    print(gate["required_products"])
    print("")
    print("Selected Products")
    print(gate["selected_products"])
    print("")
    print("Portfolio Size")
    print(gate["portfolio_size"])
    if gate.get("portfolio_size_warning") == "WARNING":
        print("")
        print("WARNING")
        print(gate.get("warnings", ["Requested count not reached."])[0])
    print("")
    print("Minimum Confidence")
    print(f"{gate['minimum_confidence']:.0f}%")
    print("")
    print("Average Confidence")
    print(f"{gate['average_confidence']:.0f}%")
    print("")
    print("Confidence")
    print(gate["confidence"])
    print("")
    print("Duplicate Check")
    print(gate["duplicate_check"])
    for relaxation in plan.constraint_relaxations:
        print("")
        print("WARNING")
        print("Constraint relaxed.")
        print("")
        print("Constraint")
        print(relaxation["constraint"])
        print("")
        print("Reason")
        print(relaxation["reason"])
    for warning in gate.get("warnings", ()):
        if warning.startswith("Portfolio contains"):
            continue
        print("")
        print("WARNING")
        print(warning)
    print("")
    print("Status")
    print(gate["status"])


def print_blocked_reasons(plan: AtlasPortfolioPlan) -> None:
    """Print specific blocked-selection reasons."""
    if not plan.selection_failure_reasons:
        return
    print("")
    print("Selection Blocked")
    for reason in plan.selection_failure_reasons:
        print(reason)


def handoff_to_forge(
    plan: AtlasPortfolioPlan,
    queue_manager: ProductionQueueManager,
) -> int:
    """Persist approved products as READY jobs for Forge."""
    created = 0
    queue_before = len(queue_manager.list_jobs())
    ready_before = sum(1 for job in queue_manager.list_jobs() if job.status == READY)
    transformed_created = len(plan.selected)
    enqueue_attempted = 0
    decision_logs: list[tuple[str, str, str]] = []
    for opportunity in plan.selected:
        enqueue_attempted += 1
        decision = resolve_watercolor_scope(
            opportunity.keyword,
            opportunity.product_type,
            opportunity.recommended_artistic_style,
        )
        if not decision.supported:
            decision_logs.append(
                (opportunity.keyword.title(), "SKIPPED", decision.reason)
            )
            continue
        brand_score = score_brand_fit(
            opportunity.keyword,
            opportunity.product_type,
            opportunity.recommended_artistic_style,
        )
        if not brand_score.accepted:
            decision_logs.append(
                (
                    opportunity.keyword.title(),
                    "SKIPPED",
                    f"{brand_score.reason} Brand score {brand_score.score}.",
                )
            )
            continue
        try:
            job = queue_manager.add_job(
                priority="High" if opportunity.confidence >= 90 else "Medium",
                product_name=opportunity.keyword.title(),
                category=decision.canonical_product_type,
                style=opportunity.recommended_artistic_style,
                seasonal_theme=opportunity.season,
                keywords=tuple(opportunity.keyword.casefold().split()),
                confidence_score=round(opportunity.confidence / 100, 2),
                estimated_competition=_competition_label(opportunity.competition_score),
                estimated_demand=_demand_label(opportunity.trend_score),
                estimated_revenue=round(80 + opportunity.commercial_potential, 2),
                status=READY,
                target_customer=opportunity.target_audience,
                demand_score=round(opportunity.trend_score / 100, 3),
                competition_score=round(opportunity.competition_score / 100, 3),
                source_evidence=opportunity.research_sources,
            )
        except ValueError:
            decision_logs.append(
                (
                    opportunity.keyword.title(),
                    "SKIPPED",
                    "Production job already exists in queue.",
                )
            )
            continue
        created += 1
        decision_logs.append(
            (
                opportunity.keyword.title(),
                "ENQUEUED",
                f"Queue write succeeded with READY status for job {job.id}.",
            )
        )
    queue_after = len(queue_manager.list_jobs())
    ready_after = sum(1 for job in queue_manager.list_jobs() if job.status == READY)
    next_job = queue_manager.next_ready_job()
    print("")
    print("Forge Handoff Diagnostics")
    print("Transformed Products Created")
    print(transformed_created)
    print("Enqueue Attempted")
    print(enqueue_attempted)
    print("Enqueue Succeeded")
    print(created)
    print("Queue Size Before Enqueue")
    print(queue_before)
    print("Queue Size After Enqueue")
    print(queue_after)
    print("Queue File Path")
    print(queue_manager.queue_path)
    print("Persisted READY Count")
    print(ready_after)
    print("READY Count Before Enqueue")
    print(ready_before)
    print("next_ready_job() Result")
    print(next_job.product_name if next_job else "None")
    print("")
    print("Forge Handoff Decision Log")
    for product, status, reason in decision_logs:
        print(product)
        print(status)
        print(reason)
    return created


def print_research_planner_output(
    research: AthenaResearchReport,
    plan: AtlasPortfolioPlan,
    estimate: ImageCostEstimate,
) -> None:
    """Print the Athena and Atlas report."""
    print("ATHENA RESEARCH")
    print("")
    print("Providers")
    for status in research.provider_statuses:
        print(f"{status.provider}: {status.status}")
    print("")
    print("Candidates")
    print(len(research.opportunities))
    print("")
    print("Top Opportunities")
    for opportunity in research.opportunities[:5]:
        print(opportunity.keyword.title())
    print("")
    print("Selected Portfolio")
    for opportunity in plan.selected:
        print(opportunity.keyword.title())
    print("")
    print("Business Decision Report")
    for decision in plan.decisions:
        print(f"- {decision.product}: {decision.reason_selected}")
    print("")
    print("Average Confidence")
    print(f"{plan.average_confidence:.0f}%")
    print("")
    print("Estimated Image Cost")
    print(estimate.render())


def _competition_label(score: float) -> str:
    if score < 38:
        return "Low"
    if score < 55:
        return "Medium"
    return "High"


def _demand_label(score: float) -> str:
    if score >= 88:
        return "High"
    if score >= 75:
        return "Medium"
    return "Low"


if __name__ == "__main__":
    main()
