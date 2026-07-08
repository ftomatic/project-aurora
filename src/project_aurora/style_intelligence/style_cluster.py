"""Style cluster model for future style-library expansion."""

from __future__ import annotations

from dataclasses import dataclass

from project_aurora.style_intelligence.style_profile import StyleProfile


@dataclass(frozen=True, slots=True)
class StyleCluster:
    """A named group of related style profiles."""

    cluster_id: str
    cluster_name: str
    profiles: tuple[StyleProfile, ...]

    def __post_init__(self) -> None:
        if not self.cluster_id.strip():
            raise ValueError("cluster_id cannot be empty.")
        if not self.cluster_name.strip():
            raise ValueError("cluster_name cannot be empty.")
        if not self.profiles:
            raise ValueError("profiles cannot be empty.")
        object.__setattr__(self, "profiles", tuple(self.profiles))
