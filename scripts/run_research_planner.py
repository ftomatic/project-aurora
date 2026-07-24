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
    COMPLETED,
    READY,
    ProductionQueueManager,
)
from project_aurora.planning.product_transformer import (  # noqa: E402
    ProductTransformation,
    ProductTransformationEngine,
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
    try:
        response = input_fn("Type APPROVE to continue\n")
    except EOFError:
        return False
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
    transformer = ProductTransformationEngine()
    transformations = transformer.transform_batch(plan.selected)
    before_jobs = queue_manager.list_jobs()
    print("")
    print("HANDOFF DIAGNOSTICS")
    print("")
    print("Queue File Path")
    print(queue_manager.queue_path)
    print("")
    print("Transformed Products Created")
    print(len(transformations))
    print("")
    print("Queue Size Before Enqueue")
    print(len(before_jobs))
    for opportunity, transformation in zip(plan.selected, transformations, strict=True):
        print("")
        print("Enqueue Attempted")
        print(transformation.production_product_name)
        if not transformation.eligible:
            print("Enqueue Succeeded")
            print("NO")
            print("Reason")
            print(transformation.transformation_reason)
            continue
        try:
            queue_manager.add_job(
                priority="High" if opportunity.confidence >= 90 else "Medium",
                product_name=transformation.production_product_name,
                category=transformation.production_product_type,
                style=transformation.production_style,
                seasonal_theme=opportunity.season,
                keywords=_transformed_keywords(opportunity, transformation),
                confidence_score=round(opportunity.confidence / 100, 2),
                estimated_competition=_competition_label(opportunity.competition_score),
                estimated_demand=_demand_label(opportunity.trend_score),
                estimated_revenue=round(80 + opportunity.commercial_potential, 2),
                status=READY,
                target_customer=opportunity.target_audience,
                demand_score=round(opportunity.trend_score / 100, 3),
                competition_score=round(opportunity.competition_score / 100, 3),
                source_evidence=(
                    *opportunity.research_sources,
                    f"Original research product type: {opportunity.product_type}",
                    f"Product transformation: {transformation.transformation_reason}",
                ),
                **transformation.to_queue_metadata(),
            )
        except ValueError as error:
            existing = queue_manager.find_by_product_name(
                transformation.production_product_name
            )
            if existing is None:
                print("Enqueue Succeeded")
                print("NO")
                print("Reason")
                print(str(error))
                continue
            if existing.status == COMPLETED:
                print("Enqueue Succeeded")
                print("NO")
                print("Reason")
                print("Product already exists as COMPLETED.")
                continue
            queue_manager.mark_product_ready(transformation.production_product_name)
            print("Enqueue Succeeded")
            print("YES")
            print("Reason")
            print(f"Existing {existing.status} job reactivated to READY.")
            created += 1
            continue
        print("Enqueue Succeeded")
        print("YES")
        print("Reason")
        print("New READY job persisted.")
        created += 1
    after_jobs = queue_manager.list_jobs()
    persisted_ready_count = sum(job.status == READY for job in after_jobs)
    next_job = queue_manager.next_ready_job()
    print("")
    print("Queue Size After Enqueue")
    print(len(after_jobs))
    print("")
    print("Persisted READY Count")
    print(persisted_ready_count)
    print("")
    print("next_ready_job()")
    print(next_job.product_name if next_job is not None else "NONE")
    return created


def build_transformations(
    plan: AtlasPortfolioPlan,
) -> tuple[tuple[object, ProductTransformation], ...]:
    """Return transformations for diagnostics without mutating the queue."""
    transformations = ProductTransformationEngine().transform_batch(plan.selected)
    return tuple(zip(plan.selected, transformations, strict=True))


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
    score_by_id = {
        str(score["opportunity_id"]): float(score["opportunity_score"])
        for score in plan.opportunity_scores
        if isinstance(score, dict)
    }
    ranked_opportunities = sorted(
        research.opportunities,
        key=lambda opportunity: (
            -score_by_id.get(opportunity.id, 0),
            opportunity.competition_score,
            opportunity.keyword.casefold(),
        ),
    )
    print("Rank   Product                          Opportunity Score")
    for index, opportunity in enumerate(ranked_opportunities[:5], start=1):
        print(f"{index:<6} {opportunity.keyword.title():<32} {score_by_id.get(opportunity.id, 0):.0f}")
    print("")
    print("Selected Portfolio")
    for opportunity in plan.selected:
        print(opportunity.keyword.title())
    transformations = build_transformations(plan)
    if transformations:
        print("")
        print("Product Transformation")
        for opportunity, transformation in transformations:
            print(f"- Researched Product: {opportunity.keyword.title()}")
            print(f"  Original Type: {opportunity.product_type}")
            print(f"  Production Type: {transformation.production_product_type}")
            print(f"  Production Name: {transformation.production_product_name}")
            print(f"  Etsy Category: {transformation.etsy_taxonomy_category}")
            print(f"  Required Images: {transformation.required_image_count}")
            print(f"  ZIP Required: {str(transformation.requires_zip_package).upper()}")
            print(f"  Template Required: {str(transformation.requires_template_engine).upper()}")
            print(f"  Layout Required: {str(transformation.requires_layout_engine).upper()}")
            print(f"  Eligibility: {'READY' if transformation.eligible else 'BLOCKED'}")
            print(f"  Reason: {transformation.transformation_reason}")
            print(
                "  Whimsical Batch: "
                f"{'YES' if transformation.whimsical_batch_designation else 'NO'}"
            )
    print("")
    print("Merchant Selection")
    for index, decision in enumerate(
        sorted(plan.decisions, key=lambda item: -item.opportunity_score),
        start=1,
    ):
        print(f"{index}. {decision.product} - Opportunity Score {decision.opportunity_score:.0f}")
    print("")
    print("Business Decision Report")
    for decision in plan.decisions:
        print(f"- {decision.product}: {decision.reason_selected}")
        print("  Factor Contributions:")
        for factor, contribution in decision.opportunity_contributions.items():
            print(f"  - {factor.replace('_', ' ').title()}: {contribution:.2f}")
        print(f"  Expected Revenue: ${decision.expected_business_value.get('expected_revenue', 0):.2f}")
        print(f"  Expected Margin: ${decision.expected_business_value.get('expected_margin', 0):.2f}")
    if plan.rejected:
        print("")
        print("Why Not Selected")
        score_details = {
            str(score["opportunity_id"]): score
            for score in plan.opportunity_scores
            if isinstance(score, dict) and "opportunity_id" in score
        }
        for opportunity, reason in plan.rejected[:10]:
            detail = score_details.get(opportunity.id, {})
            score = float(detail.get("opportunity_score", score_by_id.get(opportunity.id, 0)))
            weakest = str(detail.get("weakest_factor", ""))
            improvement = str(detail.get("suggested_improvement", ""))
            print(f"- {opportunity.keyword.title()}: Opportunity Score {score:.0f}. {reason}")
            if weakest:
                print(f"  Weakest Factor: {weakest}")
            if improvement:
                print(f"  Suggested Improvement: {improvement}")
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


def _transformed_keywords(
    opportunity: object,
    transformation: ProductTransformation,
) -> tuple[str, ...]:
    raw = (
        str(getattr(opportunity, "keyword", "")),
        str(getattr(opportunity, "primary_niche", "")),
        str(getattr(opportunity, "product_type", "")),
        transformation.production_product_name,
        "4 png illustrations",
        "digital download",
    )
    tokens: list[str] = []
    for value in raw:
        for token in value.casefold().replace("-", " ").split():
            clean = "".join(character for character in token if character.isalnum())
            if len(clean) > 2 and clean not in tokens:
                tokens.append(clean)
    return tuple(tokens[:16])


if __name__ == "__main__":
    main()
