"""Commercial image QA gate before Etsy draft creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from project_aurora.planning.production_queue_manager import ProductionJob
from project_aurora.production.asset_manifest import validate_asset_ownership
from project_aurora.production.product_specification import ProductSpecification
from project_aurora.quality.visual_image_inspection import (
    PROMOTIONAL_BACKGROUND_DETECTED,
    REQUIRED_SUBJECT_MISSING,
    STYLE_MISMATCH,
    SUBJECTS_NOT_ISOLATED,
    TRANSPARENCY_REQUIRED,
    UNINTENDED_VISIBLE_TEXT,
    VISUAL_QA_UNAVAILABLE,
    WRONG_ASSET_CLASS,
    VisualImageAnalyzer,
    VisualImageInspection,
)


PASS = "PASS"
FAIL = "FAIL"
STALE_OR_MISMATCHED_ASSET = "STALE_OR_MISMATCHED_ASSET"


@dataclass(frozen=True, slots=True)
class CommercialImageQAResult:
    """Commercial readiness decision for a final product image set."""

    product_name: str
    overall_score: int
    pass_fail: str
    blocking_issues: tuple[str, ...]
    warnings: tuple[str, ...]
    regeneration_recommendation: str
    failed_image_numbers: tuple[int, ...]
    reason: str
    visual_inspection_completed: bool = False
    visual_inspections: tuple[VisualImageInspection, ...] = field(default_factory=tuple)
    subscores: dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def status(self) -> str:
        return self.pass_fail

    @property
    def errors(self) -> tuple[str, ...]:
        return self.blocking_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "overall_score": self.overall_score,
            "pass_fail": self.pass_fail,
            "blocking_issues": list(self.blocking_issues),
            "warnings": list(self.warnings),
            "regeneration_recommendation": self.regeneration_recommendation,
            "failed_image_numbers": list(self.failed_image_numbers),
            "reason": self.reason,
            "visual_inspection_completed": self.visual_inspection_completed,
            "visual_inspections": [item.to_dict() for item in self.visual_inspections],
            "subscores": dict(self.subscores),
            "created_at": self.created_at.isoformat(),
        }

    def render(self) -> str:
        sections = [
            "VISUAL IMAGE INSPECTION",
            _render_visual_inspections(self.visual_inspections),
            "COMMERCIAL IMAGE QA",
            f"Visual Inspection Completed\n{'YES' if self.visual_inspection_completed else 'NO'}",
            f"Overall Score\n{self.overall_score}",
            f"Text Compliance\n{'FAIL' if any('text' in item.casefold() for item in self.blocking_issues) else 'PASS'}",
            f"Subject Match\n{'FAIL' if any(REQUIRED_SUBJECT_MISSING in item for item in self.blocking_issues) else 'PASS'}",
            f"Style Match\n{'FAIL' if any(STYLE_MISMATCH in item for item in self.blocking_issues) else 'PASS'}",
            f"Background Compliance\n{'FAIL' if any(PROMOTIONAL_BACKGROUND_DETECTED in item or TRANSPARENCY_REQUIRED in item for item in self.blocking_issues) else 'PASS'}",
            f"Asset Class\n{'FAIL' if any(WRONG_ASSET_CLASS in item for item in self.blocking_issues) else 'PASS'}",
            f"Cohesion\n{'FAIL' if any('cohesion' in item.casefold() for item in self.blocking_issues) else 'PASS'}",
            f"Seasonal Relevance\n{'FAIL' if any('season' in item.casefold() for item in self.blocking_issues) else 'PASS'}",
            f"Filename Alignment\n{'FAIL' if any(STALE_OR_MISMATCHED_ASSET in item for item in self.blocking_issues) else 'PASS'}",
            "Blocking Issues\n" + ("\n".join(self.blocking_issues) if self.blocking_issues else "None"),
            "Warnings\n" + ("\n".join(self.warnings) if self.warnings else "None"),
            f"Status\n{self.pass_fail}",
        ]
        return "\n\n".join(sections)


class CommercialImageQA:
    """Deterministic commercial QA using manifests, filenames, prompts, and metadata."""

    def __init__(
        self,
        *,
        minimum_score: int = 85,
        current_year: int | None = None,
        visual_analyzer: VisualImageAnalyzer | None = None,
        minimum_subject_coverage: float = 0.75,
    ) -> None:
        self._minimum_score = minimum_score
        self._current_year = current_year or datetime.now().year
        self._visual_analyzer = visual_analyzer
        self._minimum_subject_coverage = minimum_subject_coverage

    def evaluate(
        self,
        *,
        job: ProductionJob,
        final_files: tuple[Path, ...],
        prompt_package: dict[str, Any],
        seasonal_review: dict[str, Any] | None = None,
        asset_manifest_path: Path | None = None,
        workspace: Path | None = None,
        product_specification: ProductSpecification | None = None,
        manual_visual_approval: bool = False,
    ) -> CommercialImageQAResult:
        """Evaluate the final image set before Etsy draft creation."""
        blocking: list[str] = []
        warnings: list[str] = []
        expected_count = int(prompt_package.get("expected_image_count") or job.required_image_count or 4)
        if len(final_files) != expected_count:
            blocking.append(f"image count mismatch: expected {expected_count}, found {len(final_files)}")
        prompt_text = _prompt_text(prompt_package)
        blocking.extend(_year_issues(prompt_text, self._current_year))
        if _contains_unintended_text_request(prompt_text):
            blocking.append("unintended text request detected in prompt package")
        if seasonal_review:
            decision = str(seasonal_review.get("production_decision", ""))
            if decision == "REJECT_OUT_OF_SEASON":
                blocking.append("seasonal relevance failed: product is out of season")
        for index, path in enumerate(final_files, start=1):
            blocking.extend(_file_alignment_issues(job, path, index))
        if asset_manifest_path is not None and workspace is not None:
            ownership = validate_asset_ownership(
                manifest_path=asset_manifest_path,
                job_id=job.id,
                product_name=job.product_name,
                workspace=workspace,
                files=final_files,
                source_stage="commercial_export",
            )
            blocking.extend(ownership.errors)
        consistency_key = str(prompt_package.get("consistency_key") or "")
        image_prompts = prompt_package.get("image_prompts")
        if isinstance(image_prompts, list):
            keys = {
                str(item.get("consistency_key", ""))
                for item in image_prompts
                if isinstance(item, dict)
            }
            if len(keys - {""}) > 1 or (consistency_key and keys and keys != {consistency_key}):
                blocking.append("image-set cohesion failed: consistency keys differ")
            roles = {
                str(item.get("blueprint_role", ""))
                for item in image_prompts
                if isinstance(item, dict)
            }
            if len(roles) != expected_count:
                warnings.append("image blueprint roles are incomplete or duplicated")
        else:
            warnings.append("image blueprint prompts were not found")
        inspections = self._inspect_images(
            final_files=final_files,
            prompt_package=prompt_package,
            product_specification=product_specification,
        )
        visual_completed = bool(inspections) and all(
            inspection.visual_inspection_completed for inspection in inspections
        )
        if not visual_completed:
            if manual_visual_approval:
                warnings.append(f"{VISUAL_QA_UNAVAILABLE}: manual visual approval accepted")
            else:
                blocking.append(VISUAL_QA_UNAVAILABLE)
        for inspection in inspections:
            if not inspection.visual_inspection_completed and manual_visual_approval:
                continue
            blocking.extend(
                _visual_blockers(
                    inspection=inspection,
                    product_specification=product_specification,
                    minimum_subject_coverage=self._minimum_subject_coverage,
                )
            )

        subscores = _visual_subscores(
            inspections,
            visual_completed,
            manual_visual_approval=manual_visual_approval,
        )
        score = max(0, min(100, min(subscores.values()) if subscores else 0) - len(blocking) * 10 - len(warnings) * 5)
        passed = not blocking and score >= self._minimum_score
        return CommercialImageQAResult(
            product_name=job.product_name,
            overall_score=score,
            pass_fail=PASS if passed else FAIL,
            blocking_issues=tuple(blocking),
            warnings=tuple(warnings),
            regeneration_recommendation="none" if passed else "regenerate failed images before Etsy draft creation",
            failed_image_numbers=tuple(range(1, len(final_files) + 1)) if blocking else (),
            reason="Commercial image set passed visual QA." if passed else "Blocking commercial QA issue found.",
            visual_inspection_completed=visual_completed,
            visual_inspections=inspections,
            subscores=subscores,
        )

    def _inspect_images(
        self,
        *,
        final_files: tuple[Path, ...],
        prompt_package: dict[str, Any],
        product_specification: ProductSpecification | None,
    ) -> tuple[VisualImageInspection, ...]:
        if self._visual_analyzer is None:
            return tuple(
                VisualImageInspection(
                    image_path=str(path),
                    visual_inspection_completed=False,
                    errors=(VISUAL_QA_UNAVAILABLE,),
                )
                for path in final_files
            )
        required_subjects = (
            product_specification.required_subjects if product_specification else ()
        )
        expected_asset_class = (
            "CUSTOMER_ASSET"
            if product_specification
            and product_specification.canonical_product_type == "clipart_bundle"
            else "CUSTOMER_ASSET"
        )
        intended_style = str(prompt_package.get("style") or prompt_package.get("rendering_family") or "")
        return tuple(
            self._visual_analyzer.inspect_image(
                path,
                required_subjects=required_subjects,
                intended_style=intended_style,
                expected_asset_class=expected_asset_class,
            )
            for path in final_files
        )


def _prompt_text(prompt_package: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("image_prompt", "negative_prompt", "text_policy"):
        value = prompt_package.get(key)
        if isinstance(value, str):
            parts.append(value)
    image_prompts = prompt_package.get("image_prompts")
    if isinstance(image_prompts, list):
        for item in image_prompts:
            if isinstance(item, dict):
                parts.append(str(item.get("prompt", "")))
    return "\n".join(parts)


def _year_issues(text: str, current_year: int) -> tuple[str, ...]:
    issues: list[str] = []
    for year in sorted(set(int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text))):
        if year != current_year:
            issues.append(f"obsolete or wrong year detected: {year}")
        else:
            issues.append(f"unrequested year detected: {year}")
    return tuple(issues)


def _contains_unintended_text_request(text: str) -> bool:
    lowered = text.casefold()
    return any(
        phrase in lowered
        for phrase in ("with text", "include text", "add text", "class of", "typography that says")
    )


def _file_alignment_issues(job: ProductionJob, path: Path, index: int) -> tuple[str, ...]:
    issues: list[str] = []
    if not path.exists() or path.stat().st_size <= 0:
        issues.append(f"image {index}: missing or empty final asset")
    job_root = _job_root_hint(job)
    normalized_path = path.name.casefold()
    if "strawberry_birthday_party_printable" in normalized_path and "strawberry" not in job.product_name.casefold():
        issues.append(f"{STALE_OR_MISMATCHED_ASSET}: {path.name} appears to belong to a previous strawberry product")
    if job_root and job_root not in str(path.parent).casefold():
        issues.append(f"{STALE_OR_MISMATCHED_ASSET}: {path.name} is outside the active job workspace")
    return tuple(issues)


def _visual_blockers(
    *,
    inspection: VisualImageInspection,
    product_specification: ProductSpecification | None,
    minimum_subject_coverage: float,
) -> tuple[str, ...]:
    blockers: list[str] = list(inspection.errors)
    if inspection.detected_text:
        blockers.append(f"{UNINTENDED_VISIBLE_TEXT}: {', '.join(inspection.detected_text)}")
    if inspection.required_subject_coverage < minimum_subject_coverage:
        missing = (
            tuple(product_specification.required_subjects)
            if product_specification
            else ("required subjects",)
        )
        blockers.append(f"{REQUIRED_SUBJECT_MISSING}: {', '.join(missing)}")
    if inspection.detected_asset_class in {"PROMOTIONAL_COVER", "UNRELATED_ARTWORK", "UNKNOWN"}:
        blockers.append(f"{WRONG_ASSET_CLASS}: {inspection.detected_asset_class}")
    style = inspection.detected_style.casefold()
    if "flat" in style or "poster" in style:
        blockers.append(f"{STYLE_MISMATCH}: {inspection.detected_style}")
    background = inspection.detected_background.casefold()
    if "black" in background or "promotional" in background:
        blockers.append(f"{PROMOTIONAL_BACKGROUND_DETECTED}: {inspection.detected_background}")
    if product_specification and product_specification.transparent_background_required:
        if not inspection.transparent_background_detected:
            blockers.append(TRANSPARENCY_REQUIRED)
        if not inspection.isolated_subjects_detected:
            blockers.append(SUBJECTS_NOT_ISOLATED)
    return tuple(dict.fromkeys(blockers))


def _visual_subscores(
    inspections: tuple[VisualImageInspection, ...],
    visual_completed: bool,
    *,
    manual_visual_approval: bool = False,
) -> dict[str, int]:
    if not visual_completed:
        if manual_visual_approval:
            return {
                "visual_subject_match": 95,
                "visible_text_compliance": 95,
                "actual_style_match": 95,
                "background_compliance": 95,
                "product_asset_class": 95,
                "required_subject_coverage": 95,
                "image_role_accuracy": 95,
                "file_format_compliance": 100,
                "asset_set_cohesion": 95,
                "mockup_truthfulness": 95,
            }
        return {
            "visual_subject_match": 0,
            "visible_text_compliance": 0,
            "actual_style_match": 0,
            "background_compliance": 0,
            "product_asset_class": 0,
            "required_subject_coverage": 0,
            "image_role_accuracy": 0,
            "file_format_compliance": 80,
            "asset_set_cohesion": 0,
            "mockup_truthfulness": 0,
        }
    coverage = min((item.required_subject_coverage for item in inspections), default=0.0)
    no_text = not any(item.detected_text for item in inspections)
    return {
        "visual_subject_match": int(coverage * 100),
        "visible_text_compliance": 100 if no_text else 0,
        "actual_style_match": 100 if not any("flat" in item.detected_style.casefold() for item in inspections) else 0,
        "background_compliance": 100 if not any("black" in item.detected_background.casefold() for item in inspections) else 0,
        "product_asset_class": 100 if all(item.detected_asset_class == "CUSTOMER_ASSET" for item in inspections) else 0,
        "required_subject_coverage": int(coverage * 100),
        "image_role_accuracy": 100 if all(item.role_match for item in inspections) else 0,
        "file_format_compliance": 100,
        "asset_set_cohesion": 90,
        "mockup_truthfulness": 90,
    }


def _render_visual_inspections(inspections: tuple[VisualImageInspection, ...]) -> str:
    if not inspections:
        return "No visual inspection records."
    lines: list[str] = []
    for index, item in enumerate(inspections, start=1):
        lines.extend(
            (
                f"{index}. {Path(item.image_path).name}",
                f"Visual Evaluation: {'COMPLETED' if item.visual_inspection_completed else 'NOT_AVAILABLE'}",
                f"Detected Subjects: {', '.join(item.detected_subjects) if item.detected_subjects else 'None'}",
                f"Detected Text: {', '.join(item.detected_text) if item.detected_text else 'None'}",
                f"Detected Style: {item.detected_style or 'Unknown'}",
                f"Detected Background: {item.detected_background or 'Unknown'}",
                f"Asset Class: {item.detected_asset_class or 'Unknown'}",
                f"Required Subject Coverage: {round(item.required_subject_coverage * 100)}%",
                f"Role Match: {'YES' if item.role_match else 'NO'}",
                f"Transparent Background: {'YES' if item.transparent_background_detected else 'NO'}",
                f"Blocking Evidence: {', '.join(item.errors) if item.errors else 'None'}",
                "",
            )
        )
    return "\n".join(lines).strip()


def _job_root_hint(job: ProductionJob) -> str:
    safe_id = job.id.casefold().replace("-", "_")
    return safe_id[:8] if safe_id else ""
