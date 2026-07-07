"""Prompt Factory 2.0 recipe model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PromptRecipe:
    """A professional reusable prompt recipe."""

    subject: str
    character: str
    style: str
    color_palette: str
    lighting: str
    composition: str
    background: str
    rendering: str
    commercial_requirements: str
    consistency_rules: str
    negative_prompt: str
    provider_formatting: str
    final_prompt: str
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        required_values = {
            "subject": self.subject,
            "character": self.character,
            "style": self.style,
            "color_palette": self.color_palette,
            "lighting": self.lighting,
            "composition": self.composition,
            "background": self.background,
            "rendering": self.rendering,
            "commercial_requirements": self.commercial_requirements,
            "consistency_rules": self.consistency_rules,
            "negative_prompt": self.negative_prompt,
            "provider_formatting": self.provider_formatting,
            "final_prompt": self.final_prompt,
        }
        for field_name, value in required_values.items():
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
