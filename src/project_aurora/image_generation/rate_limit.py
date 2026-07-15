"""OpenAI image rate-limit retry helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from time import sleep
from typing import Callable


@dataclass(frozen=True, slots=True)
class OpenAIRateLimitConfig:
    """OpenAI image retry/backoff configuration."""

    max_retries: int = 3
    safety_seconds: float = 3.0
    base_delay_seconds: float = 15.0


def is_rate_limit_error(error: BaseException) -> bool:
    """Return whether an exception looks like an OpenAI 429 rate limit."""
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True
    message = str(error).casefold()
    return "429" in message or "rate_limit" in message or "rate limit" in message


def retry_after_seconds(message: str) -> float | None:
    """Parse retry timing from an OpenAI error message."""
    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", message, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"retry-after[:=]\s*([0-9]+(?:\.[0-9]+)?)", message, re.I)
    if match:
        return float(match.group(1))
    return None


def rate_limit_delay_seconds(
    error: BaseException,
    attempt: int,
    config: OpenAIRateLimitConfig,
) -> float:
    """Return delay for a rate-limit retry attempt."""
    parsed = retry_after_seconds(str(error))
    if parsed is not None:
        return parsed + config.safety_seconds
    return config.base_delay_seconds * (2 ** max(attempt - 1, 0)) + config.safety_seconds


def sleep_for_rate_limit(
    seconds: float,
    sleeper: Callable[[float], None] = sleep,
) -> None:
    """Sleep for rate-limit recovery when a positive delay is configured."""
    if seconds > 0:
        sleeper(seconds)
