"""Athena market intelligence for research-first production planning."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from project_aurora.planning.production_queue_manager import ProductionQueueManager
from project_aurora.research.market_opportunity import MarketOpportunity
from project_aurora.storage.memory_manager import MemoryManager


OPPORTUNITY_COLLECTION = "market_opportunities"


@dataclass(frozen=True, slots=True)
class ResearchProviderStatus:
    """Status for one Athena research provider."""

    provider: str
    priority: int
    status: str
    detail: str
    opportunities: int


@dataclass(frozen=True, slots=True)
class AthenaResearchReport:
    """Athena's normalized opportunity database report."""

    opportunities: tuple[MarketOpportunity, ...]
    provider_statuses: tuple[ResearchProviderStatus, ...]
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def providers_used(self) -> tuple[str, ...]:
        """Return providers that contributed opportunities."""
        return tuple(
            status.provider
            for status in self.provider_statuses
            if status.opportunities > 0
        )

    @property
    def providers_unavailable(self) -> tuple[ResearchProviderStatus, ...]:
        """Return unavailable providers."""
        return tuple(
            status for status in self.provider_statuses if status.status == "UNAVAILABLE"
        )

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe research report data."""
        return {
            "created_at": self.created_at.isoformat(),
            "opportunity_count": len(self.opportunities),
            "opportunities": [item.to_dict() for item in self.opportunities],
            "provider_statuses": [
                {
                    "provider": item.provider,
                    "priority": item.priority,
                    "status": item.status,
                    "detail": item.detail,
                    "opportunities": item.opportunities,
                }
                for item in self.provider_statuses
            ],
        }


class AthenaResearchProvider(Protocol):
    """Provider boundary for Athena market intelligence."""

    provider_name: str
    priority: int

    def collect(self) -> tuple[MarketOpportunity, ...]:
        """Collect researched opportunities."""


class UnavailableExternalProvider:
    """External provider placeholder that records unavailable configuration."""

    def __init__(self, provider_name: str, priority: int, required_env: tuple[str, ...]) -> None:
        self.provider_name = provider_name
        self.priority = priority
        self._required_env = required_env

    def collect(self) -> tuple[MarketOpportunity, ...]:
        missing = tuple(name for name in self._required_env if not os.getenv(name))
        if missing:
            raise RuntimeError(f"Missing configuration: {', '.join(missing)}.")
        raise RuntimeError("Live provider collection is not enabled for this planner run.")


class AuroraHistoricalProductionProvider:
    """Build opportunities from Aurora's local production memory."""

    provider_name = "Aurora Historical Production Memory"
    priority = 1

    def __init__(self, queue_manager: ProductionQueueManager | None = None) -> None:
        self._queue_manager = queue_manager or ProductionQueueManager()

    def collect(self) -> tuple[MarketOpportunity, ...]:
        opportunities: list[MarketOpportunity] = []
        for job in self._queue_manager.list_jobs():
            opportunities.append(
                _opportunity(
                    keyword=job.product_name,
                    primary_niche=job.category.title(),
                    subcategory="Historical Product",
                    target_audience=job.target_customer or "digital printable buyers",
                    season=job.seasonal_theme,
                    product_type=job.category,
                    style=job.style,
                    trend=job.demand_score * 100 if job.demand_score else 78,
                    competition=job.competition_score * 100 if job.competition_score else 42,
                    potential=min(job.confidence_score * 100 + 5, 98),
                    confidence=min(job.confidence_score * 100, 96),
                    source=self.provider_name,
                )
            )
        return tuple(opportunities)


class StaticOpportunityProvider:
    """Deterministic local research provider for known planning calendars."""

    def __init__(
        self,
        provider_name: str,
        priority: int,
        rows: tuple[dict[str, object], ...],
    ) -> None:
        self.provider_name = provider_name
        self.priority = priority
        self._rows = rows

    def collect(self) -> tuple[MarketOpportunity, ...]:
        return tuple(
            _opportunity(
                keyword=str(row["keyword"]),
                primary_niche=str(row["primary_niche"]),
                subcategory=str(row["subcategory"]),
                target_audience=str(row["target_audience"]),
                season=str(row["season"]),
                product_type=str(row["product_type"]),
                style=str(row["style"]),
                trend=float(row["trend_score"]),
                competition=float(row["competition_score"]),
                potential=float(row["commercial_potential"]),
                confidence=float(row["confidence"]),
                source=self.provider_name,
            )
            for row in self._rows
        )


class AthenaMarketIntelligence:
    """Collect opportunities, record provider status, and save runtime memory."""

    def __init__(
        self,
        providers: tuple[AthenaResearchProvider, ...] | None = None,
        memory: MemoryManager | None = None,
        candidate_count: int = 50,
    ) -> None:
        self._providers = providers or default_athena_providers()
        self._memory = memory or MemoryManager()
        self._candidate_count = candidate_count

    def run(self) -> AthenaResearchReport:
        """Collect and persist at least the configured number of opportunities."""
        opportunities: list[MarketOpportunity] = []
        statuses: list[ResearchProviderStatus] = []
        for provider in sorted(self._providers, key=lambda item: item.priority):
            try:
                collected = provider.collect()
            except RuntimeError as error:
                statuses.append(
                    ResearchProviderStatus(
                        provider=provider.provider_name,
                        priority=provider.priority,
                        status="UNAVAILABLE",
                        detail=str(error),
                        opportunities=0,
                    )
                )
                continue
            status = "AVAILABLE" if collected else "AVAILABLE_NO_DATA"
            detail = "Collected opportunities." if collected else "No local records available."
            statuses.append(
                ResearchProviderStatus(
                    provider=provider.provider_name,
                    priority=provider.priority,
                    status=status,
                    detail=detail,
                    opportunities=len(collected),
                )
            )
            opportunities.extend(collected)
        ranked = tuple(sorted(opportunities, key=_opportunity_sort_key))
        report = AthenaResearchReport(
            opportunities=ranked[: self._candidate_count],
            provider_statuses=tuple(statuses),
        )
        self._memory.save_record(OPPORTUNITY_COLLECTION, "latest", report.to_dict())
        return report


def default_athena_providers() -> tuple[AthenaResearchProvider, ...]:
    """Return Athena's default provider stack."""
    return (
        UnavailableExternalProvider(
            "Etsy Open API",
            1,
            ("ETSY_CLIENT_ID", "ETSY_SHARED_SECRET", "ETSY_ACCESS_TOKEN"),
        ),
        AuroraHistoricalProductionProvider(),
        UnavailableExternalProvider("Google Trends", 2, ("AURORA_GOOGLE_TRENDS_ENABLED",)),
        UnavailableExternalProvider(
            "Pinterest Trends",
            2,
            ("AURORA_PINTEREST_TRENDS_ENABLED",),
        ),
        StaticOpportunityProvider("Seasonal Calendar", 3, _seasonal_rows()),
        StaticOpportunityProvider("US Holiday Calendar", 3, _holiday_rows()),
        StaticOpportunityProvider("School Calendar", 3, _school_rows()),
        StaticOpportunityProvider("Wedding Season", 3, _wedding_rows()),
        StaticOpportunityProvider("Baby Season", 3, _baby_rows()),
        StaticOpportunityProvider("Interior Design Color Trends", 3, _interior_rows()),
    )


def _opportunity_sort_key(item: MarketOpportunity) -> tuple[float, float, float, str]:
    return (
        -item.confidence,
        -item.trend_score,
        item.competition_score,
        item.keyword.casefold(),
    )


def _opportunity(
    *,
    keyword: str,
    primary_niche: str,
    subcategory: str,
    target_audience: str,
    season: str,
    product_type: str,
    style: str,
    trend: float,
    competition: float,
    potential: float,
    confidence: float,
    source: str,
) -> MarketOpportunity:
    return MarketOpportunity(
        keyword=keyword,
        primary_niche=primary_niche,
        subcategory=subcategory,
        target_audience=target_audience,
        season=season,
        product_type=product_type,
        recommended_artistic_style=style,
        trend_score=trend,
        competition_score=competition,
        commercial_potential=potential,
        confidence=confidence,
        research_sources=(source,),
    )


def _seasonal_rows() -> tuple[dict[str, object], ...]:
    return (
        _row("spring bunny nursery art", "Nursery", "Spring Nursery", "parents", "Spring", "wall art", "Soft Nursery", 92, 38, 91, 93),
        _row("summer strawberry birthday printable", "Birthday", "Summer Party", "parents", "Summer", "party printable", "Storybook Watercolor", 94, 42, 94, 92),
        _row("autumn mushroom clipart", "Botanical", "Fall Woodland", "crafters", "Fall", "clipart", "Cottagecore Watercolor", 90, 36, 90, 91),
        _row("winter woodland digital paper", "Digital Paper", "Winter Pattern", "crafters", "Winter", "digital paper", "Woodland Friends", 88, 35, 88, 90),
        _row("valentine classroom cards", "Teacher", "Classroom Holiday", "teachers", "Valentine", "party printable", "Cute", 87, 45, 86, 88),
        _row("spring garden sticker sheet", "Planner Stickers", "Garden Planner", "planner buyers", "Spring", "sticker sheet", "Vintage Botanical", 86, 39, 85, 87),
        _row("summer lemonade kitchen print", "Kitchen", "Seasonal Kitchen", "home decorators", "Summer", "wall art", "French Country", 85, 41, 84, 86),
        _row("fall farmhouse recipe cards", "Farmhouse", "Kitchen Printable", "home decorators", "Fall", "party printable", "Farmhouse", 84, 40, 83, 85),
    )


def _holiday_rows() -> tuple[dict[str, object], ...]:
    return (
        _row("vintage christmas gift tags", "Christmas", "Gift Tags", "crafters", "Christmas", "junk journal", "Vintage Christmas", 93, 44, 92, 91),
        _row("cute halloween party bundle", "Halloween", "Party Printable", "parents", "Halloween", "party printable", "Cute Halloween", 91, 43, 91, 90),
        _row("thanksgiving watercolor wall art", "Holiday", "Home Decor", "home decorators", "Thanksgiving", "wall art", "Watercolor", 84, 37, 84, 86),
        _row("easter bunny clipart bundle", "Holiday", "Easter Clipart", "crafters", "Easter", "clipart", "Storybook", 87, 40, 87, 88),
        _row("fourth of july digital paper", "Digital Paper", "Patriotic Pattern", "crafters", "Summer", "digital paper", "Bold Modern", 82, 36, 82, 84),
        _row("new year planner stickers", "Planner Stickers", "Planner", "planner buyers", "New Year", "sticker sheet", "Minimalist", 85, 34, 84, 87),
        _row("mother day floral art", "Botanical", "Gift Art", "gift buyers", "Spring", "wall art", "Vintage Botanical", 86, 38, 86, 88),
        _row("teacher appreciation printable", "Teacher", "School Gift", "teachers", "Spring", "party printable", "Cute", 88, 41, 88, 89),
    )


def _school_rows() -> tuple[dict[str, object], ...]:
    return (
        _row("back to school teacher stickers", "Teacher", "Classroom", "teachers", "Back To School", "sticker sheet", "Kawaii", 91, 39, 90, 91),
        _row("classroom alphabet wall art", "Teacher", "Classroom Decor", "teachers", "Back To School", "wall art", "Bold Modern", 89, 42, 88, 89),
        _row("graduation party printable", "Holiday", "Graduation", "parents", "Graduation", "party printable", "Minimalist", 86, 37, 86, 87),
        _row("preschool animal clipart", "Animals", "Education Clipart", "teachers", "Evergreen", "clipart", "Cute Farm Animals", 90, 40, 90, 90),
        _row("reading corner woodland posters", "Wall Art", "Classroom Decor", "teachers", "Evergreen", "wall art", "Woodland Friends", 85, 35, 84, 86),
        _row("planner school icons", "Planner Stickers", "Planner", "planner buyers", "Back To School", "sticker sheet", "Flat Design", 84, 33, 83, 85),
        _row("teacher boho rainbow decor", "Boho", "Classroom Decor", "teachers", "Back To School", "wall art", "Boho", 88, 43, 88, 88),
        _row("homeschool reward chart", "Teacher", "Homeschool", "parents", "Evergreen", "party printable", "Soft Pastel", 83, 32, 83, 85),
    )


def _wedding_rows() -> tuple[dict[str, object], ...]:
    return (
        _row("wildflower wedding invitation", "Wedding", "Invitation", "brides", "Wedding Season", "party printable", "Vintage Botanical", 90, 46, 91, 89),
        _row("boho bridal shower games", "Wedding", "Bridal Shower", "brides", "Wedding Season", "party printable", "Boho", 88, 44, 88, 87),
        _row("sage green wedding signs", "Wedding", "Wedding Signs", "brides", "Wedding Season", "wall art", "Minimalist", 87, 41, 87, 86),
        _row("coquette bow bridal clipart", "Coquette", "Bridal Graphics", "crafters", "Wedding Season", "clipart", "Coquette", 89, 39, 90, 90),
        _row("vintage lace digital paper", "Digital Paper", "Wedding Paper", "crafters", "Wedding Season", "digital paper", "Victorian", 86, 36, 86, 87),
        _row("french country wedding menu", "Wedding", "Reception", "brides", "Wedding Season", "party printable", "French Country", 85, 38, 85, 86),
        _row("floral monogram wall art", "Botanical", "Gift Art", "gift buyers", "Wedding Season", "wall art", "Ink Illustration", 84, 35, 84, 85),
        _row("wedding planner stickers", "Planner Stickers", "Planner", "brides", "Wedding Season", "sticker sheet", "Soft Pastel", 83, 34, 83, 85),
    )


def _baby_rows() -> tuple[dict[str, object], ...]:
    return (
        _row("baby shower woodland invitation", "Baby Shower", "Invitation", "parents", "Baby Season", "party printable", "Woodland Friends", 92, 43, 92, 91),
        _row("nursery safari wall art", "Nursery", "Nursery Decor", "parents", "Baby Season", "wall art", "Cute Farm Animals", 90, 44, 90, 89),
        _row("pastel baby animal clipart", "Animals", "Nursery Clipart", "crafters", "Baby Season", "clipart", "Soft Pastel", 91, 41, 91, 90),
        _row("moon star digital paper", "Digital Paper", "Nursery Pattern", "crafters", "Baby Season", "digital paper", "Soft Nursery", 88, 37, 88, 88),
        _row("teddy bear thank you cards", "Baby Shower", "Cards", "parents", "Baby Season", "party printable", "Children's Book", 87, 36, 87, 87),
        _row("new baby milestone stickers", "Planner Stickers", "Baby Planner", "parents", "Baby Season", "sticker sheet", "Kawaii", 86, 35, 86, 86),
        _row("rainbow nursery alphabet", "Nursery", "Alphabet", "parents", "Baby Season", "wall art", "Scandinavian", 85, 33, 85, 86),
        _row("baby woodland junk journal", "Junk Journal", "Memory Book", "crafters", "Baby Season", "junk journal", "Cottagecore", 84, 34, 84, 85),
    )


def _interior_rows() -> tuple[dict[str, object], ...]:
    return (
        _row("sage botanical kitchen art", "Kitchen", "Home Decor", "home decorators", "Evergreen", "wall art", "Botanical", 88, 35, 89, 89),
        _row("moody dark academia prints", "Wall Art", "Interior Decor", "home decorators", "Fall", "wall art", "Dark Academia", 87, 34, 88, 88),
        _row("mid century fruit poster", "Kitchen", "Retro Decor", "home decorators", "Evergreen", "wall art", "Mid Century", 86, 32, 87, 87),
        _row("coastal blue digital paper", "Digital Paper", "Interior Color", "crafters", "Summer", "digital paper", "Minimalist", 84, 31, 84, 85),
        _row("folk art floral clipart", "Botanical", "Commercial Graphics", "crafters", "Evergreen", "clipart", "Folk Art", 89, 37, 90, 90),
        _row("neutral boho wall art", "Boho", "Interior Decor", "home decorators", "Evergreen", "wall art", "Boho", 85, 36, 85, 86),
        _row("victorian botanical journal kit", "Vintage", "Junk Journal", "crafters", "Evergreen", "junk journal", "Victorian", 86, 39, 87, 87),
        _row("scandinavian nursery shapes", "Nursery", "Interior Decor", "parents", "Evergreen", "wall art", "Scandinavian", 83, 30, 83, 85),
        _row("warm butter yellow kitchen prints", "Kitchen", "Interior Color", "home decorators", "Evergreen", "wall art", "French Country", 84, 29, 84, 86),
        _row("soft blue farmhouse digital paper", "Farmhouse", "Interior Color", "crafters", "Evergreen", "digital paper", "Farmhouse", 83, 31, 83, 85),
        _row("coastal scrapbook digital paper", "Digital Paper", "Scrapbook Paper", "scrapbook buyers", "Coastal", "digital paper", "Flat Design", 88, 30, 88, 90),
    )


def _row(
    keyword: str,
    primary_niche: str,
    subcategory: str,
    target_audience: str,
    season: str,
    product_type: str,
    style: str,
    trend_score: float,
    competition_score: float,
    commercial_potential: float,
    confidence: float,
) -> dict[str, object]:
    return {
        "keyword": keyword,
        "primary_niche": primary_niche,
        "subcategory": subcategory,
        "target_audience": target_audience,
        "season": season,
        "product_type": product_type,
        "style": style,
        "trend_score": trend_score,
        "competition_score": competition_score,
        "commercial_potential": commercial_potential,
        "confidence": confidence,
    }
