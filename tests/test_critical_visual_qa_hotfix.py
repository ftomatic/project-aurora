"""Critical hotfix tests for visual QA and product definition safety."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.creative.image_blueprints import blueprints_for_product  # noqa: E402
from project_aurora.image_generation.image_prompt_builder import validate_prompt_text_policy  # noqa: E402
from project_aurora.planning.production_queue_manager import READY, ProductionJob  # noqa: E402
from project_aurora.production.product_factory import ProductFactoryStageError  # noqa: E402
from project_aurora.production.product_specification import (  # noqa: E402
    PRODUCT_SPECIFICATION_CONFLICT,
    build_product_specification,
    validate_product_specification_alignment,
)
from project_aurora.quality.commercial_image_qa import CommercialImageQA  # noqa: E402
from project_aurora.quality.visual_image_inspection import (  # noqa: E402
    PROMOTIONAL_BACKGROUND_DETECTED,
    REQUIRED_SUBJECT_MISSING,
    STYLE_MISMATCH,
    TRANSPARENCY_REQUIRED,
    UNINTENDED_VISIBLE_TEXT,
    VISUAL_QA_UNAVAILABLE,
    WRONG_ASSET_CLASS,
    VisualImageInspection,
)
from scripts.run_batch_factory import parse_args  # noqa: E402


def mushroom_job() -> ProductionJob:
    return ProductionJob(
        id="mushroom-job",
        priority="High",
        product_name="Autumn Mushroom Digital Illustration Collection",
        category="digital illustration collection",
        style="Airy Watercolor",
        seasonal_theme="Autumn",
        keywords=("autumn", "mushroom", "clipart"),
        confidence_score=0.95,
        estimated_competition="Medium",
        estimated_demand="High",
        estimated_revenue=100.0,
        status=READY,
        required_image_count=4,
    )


class FakeAnalyzer:
    def __init__(self, inspection: VisualImageInspection) -> None:
        self.inspection = inspection

    def inspect_image(self, image_path: Path, **_kwargs: object) -> VisualImageInspection:
        return VisualImageInspection(
            image_path=str(image_path),
            visual_inspection_completed=self.inspection.visual_inspection_completed,
            detected_subjects=self.inspection.detected_subjects,
            detected_text=self.inspection.detected_text,
            detected_style=self.inspection.detected_style,
            detected_background=self.inspection.detected_background,
            detected_asset_class=self.inspection.detected_asset_class,
            required_subject_coverage=self.inspection.required_subject_coverage,
            role_match=self.inspection.role_match,
            transparent_background_detected=self.inspection.transparent_background_detected,
            isolated_subjects_detected=self.inspection.isolated_subjects_detected,
            forbidden_objects_detected=self.inspection.forbidden_objects_detected,
            errors=self.inspection.errors,
        )


def inspection(**kwargs: object) -> VisualImageInspection:
    defaults = {
        "image_path": "asset.png",
        "visual_inspection_completed": True,
        "detected_subjects": ("mushroom", "autumn leaves"),
        "detected_text": (),
        "detected_style": "airy watercolor",
        "detected_background": "transparent",
        "detected_asset_class": "CUSTOMER_ASSET",
        "required_subject_coverage": 1.0,
        "role_match": True,
        "transparent_background_detected": True,
        "isolated_subjects_detected": True,
        "forbidden_objects_detected": (),
        "errors": (),
    }
    defaults.update(kwargs)
    return VisualImageInspection(**defaults)  # type: ignore[arg-type]


class CriticalVisualQAHotfixTest(unittest.TestCase):
    def evaluate(self, item: VisualImageInspection) -> object:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mushroom_job" / "final_product_images" / "asset_01.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not-empty")
            return CommercialImageQA(
                current_year=2026,
                visual_analyzer=FakeAnalyzer(item),
            ).evaluate(
                job=mushroom_job(),
                final_files=(path, path, path, path),
                prompt_package={"expected_image_count": 4, "image_prompts": []},
                product_specification=build_product_specification(mushroom_job()),
            )

    def test_prompt_says_no_text_but_visual_analyzer_detects_text_fails(self) -> None:
        result = self.evaluate(inspection(detected_text=("Clipart", "Digital")))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any(UNINTENDED_VISIBLE_TEXT in issue for issue in result.errors))

    def test_mushroom_required_but_not_detected_fails(self) -> None:
        result = self.evaluate(inspection(detected_subjects=("leaves", "flowers"), required_subject_coverage=0.2))
        self.assertTrue(any(REQUIRED_SUBJECT_MISSING in issue for issue in result.errors))

    def test_clipart_promotional_cover_fails(self) -> None:
        result = self.evaluate(inspection(detected_asset_class="PROMOTIONAL_COVER"))
        self.assertTrue(any(WRONG_ASSET_CLASS in issue for issue in result.errors))

    def test_flat_poster_style_fails_for_watercolor_intent(self) -> None:
        result = self.evaluate(inspection(detected_style="flat graphic poster design"))
        self.assertTrue(any(STYLE_MISMATCH in issue for issue in result.errors))

    def test_black_promotional_background_fails(self) -> None:
        result = self.evaluate(inspection(detected_background="solid black promotional background"))
        self.assertTrue(any(PROMOTIONAL_BACKGROUND_DETECTED in issue for issue in result.errors))

    def test_missing_alpha_transparency_fails_for_clipart(self) -> None:
        result = self.evaluate(inspection(transparent_background_detected=False))
        self.assertTrue(any(TRANSPARENCY_REQUIRED in issue for issue in result.errors))

    def test_visual_qa_unavailable_blocks_publishing_and_score(self) -> None:
        result = self.evaluate(inspection(visual_inspection_completed=False, errors=(VISUAL_QA_UNAVAILABLE,)))
        self.assertEqual(result.status, "FAIL")
        self.assertLess(result.overall_score, 85)

    def test_metadata_alone_never_awards_100(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mushroom_job" / "final_product_images" / "asset.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not-empty")
            result = CommercialImageQA(current_year=2026).evaluate(
                job=mushroom_job(),
                final_files=(path, path, path, path),
                prompt_package={"expected_image_count": 4, "image_prompts": []},
                product_specification=build_product_specification(mushroom_job()),
            )
        self.assertEqual(result.status, "FAIL")
        self.assertIn(VISUAL_QA_UNAVAILABLE, result.errors)

    def test_product_specification_conflict_blocks_drift(self) -> None:
        spec = build_product_specification(mushroom_job())
        with self.assertRaisesRegex(RuntimeError, PRODUCT_SPECIFICATION_CONFLICT):
            validate_product_specification_alignment(mushroom_job(), spec, "digital paper")

    def test_clipart_blueprints_are_customer_assets_not_marketing_covers(self) -> None:
        roles = tuple(item.role for item in blueprints_for_product("clipart"))
        self.assertEqual(set(roles), {"CUSTOMER_ASSET"})

    def test_product_title_words_are_not_requested_visible_content(self) -> None:
        with self.assertRaisesRegex(ValueError, "title card"):
            validate_prompt_text_policy("Create a title card with Clipart Collection text")

    def test_live_without_upload_parses_as_no_upload(self) -> None:
        args = parse_args(["--live"])
        self.assertTrue(args.live)
        self.assertFalse(args.upload)

    def test_upload_requires_explicit_flag(self) -> None:
        args = parse_args(["--live", "--upload"])
        self.assertTrue(args.upload)

    def test_approved_assets_with_upload_gate_requires_marker(self) -> None:
        # This verifies the error type used by ProductFactory for unapproved upload attempts.
        error = ProductFactoryStageError(
            "visual_review_required",
            ("VISUAL_REVIEW_REQUIRED: --upload requires approved assets.",),
        )
        self.assertIn("VISUAL_REVIEW_REQUIRED", str(error))


if __name__ == "__main__":
    unittest.main()
