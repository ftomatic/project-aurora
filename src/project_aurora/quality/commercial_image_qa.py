"""Commercial image QA gate before Etsy draft creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from project_aurora.planning.production_queue_manager import ProductionJob


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
            "created_at": self.created_at.isoformat(),
        }

    def render(self) -> str:
        return "\n\n".join(
            (
                "COMMERCIAL IMAGE QA",
                f"Overall Score\n{self.overall_score}",
                f"Text Compliance\n{'FAIL' if any('text' in item.casefold() for item in self.blocking_issues) else 'PASS'}",
                f"Cohesion\n{'FAIL' if any('cohesion' in item.casefold() for item in self.blocking_issues) else 'PASS'}",
                f"Seasonal Relevance\n{'FAIL' if any('season' in item.casefold() for item in self.blocking_issues) else 'PASS'}",
                f"Filename Alignment\n{'FAIL' if any(STALE_OR_MISMATCHED_ASSET in item for item in self.blocking_issues) else 'PASS'}",
                "Blocking Issues\n" + ("\n".join(self.blocking_issues) if self.blocking_issues else "None"),
                f"Status\n{self.pass_fail}",
            )
        )


class CommercialImageQA:
    """Deterministic commercial QA using manifests, filenames, prompts, and metadata."""

    def __init__(
        self,
        *,
        minimum_score: int = 85,
        current_year: int | None = None,
    ) -> None:
        self._minimum_score = minimum_score
        self._current_year = current_year or datetime.now().year

    def evaluate(
        self,
        *,
        job: ProductionJob,
        final_files: tuple[Path, ...],
        prompt_package: dict[str, Any],
        seasonal_review: dict[str, Any] | None = None,
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

        score = max(0, 100 - len(blocking) * 25 - len(warnings) * 5)
        passed = not blocking and score >= self._minimum_score
        return CommercialImageQAResult(
            product_name=job.product_name,
            overall_score=score,
            pass_fail=PASS if passed else FAIL,
            blocking_issues=tuple(blocking),
            warnings=tuple(warnings),
            regeneration_recommendation="none" if passed else "regenerate failed images before Etsy draft creation",
            failed_image_numbers=tuple(range(1, len(final_files) + 1)) if blocking else (),
            reason="Commercial image set passed deterministic QA." if passed else "Blocking commercial QA issue found.",
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


def _job_root_hint(job: ProductionJob) -> str:
    safe_id = job.id.casefold().replace("-", "_")
    return safe_id[:8] if safe_id else ""
