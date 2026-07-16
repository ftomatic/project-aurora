"""Tests for Aurora image QA engine."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_result import ImageResult  # noqa: E402
from project_aurora.image_qa.qa_engine import ImageQAEngine  # noqa: E402
from project_aurora.image_qa.qa_report import QAReport  # noqa: E402
from project_aurora.image_qa.qa_result import (  # noqa: E402
    APPROVE,
    FAIL,
    MANUAL_REVIEW,
    PASS,
    WARNING,
    QAResult,
)
from project_aurora.image_qa.qa_rules import (  # noqa: E402
    AssetContext,
    FileExistsRule,
    ImageDimensionsRule,
    NamingConventionRule,
    ResolutionRule,
    TransparentBackgroundRule,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
    b"\x02\xfeA\xd8\x8f\x8d\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ImageQATest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(storage=CSVStorage(base_path=self.base_path))
        self.image_path = self.base_path / "strawberry_birthday_01.png"
        self.image_path.write_bytes(PNG_BYTES)
        self.metadata = {
            "image_count": 1,
            "image_type": "product_asset",
            "width": 3000,
            "height": 3000,
            "dpi": 300,
            "transparent_background": True,
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_qa_result_dataclass(self) -> None:
        result = QAResult(
            asset_name="strawberry_birthday_01.png",
            status=PASS,
            overall_score=100,
            checks_passed=("File Exists",),
            checks_failed=(),
            warnings=(),
            recommended_action=APPROVE,
            review_required=False,
        )

        self.assertEqual(result.status, PASS)
        self.assertEqual(result.recommended_action, APPROVE)
        self.assertFalse(result.review_required)

    def test_qa_rules_pass_for_valid_asset(self) -> None:
        context = AssetContext(
            asset_path=self.image_path,
            all_asset_paths=(self.image_path,),
            metadata=self.metadata,
        )

        self.assertTrue(FileExistsRule().evaluate(context).passed)
        self.assertTrue(NamingConventionRule().evaluate(context).passed)
        self.assertTrue(ResolutionRule().evaluate(context).passed)
        self.assertTrue(ImageDimensionsRule().evaluate(context).passed)
        self.assertTrue(TransparentBackgroundRule().evaluate(context).passed)

    def test_qa_engine_pass(self) -> None:
        image_result = ImageResult(
            status="SUCCESS",
            provider="Mock Provider",
            generated_files=(str(self.image_path),),
            generation_time=0.1,
            cost_estimate=0.0,
            metadata=self.metadata,
        )
        self.memory.save_image_result(image_result)

        results = ImageQAEngine(memory=self.memory).run()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, PASS)
        self.assertEqual(results[0].recommended_action, APPROVE)

    def test_qa_engine_warning(self) -> None:
        awkward_name = self.base_path / "Bad Name.png"
        awkward_name.write_bytes(PNG_BYTES)
        image_result = ImageResult(
            status="SUCCESS",
            provider="Mock Provider",
            generated_files=(str(awkward_name),),
            generation_time=0.1,
            cost_estimate=0.0,
            metadata=self.metadata,
        )

        results = ImageQAEngine(memory=self.memory).evaluate_image_result(
            self.memory._to_record(image_result)  # noqa: SLF001
        )

        self.assertEqual(results[0].status, WARNING)
        self.assertEqual(results[0].recommended_action, MANUAL_REVIEW)
        self.assertTrue(results[0].review_required)

    def test_qa_engine_fail(self) -> None:
        missing_path = self.base_path / "missing_asset_01.png"
        image_result = {
            "generated_files": [str(missing_path)],
            "metadata": self.metadata,
        }

        results = ImageQAEngine(memory=self.memory).evaluate_image_result(
            image_result
        )

        self.assertEqual(results[0].status, FAIL)
        self.assertIn("File Exists", results[0].checks_failed)

    def test_structured_qa_findings_include_style_rule_reasons(self) -> None:
        image_result = {
            "generated_files": [str(self.image_path)],
            "metadata": {
                **self.metadata,
                "expected_style": "Flat Vector",
                "style": "Watercolor Landscape",
                "expected_rendering": "flat vector",
                "rendering": "soft watercolor",
                "expected_palette": "bright primary",
                "palette": "muted earth tones",
                "expected_composition": "finished readable alphabet poster wall-art composition",
                "composition": "sticker sheet cluster",
                "expected_background_treatment": "clean light poster background",
                "background_treatment": "misty landscape background",
                "expected_product_type": "teacher wall art",
            },
        }

        findings = ImageQAEngine(memory=self.memory).evaluate_image_findings(image_result)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["selected_style"], "Flat Vector")
        self.assertEqual(finding["rendering_family_result"]["status"], "FAIL")
        self.assertEqual(finding["palette_result"]["status"], "FAIL")
        self.assertEqual(finding["composition_result"]["status"], "FAIL")
        self.assertEqual(finding["background_result"]["status"], "FAIL")
        self.assertIn("Composition Match", finding["failed_rules"])
        self.assertEqual(finding["rule_confidence"]["Composition Match"], 0)

    def test_technical_pass_but_style_fail_is_explained(self) -> None:
        image_result = {
            "generated_files": [str(self.image_path)],
            "metadata": {
                **self.metadata,
                "expected_style": "Flat Vector",
                "style": "Oil Painting",
            },
        }

        results = ImageQAEngine(memory=self.memory).evaluate_image_result(image_result)
        findings = ImageQAEngine(memory=self.memory).evaluate_image_findings(image_result)

        self.assertEqual(results[0].status, FAIL)
        self.assertNotIn("File Exists", findings[0]["technical_failed_rules"])
        self.assertIn("Style Match", findings[0]["style_failed_rules"])

    def test_memory_saving(self) -> None:
        image_result = ImageResult(
            status="SUCCESS",
            provider="Mock Provider",
            generated_files=(str(self.image_path),),
            generation_time=0.1,
            cost_estimate=0.0,
            metadata=self.metadata,
        )
        self.memory.save_image_result(image_result)

        results = ImageQAEngine(memory=self.memory).run()
        saved = self.memory.load_image_qa_results()

        self.assertEqual(saved["results"][0]["asset_name"], results[0].asset_name)
        self.assertEqual(saved["results"][0]["status"], PASS)

    def test_qa_report_summary(self) -> None:
        report = QAReport(
            results=(
                QAResult(
                    asset_name="a_01.png",
                    status=PASS,
                    overall_score=100,
                    checks_passed=("File Exists",),
                    checks_failed=(),
                    recommended_action=APPROVE,
                    review_required=False,
                ),
                QAResult(
                    asset_name="a_02.png",
                    status=WARNING,
                    overall_score=90,
                    checks_passed=("File Exists",),
                    checks_failed=(),
                    warnings=("Naming warning.",),
                    recommended_action=MANUAL_REVIEW,
                    review_required=True,
                ),
            )
        )

        rendered = report.render()

        self.assertIn("IMAGE QA REPORT", rendered)
        self.assertIn("Assets Reviewed\n2", rendered)
        self.assertIn("Approval Rate\n50%", rendered)


if __name__ == "__main__":
    unittest.main()
