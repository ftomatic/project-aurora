"""Reusable creative prompt components."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptComponent:
    """A named reusable prompt component."""

    name: str
    phrases: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Component name cannot be empty.")
        if not self.phrases:
            raise ValueError("Component phrases cannot be empty.")
        object.__setattr__(self, "phrases", tuple(self.phrases))

    def render(self) -> str:
        """Return component phrases as prompt text."""
        return ", ".join(self.phrases)


@dataclass(frozen=True, slots=True)
class PromptComponents:
    """All reusable components needed to compose one recipe."""

    subject: PromptComponent
    character: PromptComponent
    style: PromptComponent
    color_palette: PromptComponent
    lighting: PromptComponent
    composition: PromptComponent
    background: PromptComponent
    rendering: PromptComponent
    commercial_requirements: PromptComponent
    consistency_rules: PromptComponent
    negative_prompt: PromptComponent
    provider_formatting: PromptComponent
