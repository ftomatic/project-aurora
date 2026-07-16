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
            message=(
                "Required metadata is present."
                if passed
                else f"Missing metadata: {', '.join(missing)}."
            ),
        )


class StyleMatchRule:
    """Ensure generated metadata matches the chosen Muse style."""

    name = "Style Match"

    def evaluate(self, context: AssetContext) -> RuleResult:
        expected = context.metadata.get("expected_style")
        actual = context.metadata.get("style")
        if expected is None:
            return RuleResult(self.name, True, message="No style expectation provided.")
        passed = str(actual).casefold() == str(expected).casefold()
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            message="Image metadata matches chosen style." if passed else "Image metadata does not match chosen style.",
        )


class PaletteMatchRule:
    """Ensure generated metadata matches the chosen palette."""

    name = "Palette Match"

    def evaluate(self, context: AssetContext) -> RuleResult:
        expected = context.metadata.get("expected_palette")
        actual = context.metadata.get("palette")
        if expected is None:
            return RuleResult(self.name, True, message="No palette expectation provided.")
        passed = str(expected).casefold() in str(actual).casefold()
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            message="Image metadata matches chosen palette." if passed else "Image metadata does not match chosen palette.",
        )


class CompositionMatchRule:
    """Ensure generated metadata matches the chosen composition."""

    name = "Composition Match"

    def evaluate(self, context: AssetContext) -> RuleResult:
        expected = context.metadata.get("expected_composition")
        actual = context.metadata.get("composition")
        if expected is None:
            return RuleResult(self.name, True, message="No composition expectation provided.")
        passed = str(expected).casefold() in str(actual).casefold()
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            message="Image metadata matches chosen composition." if passed else "Image metadata does not match chosen composition.",
        )


class RenderingConsistencyRule:
    """Ensure generated metadata matches the chosen rendering method."""

    name = "Rendering Consistency"

    def evaluate(self, context: AssetContext) -> RuleResult:
        expected = context.metadata.get("expected_rendering")
        actual = context.metadata.get("rendering")
        if expected is None:
            return RuleResult(self.name, True, message="No rendering expectation provided.")
        passed = str(expected).casefold() in str(actual).casefold()
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            message="Image metadata matches chosen rendering." if passed else "Image metadata does not match chosen rendering.",
        )


class BackgroundTreatmentRule:
    """Ensure generated metadata matches the chosen background treatment."""

    name = "Background Treatment"

    def evaluate(self, context: AssetContext) -> RuleResult:
        expected = context.metadata.get("expected_background_treatment")
        actual = context.metadata.get("background_treatment")
        if expected is None or expected == "":
            return RuleResult(self.name, True, message="No background expectation provided.")
        passed = str(expected).casefold() in str(actual).casefold()
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            message="Image metadata matches chosen background." if passed else "Image metadata does not match chosen background.",
        )


class ProductTypeSuitabilityRule:
    """Ensure composition metadata is suitable for product type."""

    name = "Product Type Suitability"

    def evaluate(self, context: AssetContext) -> RuleResult:
        product_type = str(context.metadata.get("expected_product_type", "")).casefold()
        composition = str(context.metadata.get("composition", "")).casefold()
        background = str(context.metadata.get("background_treatment", "")).casefold()
        if not product_type:
            return RuleResult(self.name, True, message="No product type expectation provided.")
        if "digital paper" in product_type:
            passed = "pattern" in composition or "tile" in composition or "seamless" in composition
            message = "Digital paper is pattern-like." if passed else "Digital paper is not tileable/pattern-like."
        elif "clipart" in product_type:
            passed = ("isolated" in composition or "elements" in composition) and "room mockup" not in background
            message = "Clipart uses isolated elements." if passed else "Clipart is not presented as isolated elements."
        elif "wall art" in product_type:
            passed = "isolated clipart" not in composition
            message = "Wall art composition is suitable." if passed else "Wall art is presented only as isolated clipart."
        elif "sticker" in product_type:
            passed = "sticker" in composition or "grid" in composition or "cluster" in composition
            message = "Sticker sheet composition is suitable." if passed else "Sticker sheet lacks grid/cluster layout."
        elif "invitation" in product_type:
            passed = "invitation" in composition or "layout" in composition or "typography" in composition
            message = "Invitation layout is suitable." if passed else "Invitation lacks layout/typography hierarchy."
        else:
            passed = True
            message = "Product type has no specific suitability rule."
        return RuleResult(rule_name=self.name, passed=passed, message=message)


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
