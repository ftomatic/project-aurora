"""Tests for the Project Aurora workflow orchestrator."""

from __future__ import annotations

import logging
import sys
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.agents.morning_research_agent import (  # noqa: E402
    MorningResearchAgent,
    MorningResearchPaths,
)
from project_aurora.agents.product_strategy_agent import (  # noqa: E402
    ProductStrategyAgent,
)
from project_aurora.core.agent_result import AgentResult  # noqa: E402
from project_aurora.core.workflow_orchestrator import (  # noqa: E402
    FAILED,
    SUCCESS,
    WorkflowOrchestrator,
)


def make_test_logger() -> logging.Logger:
    logger = logging.getLogger("test_workflow_orchestrator")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


def make_paths() -> MorningResearchPaths:
    return MorningResearchPaths(
        shop_csv=PROJECT_ROOT / "data" / "research" / "sample_shop.csv",
        market_trends_csv=(
            PROJECT_ROOT / "data" / "research" / "sample_market_trends.csv"
        ),
    )


class FailingMorningResearchAgent:
    def build_report(self, paths: MorningResearchPaths) -> object:
        raise ValueError("Missing market data.")


class WorkflowOrchestratorTest(unittest.TestCase):
    def test_agent_result_creation(self) -> None:
        started_at = datetime.now()
        finished_at = datetime.now()

        result = AgentResult(
            agent_name="Morning Research Agent",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            execution_time=0.25,
            confidence=0.95,
            summary="Research completed.",
            output={"ok": True},
            next_agent="Product Strategy Agent",
            warnings=("Local sample data only.",),
        )

        self.assertEqual(result.agent_name, "Morning Research Agent")
        self.assertEqual(result.status, SUCCESS)
        self.assertEqual(result.execution_time, 0.25)
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(result.next_agent, "Product Strategy Agent")
        self.assertEqual(result.warnings, ("Local sample data only.",))

    def test_successful_workflow_generates_ceo_briefing(self) -> None:
        orchestrator = WorkflowOrchestrator(logger=make_test_logger())

        briefing = orchestrator.run_day(
            morning_agent=MorningResearchAgent(logger=make_test_logger()),
            strategy_agent=ProductStrategyAgent(logger=make_test_logger()),
            paths=make_paths(),
        )

        self.assertEqual([result.status for result in orchestrator.results], [
            SUCCESS,
            SUCCESS,
            SUCCESS,
        ])
        self.assertIn("AURORA CEO DAILY BRIEFING", briefing)
        self.assertIn("Today's production plan has been finalized.", briefing)
        self.assertIn("Summer Strawberry Birthday Collection", briefing)
        self.assertIn("Workflow Timeline", briefing)
        self.assertIn("Prompt Factory Agent", briefing)

    def test_failed_workflow_stops_downstream_execution(self) -> None:
        orchestrator = WorkflowOrchestrator(logger=make_test_logger())

        briefing = orchestrator.run_day(
            morning_agent=FailingMorningResearchAgent(),  # type: ignore[arg-type]
            strategy_agent=ProductStrategyAgent(logger=make_test_logger()),
            paths=make_paths(),
        )

        self.assertEqual(len(orchestrator.results), 1)
        self.assertEqual(orchestrator.results[0].status, FAILED)
        self.assertIn("Morning Research Agent failed.", briefing)
        self.assertIn("Missing market data.", briefing)
        self.assertIn("Workflow stopped.", briefing)
        self.assertNotIn("Product Strategy Agent      ✓ Completed", briefing)

    def test_workflow_summary_generation(self) -> None:
        orchestrator = WorkflowOrchestrator(logger=make_test_logger())
        started_at = datetime.now()
        orchestrator._results = [  # noqa: SLF001 - focused unit test.
            AgentResult(
                agent_name="Morning Research Agent",
                status=SUCCESS,
                started_at=started_at,
                finished_at=started_at,
                execution_time=0.42,
                confidence=0.95,
                summary="Research completed.",
            ),
            AgentResult(
                agent_name="Product Strategy Agent",
                status=SUCCESS,
                started_at=started_at,
                finished_at=started_at,
                execution_time=0.18,
                confidence=0.93,
                summary="Strategy completed.",
            ),
        ]

        summary = orchestrator.generate_workflow_summary()

        self.assertIn("Workflow Summary", summary)
        self.assertIn("Morning Research Agent", summary)
        self.assertIn("0.42 sec", summary)
        self.assertIn("95%", summary)
        self.assertIn("Product Strategy Agent", summary)
        self.assertIn("0.18 sec", summary)
        self.assertIn("93%", summary)


if __name__ == "__main__":
    unittest.main()
