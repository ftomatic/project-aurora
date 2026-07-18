"""AI COO data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class OperatingTask:
    """One scored operational task."""

    task_id: str
    name: str
    category: str
    priority_score: float
    estimated_value: float
    estimated_effort_minutes: int
    required_resource: str
    reason: str
    status: str = "PLANNED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "category": self.category,
            "priority_score": self.priority_score,
            "estimated_value": self.estimated_value,
            "estimated_effort_minutes": self.estimated_effort_minutes,
            "required_resource": self.required_resource,
            "reason": self.reason,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ResourcePlan:
    """Available daily operating resources."""

    image_generation_budget: int
    api_usage_budget: int
    publishing_capacity: int
    review_time_minutes: int
    selected_image_tasks: int
    selected_api_tasks: int
    selected_publishing_tasks: int
    selected_review_minutes: int

    @property
    def overloaded(self) -> bool:
        return (
            self.selected_image_tasks > self.image_generation_budget
            or self.selected_api_tasks > self.api_usage_budget
            or self.selected_publishing_tasks > self.publishing_capacity
            or self.selected_review_minutes > self.review_time_minutes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_generation_budget": self.image_generation_budget,
            "api_usage_budget": self.api_usage_budget,
            "publishing_capacity": self.publishing_capacity,
            "review_time_minutes": self.review_time_minutes,
            "selected_image_tasks": self.selected_image_tasks,
            "selected_api_tasks": self.selected_api_tasks,
            "selected_publishing_tasks": self.selected_publishing_tasks,
            "selected_review_minutes": self.selected_review_minutes,
            "overloaded": self.overloaded,
        }


@dataclass(frozen=True, slots=True)
class SeasonalCalendarEvent:
    """Merchandising calendar event."""

    name: str
    season_start_month: int
    production_lead_days: int
    recommended_start_month: int
    priority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "season_start_month": self.season_start_month,
            "production_lead_days": self.production_lead_days,
            "recommended_start_month": self.recommended_start_month,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class BacklogPlan:
    """Prioritized business backlogs."""

    collections: tuple[OperatingTask, ...]
    products: tuple[OperatingTask, ...]
    experiments: tuple[OperatingTask, ...]
    research: tuple[OperatingTask, ...]
    marketing: tuple[OperatingTask, ...]
    technical_debt: tuple[OperatingTask, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "collections": [task.to_dict() for task in self.collections],
            "products": [task.to_dict() for task in self.products],
            "experiments": [task.to_dict() for task in self.experiments],
            "research": [task.to_dict() for task in self.research],
            "marketing": [task.to_dict() for task in self.marketing],
            "technical_debt": [task.to_dict() for task in self.technical_debt],
        }


@dataclass(frozen=True, slots=True)
class BusinessRisk:
    """One AI COO business risk."""

    risk_type: str
    severity: str
    message: str
    mitigation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "risk_type": self.risk_type,
            "severity": self.severity,
            "message": self.message,
            "mitigation": self.mitigation,
        }


@dataclass(frozen=True, slots=True)
class ExecutiveDecisionReport:
    """Daily executive decision report."""

    completed_yesterday: str
    todays_plan: str
    risks: tuple[str, ...]
    opportunities: tuple[str, ...]
    recommendations: tuple[str, ...]
    confidence: float

    def render(self) -> str:
        return "\n".join(
            (
                "DAILY EXECUTIVE REPORT",
                "",
                "Completed Yesterday",
                self.completed_yesterday,
                "",
                "Today's Plan",
                self.todays_plan,
                "",
                "Risks",
                *self.risks,
                "",
                "Opportunities",
                *self.opportunities,
                "",
                "Recommendations",
                *self.recommendations,
                "",
                "Confidence",
                f"{self.confidence:.0f}%",
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_yesterday": self.completed_yesterday,
            "todays_plan": self.todays_plan,
            "risks": list(self.risks),
            "opportunities": list(self.opportunities),
            "recommendations": list(self.recommendations),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class DailyBusinessPlan:
    """Aurora AI COO daily operating plan."""

    plan_date: date
    daily_business_plan: str
    production_goals: tuple[str, ...]
    publishing_goals: tuple[str, ...]
    collection_goals: tuple[str, ...]
    research_goals: tuple[str, ...]
    improvement_goals: tuple[str, ...]
    selected_tasks: tuple[OperatingTask, ...]
    backlog: BacklogPlan
    resource_plan: ResourcePlan
    seasonal_calendar: tuple[SeasonalCalendarEvent, ...]
    business_risks: tuple[BusinessRisk, ...]
    executive_report: ExecutiveDecisionReport
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_date": self.plan_date.isoformat(),
            "daily_business_plan": self.daily_business_plan,
            "production_goals": list(self.production_goals),
            "publishing_goals": list(self.publishing_goals),
            "collection_goals": list(self.collection_goals),
            "research_goals": list(self.research_goals),
            "improvement_goals": list(self.improvement_goals),
            "selected_tasks": [task.to_dict() for task in self.selected_tasks],
            "backlog": self.backlog.to_dict(),
            "resource_plan": self.resource_plan.to_dict(),
            "seasonal_calendar": [event.to_dict() for event in self.seasonal_calendar],
            "business_risks": [risk.to_dict() for risk in self.business_risks],
            "executive_report": self.executive_report.to_dict(),
            "created_at": self.created_at.isoformat(),
        }
