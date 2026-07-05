"""Custom exceptions for Project Aurora core components."""

from __future__ import annotations


class AgentRegistryError(Exception):
    """Base exception for agent registry failures."""


class AgentAlreadyRegisteredError(AgentRegistryError):
    """Raised when an agent name is registered more than once."""


class AgentNotFoundError(AgentRegistryError):
    """Raised when a requested agent does not exist in the registry."""
