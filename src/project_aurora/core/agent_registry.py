"""Reusable in-memory registry for Project Aurora agents."""

from __future__ import annotations

from collections.abc import Iterable
from logging import Logger

from project_aurora.core.constants import DEFAULT_PLATFORM_AGENTS
from project_aurora.core.exceptions import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
)
from project_aurora.core.logger import get_logger
from project_aurora.core.models import AgentDefinition


class AgentRegistry:
    """Register, retrieve, list, enable, and disable Aurora agents."""

    def __init__(
        self,
        agents: Iterable[AgentDefinition] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        self._logger = logger or get_logger(__name__)

        if agents is not None:
            for agent in agents:
                self.register(agent)

    def register(self, agent: AgentDefinition) -> AgentDefinition:
        """Register an agent and return the stored definition."""
        key = self._key(agent.name)
        if key in self._agents:
            self._logger.warning("Duplicate agent registration blocked: %s", key)
            raise AgentAlreadyRegisteredError(
                f"Agent '{agent.name}' is already registered."
            )

        self._agents[key] = agent
        self._logger.info("Registered agent: %s", agent.name)
        return agent

    def get(self, name: str) -> AgentDefinition:
        """Return an agent by name."""
        key = self._key(name)
        try:
            agent = self._agents[key]
        except KeyError as error:
            self._logger.warning("Agent lookup failed: %s", key)
            raise AgentNotFoundError(
                f"Agent '{name}' is not registered."
            ) from error

        self._logger.info("Retrieved agent: %s", agent.name)
        return agent

    def list_all(self) -> tuple[AgentDefinition, ...]:
        """Return all registered agents sorted by name."""
        agents = tuple(
            self._agents[key] for key in sorted(self._agents)
        )
        self._logger.info("Listed %s registered agents", len(agents))
        return agents

    def enable(self, name: str) -> AgentDefinition:
        """Enable an agent and return its updated definition."""
        agent = self.get(name)
        updated_agent = agent.with_enabled(True)
        self._agents[self._key(name)] = updated_agent
        self._logger.info("Enabled agent: %s", updated_agent.name)
        return updated_agent

    def disable(self, name: str) -> AgentDefinition:
        """Disable an agent and return its updated definition."""
        agent = self.get(name)
        updated_agent = agent.with_enabled(False)
        self._agents[self._key(name)] = updated_agent
        self._logger.info("Disabled agent: %s", updated_agent.name)
        return updated_agent

    @staticmethod
    def _key(name: str) -> str:
        key = name.strip().casefold()
        if not key:
            raise AgentNotFoundError("Agent name cannot be empty.")
        return key


def create_default_agent_registry(logger: Logger | None = None) -> AgentRegistry:
    """Return a registry populated with Aurora platform agents."""
    agents = (
        AgentDefinition(
            name=str(agent["name"]),
            description=str(agent["description"]),
            department=str(agent["department"]),
            role=str(agent["role"]),
            enabled=bool(agent["enabled"]),
        )
        for agent in DEFAULT_PLATFORM_AGENTS
    )
    return AgentRegistry(agents=agents, logger=logger)
