"""Print registered Project Aurora platform agents."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.core.agent_registry import create_default_agent_registry


def main() -> None:
    """Print platform agents in a clean table."""
    logger = logging.getLogger("project_aurora.run")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)

    registry = create_default_agent_registry(logger=logger)
    agents = registry.list_all()

    headers = ("Name", "Department", "Status", "Role")
    rows = [
        (
            agent.name,
            agent.department,
            "enabled" if agent.enabled else "disabled",
            agent.role,
        )
        for agent in agents
    ]
    widths = [
        max(len(row[index]) for row in (headers, *rows))
        for index in range(len(headers))
    ]

    header_row = " | ".join(
        value.ljust(widths[index]) for index, value in enumerate(headers)
    )
    separator = "-+-".join("-" * width for width in widths)

    print(header_row)
    print(separator)
    for row in rows:
        print(
            " | ".join(
                value.ljust(widths[index])
                for index, value in enumerate(row)
            )
        )


if __name__ == "__main__":
    main()
