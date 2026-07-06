"""Image QA result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"

APPROVE = "Approve"
REGENERATE = "Regenerate"
MANUAL_REVIEW = "Manual Review"
REJECT = "Reject"


@dataclass(frozen=True, slots=True)
class QAResult:
    """Quality assurance decision for one generated asset."""

    asset_name: str
    status: str
    overall_score: int
    checks_passed: tuple[str, ...]
    checks_failed: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    recommended_action: str = MANUAL_REVIEW
    review_required: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.asset_name.strip():
            raise ValueError("Asset name cannot be empty.")
        if self.status not in {PASS, WARNING, FAIL}:
            raise ValueError(f"Unsupported QA status: {self.status}.")
        if not 0 <= self.overall_score <= 100:
            raise ValueError("Overall score must be between 0 and 100.")
        if self.recommended_action not in {
            APPROVE,
            REGENERATE,
            MANUAL_REVIEW,
            REJECT,
        }:
            raise ValueError(
                f"Unsupported recommended action: {self.recommended_action}."
            )

        object.__setattr__(self, "checks_passed", tuple(self.checks_passed))
        object.__setattr__(self, "checks_failed", tuple(self.checks_failed))
        object.__setattr__(self, "warnings", tuple(self.warnings))
