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


DEFAULT_QA_RULES: tuple[QARule, ...] = (
    FileExistsRule(),
    DuplicateFilenameRule(),
    NamingConventionRule(),
    MetadataPresentRule(),
    ResolutionRule(),
    ImageDimensionsRule(),
    TransparentBackgroundRule(),
)
