"""Structured market-driven style registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class MarketStyle:
    """A commercially scored style record."""

    style_id: str
    name: str
    rendering_family: str
    palette_guidance: str
    dominant_palette_family: str
    composition_guidance: str
    composition_template: str
    background_treatment: str
    texture_guidance: str
    texture_family: str
    lighting_guidance: str
    typography_guidance: str
    best_fit_categories: tuple[str, ...]
    avoid_categories: tuple[str, ...]
    commercial_appeal_score: int
    current_trend_score: int
    recent_use_penalty: int
    historical_performance_score: int
    prompt_directives: tuple[str, ...]
    negative_prompt_directives: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("style_id", "name", "rendering_family"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} cannot be empty.")
        object.__setattr__(self, "best_fit_categories", tuple(self.best_fit_categories))
        object.__setattr__(self, "avoid_categories", tuple(self.avoid_categories))
        object.__setattr__(self, "prompt_directives", tuple(self.prompt_directives))
        object.__setattr__(self, "negative_prompt_directives", tuple(self.negative_prompt_directives))


class StyleRegistry:
    """Load style records and category playbooks."""

    def __init__(
        self,
        styles: tuple[MarketStyle, ...],
        playbooks: dict[str, tuple[str, ...]],
    ) -> None:
        self._styles = styles
        self._playbooks = playbooks

    @classmethod
    def from_config(
        cls,
        registry_path: Path | None = None,
        playbook_path: Path | None = None,
    ) -> "StyleRegistry":
        """Load registry and playbooks from config/styles."""
        registry_path = registry_path or PROJECT_ROOT / "config" / "styles" / "style_registry.json"
        playbook_path = playbook_path or PROJECT_ROOT / "config" / "styles" / "category_playbooks.json"
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        playbook_data = json.loads(playbook_path.read_text(encoding="utf-8"))
        styles = tuple(_style_from_record(record) for record in registry_data["styles"])
        playbooks = {
            str(category): tuple(str(style_id) for style_id in style_ids)
            for category, style_ids in playbook_data["playbooks"].items()
        }
        return cls(styles, playbooks)

    @property
    def styles(self) -> tuple[MarketStyle, ...]:
        """Return styles."""
        return self._styles

    def get(self, style_id_or_name: str) -> MarketStyle:
        """Return a style by id or name."""
        normalized = style_id_or_name.casefold()
        for style in self._styles:
            if style.style_id.casefold() == normalized or style.name.casefold() == normalized:
                return style
        raise ValueError(f"Unknown style: {style_id_or_name}.")

    def playbook_for_category(self, category: str) -> tuple[MarketStyle, ...]:
        """Return ranked styles for the closest category playbook."""
        normalized = _normalize_category(category)
        style_ids = self._playbooks.get(normalized, ())
        if not style_ids:
            for key, values in self._playbooks.items():
                if key in normalized or normalized in key:
                    style_ids = values
                    break
        if not style_ids:
            style_ids = tuple(style.style_id for style in self._styles)
        return tuple(self.get(style_id) for style_id in style_ids)


def _style_from_record(record: dict[str, object]) -> MarketStyle:
    return MarketStyle(
        style_id=str(record["style_id"]),
        name=str(record["name"]),
        rendering_family=str(record["rendering_family"]),
        palette_guidance=str(record["palette_guidance"]),
        dominant_palette_family=str(record["dominant_palette_family"]),
        composition_guidance=str(record["composition_guidance"]),
        composition_template=str(record["composition_template"]),
        background_treatment=str(record["background_treatment"]),
        texture_guidance=str(record["texture_guidance"]),
        texture_family=str(record["texture_family"]),
        lighting_guidance=str(record["lighting_guidance"]),
        typography_guidance=str(record["typography_guidance"]),
        best_fit_categories=tuple(str(item) for item in record["best_fit_categories"]),  # type: ignore[index]
        avoid_categories=tuple(str(item) for item in record["avoid_categories"]),  # type: ignore[index]
        commercial_appeal_score=int(record["commercial_appeal_score"]),
        current_trend_score=int(record["current_trend_score"]),
        recent_use_penalty=int(record["recent_use_penalty"]),
        historical_performance_score=int(record["historical_performance_score"]),
        prompt_directives=tuple(str(item) for item in record["prompt_directives"]),  # type: ignore[index]
        negative_prompt_directives=tuple(str(item) for item in record["negative_prompt_directives"]),  # type: ignore[index]
    )


def _normalize_category(category: str) -> str:
    return " ".join(category.casefold().replace("-", " ").split())
