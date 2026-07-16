"""Rule framework for Aurora image QA."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AssetContext:
    """Context passed into every QA rule."""

    asset_path: Path
    all_asset_paths: tuple[Path, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Result from one QA rule."""

    rule_name: str
    passed: bool
    warning: bool = False
    message: str = ""
    confidence: int = 100
    rule_family: str = "technical"
    semantic_status: str = ""


class QARule(Protocol):
    """Protocol for pluggable QA rules."""

    name: str

    def evaluate(self, context: AssetContext) -> RuleResult:
        """Evaluate an asset and return a rule result."""


class FileExistsRule:
    """Ensure the generated file exists."""

    name = "File Exists"

    def evaluate(self, context: AssetContext) -> RuleResult:
        exists = context.asset_path.exists()
        return RuleResult(
            rule_name=self.name,
            passed=exists,
            message="File is present." if exists else "File is missing.",
            confidence=100 if exists else 0,
        )


class DuplicateFilenameRule:
    """Warn when duplicate filenames are present in a batch."""

    name = "Duplicate Filename"

    def evaluate(self, context: AssetContext) -> RuleResult:
        names = [path.name for path in context.all_asset_paths]
        duplicate = names.count(context.asset_path.name) > 1
        return RuleResult(
            rule_name=self.name,
            passed=not duplicate,
            warning=duplicate,
            confidence=70 if duplicate else 100,
            message=(
                "Filename is unique."
                if not duplicate
                else "Duplicate filename detected."
            ),
        )


class NamingConventionRule:
    """Ensure generated files follow Aurora naming conventions."""

    name = "Naming Convention"
    _pattern = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*_\d{2}\.png$")

    def evaluate(self, context: AssetContext) -> RuleResult:
        valid = bool(self._pattern.match(context.asset_path.name))
        return RuleResult(
            rule_name=self.name,
            passed=valid,
            warning=not valid,
            confidence=70 if not valid else 100,
            message=(
                "Filename follows Aurora convention."
                if valid
                else "Filename should be lowercase snake_case ending in _NN.png."
            ),
        )


class ResolutionRule:
    """Ensure resolution metadata is present and production-ready."""

    name = "Resolution"

    def evaluate(self, context: AssetContext) -> RuleResult:
        dpi = context.metadata.get("dpi")
        passed = isinstance(dpi, int) and dpi >= 300
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            warning=not passed,
            confidence=70 if not passed else 100,
            message=(
                "DPI metadata is production-ready."
                if passed
                else "DPI metadata is missing or below 300."
            ),
        )


class ImageDimensionsRule:
    """Ensure dimension metadata meets minimum production dimensions."""

    name = "Image Dimensions"

    def evaluate(self, context: AssetContext) -> RuleResult:
        width = context.metadata.get("width")
        height = context.metadata.get("height")
        passed = (
            isinstance(width, int)
            and isinstance(height, int)
            and width >= 2000
            and height >= 2000
        )
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            warning=not passed,
            confidence=70 if not passed else 100,
            message=(
                "Image dimensions are production-ready."
                if passed
                else "Image dimensions are missing or below 2000px."
            ),
        )


class TransparentBackgroundRule:
    """Ensure transparent-background intent is recorded."""

    name = "Transparent Background"

    def evaluate(self, context: AssetContext) -> RuleResult:
        transparent = context.metadata.get("transparent_background")
        passed = transparent is True
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            warning=not passed,
            confidence=70 if not passed else 100,
            message=(
                "Transparent background metadata is present."
                if passed
                else "Transparent background metadata is missing or false."
            ),
        )


class MetadataPresentRule:
    """Ensure provider metadata includes required keys."""

    name = "Metadata Present"
    _required_keys = frozenset(
        {"image_count", "image_type", "width", "height", "dpi"}
    )

    def evaluate(self, context: AssetContext) -> RuleResult:
        missing = sorted(self._required_keys - context.metadata.keys())
        passed = not missing
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            warning=not passed,
            confidence=70 if not passed else 100,
            message=(
                "Required metadata is present."
                if passed
                else f"Missing metadata: {', '.join(missing)}."
            ),
        )


class StyleMatchRule:
    """Evaluate style only when visual semantic evidence is present."""

    name = "Style Match"
    evidence_key = "style"
    expectation_key = "expected_style"

    def evaluate(self, context: AssetContext) -> RuleResult:
        return _semantic_rule_result(self.name, self.evidence_key, self.expectation_key, context)


class PaletteMatchRule:
    """Evaluate palette only when visual semantic evidence is present."""

    name = "Palette Match"
    evidence_key = "palette"
    expectation_key = "expected_palette"

    def evaluate(self, context: AssetContext) -> RuleResult:
        return _semantic_rule_result(self.name, self.evidence_key, self.expectation_key, context)


class CompositionMatchRule:
    """Evaluate composition only when visual semantic evidence is present."""

    name = "Composition Match"
    evidence_key = "composition"
    expectation_key = "expected_composition"

    def evaluate(self, context: AssetContext) -> RuleResult:
        return _semantic_rule_result(self.name, self.evidence_key, self.expectation_key, context)


class RenderingConsistencyRule:
    """Evaluate rendering only when visual semantic evidence is present."""

    name = "Rendering Consistency"
    evidence_key = "rendering_family"
    expectation_key = "expected_rendering"

    def evaluate(self, context: AssetContext) -> RuleResult:
        return _semantic_rule_result(self.name, self.evidence_key, self.expectation_key, context)


class BackgroundTreatmentRule:
    """Evaluate background only when visual semantic evidence is present."""

    name = "Background Treatment"
    evidence_key = "background"
    expectation_key = "expected_background_treatment"

    def evaluate(self, context: AssetContext) -> RuleResult:
        return _semantic_rule_result(self.name, self.evidence_key, self.expectation_key, context)


class ProductTypeSuitabilityRule:
    """Evaluate product suitability only when visual semantic evidence is present."""

    name = "Product Type Suitability"
    evidence_key = "product_type_suitability"
    expectation_key = "expected_product_type"

    def evaluate(self, context: AssetContext) -> RuleResult:
        return _semantic_rule_result(self.name, self.evidence_key, self.expectation_key, context)


def _semantic_rule_result(
    rule_name: str,
    evidence_key: str,
    expectation_key: str,
    context: AssetContext,
) -> RuleResult:
    if not str(context.metadata.get(expectation_key, "")).strip():
        return RuleResult(
            rule_name=rule_name,
            passed=True,
            message=f"{rule_name} skipped: no configured expectation.",
            confidence=0,
            rule_family="style",
            semantic_status="NO_EXPECTATION",
        )
    evaluation = context.metadata.get("visual_semantic_evaluation")
    if not isinstance(evaluation, dict):
        return RuleResult(
            rule_name=rule_name,
            passed=True,
            warning=True,
            message=(
                f"{rule_name} NOT_EVALUATED: no visual semantic evaluator "
                "result is available."
            ),
            confidence=0,
            rule_family="style",
            semantic_status="NOT_EVALUATED",
        )
    record = evaluation.get(evidence_key)
    if not isinstance(record, dict):
        return RuleResult(
            rule_name=rule_name,
            passed=True,
            warning=True,
            message=f"{rule_name} NOT_EVALUATED: visual evaluator did not score this criterion.",
            confidence=0,
            rule_family="style",
            semantic_status="NOT_EVALUATED",
        )
    status = str(record.get("status", "NOT_EVALUATED")).upper()
    score = int(record.get("score", 0) or 0)
    reason = str(record.get("reason", "")).strip()
    if status == "PASS":
        return RuleResult(
            rule_name=rule_name,
            passed=True,
            message=reason or f"{rule_name} passed visual semantic evaluation.",
            confidence=score,
            rule_family="style",
            semantic_status="PASS",
        )
    if status == "FAIL":
        return RuleResult(
            rule_name=rule_name,
            passed=False,
            message=reason or f"{rule_name} failed visual semantic evaluation.",
            confidence=score,
            rule_family="style",
            semantic_status="FAIL",
        )
    return RuleResult(
        rule_name=rule_name,
        passed=True,
        warning=True,
        message=reason or f"{rule_name} NOT_EVALUATED by visual semantic evaluator.",
        confidence=score,
        rule_family="style",
        semantic_status="NOT_EVALUATED",
    )


DEFAULT_QA_RULES: tuple[QARule, ...] = (
    FileExistsRule(),
    DuplicateFilenameRule(),
    NamingConventionRule(),
    MetadataPresentRule(),
    ResolutionRule(),
    ImageDimensionsRule(),
    TransparentBackgroundRule(),
    StyleMatchRule(),
    PaletteMatchRule(),
    CompositionMatchRule(),
    RenderingConsistencyRule(),
    BackgroundTreatmentRule(),
    ProductTypeSuitabilityRule(),
)
