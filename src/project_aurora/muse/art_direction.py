"""Muse art direction result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ArtDirection:
    """Selected visual direction for a product."""

    product_name: str
    recommended_style: str
    confidence: int
    reason: str
    palette: str
    rendering_method: str
    composition: str
    mood: str
    trend_score: int
    portfolio_diversity: str
    alternative_styles: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("product_name cannot be empty.")
        if not self.recommended_style.strip():
            raise ValueError("recommended_style cannot be empty.")
        if not 0 <= self.confidence <= 100:
            raise ValueError("confidence must be between 0 and 100.")
        object.__setattr__(self, "alternative_styles", tuple(self.alternative_styles))

    @property
    def status(self) -> str:
        """Return style review status."""
        return "APPROVED" if self.confidence >= 70 else "REJECTED"
