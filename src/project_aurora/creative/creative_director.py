"""Aurora Creative Director."""

from __future__ import annotations

from typing import Any

from project_aurora.config.project_profile import ProjectProfile
from project_aurora.creative.collection_engine import CollectionEngine
from project_aurora.creative.collection_plan import CollectionPlan


class CreativeDirector:
    """Decide what Aurora should produce for a collection."""

    def __init__(self, collection_engine: CollectionEngine | None = None) -> None:
        self._collection_engine = collection_engine or CollectionEngine()

    def plan_collection(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        project_profile: ProjectProfile,
    ) -> CollectionPlan:
        """Return a complete collection plan."""
        return self._collection_engine.build_plan(
            research=research,
            strategy=strategy,
            project_profile=project_profile,
        )
