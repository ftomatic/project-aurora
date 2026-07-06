"""Aurora workflow orchestration layer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from logging import Logger
from time import perf_counter
from typing import Any

from project_aurora.agents.morning_research_agent import (
    MorningResearchAgent,
    MorningResearchPaths,
)
from project_aurora.agents.product_strategy_agent import ProductStrategyAgent
from project_aurora.core.agent_result import AgentResult
from project_aurora.core.logger import get_logger
from project_aurora.research.recommendation_engine import ResearchReport
from project_aurora.strategy.product_plan import ProductPlan


SUCCESS = "SUCCESS"
FAILED = "FAILED"


class WorkflowOrchestrator:
    """Execute Aurora agents in sequence and generate executive briefings."""

    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or get_logger(__name__)
        self._results: list[AgentResult] = []
        self._workflow_started_at: float = 0.0
        self._workflow_finished_at: float = 0.0

    @property
    def results(self) -> tuple[AgentResult, ...]:
        """Return stored workflow results."""
        return tuple(self._results)

    @property
    def total_workflow_time(self) -> float:
        """Return total workflow duration in seconds."""
        if self._workflow_finished_at <= self._workflow_started_at:
            return 0.0
        return self._workflow_finished_at - self._workflow_started_at

    def run_day(
        self,
        morning_agent: MorningResearchAgent,
        strategy_agent: ProductStrategyAgent,
        paths: MorningResearchPaths,
    ) -> str:
        """Run Aurora's local daily workflow and return a CEO briefing."""
        self._results = []
        self._workflow_started_at = perf_counter()
        self._logger.info("Aurora workflow started")

        morning_result = self.execute_agent(
            agent_name="Morning Research Agent",
            action=lambda: morning_agent.build_report(paths),
            confidence=0.95,
            summary_builder=self._morning_summary,
            next_agent="Product Strategy Agent",
        )
        self._results.append(morning_result)
        if morning_result.status == FAILED:
            return self._finish_with_error(morning_result)

        strategy_result = self.execute_agent(
            agent_name="Product Strategy Agent",
            action=lambda: strategy_agent.build_plan(
                self._require_output(morning_result, ResearchReport)
            ),
            confidence=0.93,
            summary_builder=self._strategy_summary,
            next_agent="Prompt Factory Agent",
        )
        self._results.append(strategy_result)
        if strategy_result.status == FAILED:
            return self._finish_with_error(strategy_result)

        briefing_result = self.execute_agent(
            agent_name="CEO Briefing Generated",
            action=lambda: self._base_ceo_briefing(
                self._require_output(strategy_result, ProductPlan)
            ),
            confidence=self._average_confidence(),
            summary_builder=lambda _: "CEO briefing generated.",
            next_agent="Prompt Factory Agent",
        )
        self._results.append(briefing_result)
        self._workflow_finished_at = perf_counter()
        self._logger.info(
            "Aurora workflow completed in %.2f seconds",
            self.total_workflow_time,
        )

        return (
            str(briefing_result.output)
            + "\n\n"
            + self.generate_workflow_summary()
            + "\n\n"
            + self.generate_workflow_timeline()
        )

    def execute_agent(
        self,
        agent_name: str,
        action: Callable[[], Any],
        confidence: float,
        summary_builder: Callable[[Any], str],
        next_agent: str | None,
    ) -> AgentResult:
        """Execute one workflow step and return an AgentResult."""
        self._logger.info("Executing %s", agent_name)
        started_at = datetime.now()
        started_perf = perf_counter()

        try:
            output = action()
        except Exception as error:  # noqa: BLE001 - captured for CEO report.
            finished_at = datetime.now()
            execution_time = perf_counter() - started_perf
            self._logger.exception("%s failed after %.2f seconds", agent_name, execution_time)
            return AgentResult(
                agent_name=agent_name,
                status=FAILED,
                started_at=started_at,
                finished_at=finished_at,
                execution_time=execution_time,
                confidence=0.0,
                summary=f"{agent_name} failed.",
                output=None,
                next_agent=None,
                errors=(str(error),),
            )

        finished_at = datetime.now()
        execution_time = perf_counter() - started_perf
        self._logger.info(
            "%s completed in %.2f seconds",
            agent_name,
            execution_time,
        )
        return AgentResult(
            agent_name=agent_name,
            status=SUCCESS,
            started_at=started_at,
            finished_at=finished_at,
            execution_time=execution_time,
            confidence=confidence,
            summary=summary_builder(output),
            output=output,
            next_agent=next_agent,
        )

    def generate_workflow_summary(self) -> str:
        """Return a compact workflow summary table."""
        lines = [
            "Workflow Summary",
            "----------------",
        ]
        for result in self._results:
            lines.extend(
                (
                    result.agent_name,
                    result.status,
                    f"{result.execution_time:.2f} sec",
                    f"{result.confidence:.0%}",
                    "",
                )
            )
        return "\n".join(lines).rstrip()

    def generate_workflow_timeline(self) -> str:
        """Return the workflow timeline section."""
        lines = ["Workflow Timeline", "-----------------"]
        for result in self._results:
            marker = "✓ Completed" if result.status == SUCCESS else "✗ Failed"
            lines.append(
                f"{result.finished_at:%H:%M:%S}  "
                f"{result.agent_name:<28} {marker}"
            )
        lines.append("")
        lines.append(f"Total Workflow Time: {self.total_workflow_time:.2f} seconds")
        return "\n".join(lines)

    def _finish_with_error(self, failed_result: AgentResult) -> str:
        self._workflow_finished_at = perf_counter()
        self._logger.info(
            "Aurora workflow stopped in %.2f seconds",
            self.total_workflow_time,
        )
        return (
            self._ceo_error_report(failed_result)
            + "\n\n"
            + self.generate_workflow_summary()
            + "\n\n"
            + self.generate_workflow_timeline()
        )

    @staticmethod
    def _require_output(
        result: AgentResult,
        expected_type: type[Any],
    ) -> Any:
        if not isinstance(result.output, expected_type):
            raise TypeError(
                f"{result.agent_name} did not return "
                f"{expected_type.__name__}."
            )
        return result.output

    @staticmethod
    def _morning_summary(output: Any) -> str:
        report = output
        return (
            f"Reviewed {len(report.recommendations)} recommendations; "
            f"selected {report.production_selection.best_product.name}."
        )

    @staticmethod
    def _strategy_summary(output: Any) -> str:
        plan = output
        return (
            f"Finalized {plan.collection_name} with "
            f"{plan.asset_count} assets."
        )

    def _base_ceo_briefing(self, plan: ProductPlan) -> str:
        return "\n".join(
            (
                "=" * 48,
                "AURORA CEO DAILY BRIEFING",
                "",
                "Good morning Elena.",
                "",
                "Today's production plan has been finalized.",
                "",
                "Research Status",
                self._status_for_agent("Morning Research Agent"),
                "",
                "Strategy Status",
                self._status_for_agent("Product Strategy Agent"),
                "",
                "Today's Production",
                plan.collection_name,
                "",
                "Priority",
                plan.production_priority.upper(),
                "",
                "Commercial Potential",
                self._commercial_stars(plan.estimated_commercial_potential),
                "",
                "Recommended Product Count",
                f"{plan.asset_count} assets",
                "",
                "Estimated Studio Time",
                self._estimated_studio_time(plan.asset_count),
                "",
                "Next Agent",
                "Prompt Factory Agent",
                "",
                "Workflow Health",
                self._workflow_health(),
                "",
                "Confidence",
                f"{self._average_confidence():.0%}",
                "=" * 48,
            )
        )

    def _ceo_error_report(self, failed_result: AgentResult) -> str:
        reason = "Unknown error."
        if failed_result.errors:
            reason = failed_result.errors[0]

        return "\n".join(
            (
                "=" * 48,
                "AURORA CEO DAILY BRIEFING",
                "",
                f"{failed_result.agent_name} failed.",
                "",
                "Reason:",
                reason,
                "",
                "Workflow stopped.",
                "=" * 48,
            )
        )

    def _status_for_agent(self, agent_name: str) -> str:
        for result in self._results:
            if result.agent_name == agent_name:
                return result.status
        return "NOT RUN"

    def _average_confidence(self) -> float:
        successful_results = [
            result.confidence
            for result in self._results
            if result.status == SUCCESS
        ]
        if not successful_results:
            return 0.0
        return sum(successful_results) / len(successful_results)

    def _workflow_health(self) -> str:
        if all(result.status == SUCCESS for result in self._results):
            return "Excellent"
        return "Needs Attention"

    @staticmethod
    def _commercial_stars(commercial_potential: str) -> str:
        normalized = commercial_potential.casefold()
        if "high" in normalized:
            return "★★★★★"
        if "medium" in normalized:
            return "★★★★☆"
        return "★★★☆☆"

    @staticmethod
    def _estimated_studio_time(asset_count: int) -> str:
        hours = max(1.0, asset_count * 0.09)
        return f"{hours:.1f} hours"
