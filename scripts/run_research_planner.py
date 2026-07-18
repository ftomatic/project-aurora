"""Run Athena research and Atlas production portfolio planning."""

from __future__ import annotations

import argparse
import sys
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
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionQueueManager,
)
from project_aurora.portfolio.atlas_portfolio_manager import (  # noqa: E402
    AtlasPortfolioManager,
    AtlasPortfolioPlan,
)
from project_aurora.research.athena_market_intelligence import (  # noqa: E402
    AthenaMarketIntelligence,
    AthenaResearchReport,
)
from project_aurora.research.research_config import ResearchPlannerConfig  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
RESEARCH_CONFIG_PATH = PROJECT_ROOT / "config" / "research.yaml"
OPENAI_CONFIG_PATH = PROJECT_ROOT / "config" / "openai.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Aurora research planner.")
    parser.add_argument("--auto-approve", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run research-first planning and optional Forge handoff."""
    args = parse_args(argv)
    config = ResearchPlannerConfig.from_file(RESEARCH_CONFIG_PATH)
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
    plan = atlas.build_portfolio(
        research.opportunities,
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
    print("Awaiting Approval")
    approved = args.auto_approve or request_production_approval(
        plan,
        estimate,
        input,
    )
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
    print("Target Portfolio")
    print(gate["target_portfolio"])
    print("")
    print("Required Products")
    print(gate["required_products"])
    print("")
    print("Selected")
    print(gate["selected"])
    print("")
    print("Selected Products")
    print(gate["selected_products"])
    print("")
    print("Minimum Required")
    print(gate["minimum_required"])
    print("")
    print("Portfolio Size")
    print(gate["portfolio_size"])
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
        print("Constraint Relaxed")
        print(relaxation["constraint"])
        print("")
        print("Reason")
        print(relaxation["reason"])
    print("")
    print("Status")
    print(gate["status"])
    print("")
    print("Reason")
    print(gate["reason"])


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
    for opportunity in plan.selected:
        try:
            queue_manager.add_job(
                priority="High" if opportunity.confidence >= 90 else "Medium",
                product_name=opportunity.keyword.title(),
                category=opportunity.product_type,
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
            continue
        created += 1
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
