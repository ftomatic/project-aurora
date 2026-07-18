"""Merchandising calendar for Aurora AI COO."""

from __future__ import annotations

from project_aurora.ai_coo.coo_models import SeasonalCalendarEvent


def merchandising_calendar() -> tuple[SeasonalCalendarEvent, ...]:
    """Return Aurora's deterministic merchandising calendar."""
    return (
        _event("Valentine's", 2, 90, 11, "High"),
        _event("Mother's Day", 5, 90, 2, "High"),
        _event("Teacher Appreciation", 5, 75, 2, "High"),
        _event("Graduation", 6, 90, 3, "Medium"),
        _event("Wedding Season", 6, 120, 2, "High"),
        _event("Baby Season", 5, 90, 2, "Medium"),
        _event("Halloween", 10, 120, 6, "High"),
        _event("Christmas", 12, 150, 7, "High"),
    )


def current_calendar_focus(month: int) -> tuple[SeasonalCalendarEvent, ...]:
    """Return events Aurora should currently be producing/researching."""
    return tuple(
        event
        for event in merchandising_calendar()
        if event.recommended_start_month <= month <= event.season_start_month
        or (
            event.recommended_start_month > event.season_start_month
            and (month >= event.recommended_start_month or month <= event.season_start_month)
        )
    )


def _event(
    name: str,
    season_start_month: int,
    production_lead_days: int,
    recommended_start_month: int,
    priority: str,
) -> SeasonalCalendarEvent:
    return SeasonalCalendarEvent(
        name=name,
        season_start_month=season_start_month,
        production_lead_days=production_lead_days,
        recommended_start_month=recommended_start_month,
        priority=priority,
    )
