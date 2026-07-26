"""Read-only Etsy Intelligence Agent."""

from __future__ import annotations

from project_aurora.etsy_intelligence.intelligence_models import (
    READ_ONLY,
    EtsyIntelligenceReport,
)
from project_aurora.etsy_intelligence.intelligence_repository import EtsyIntelligenceRepository
from project_aurora.etsy_intelligence.keyword_analyzer import KeywordAnalyzer
from project_aurora.etsy_intelligence.opportunity_ranker import OpportunityRanker
from project_aurora.etsy_intelligence.performance_analyzer import PerformanceAnalyzer
from project_aurora.etsy_intelligence.pricing_analyzer import PricingAnalyzer
from project_aurora.etsy_intelligence.shop_reader import EtsyShopReader
from project_aurora.storage.memory_manager import MemoryManager


class EtsyIntelligenceAgent:
    """Build Etsy intelligence reports without writing to Etsy."""

    def __init__(
        self,
        *,
        memory: MemoryManager,
        shop_reader: EtsyShopReader,
        repository: EtsyIntelligenceRepository | None = None,
        mode: str = READ_ONLY,
    ) -> None:
        self._memory = memory
        self._shop_reader = shop_reader
        self._repository = repository or EtsyIntelligenceRepository(memory)
        self._mode = mode

    def run(self) -> EtsyIntelligenceReport:
        """Create and persist a read-only Etsy intelligence report."""
        if self._mode != READ_ONLY:
            raise RuntimeError("Sprint 35-36 Etsy Intelligence Agent only supports READ_ONLY mode.")
        shop, listings, warnings = self._shop_reader.read()
        learnings = (
            *PerformanceAnalyzer().analyze(listings),
            *KeywordAnalyzer().analyze(listings),
            PricingAnalyzer().analyze(listings),
        )
        opportunities = OpportunityRanker().rank(listings)[:5]
        actions = tuple(_recommended_actions(opportunities, warnings))
        report = EtsyIntelligenceReport(
            mode=self._mode,
            shop_snapshot=shop,
            listing_snapshots=listings,
            top_opportunities=opportunities,
            shop_learnings=learnings,
            recommended_actions=actions,
            warnings=warnings,
            writes_performed=False,
        )
        self._repository.save_report(report)
        return report


def _recommended_actions(opportunities: tuple[object, ...], warnings: tuple[str, ...]) -> list[str]:
    actions = ["Review top opportunities before adding production jobs."]
    if warnings:
        actions.append("Resolve unavailable Etsy data sources when needed.")
    if opportunities:
        actions.append("Use recommendations as research input only; do not bypass visual approval.")
    return actions
