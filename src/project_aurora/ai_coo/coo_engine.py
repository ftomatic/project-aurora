"""AI COO daily operating-plan engine."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from project_aurora.ai_coo.coo_models import (
    BacklogPlan,
    BusinessRisk,
    DailyBusinessPlan,
    ExecutiveDecisionReport,
    OperatingTask,
    ResourcePlan,
)
from project_aurora.ai_coo.seasonal_calendar import (
    current_calendar_focus,
    merchandising_calendar,
)
from project_aurora.business_intelligence import BusinessIntelligenceEngine
from project_aurora.executive import ExecutiveDashboard, ExecutiveDashboardEngine
from project_aurora.planning.production_queue_manager import (
    FAILED,
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.storage.memory_manager import MemoryManager


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"


class AICOOEngine:
    """Create Aurora's daily operating plan."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        queue_manager: ProductionQueueManager | None = None,
        dashboard_engine: ExecutiveDashboardEngine | None = None,
        business_intelligence: BusinessIntelligenceEngine | None = None,
        image_generation_budget: int = 3,
        api_usage_budget: int = 12,
        publishing_capacity: int = 5,
        review_time_minutes: int = 90,
    ) -> None:
        self._memory = memory or MemoryManager()
        self._queue_manager = queue_manager or ProductionQueueManager(queue_path=DEFAULT_QUEUE_PATH)
        self._dashboard_engine = dashboard_engine or ExecutiveDashboardEngine(
            memory=self._memory,
            queue_manager=self._queue_manager,
        )
        self._business_intelligence = business_intelligence or BusinessIntelligenceEngine(memory=self._memory)
        self._image_generation_budget = image_generation_budget
        self._api_usage_budget = api_usage_budget
        self._publishing_capacity = publishing_capacity
        self._review_time_minutes = review_time_minutes

    def create_daily_plan(self, plan_date: date | None = None) -> DailyBusinessPlan:
        """Create, save, and journal today's operating plan."""
        resolved_date = plan_date or date.today()
        dashboard = self._dashboard_engine.build()
        recommendations = self._business_intelligence.generate_recommendations()
        proposals = self._business_intelligence.propose_strategy_adjustments()
        jobs = self._safe_jobs()
        tasks = _score_tasks(
            _candidate_tasks(
                dashboard=dashboard,
                jobs=jobs,
                recommendations=tuple(item.to_dict() for item in recommendations),
                proposals=tuple(item.to_dict() for item in proposals),
                plan_date=resolved_date,
            )
        )
        selected = _select_tasks(
            tasks,
            image_budget=self._image_generation_budget,
            api_budget=self._api_usage_budget,
            publishing_capacity=self._publishing_capacity,
            review_minutes=self._review_time_minutes,
        )
        resources = _resource_plan(
            selected,
            image_budget=self._image_generation_budget,
            api_budget=self._api_usage_budget,
            publishing_capacity=self._publishing_capacity,
            review_minutes=self._review_time_minutes,
        )
        risks = _business_risks(dashboard, jobs)
        backlog = _backlog(tasks, selected)
        executive_report = _executive_report(
            dashboard=dashboard,
            selected=selected,
            risks=risks,
            recommendations=tuple(item.recommendation for item in recommendations),
        )
        plan = DailyBusinessPlan(
            plan_date=resolved_date,
            daily_business_plan=_daily_plan_summary(selected),
            production_goals=_goals(selected, "Production"),
            publishing_goals=_goals(selected, "Publishing"),
            collection_goals=_goals(selected, "Collections"),
            research_goals=_goals(selected, "Research"),
            improvement_goals=_goals(selected, "Improvement"),
            selected_tasks=selected,
            backlog=backlog,
            resource_plan=resources,
            seasonal_calendar=merchandising_calendar(),
            business_risks=risks,
            executive_report=executive_report,
        )
        self._save_plan(plan)
        return plan

    def _safe_jobs(self) -> tuple[ProductionJob, ...]:
        try:
            return self._queue_manager.list_jobs()
        except (FileNotFoundError, ValueError):
            return ()

    def _save_plan(self, plan: DailyBusinessPlan) -> None:
        key = plan.plan_date.isoformat()
        record = plan.to_dict()
        self._memory.save_record("ai_coo_daily_plans", key, record)
        self._memory.save_record("ai_coo_daily_plans", "latest", record)
        self._memory.save_record(
            "business_journal",
            f"{key}_{datetime.now().strftime('%H%M%S%f')}",
            {
                "decision": plan.daily_business_plan,
                "lessons_preserved": [
                    risk.message for risk in plan.business_risks
                ],
                "selected_tasks": [task.name for task in plan.selected_tasks],
                "confidence": plan.executive_report.confidence,
                "created_at": datetime.now().isoformat(),
            },
        )


def _candidate_tasks(
    *,
    dashboard: ExecutiveDashboard,
    jobs: tuple[ProductionJob, ...],
    recommendations: tuple[dict[str, Any], ...],
    proposals: tuple[dict[str, Any], ...],
    plan_date: date,
) -> tuple[OperatingTask, ...]:
    tasks: list[OperatingTask] = []
    for item in dashboard.collection_health:
        if item.completion_percent < 100:
            tasks.append(
                _task(
                    "finish_collection",
                    f"Finish Collection: {item.collection_name}",
                    "Collections",
                    item.revenue_estimate,
                    35,
                    "review",
                    f"{item.collection_name} is {item.completion_percent:.0f}% complete.",
                )
            )
    for alert in dashboard.alerts:
        if alert.alert_type == "Poor merchant QA":
            tasks.append(_task("fix_merchant_qa", "Fix Merchant QA", "Improvement", 130, 30, "review", alert.message))
        elif alert.alert_type == "Weak SEO":
            tasks.append(_task("fix_weak_seo", "Improve Weak SEO", "Improvement", 110, 25, "review", alert.message))
        elif alert.alert_type == "Low thumbnail score":
            tasks.append(_task("improve_thumbnail", "Improve Weak Thumbnail", "Improvement", 105, 30, "review", alert.message))
        elif alert.alert_type == "Duplicate detected":
            tasks.append(_task("dedupe_concepts", "Resolve Duplicate Concepts", "Technical Debt", 95, 25, "review", alert.message))
    if dashboard.executive_summary.drafts_pending_review > 0:
        tasks.append(
            _task(
                "publish_drafts",
                "Publish Drafts",
                "Publishing",
                dashboard.executive_summary.drafts_pending_review * 45,
                20,
                "publishing",
                "Draft listings are waiting for review.",
            )
        )
    for job in jobs:
        if job.status == READY:
            tasks.append(
                _task(
                    f"produce_{job.id}",
                    f"Produce: {job.product_name}",
                    "Production",
                    job.estimated_revenue,
                    45,
                    "image_generation",
                    f"{job.product_name} is READY with {job.estimated_demand} demand.",
                )
            )
        elif job.status == FAILED:
            tasks.append(
                _task(
                    f"repair_{job.id}",
                    f"Repair Failed Job: {job.product_name}",
                    "Technical Debt",
                    job.estimated_revenue * 0.7,
                    35,
                    "api",
                    f"{job.product_name} failed and needs recovery.",
                )
            )
    for event in current_calendar_focus(plan_date.month):
        tasks.append(
            _task(
                f"research_{event.name}",
                f"Research {event.name}",
                "Research",
                120 if event.priority == "High" else 80,
                25,
                "api",
                f"{event.name} production should begin around month {event.recommended_start_month}.",
            )
        )
    for recommendation in recommendations:
        tasks.append(
            _task(
                "analyze_sales",
                str(recommendation.get("recommendation") or "Analyze Sales"),
                "Research",
                float(recommendation.get("confidence") or 0),
                20,
                "api",
                str(recommendation.get("reasoning") or "BI recommendation."),
            )
        )
    for proposal in proposals:
        if proposal.get("approved_for_application"):
            tasks.append(
                _task(
                    "apply_learning",
                    f"Review Strategy Adjustment: {proposal.get('proposed_change')}",
                    "Improvement",
                    float(proposal.get("confidence") or 0),
                    20,
                    "review",
                    "Supported by sufficient BI data.",
                )
            )
    tasks.append(_task("analyze_sales", "Analyze Sales", "Research", 70, 20, "api", "Keep BI learning current."))
    tasks.append(_task("generate_pinterest", "Generate Pinterest Pins", "Marketing", 65, 30, "api", "Support product discovery traffic."))
    return tuple(tasks)


def _score_tasks(tasks: tuple[OperatingTask, ...]) -> tuple[OperatingTask, ...]:
    scored = tuple(
        OperatingTask(
            task_id=task.task_id,
            name=task.name,
            category=task.category,
            priority_score=round(task.estimated_value * _category_weight(task.category) / max(task.estimated_effort_minutes, 1), 2),
            estimated_value=task.estimated_value,
            estimated_effort_minutes=task.estimated_effort_minutes,
            required_resource=task.required_resource,
            reason=task.reason,
            status=task.status,
        )
        for task in tasks
    )
    return tuple(sorted(scored, key=lambda task: (-task.priority_score, task.name)))


def _select_tasks(
    tasks: tuple[OperatingTask, ...],
    *,
    image_budget: int,
    api_budget: int,
    publishing_capacity: int,
    review_minutes: int,
) -> tuple[OperatingTask, ...]:
    selected: list[OperatingTask] = []
    image_used = 0
    api_used = 0
    publish_used = 0
    review_used = 0
    for task in tasks:
        if task.required_resource == "image_generation":
            if image_used >= image_budget:
                continue
            image_used += 1
        elif task.required_resource == "api":
            if api_used >= api_budget:
                continue
            api_used += 1
        elif task.required_resource == "publishing":
            if publish_used >= publishing_capacity:
                continue
            publish_used += 1
        elif task.required_resource == "review":
            if review_used + task.estimated_effort_minutes > review_minutes:
                continue
            review_used += task.estimated_effort_minutes
        selected.append(task)
        if len(selected) >= 8:
            break
    return tuple(selected)


def _resource_plan(
    selected: tuple[OperatingTask, ...],
    *,
    image_budget: int,
    api_budget: int,
    publishing_capacity: int,
    review_minutes: int,
) -> ResourcePlan:
    return ResourcePlan(
        image_generation_budget=image_budget,
        api_usage_budget=api_budget,
        publishing_capacity=publishing_capacity,
        review_time_minutes=review_minutes,
        selected_image_tasks=sum(1 for task in selected if task.required_resource == "image_generation"),
        selected_api_tasks=sum(1 for task in selected if task.required_resource == "api"),
        selected_publishing_tasks=sum(1 for task in selected if task.required_resource == "publishing"),
        selected_review_minutes=sum(task.estimated_effort_minutes for task in selected if task.required_resource == "review"),
    )


def _business_risks(
    dashboard: ExecutiveDashboard,
    jobs: tuple[ProductionJob, ...],
) -> tuple[BusinessRisk, ...]:
    risks: list[BusinessRisk] = []
    seasonal = dashboard.shop_health.seasonal_vs_evergreen
    seasonal_count = int(seasonal.get("Seasonal", 0))
    evergreen_count = int(seasonal.get("Evergreen", 0))
    if seasonal_count > evergreen_count * 2 and seasonal_count >= 3:
        risks.append(_risk("Too many seasonal products", "MEDIUM", "Seasonal work outweighs evergreen catalog.", "Add evergreen collections to stabilize revenue."))
    if evergreen_count < 2:
        risks.append(_risk("Weak evergreen catalog", "MEDIUM", "Evergreen catalog is thin.", "Prioritize evergreen clipart, wall art, and digital paper."))
    if dashboard.shop_health.average_listing_price and dashboard.shop_health.average_listing_price < 3:
        risks.append(_risk("Price inconsistency", "LOW", "Average listing price is low.", "Review BI pricing recommendations."))
    if any(item.completion_percent < 75 for item in dashboard.collection_health):
        risks.append(_risk("Collection imbalance", "MEDIUM", "Some collections are incomplete.", "Finish high-value collection roadmaps."))
    duplicates = _duplicates(job.product_name for job in jobs)
    if duplicates:
        risks.append(_risk("Duplicate concepts", "HIGH", "Duplicate concepts exist in the queue.", "Differentiate or remove duplicate jobs."))
    if len(dashboard.shop_health.products_per_category) < 3 and jobs:
        risks.append(_risk("Low category diversity", "MEDIUM", "Product category diversity is narrow.", "Add products from a new category."))
    return tuple(risks)


def _backlog(
    tasks: tuple[OperatingTask, ...],
    selected: tuple[OperatingTask, ...],
) -> BacklogPlan:
    selected_ids = {task.task_id for task in selected}
    remaining = tuple(task for task in tasks if task.task_id not in selected_ids)
    return BacklogPlan(
        collections=_category_tasks(remaining, "Collections"),
        products=_category_tasks(remaining, "Production"),
        experiments=_category_tasks(remaining, "Experiments"),
        research=_category_tasks(remaining, "Research"),
        marketing=_category_tasks(remaining, "Marketing"),
        technical_debt=_category_tasks(remaining, "Technical Debt"),
    )


def _executive_report(
    *,
    dashboard: ExecutiveDashboard,
    selected: tuple[OperatingTask, ...],
    risks: tuple[BusinessRisk, ...],
    recommendations: tuple[str, ...],
) -> ExecutiveDecisionReport:
    top_tasks = tuple(task.name for task in selected[:5])
    confidence = _confidence(selected, risks)
    return ExecutiveDecisionReport(
        completed_yesterday=(
            f"{dashboard.executive_summary.products_generated_today} products generated; "
            f"{dashboard.executive_summary.drafts_pending_review} drafts pending review."
        ),
        todays_plan=", ".join(top_tasks) if top_tasks else "Monitor dashboard and collect BI data.",
        risks=tuple(risk.message for risk in risks) or ("No major business risks detected.",),
        opportunities=tuple(item.product for item in dashboard.top_opportunities[:3]) or ("No scored opportunities available.",),
        recommendations=recommendations[:3] or tuple(task.reason for task in selected[:3]),
        confidence=confidence,
    )


def _daily_plan_summary(selected: tuple[OperatingTask, ...]) -> str:
    if not selected:
        return "Monitor Aurora operations and collect performance data."
    return f"Execute {len(selected)} highest-value tasks, starting with {selected[0].name}."


def _goals(selected: tuple[OperatingTask, ...], category: str) -> tuple[str, ...]:
    goals = tuple(task.name for task in selected if task.category == category)
    return goals or (f"No {category.lower()} goal selected today.",)


def render_daily_business_plan(plan: DailyBusinessPlan) -> str:
    """Render a Daily Business Plan for the console."""
    return "\n\n".join(
        (
            "AI COO DAILY BUSINESS PLAN",
            f"Date\n{plan.plan_date.isoformat()}",
            f"Daily Business Plan\n{plan.daily_business_plan}",
            "Production Goals\n" + "\n".join(plan.production_goals),
            "Publishing Goals\n" + "\n".join(plan.publishing_goals),
            "Collection Goals\n" + "\n".join(plan.collection_goals),
            "Research Goals\n" + "\n".join(plan.research_goals),
            "Improvement Goals\n" + "\n".join(plan.improvement_goals),
            "Top Tasks\n" + "\n".join(f"{task.name} ({task.priority_score:.1f})" for task in plan.selected_tasks[:8]),
            "Resources\n" + (
                f"Image tasks {plan.resource_plan.selected_image_tasks}/{plan.resource_plan.image_generation_budget}\n"
                f"API tasks {plan.resource_plan.selected_api_tasks}/{plan.resource_plan.api_usage_budget}\n"
                f"Publishing tasks {plan.resource_plan.selected_publishing_tasks}/{plan.resource_plan.publishing_capacity}\n"
                f"Review minutes {plan.resource_plan.selected_review_minutes}/{plan.resource_plan.review_time_minutes}"
            ),
            "Business Risks\n" + "\n".join(f"{risk.severity}: {risk.risk_type}" for risk in plan.business_risks),
            plan.executive_report.render(),
            "Status\nSUCCESS",
        )
    )


def _task(
    task_id: str,
    name: str,
    category: str,
    value: float,
    effort: int,
    resource: str,
    reason: str,
) -> OperatingTask:
    return OperatingTask(
        task_id=task_id,
        name=name,
        category=category,
        priority_score=0.0,
        estimated_value=round(value, 2),
        estimated_effort_minutes=effort,
        required_resource=resource,
        reason=reason,
    )


def _category_weight(category: str) -> float:
    return {
        "Collections": 1.25,
        "Publishing": 1.2,
        "Improvement": 1.15,
        "Production": 1.0,
        "Research": 0.9,
        "Marketing": 0.75,
        "Technical Debt": 0.85,
        "Experiments": 0.8,
    }.get(category, 1.0)


def _category_tasks(tasks: tuple[OperatingTask, ...], category: str) -> tuple[OperatingTask, ...]:
    return tuple(task for task in tasks if task.category == category)


def _risk(risk_type: str, severity: str, message: str, mitigation: str) -> BusinessRisk:
    return BusinessRisk(risk_type=risk_type, severity=severity, message=message, mitigation=mitigation)


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    counts = Counter(value.casefold() for value in values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def _confidence(selected: tuple[OperatingTask, ...], risks: tuple[BusinessRisk, ...]) -> float:
    if not selected:
        return 50.0
    base = 86 + min(8, len(selected))
    high_risk_penalty = sum(8 for risk in risks if risk.severity == "HIGH")
    medium_risk_penalty = sum(3 for risk in risks if risk.severity == "MEDIUM")
    return max(55.0, min(98.0, base - high_risk_penalty - medium_risk_penalty))
