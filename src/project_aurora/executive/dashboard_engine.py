"""Executive dashboard aggregation engine."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from project_aurora.executive.dashboard_models import (
    BusinessMetrics,
    CollectionHealthItem,
    ExecutiveAlert,
    ExecutiveDashboard,
    ExecutiveSummary,
    PipelineSummary,
    QualityMetrics,
    ShopHealthMetrics,
    TopOpportunity,
)
from project_aurora.planning.production_queue_manager import (
    COMPLETED,
    FAILED,
    IN_PROGRESS,
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.storage.memory_manager import MemoryManager


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"


class ExecutiveDashboardEngine:
    """Build a read-only executive dashboard from Aurora memory."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        queue_manager: ProductionQueueManager | None = None,
    ) -> None:
        self._memory = memory or MemoryManager()
        self._queue_manager = queue_manager or ProductionQueueManager(queue_path=DEFAULT_QUEUE_PATH)

    def build(self) -> ExecutiveDashboard:
        """Return a complete executive dashboard snapshot."""
        jobs = self._safe_jobs()
        reports = _records(self._memory, "production_reports")
        opportunities = _records(self._memory, "opportunity_scores")
        creative = _records(self._memory, "creative_briefs")
        preflight = _records(self._memory, "merchant_preflight")
        seo = _records(self._memory, "seo")
        collections = _records(self._memory, "collection_plans")
        image_qa = _records(self._memory, "image_qa")
        listings = _records(self._memory, "listings")

        quality = _quality_metrics(creative, preflight, seo, image_qa, reports)
        business = _business_metrics(jobs, reports, collections, opportunities)
        collection_health = _collection_health(collections)
        pipeline = _pipeline_summary(
            jobs=jobs,
            reports=reports,
            opportunities=opportunities,
            creative=creative,
            preflight=preflight,
            listings=listings,
        )
        summary = _executive_summary(
            jobs=jobs,
            reports=reports,
            collections=collections,
            opportunities=opportunities,
            quality=quality,
            business=business,
        )
        top = _top_opportunities(opportunities, jobs, collections)
        shop = _shop_health(jobs, reports, collections)
        alerts = _alerts(
            pipeline=pipeline,
            quality=quality,
            collection_health=collection_health,
            jobs=jobs,
            opportunities=opportunities,
        )
        report = _daily_report(
            summary=summary,
            pipeline=pipeline,
            business=business,
            alerts=alerts,
            top=top,
        )
        dashboard = ExecutiveDashboard(
            executive_summary=summary,
            production_pipeline=pipeline,
            shop_health=shop,
            quality_metrics=quality,
            business_metrics=business,
            top_opportunities=top,
            collection_health=collection_health,
            alerts=alerts,
            daily_report=report,
        )
        self._memory.save_record("executive_dashboards", "latest", dashboard.to_dict())
        return dashboard

    def _safe_jobs(self) -> tuple[ProductionJob, ...]:
        try:
            return self._queue_manager.list_jobs()
        except (FileNotFoundError, ValueError):
            return ()


def _records(memory: MemoryManager, collection: str) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    try:
        keys = memory.list_records(collection)
    except (FileNotFoundError, ValueError):
        return ()
    for key in keys:
        try:
            records.append(memory.load_record(collection, key))
        except (FileNotFoundError, ValueError):
            continue
    return tuple(records)


def _executive_summary(
    *,
    jobs: tuple[ProductionJob, ...],
    reports: tuple[dict[str, Any], ...],
    collections: tuple[dict[str, Any], ...],
    opportunities: tuple[dict[str, Any], ...],
    quality: QualityMetrics,
    business: BusinessMetrics,
) -> ExecutiveSummary:
    today_reports = [record for record in reports if _is_today(record.get("created_at"))]
    completed_reports = [record for record in reports if bool(record.get("success"))]
    draft_reports = [record for record in reports if record.get("draft_id")]
    return ExecutiveSummary(
        products_generated_today=sum(int(record.get("images") or 0) > 0 for record in today_reports),
        products_published=sum(1 for record in reports if str(record.get("status", "")).upper() == "PUBLISHED"),
        drafts_pending_review=len(draft_reports) - sum(1 for record in reports if str(record.get("status", "")).upper() == "PUBLISHED"),
        collections_active=len(collections),
        collections_in_progress=sum(1 for record in collections if _collection_completion(record) < 100),
        products_waiting=sum(1 for job in jobs if job.status == READY),
        average_opportunity_score=_avg(_float(record.get("opportunity_score")) for record in opportunities),
        average_creative_score=quality.creative_score,
        average_thumbnail_score=quality.thumbnail_score,
        average_merchant_qa_score=quality.merchant_qa,
        estimated_monthly_revenue=business.expected_monthly_revenue,
    )


def _pipeline_summary(
    *,
    jobs: tuple[ProductionJob, ...],
    reports: tuple[dict[str, Any], ...],
    opportunities: tuple[dict[str, Any], ...],
    creative: tuple[dict[str, Any], ...],
    preflight: tuple[dict[str, Any], ...],
    listings: tuple[dict[str, Any], ...],
) -> PipelineSummary:
    qa_count = sum(1 for record in reports if int(record.get("images") or 0) > 0)
    published = sum(1 for record in reports if str(record.get("status", "")).upper() == "PUBLISHED")
    counts = {
        "research": len(_records_from_latest_market(opportunities)),
        "opportunity": len(opportunities),
        "creative": len(creative),
        "production": sum(1 for job in jobs if job.status in {IN_PROGRESS, COMPLETED, FAILED}),
        "qa": qa_count,
        "etsy_draft": sum(1 for record in reports if record.get("draft_id")) + len(listings),
        "published": published,
    }
    bottlenecks = tuple(
        name.replace("_", " ").title()
        for name, count in counts.items()
        if name != "published" and count > counts.get(_next_stage(name), count)
    )
    if sum(1 for job in jobs if job.status == READY) > 0:
        bottlenecks = (*bottlenecks, "Products Waiting")
    if any(str(record.get("status", "")).upper() == "PREFLIGHT_FAILED" for record in preflight):
        bottlenecks = (*bottlenecks, "Merchant QA")
    return PipelineSummary(bottlenecks=tuple(dict.fromkeys(bottlenecks)), **counts)


def _shop_health(
    jobs: tuple[ProductionJob, ...],
    reports: tuple[dict[str, Any], ...],
    collections: tuple[dict[str, Any], ...],
) -> ShopHealthMetrics:
    categories = Counter(job.category for job in jobs)
    seasonal = Counter("Evergreen" if job.seasonal_theme == "Evergreen" else "Seasonal" for job in jobs)
    prices = [_price_from_record(record) for record in reports]
    bundle_sizes = [_bundle_size(job.product_name, job.category) for job in jobs]
    collection_counts = {
        str(record.get("collection") or record.get("collection_name") or "Unassigned"): len(record.get("products", ()))
        for record in collections
    }
    diversity = "Healthy" if len(categories) >= 4 and len(collection_counts) >= 2 else "Growing"
    return ShopHealthMetrics(
        products_per_category=dict(sorted(categories.items())),
        products_per_collection=dict(sorted(collection_counts.items())),
        seasonal_vs_evergreen=dict(sorted(seasonal.items())),
        average_listing_price=_avg(price for price in prices if price > 0),
        average_bundle_size=_avg(bundle_sizes),
        portfolio_diversity=diversity,
    )


def _quality_metrics(
    creative: tuple[dict[str, Any], ...],
    preflight: tuple[dict[str, Any], ...],
    seo: tuple[dict[str, Any], ...],
    image_qa: tuple[dict[str, Any], ...],
    reports: tuple[dict[str, Any], ...],
) -> QualityMetrics:
    creative_scores = [
        _float(record.get("creative_score", {}).get("overall_creative_score"))
        for record in creative
        if isinstance(record.get("creative_score"), dict)
    ]
    merchant_scores = [
        100.0 if str(record.get("merchant_qa_status") or record.get("status")) in {"PASS", "READY_FOR_ETSY_DRAFT"} else 0.0
        for record in preflight
    ]
    seo_scores = [_float(record.get("seo_score")) for record in seo]
    thumbnail_scores = [_thumbnail_score(record) for record in image_qa]
    blueprint_scores = [
        100.0 if record.get("style_id") and record.get("palette_id") and record.get("moodboard_id") else 0.0
        for record in creative
    ]
    total_reports = len(reports)
    rejected = sum(1 for record in reports if not bool(record.get("success", False)))
    return QualityMetrics(
        creative_score=_avg(creative_scores),
        merchant_qa=_avg(merchant_scores),
        thumbnail_score=_avg(thumbnail_scores),
        seo_score=_avg(seo_scores),
        blueprint_compliance=_avg(blueprint_scores),
        reject_rate=round((rejected / total_reports) * 100, 2) if total_reports else 0.0,
    )


def _business_metrics(
    jobs: tuple[ProductionJob, ...],
    reports: tuple[dict[str, Any], ...],
    collections: tuple[dict[str, Any], ...],
    opportunities: tuple[dict[str, Any], ...],
) -> BusinessMetrics:
    potential = sum(job.estimated_revenue for job in jobs)
    if not potential:
        potential = sum(_float(record.get("expected_revenue")) for record in opportunities)
    monthly = round(potential * 0.18, 2)
    margin = round(monthly * 0.82, 2)
    collection_values = [
        _float(record.get("roadmap", {}).get("estimated_collection_revenue"))
        for record in collections
        if isinstance(record.get("roadmap"), dict)
    ]
    product_values = [_price_from_record(record) for record in reports if _price_from_record(record) > 0]
    if not product_values:
        product_values = [job.estimated_revenue for job in jobs]
    return BusinessMetrics(
        potential_revenue=round(potential, 2),
        expected_monthly_revenue=monthly,
        expected_annual_revenue=round(monthly * 12, 2),
        expected_margin=margin,
        average_product_value=_avg(product_values),
        average_collection_value=_avg(collection_values),
    )


def _top_opportunities(
    opportunities: tuple[dict[str, Any], ...],
    jobs: tuple[ProductionJob, ...],
    collections: tuple[dict[str, Any], ...],
) -> tuple[TopOpportunity, ...]:
    status_by_product = {job.product_name.casefold(): job.status for job in jobs}
    collection_names = tuple(str(record.get("collection") or record.get("collection_name") or "") for record in collections)
    sorted_items = sorted(
        opportunities,
        key=lambda record: (-_float(record.get("opportunity_score")), str(record.get("product", "")).casefold()),
    )
    return tuple(
        TopOpportunity(
            rank=index,
            product=str(record.get("product") or "Unknown Opportunity"),
            score=_float(record.get("opportunity_score")),
            estimated_revenue=_float(record.get("expected_revenue")),
            collection=_matching_collection(str(record.get("product") or ""), collection_names),
            status=status_by_product.get(str(record.get("product") or "").casefold(), str(record.get("selection_outcome") or "CANDIDATE")),
        )
        for index, record in enumerate(sorted_items[:20], start=1)
    )


def _collection_health(collections: tuple[dict[str, Any], ...]) -> tuple[CollectionHealthItem, ...]:
    rows: list[CollectionHealthItem] = []
    for record in collections:
        roadmap = record.get("roadmap") if isinstance(record.get("roadmap"), dict) else {}
        planned = roadmap.get("products_planned") or record.get("products") or ()
        completed = roadmap.get("products_completed") or record.get("products") or ()
        planned_count = len(planned)
        completion = round((len(completed) / planned_count) * 100, 2) if planned_count else 0.0
        score = record.get("collection_score") if isinstance(record.get("collection_score"), dict) else {}
        rows.append(
            CollectionHealthItem(
                collection_name=str(record.get("collection") or record.get("collection_name") or "Unknown Collection"),
                completion_percent=completion,
                products=planned_count,
                revenue_estimate=_float(roadmap.get("estimated_collection_revenue")),
                cross_sell_score=_float(score.get("cross_sell_potential")),
                brand_consistency=_float(score.get("brand_consistency")),
            )
        )
    return tuple(sorted(rows, key=lambda row: (-row.revenue_estimate, row.collection_name)))


def _alerts(
    *,
    pipeline: PipelineSummary,
    quality: QualityMetrics,
    collection_health: tuple[CollectionHealthItem, ...],
    jobs: tuple[ProductionJob, ...],
    opportunities: tuple[dict[str, Any], ...],
) -> tuple[ExecutiveAlert, ...]:
    alerts: list[ExecutiveAlert] = []
    for row in collection_health:
        if row.completion_percent < 100:
            alerts.append(
                ExecutiveAlert(
                    alert_type="Collection incomplete",
                    severity="MEDIUM",
                    message=f"{row.collection_name} is {row.completion_percent:.0f}% complete.",
                    recommended_action="Schedule remaining collection products.",
                )
            )
    if quality.thumbnail_score and quality.thumbnail_score < 75:
        alerts.append(_alert("Low thumbnail score", "HIGH", "Thumbnail quality is below 75%.", "Review mockups before Etsy upload."))
    if quality.seo_score and quality.seo_score < 80:
        alerts.append(_alert("Weak SEO", "HIGH", "Average SEO score is below 80.", "Repair listing titles, tags, and descriptions."))
    if quality.merchant_qa and quality.merchant_qa < 90:
        alerts.append(_alert("Poor merchant QA", "HIGH", "Merchant QA is below production standards.", "Fix package specs before upload."))
    if pipeline.bottlenecks:
        alerts.append(_alert("Pipeline bottleneck", "MEDIUM", "Bottleneck detected: " + ", ".join(pipeline.bottlenecks), "Clear the highest-count blocked stage."))
    duplicate_names = _duplicates(job.product_name for job in jobs)
    if duplicate_names:
        alerts.append(_alert("Duplicate detected", "HIGH", "Duplicate products queued: " + ", ".join(duplicate_names), "Remove or differentiate duplicate jobs."))
    if any("season" in str(record.get("weakest_factor", "")).casefold() for record in opportunities):
        alerts.append(_alert("Season ending", "LOW", "Some opportunities show weak seasonality.", "Prioritize seasonal windows before demand fades."))
    if any(_float(record.get("trend_velocity_score")) >= 88 for record in opportunities):
        alerts.append(_alert("Trend emerging", "LOW", "High trend velocity opportunity detected.", "Review top opportunities for fast production."))
    return tuple(alerts)


def _daily_report(
    *,
    summary: ExecutiveSummary,
    pipeline: PipelineSummary,
    business: BusinessMetrics,
    alerts: tuple[ExecutiveAlert, ...],
    top: tuple[TopOpportunity, ...],
) -> str:
    top_name = top[0].product if top else "No ranked opportunity"
    risk = alerts[0].message if alerts else "No critical operational risks detected."
    return "\n".join(
        (
            "DAILY EXECUTIVE REPORT",
            "",
            "What happened yesterday",
            f"{summary.products_generated_today} products were generated and {summary.drafts_pending_review} Etsy drafts are pending review.",
            "",
            "What Aurora plans today",
            f"Focus on {top_name} and clear {', '.join(pipeline.bottlenecks) if pipeline.bottlenecks else 'the next ready production jobs'}.",
            "",
            "Business risks",
            risk,
            "",
            "Business opportunities",
            f"Estimated monthly revenue is ${business.expected_monthly_revenue:.2f}; top opportunity is {top_name}.",
            "",
            "Recommended actions",
            _recommended_action(alerts),
        )
    )


def render_dashboard(dashboard: ExecutiveDashboard) -> str:
    """Render the executive dashboard as console text."""
    summary = dashboard.executive_summary
    pipeline = dashboard.production_pipeline
    return "\n\n".join(
        (
            "AURORA EXECUTIVE DASHBOARD",
            f"Products Generated Today\n{summary.products_generated_today}",
            f"Products Published\n{summary.products_published}",
            f"Drafts Pending Review\n{summary.drafts_pending_review}",
            f"Collections Active\n{summary.collections_active}",
            f"Products Waiting\n{summary.products_waiting}",
            f"Average Opportunity Score\n{summary.average_opportunity_score:.1f}",
            f"Average Creative Score\n{summary.average_creative_score:.1f}",
            f"Estimated Monthly Revenue\n${summary.estimated_monthly_revenue:.2f}",
            "PRODUCTION PIPELINE\n"
            f"Research: {pipeline.research}\n"
            f"Opportunity: {pipeline.opportunity}\n"
            f"Creative: {pipeline.creative}\n"
            f"Production: {pipeline.production}\n"
            f"QA: {pipeline.qa}\n"
            f"Etsy Draft: {pipeline.etsy_draft}\n"
            f"Published: {pipeline.published}",
            "TOP OPPORTUNITIES\n"
            + "\n".join(f"{item.rank}. {item.product} - {item.score:.0f}" for item in dashboard.top_opportunities[:5]),
            "ALERTS\n"
            + ("\n".join(f"{alert.severity}: {alert.alert_type} - {alert.message}" for alert in dashboard.alerts) or "None"),
            dashboard.daily_report,
        )
    )


def _records_from_latest_market(opportunities: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    return opportunities


def _next_stage(name: str) -> str:
    stages = ("research", "opportunity", "creative", "production", "qa", "etsy_draft", "published")
    try:
        return stages[stages.index(name) + 1]
    except (ValueError, IndexError):
        return name


def _is_today(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return datetime.fromisoformat(value).date() == datetime.now().date()
    except ValueError:
        return False


def _avg(values: Iterable[float]) -> float:
    items = [float(value) for value in values if value is not None]
    if not items:
        return 0.0
    return round(sum(items) / len(items), 2)


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _price_from_record(record: dict[str, Any]) -> float:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for value in (
        record.get("price"),
        metadata.get("price"),
        metadata.get("listing", {}).get("price") if isinstance(metadata.get("listing"), dict) else None,
        metadata.get("etsy_draft", {}).get("price") if isinstance(metadata.get("etsy_draft"), dict) else None,
    ):
        price = _float(value)
        if price:
            return price
    return 0.0


def _bundle_size(product_name: str, category: str) -> int:
    lowered = f"{product_name} {category}".casefold()
    if "digital paper" in lowered:
        return 12
    if "clipart" in lowered:
        return 20
    if "sticker" in lowered:
        return 8
    return 4


def _thumbnail_score(record: dict[str, Any]) -> float:
    if "thumbnail_score" in record:
        return _float(record.get("thumbnail_score"))
    results = record.get("results")
    if isinstance(results, list):
        scores = [_float(item.get("overall_score")) for item in results if isinstance(item, dict)]
        return _avg(scores)
    return 0.0


def _collection_completion(record: dict[str, Any]) -> float:
    roadmap = record.get("roadmap") if isinstance(record.get("roadmap"), dict) else {}
    planned = roadmap.get("products_planned") or record.get("products") or ()
    completed = roadmap.get("products_completed") or record.get("products") or ()
    return round((len(completed) / len(planned)) * 100, 2) if planned else 0.0


def _matching_collection(product: str, collections: tuple[str, ...]) -> str:
    normalized = product.casefold()
    for collection in collections:
        if collection and any(token in normalized for token in collection.casefold().split()):
            return collection
    return "Unassigned"


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    counts = Counter(value.casefold() for value in values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def _alert(alert_type: str, severity: str, message: str, action: str) -> ExecutiveAlert:
    return ExecutiveAlert(
        alert_type=alert_type,
        severity=severity,
        message=message,
        recommended_action=action,
    )


def _recommended_action(alerts: tuple[ExecutiveAlert, ...]) -> str:
    if not alerts:
        return "Continue production and review the top opportunities."
    return alerts[0].recommended_action
