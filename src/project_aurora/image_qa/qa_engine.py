"""Aurora image quality assurance engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from project_aurora.image_qa.qa_result import (
    APPROVE,
    FAIL,
    MANUAL_REVIEW,
    PASS,
    REGENERATE,
    WARNING,
    QAResult,
)
from project_aurora.image_qa.qa_rules import (
    DEFAULT_QA_RULES,
    AssetContext,
    QARule,
    RuleResult,
)
from project_aurora.storage.memory_manager import MemoryManager


class ImageQAEngine:
    """Evaluate generated image assets with deterministic QA rules."""

    def __init__(
        self,
        memory: MemoryManager,
        rules: tuple[QARule, ...] | None = None,
    ) -> None:
        self._memory = memory
        self._rules = rules or DEFAULT_QA_RULES

    def run(self, image_result_id: str = "latest") -> tuple[QAResult, ...]:
        """Load generated image assets, evaluate them, and save QA results."""
        image_result = self._memory.load_image_result(image_result_id)
        results = self.evaluate_image_result(image_result)
        self._memory.save_image_qa_results(results)
        findings = self.evaluate_image_findings(image_result)
        self._memory.save_record("image_qa_findings", image_result_id, {"findings": findings})
        self._memory.save_record("image_qa_findings", "latest", {"findings": findings})
        return results

    def evaluate_image_result(
        self,
        image_result: dict[str, Any],
    ) -> tuple[QAResult, ...]:
        """Evaluate all assets in a stored image generation result."""
        generated_files = image_result.get("generated_files")
        if not isinstance(generated_files, list):
            raise ValueError("Image result does not include generated files.")

        metadata = image_result.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        asset_paths = tuple(Path(str(path)) for path in generated_files)
        return tuple(
            self.evaluate_asset(
                asset_path=asset_path,
                all_asset_paths=asset_paths,
                metadata=metadata,
            )
            for asset_path in asset_paths
        )

    def evaluate_asset(
        self,
        asset_path: Path,
        all_asset_paths: tuple[Path, ...],
        metadata: dict[str, Any],
    ) -> QAResult:
        """Evaluate one image asset and return a QA result."""
        context = AssetContext(
            asset_path=asset_path,
            all_asset_paths=all_asset_paths,
            metadata=metadata,
        )
        rule_results = tuple(rule.evaluate(context) for rule in self._rules)
        return self._build_result(asset_path, rule_results)

    def evaluate_image_findings(
        self,
        image_result: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        """Return structured QA findings for every generated asset."""
        generated_files = image_result.get("generated_files")
        if not isinstance(generated_files, list):
            raise ValueError("Image result does not include generated files.")

        metadata = image_result.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        asset_paths = tuple(Path(str(path)) for path in generated_files)
        findings: list[dict[str, Any]] = []
        for asset_path in asset_paths:
            context = AssetContext(
                asset_path=asset_path,
                all_asset_paths=asset_paths,
                metadata=metadata,
            )
            rule_results = tuple(rule.evaluate(context) for rule in self._rules)
            findings.append(_structured_finding(asset_path, metadata, rule_results))
        return tuple(findings)

    @staticmethod
    def _build_result(
        asset_path: Path,
        rule_results: tuple[RuleResult, ...],
    ) -> QAResult:
        checks_passed = tuple(
            result.rule_name
            for result in rule_results
            if result.passed
        )
        checks_failed = tuple(
            result.rule_name
            for result in rule_results
            if not result.passed and not result.warning
        )
        warnings = tuple(
            result.message
            for result in rule_results
            if result.warning and result.message
        )

        if checks_failed:
            status = FAIL
            action = REGENERATE
            review_required = True
        elif warnings:
            status = WARNING
            action = MANUAL_REVIEW
            review_required = True
        else:
            status = PASS
            action = APPROVE
            review_required = False

        failed_count = len(checks_failed)
        warning_count = len(warnings)
        score = max(0, 100 - failed_count * 30 - warning_count * 10)
        if status == FAIL and failed_count >= 3:
            action = "Reject"

        return QAResult(
            asset_name=asset_path.name,
            status=status,
            overall_score=score,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            warnings=warnings,
            recommended_action=action,
            review_required=review_required,
            created_at=datetime.now(),
        )


STYLE_RULE_FIELDS = {
    "Rendering Consistency": "rendering_family_result",
    "Palette Match": "palette_result",
    "Composition Match": "composition_result",
    "Background Treatment": "background_result",
    "Product Type Suitability": "product_type_suitability",
}


def _structured_finding(
    asset_path: Path,
    metadata: dict[str, Any],
    rule_results: tuple[RuleResult, ...],
) -> dict[str, Any]:
    by_name = {result.rule_name: result for result in rule_results}
    failed_rules = tuple(
        result.rule_name
        for result in rule_results
        if not result.passed and not result.warning
    )
    technical_failed = tuple(
        result.rule_name
        for result in rule_results
        if result.rule_family == "technical" and not result.passed and not result.warning
    )
    style_failed = tuple(
        result.rule_name
        for result in rule_results
        if result.rule_family == "style" and not result.passed and not result.warning
    )
    finding: dict[str, Any] = {
        "file": str(asset_path),
        "selected_style": metadata.get("expected_style") or metadata.get("style") or "",
        "failed_rules": failed_rules,
        "technical_failed_rules": technical_failed,
        "style_failed_rules": style_failed,
        "rule_confidence": {
            result.rule_name: int(result.confidence)
            for result in rule_results
        },
    }
    for rule_name, field_name in STYLE_RULE_FIELDS.items():
        result = by_name.get(rule_name)
        if result is None:
            finding[field_name] = {
                "status": "NOT_EVALUATED",
                "message": "",
                "confidence": 0,
            }
        else:
            finding[field_name] = {
                "status": "PASS" if result.passed else "FAIL",
                "message": result.message,
                "confidence": int(result.confidence),
            }
    return finding
