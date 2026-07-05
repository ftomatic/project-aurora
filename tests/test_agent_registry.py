"""Tests for the Project Aurora agent registry."""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.core.agent_registry import (  # noqa: E402
    AgentRegistry,
    create_default_agent_registry,
)
from project_aurora.core.exceptions import (  # noqa: E402
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
)
from project_aurora.core.models import AgentDefinition  # noqa: E402


def make_registry() -> AgentRegistry:
    return AgentRegistry(logger=make_test_logger())


def make_test_logger() -> logging.Logger:
    logger = logging.getLogger("test_agent_registry")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


class AgentRegistryTest(unittest.TestCase):
    def test_register_and_get_agent_by_name(self) -> None:
        registry = make_registry()
        agent = AgentDefinition(
            name="Planner",
            description="Coordinates task planning.",
        )

        registry.register(agent)

        self.assertEqual(registry.get("planner"), agent)

    def test_register_prevents_duplicate_names(self) -> None:
        registry = make_registry()
        registry.register(
            AgentDefinition(
                name="planner",
                description="Coordinates task planning.",
            )
        )

        with self.assertRaises(AgentAlreadyRegisteredError) as context:
            registry.register(
                AgentDefinition(
                    name="PLANNER",
                    description="Duplicate task planner.",
                )
            )

        self.assertIn("already registered", str(context.exception))

    def test_get_unknown_agent_raises_meaningful_exception(self) -> None:
        registry = make_registry()

        with self.assertRaises(AgentNotFoundError) as context:
            registry.get("missing")

        self.assertIn("missing", str(context.exception))

    def test_list_all_returns_agents_sorted_by_name(self) -> None:
        registry = make_registry()
        registry.register(
            AgentDefinition(name="operator", description="Runs tasks.")
        )
        registry.register(
            AgentDefinition(name="planner", description="Plans tasks.")
        )

        agents = registry.list_all()

        self.assertEqual(
            [agent.name for agent in agents],
            ["operator", "planner"],
        )

    def test_enable_and_disable_agent(self) -> None:
        registry = make_registry()
        registry.register(
            AgentDefinition(name="operator", description="Runs tasks.")
        )

        disabled = registry.disable("operator")
        enabled = registry.enable("operator")

        self.assertIs(disabled.enabled, False)
        self.assertIs(enabled.enabled, True)
        self.assertIs(registry.get("operator").enabled, True)

    def test_enable_unknown_agent_raises_meaningful_exception(self) -> None:
        registry = make_registry()

        with self.assertRaises(AgentNotFoundError):
            registry.enable("missing")

    def test_default_registry_contains_platform_agents(self) -> None:
        registry = create_default_agent_registry(logger=make_test_logger())

        self.assertEqual(
            [agent.name for agent in registry.list_all()],
            [
                "ChiefArchitect",
                "ConfigurationManager",
                "EtsyAPIAgent",
                "FileProcessingAgent",
                "ImageGenerationAgent",
                "ImageQAAgent",
                "LoggingAgent",
                "MarketingAgent",
                "MockupAgent",
                "ProductOwner",
                "ProductStrategyAgent",
                "PromptFactoryAgent",
                "ReviewQueueAgent",
                "SEOAgent",
                "TrendResearchAgent",
            ],
        )

    def test_default_platform_agents_include_department_and_role(self) -> None:
        registry = create_default_agent_registry(logger=make_test_logger())

        for agent in registry.list_all():
            self.assertTrue(agent.department)
            self.assertTrue(agent.role)
            self.assertTrue(agent.description)


if __name__ == "__main__":
    unittest.main()
