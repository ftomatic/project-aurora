"""Aurora Style Intelligence Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_aurora.config.project_profile import ProjectProfile
from project_aurora.creative.collection_plan import CollectionPlan
from project_aurora.storage.memory_manager import MemoryManager
from project_aurora.style_intelligence.style_library_builder import (
    StyleLibraryBuilder,
)
from project_aurora.style_intelligence.style_profile import StyleProfile
from project_aurora.style_intelligence.style_selector import (
    StyleSelection,
    StyleSelector,
)


@dataclass(frozen=True, slots=True)
class StyleIntelligenceResult:
    """Result returned by the style intelligence engine."""

    styles_available: int
    selection: StyleSelection
    saved_style_ids: tuple[str, ...]
    status: str


class StyleEngine:
    """Build, save, and select reusable style profiles."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        library_builder: StyleLibraryBuilder | None = None,
        style_selector: StyleSelector | None = None,
    ) -> None:
        self._memory = memory
        self._library_builder = library_builder or StyleLibraryBuilder()
        self._style_selector = style_selector or StyleSelector()

    def build_library(self) -> tuple[StyleProfile, ...]:
        """Return the available seed style profiles."""
        return self._library_builder.build_seed_library()

    def run(
        self,
        project_profile: ProjectProfile,
        trend_research: dict[str, Any],
        collection_plan: CollectionPlan,
    ) -> StyleIntelligenceResult:
        """Build style library, save profiles, and select the best style."""
        profiles = self.build_library()
        saved_ids = self._save_profiles(profiles)
        selection = self._style_selector.select(
            project_profile=project_profile,
            trend_research=trend_research,
            collection_plan=collection_plan,
            style_profiles=profiles,
        )
        return StyleIntelligenceResult(
            styles_available=len(profiles),
            selection=selection,
            saved_style_ids=saved_ids,
            status="SUCCESS",
        )

    def _save_profiles(
        self,
        profiles: tuple[StyleProfile, ...],
    ) -> tuple[str, ...]:
        if self._memory is None:
            return ()
        return tuple(
            self._memory.save_style_profile(profile, style_id=profile.style_id)
            for profile in profiles
        )
