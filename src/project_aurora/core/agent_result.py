"""Shared result envelope for Aurora agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Structured execution result returned by every orchestrated agent."""

    agent_name: str
    status: str
    started_at: datetime
    finished_at: datetime
    execution_time: float
    confidence: float
    summary: str
    output: Any = None
    next_agent: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.agent_name.strip():
            raise ValueError("Agent name cannot be empty.")
        if not self.status.strip():
            raise ValueError("Agent status cannot be empty.")
        if self.execution_time < 0:
            raise ValueError("Execution time cannot be negative.")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1.")

        object.__setattr__(self, "agent_name", self.agent_name.strip())
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "summary", self.summary.strip())
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
