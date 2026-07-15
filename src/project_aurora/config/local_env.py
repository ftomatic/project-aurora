"""Safe local environment loading for Aurora scheduled scripts."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(path: Path) -> tuple[str, ...]:
    """Load KEY=VALUE pairs into the process environment without printing values."""
    if not path.exists():
        return ()
    loaded: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key:
            continue
        os.environ.setdefault(key, value)
        loaded.append(key)
    return tuple(loaded)
