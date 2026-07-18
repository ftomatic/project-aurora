"""Creative QA and scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from project_aurora.creative.creative_brief import CreativeBrief
from project_aurora.creative.prompt_blocks import CreativePrompt


@dataclass(frozen=True, slots=True)
class CreativeQAResult:
    """Creative QA decision."""

    status: str
    checks_passed: tuple[str, ...]
    checks_failed: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks_passed": list(self.checks_passed),
            "checks_failed": list(self.checks_failed),
            "warnings": list(self.warnings),
        }


class CreativeQAEngine:
    """Validate creative direction before image generation."""

    def evaluate(
        self,
        *,
        brief: CreativeBrief,
        prompt: CreativePrompt,
        collection_briefs: tuple[CreativeBrief, ...] = (),
    ) -> CreativeQAResult:
        passed: list[str] = []
        failed: list[str] = []
        _check(
            bool(brief.illustration_style.strip()),
            "style consistency",
            passed,
            failed,
        )
        _check(
            all(
                value.strip()
                for value in (
                    brief.color_palette.primary,
                    brief.color_palette.secondary,
                    brief.color_palette.accent,
                    brief.color_palette.neutral,
                    brief.color_palette.background,
                )
            ),
            "palette consistency",
            passed,
            failed,
        )
        _check(
            brief.creative_score.commercial_appeal >= 75,
            "commercial appeal",
            passed,
            failed,
        )
        _check(
            _collection_consistent(brief, collection_briefs),
            "collection consistency",
            passed,
            failed,
        )
        _check(
            _prompt_complete(prompt),
            "prompt completeness",
            passed,
            failed,
        )
        return CreativeQAResult(
            status="PASS" if not failed else "FAIL",
            checks_passed=tuple(passed),
            checks_failed=tuple(failed),
        )


def _check(condition: bool, label: str, passed: list[str], failed: list[str]) -> None:
    if condition:
        passed.append(label)
    else:
        failed.append(label)


def _collection_consistent(
    brief: CreativeBrief,
    collection_briefs: tuple[CreativeBrief, ...],
) -> bool:
    if not collection_briefs:
        return True
    anchor = collection_briefs[0]
    return (
        brief.collection_name == anchor.collection_name
        and brief.illustration_style == anchor.illustration_style
        and brief.lighting_style == anchor.lighting_style
        and brief.color_palette.primary == anchor.color_palette.primary
        and brief.color_palette.background == anchor.color_palette.background
    )


def _prompt_complete(prompt: CreativePrompt) -> bool:
    values = (
        prompt.subject,
        prompt.style,
        prompt.composition,
        prompt.color,
        prompt.texture,
        prompt.quality,
        prompt.commercial_requirements,
        prompt.negative_prompt,
    )
    return all(value.strip() for value in values)
