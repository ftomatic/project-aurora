"""Image quality validation shared by generation components."""

from __future__ import annotations


SUPPORTED_OPENAI_IMAGE_QUALITIES = ("low", "medium", "high", "auto")
DEFAULT_OPENAI_IMAGE_QUALITY = "medium"


def validate_image_quality(quality: str) -> str:
    """Return normalized image quality or raise for unsupported values."""
    normalized = quality.casefold().strip()
    if normalized not in SUPPORTED_OPENAI_IMAGE_QUALITIES:
        supported = ", ".join(SUPPORTED_OPENAI_IMAGE_QUALITIES)
        raise ValueError(
            f"Unsupported OpenAI image quality: {quality}. "
            f"Supported values are: {supported}."
        )
    return normalized
