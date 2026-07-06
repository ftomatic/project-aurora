"""Console reporting for Aurora image QA."""

from __future__ import annotations

from dataclasses import dataclass

from project_aurora.image_qa.qa_result import FAIL, PASS, WARNING, QAResult


@dataclass(frozen=True, slots=True)
class QAReport:
    """Summary report for a batch of image QA results."""

    results: tuple[QAResult, ...]

    @property
    def assets_reviewed(self) -> int:
        """Return total reviewed assets."""
        return len(self.results)

    @property
    def passed(self) -> int:
        """Return count of passing assets."""
        return sum(1 for result in self.results if result.status == PASS)

    @property
    def warnings(self) -> int:
        """Return count of warning assets."""
        return sum(1 for result in self.results if result.status == WARNING)

    @property
    def failed(self) -> int:
        """Return count of failed assets."""
        return sum(1 for result in self.results if result.status == FAIL)

    @property
    def approval_rate(self) -> int:
        """Return approval rate as a whole-number percentage."""
        if not self.results:
            return 0
        return round((self.passed / len(self.results)) * 100)

    @property
    def recommended_action(self) -> str:
        """Return the recommended next workflow action."""
        if self.failed:
            return "Regenerate Failed Assets"
        if self.warnings:
            return "Manual Review Before Mockup Generation"
        return "Proceed to Mockup Generation"

    def render(self) -> str:
        """Return a plain-text QA report."""
        return "\n\n".join(
            (
                "IMAGE QA REPORT",
                f"Assets Reviewed\n{self.assets_reviewed}",
                f"Passed\n{self.passed}",
                f"Warnings\n{self.warnings}",
                f"Failed\n{self.failed}",
                f"Approval Rate\n{self.approval_rate}%",
                f"Recommended Action\n{self.recommended_action}",
            )
        )
