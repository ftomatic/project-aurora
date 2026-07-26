"""Sprint 34 tests for seasonal intelligence, creative prompts, and QA gates."""

from __future__ import annotations

from datetime import date
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from project_aurora.creative.product_creative_director import (  # noqa: E402
    ProductionCreativeDirector,
    TEXT_POLICY_FORBIDDEN,
)
from project_aurora.image_generation.image_prompt_builder import (  # noqa: E402
    StructuredImagePromptBuilder,
    validate_prompt_text_policy,
)
from project_aurora.planning.production_queue_manager import READY, ProductionJob, ProductionQueueManager  # noqa: E402
from project_aurora.production.merchant_package import MerchantPackage  # noqa: E402
from project_aurora.production.merchant_preflight import MerchantPreflight  # noqa: E402
from project_aurora.production.product_factory import ProductFactory, ProductFactoryStageError  # noqa: E402
from project_aurora.quality.commercial_image_qa import (  # noqa: E402
    FAIL,
    PASS,
    STALE_OR_MISMATCHED_ASSET,
    CommercialImageQA,
)
from project_aurora.research.seasonal_intelligence import (  # noqa: E402
    EVERGREEN,
    PRODUCE_NOW,
    REJECT_OUT_OF_SEASON,
    SeasonalIntelligence,
)
from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def job(name: str = "Back To School Watercolor Clipart") -> ProductionJob:
    return ProductionJob(
        id="job-1234",
        priority="High",
        product_name=name,
        category="digital illustration collection",
        style="Whimsical Storybook Watercolor",
        seasonal_theme="Evergreen",
        keywords=tuple(name.casefold().split()),
        confidence_score=0.95,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=100,
        status=READY,
        target_customer="Etsy buyers",
        required_image_count=4,
    )


def art_direction() -> SimpleNamespace:
    return SimpleNamespace(
        recommended_style="Whimsical Storybook Watercolor",
        palette="cream, sage, blush, warm gold",
        rendering_family="watercolor",
        rendering_method="watercolor",
        composition="cohesive grouped product presentation",
        background_treatment="clean light background",
        lighting="soft natural lighting",
        texture="delicate watercolor paper texture",
        mood="cozy commercial",
    )


class Sprint34CreativeQualityTest(unittest.TestCase):
    def test_graduation_in_late_july_is_rejected(self) -> None:
        review = SeasonalIntelligence(today=date(2026, 7, 25)).evaluate(
            "Graduation Party Printable Digital Illustration Collection",
            "Graduation",
            "digital illustration collection",
        )

        self.assertEqual(review.production_decision, REJECT_OUT_OF_SEASON)
        self.assertTrue(review.is_out_of_season)

    def test_back_to_school_in_july_scores_high(self) -> None:
        review = SeasonalIntelligence(today=date(2026, 7, 25)).evaluate(
            "Back To School Teacher Clipart",
            "Back To School",
            "digital illustration collection",
        )

        self.assertEqual(review.production_decision, PRODUCE_NOW)
        self.assertGreaterEqual(review.seasonal_score, 90)

    def test_evergreen_remains_eligible(self) -> None:
        review = SeasonalIntelligence(today=date(2026, 7, 25)).evaluate(
            "Botanical Clipart",
            "Evergreen",
            "digital illustration collection",
        )

        self.assertEqual(review.production_decision, EVERGREEN)

    def test_prompts_prohibit_text_and_years(self) -> None:
        current_job = job("Graduation Party Printable Digital Illustration Collection")
        brief = ProductionCreativeDirector().create_brief(current_job, art_direction())
        seasonal = SeasonalIntelligence(today=date(2026, 7, 25), allow_inventory_build=True).evaluate(
            current_job.product_name,
            "Graduation",
            current_job.category,
            inventory_build=True,
        )

        prompts = StructuredImagePromptBuilder().build_prompts(brief, seasonal)

        self.assertTrue(all(prompt.text_policy == TEXT_POLICY_FORBIDDEN for prompt in prompts))
        self.assertTrue(all("no text" in prompt.negative_prompt for prompt in prompts))
        self.assertFalse(any("2024" in prompt.prompt or "2026" in prompt.prompt for prompt in prompts))

    def test_class_of_2024_is_blocked(self) -> None:
        with self.assertRaises(ValueError):
            validate_prompt_text_policy("Elegant graduation cap, Class of 2024 lettering")

    def test_four_prompts_share_consistency_key_and_roles_differ(self) -> None:
        current_job = job()
        brief = ProductionCreativeDirector().create_brief(current_job, art_direction())
        seasonal = SeasonalIntelligence(today=date(2026, 7, 25)).evaluate(
            current_job.product_name,
            current_job.seasonal_theme,
            current_job.category,
        )

        prompts = StructuredImagePromptBuilder().build_prompts(brief, seasonal)

        self.assertEqual(len({prompt.consistency_key for prompt in prompts}), 1)
        self.assertEqual(len({prompt.blueprint_role for prompt in prompts}), 4)

    def test_commercial_qa_blocks_strawberry_files_for_graduation_product(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "job_1234_graduation" / "strawberry_birthday_party_printable_01.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not-empty")
            current_job = job("Graduation Party Printable Digital Illustration Collection")
            result = CommercialImageQA(current_year=2026).evaluate(
                job=current_job,
                final_files=(path, path, path, path),
                prompt_package={"expected_image_count": 4, "image_prompts": []},
            )

        self.assertEqual(result.pass_fail, FAIL)
        self.assertTrue(any(STALE_OR_MISMATCHED_ASSET in issue for issue in result.blocking_issues))

    def test_good_coherent_set_passes_commercial_qa(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "job_1234_product" / "final_product_images"
            root.mkdir(parents=True)
            files = []
            for index in range(1, 5):
                path = root / f"back_to_school_clipart_{index:02d}.png"
                path.write_bytes(b"not-empty")
                files.append(path)
            prompt_package = {
                "expected_image_count": 4,
                "consistency_key": "abc",
                "image_prompts": [
                    {"blueprint_role": f"role {index}", "consistency_key": "abc"}
                    for index in range(1, 5)
                ],
            }
            result = CommercialImageQA(current_year=2026).evaluate(
                job=job(),
                final_files=tuple(files),
                prompt_package=prompt_package,
            )

        self.assertEqual(result.pass_fail, PASS)

    def test_merchant_preflight_fails_when_commercial_qa_not_approved(self) -> None:
        current_job = job()
        seo = SEOEngine().build_package(
            {
                "job_id": current_job.id,
                "product_name": current_job.product_name,
                "product_type": current_job.category,
                "target_buyer": "Etsy buyers",
            }
        )
        merchant = MerchantPackage(
            job_id=current_job.id,
            product_name=current_job.product_name,
            product_type=current_job.category,
            capability_mode="IMAGE_ONLY",
            etsy_taxonomy_id=6844,
            etsy_taxonomy_path="Craft Supplies & Tools > Digital > Clip Art & Image Files",
            taxonomy_confidence=92,
            price_range=(3.99, 4.99, 6.99),
            recommended_price=4.99,
            launch_price=4.79,
            pricing_reason="test",
            pricing_source="CONFIGURED_FALLBACK",
            selected_style=current_job.style,
            style_confidence=95,
            composition="cohesive",
            background="clean",
            product_capability_result={"supported": True},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = MerchantPreflight().run(
                job=current_job,
                merchant_package=merchant,
                seo_package=seo,
                final_images_dir=Path(temp_dir),
                image_qa_approved=False,
            )

        self.assertEqual(result.status, "PREFLIGHT_FAILED")
        self.assertIn("Image QA has not passed", "; ".join(result.errors))

    def test_image_generation_failure_does_not_create_etsy_draft(self) -> None:
        class FailingRunner:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def compose_prompts(self, current_job: ProductionJob) -> object:
                self.calls.append("prompt_composition")
                return SimpleNamespace(status="SUCCESS")

            def generate_images(self, current_job: ProductionJob) -> object:
                self.calls.append("image_generation")
                return SimpleNamespace(status="FAILED", errors=("image failed",))

            def create_etsy_draft(self, current_job: ProductionJob, seo_package: object) -> object:
                self.calls.append("etsy_draft")
                return SimpleNamespace(status="DRAFT_CREATED", etsy_listing_id="bad")

        with tempfile.TemporaryDirectory() as temp_dir:
            queue = ProductionQueueManager(queue_path=Path(temp_dir) / "queue.json")
            current_job = queue.add_existing_job(job())
            memory = MemoryManager(CSVStorage(base_path=Path(temp_dir) / "memory"))
            runner = FailingRunner()

            report = ProductFactory(queue, memory, runner).execute(current_job)

        self.assertFalse(report.success)
        self.assertNotIn("etsy_draft", runner.calls)


if __name__ == "__main__":
    unittest.main()
