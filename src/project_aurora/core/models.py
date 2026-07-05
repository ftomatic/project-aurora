"""Data models for Project Aurora core components."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Description of an agent known to Aurora OS."""

    name: str
    description: str
    department: str = "Core"
    role: str = "Agent"
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        normalized_description = self.description.strip()
        normalized_department = self.department.strip()
        normalized_role = self.role.strip()

        if not normalized_name:
            raise ValueError("Agent name cannot be empty.")
        if not normalized_description:
            raise ValueError("Agent description cannot be empty.")
        if not normalized_department:
            raise ValueError("Agent department cannot be empty.")
        if not normalized_role:
            raise ValueError("Agent role cannot be empty.")

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "description", normalized_description)
        object.__setattr__(self, "department", normalized_department)
        object.__setattr__(self, "role", normalized_role)
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    def with_enabled(self, enabled: bool) -> "AgentDefinition":
        """Return a copy of the agent with updated enabled state."""
        return replace(self, enabled=enabled)
