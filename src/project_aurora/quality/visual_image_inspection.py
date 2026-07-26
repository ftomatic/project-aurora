"""Visual image inspection contracts for commercial QA."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


VISUAL_QA_UNAVAILABLE = "VISUAL_QA_UNAVAILABLE"
UNINTENDED_VISIBLE_TEXT = "UNINTENDED_VISIBLE_TEXT"
REQUIRED_SUBJECT_MISSING = "REQUIRED_SUBJECT_MISSING"
WRONG_ASSET_CLASS = "WRONG_ASSET_CLASS"
STYLE_MISMATCH = "STYLE_MISMATCH"
TRANSPARENCY_REQUIRED = "TRANSPARENCY_REQUIRED"
PROMOTIONAL_BACKGROUND_DETECTED = "PROMOTIONAL_BACKGROUND_DETECTED"
SUBJECTS_NOT_ISOLATED = "SUBJECTS_NOT_ISOLATED"


@dataclass(frozen=True, slots=True)
class VisualImageInspection:
    """Structured description from actual image inspection."""

    image_path: str
    visual_inspection_completed: bool
    detected_subjects: tuple[str, ...] = field(default_factory=tuple)
    detected_text: tuple[str, ...] = field(default_factory=tuple)
    detected_style: str = "UNKNOWN"
    detected_background: str = "UNKNOWN"
    detected_asset_class: str = "UNKNOWN"
    required_subject_coverage: float = 0.0
    role_match: bool = False
    transparent_background_detected: bool = False
    isolated_subjects_detected: bool = False
    forbidden_objects_detected: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe inspection data."""
        return {
            "image_path": self.image_path,
            "visual_inspection_completed": self.visual_inspection_completed,
            "detected_subjects": list(self.detected_subjects),
            "detected_text": list(self.detected_text),
            "detected_style": self.detected_style,
            "detected_background": self.detected_background,
            "detected_asset_class": self.detected_asset_class,
            "required_subject_coverage": self.required_subject_coverage,
            "role_match": self.role_match,
            "transparent_background_detected": self.transparent_background_detected,
            "isolated_subjects_detected": self.isolated_subjects_detected,
            "forbidden_objects_detected": list(self.forbidden_objects_detected),
            "errors": list(self.errors),
        }


class VisualImageAnalyzer(Protocol):
    """Provider interface for real image visual analysis."""

    def inspect_image(
        self,
        image_path: Path,
        *,
        required_subjects: tuple[str, ...],
        intended_style: str,
        expected_asset_class: str,
    ) -> VisualImageInspection:
        """Inspect an actual image file and return structured evidence."""
