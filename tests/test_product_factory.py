"""Tests for Sprint 20 Product Factory orchestration."""

from __future__ import annotations

import sys
import tempfile
import unittest
import base64
import json
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.image_generation.image_result import ImageResult  # noqa: E402
from project_aurora.production.generation_plan import (  # noqa: E402
    GENERATION_MODE_BOTANICAL,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_ORIGINAL,
    GENERATION_MODE_STORYBOOK,
    GENERATION_MODE_WEDDING,
)
from project_aurora.production.art_direction_package import (  # noqa: E402
    build_art_direction_package,
)
from project_aurora.production.product_factory import (  # noqa: E402
    REPORT_COLLECTION,
    DefaultProductFactoryStageRunner,
    DryRunProductFactoryStageRunner,
    ProductFactoryPaths,
    ProductFactory,
    ProductFactoryStageError,
    _product_family_prompt,
    _original_scene_prompt,
    _raise_if_failed,
    _storybook_scene_prompt,
    _valid_existing_listing_previews,
)
from project_aurora.production.production_report import (  # noqa: E402
    ProductionReport,
)
from project_aurora.image_generation.openai_provider import (  # noqa: E402
    OpenAIImageProvider,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyImageUploadAttempt,
    EtsyImageUploadResult,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_product_factory import (  # noqa: E402
    parse_args,
    print_etsy_config_diagnostics,
)


def make_job(job_id: str = "job-1") -> ProductionJob:
    return ProductionJob(
        id=job_id,
        priority="High",
        product_name="Woodland Baby Animals",
        category="Digital Clipart",
        style="Storybook Watercolor",
        seasonal_theme="Evergreen",
        keywords=("woodland", "baby", "animals"),
        confidence_score=0.96,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=164.0,
        status=READY,
    )


def make_visible_png_base64() -> str:
    output = BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def make_transparent_clipart_png_base64() -> str:
    output = BytesIO()
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    for x in range(12, 52):
        for y in range(10, 54):
            image.putpixel((x, y), (120, 70, 30, 255))
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def write_visible_png(path: Path, size: tuple[int, int] = (2, 2)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 0, 0, 255)).save(path, format="PNG")


def write_transparent_clipart_png(path: Path, size: tuple[int, int] = (64, 64)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    for x in range(12, 52):
        for y in range(10, 54):
            image.putpixel((x, y), (120, 70, 30, 255))
    image.save(path, format="PNG")


def write_edge_touching_clipart_png(
    path: Path,
    size: tuple[int, int] = (64, 64),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    for x in range(0, 52):
        for y in range(10, 64):
            image.putpixel((x, y), (120, 70, 30, 255))
    image.save(path, format="PNG")


def write_full_scene_png(path: Path, size: tuple[int, int] = (128, 128)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (120, 170, 130, 255))
    for x in range(size[0]):
        for y in range(size[1]):
            image.putpixel((x, y), ((x * 3) % 255, (y * 2) % 255, 120, 255))
    image.save(path, format="PNG")


class FakeOpenAIImagesClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        count = int(kwargs["n"])
        return SimpleNamespace(
            data=[
                {"b64_json": make_transparent_clipart_png_base64()}
                for _ in range(count)
            ]
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.images = FakeOpenAIImagesClient()


class FakeEtsyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeEtsyResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeStageRunner:
    def __init__(self, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage
        self.calls: list[str] = []

    def compose_prompts(self, job: ProductionJob) -> object:
        self.calls.append("prompt_composition")
        return SimpleNamespace(final_prompt="prompt")

    def generate_images(self, job: ProductionJob) -> object:
        self.calls.append("image_generation")
        if self.fail_stage == "image_generation":
            return SimpleNamespace(
                status="FAILED",
                errors=("OpenAI image generation failed.",),
                generated_files=(),
            )
        return SimpleNamespace(
            status="SUCCESS",
            generated_files=("image1.png", "image2.png", "image3.png", "image4.png"),
            warnings=(),
        )

    def run_image_qa(self, job: ProductionJob) -> tuple[object, ...]:
        self.calls.append("image_qa")
        return (
            SimpleNamespace(status="PASS", asset_name="image1.png"),
            SimpleNamespace(status="PASS", asset_name="image2.png"),
            SimpleNamespace(status="PASS", asset_name="image3.png"),
            SimpleNamespace(status="PASS", asset_name="image4.png"),
        )

    def export_commercial_images(self, job: ProductionJob) -> object:
        self.calls.append("commercial_export")
        return SimpleNamespace(
            status="SUCCESS",
            exported_files=("final1.png", "final2.png", "final3.png", "final4.png"),
            warnings=(),
            errors=(),
        )

    def generate_seo(self, job: ProductionJob) -> object:
        self.calls.append("seo_generation")
        return SimpleNamespace(status="SUCCESS", title="SEO title", warnings=())

    def create_etsy_draft(self, job: ProductionJob, seo_package: object) -> object:
        self.calls.append("etsy_draft")
        if self.fail_stage == "etsy_draft":
            return SimpleNamespace(
                status="VALIDATION_FAILED",
                etsy_listing_id=None,
                errors=("Draft validation failed.",),
            )
        return SimpleNamespace(
            status="DRAFT_CREATED",
            etsy_listing_id="4537338498",
            warnings=(),
        )

    def upload_listing_images(self, job: ProductionJob) -> object:
        self.calls.append("listing_image_upload")
        if self.fail_stage == "listing_image_upload":
            return SimpleNamespace(
                status="PARTIAL_FAILURE",
                images_uploaded=2,
                failed=2,
                errors=("Image upload failed.",),
            )
        return SimpleNamespace(
            status="SUCCESS",
            images_uploaded=4,
            failed=0,
            warnings=(),
        )

    def upload_customer_downloads(
        self,
        job: ProductionJob,
        listing_id: str | None,
    ) -> object:
        self.calls.append("customer_download_upload")
        return SimpleNamespace(
            status="SUCCESS",
            files_uploaded=4,
            failed=0,
            warnings=(),
        )


class PathAwareFakeStageRunner(FakeStageRunner):
    def __init__(self, paths: object) -> None:
        super().__init__()
        self._paths = paths

    def job_paths(self, job: ProductionJob) -> object:
        return self._paths.for_job(job)


class ProductFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.queue = ProductionQueueManager(
            queue_path=self.base_path / "queue.json",
            id_factory=lambda: "unused",
        )
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )
        self.job = self.queue.add_existing_job(make_job())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_production_report_dataclass(self) -> None:
        report = ProductionReport(
            job_id="job-1",
            product="Woodland Baby Animals",
            style="Storybook Watercolor",
            draft_id="4537338498",
            images=4,
            downloads=4,
            time=1.2,
            success=True,
        )

        self.assertEqual(report.queue_status, COMPLETED)
        self.assertEqual(report.to_dict()["draft_id"], "4537338498")

    def test_unsupported_product_type_fails_before_paid_generation(self) -> None:
        unsupported_job = ProductionJob(
            id="unsupported-1",
            priority="High",
            product_name="Wedding Planner Stickers",
            category="planner stickers",
            style="Flat Vector",
            seasonal_theme="Wedding",
            keywords=("planner", "stickers"),
            confidence_score=0.9,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100.0,
            status=READY,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=EtsyConfig(mode="mock"),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            image_config=ImageProviderConfig(provider="openai", number_of_images=4),
        )
        self.memory.save_prompt_package(
            {
                "product_name": unsupported_job.product_name,
                "style": "Storybook Watercolor",
                "image_prompt": "prompt",
            },
            package_id=unsupported_job.id,
        )

        with self.assertRaisesRegex(RuntimeError, "Unsupported recovery product type"):
            runner.generate_images(unsupported_job)

    def test_factory_success_marks_queue_complete_and_saves_report(self) -> None:
        paths = ProductFactoryPaths(jobs_dir=self.base_path / "jobs")
        runner = PathAwareFakeStageRunner(paths)

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertTrue(report.success)
        self.assertEqual(report.draft_id, "4537338498")
        self.assertEqual(report.images, 4)
        self.assertEqual(report.downloads, 4)
        self.assertEqual(self.queue.list_jobs()[0].status, COMPLETED)
        saved = self.memory.load_record(REPORT_COLLECTION, "latest")
        self.assertEqual(saved["product"], "Woodland Baby Animals")
        self.assertEqual(saved["queue_status"], COMPLETED)
        self.assertIn("job_1_woodland_baby_animals", saved["job_paths"]["job_root"])
        self.assertEqual(saved["job_paths"], report.job_paths)
        self.assertEqual(
            runner.calls,
            [
                "prompt_composition",
                "image_generation",
                "image_qa",
                "commercial_export",
                "seo_generation",
                "etsy_draft",
                "listing_image_upload",
                "customer_download_upload",
            ],
        )

    def test_image_failure_stops_and_marks_queue_failed(self) -> None:
        runner = FakeStageRunner(fail_stage="image_generation")

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertFalse(report.success)
        self.assertEqual(report.failed_stage, "image_generation")
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)
        self.assertIn("OpenAI image generation failed.", report.errors[0])
        self.assertEqual(runner.calls, ["prompt_composition", "image_generation"])

    def test_etsy_failure_preserves_draft_id_and_partial_images(self) -> None:
        runner = FakeStageRunner(fail_stage="listing_image_upload")

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertFalse(report.success)
        self.assertEqual(report.failed_stage, "listing_image_upload")
        self.assertEqual(report.draft_id, "4537338498")
        self.assertEqual(report.images, 4)
        self.assertEqual(report.downloads, 0)
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)
        self.assertNotIn("customer_download_upload", runner.calls)

    def test_queue_transitions_from_ready_to_failed_on_draft_error(self) -> None:
        runner = FakeStageRunner(fail_stage="etsy_draft")

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertFalse(report.success)
        self.assertEqual(report.failed_stage, "etsy_draft")
        self.assertIsNone(report.draft_id)
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)

    def test_dry_run_does_not_mutate_queue_or_save_report(self) -> None:
        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=DryRunProductFactoryStageRunner(),
            dry_run=True,
        ).execute(self.job)

        self.assertTrue(report.success)
        self.assertIsNone(report.draft_id)
        self.assertEqual(report.images, 4)
        self.assertEqual(report.downloads, 4)
        self.assertEqual(self.queue.list_jobs()[0].status, READY)
        with self.assertRaises(FileNotFoundError):
            self.memory.load_record(REPORT_COLLECTION, "latest")

    def test_dry_run_can_save_report_only_when_explicit(self) -> None:
        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=DryRunProductFactoryStageRunner(),
            dry_run=True,
            save_report=True,
        ).execute(self.job)

        saved = self.memory.load_record(REPORT_COLLECTION, "latest")

        self.assertTrue(report.success)
        self.assertEqual(saved["queue_status"], COMPLETED)
        self.assertEqual(self.queue.list_jobs()[0].status, READY)

    def test_product_factory_cli_defaults_to_dry_run(self) -> None:
        args = parse_args([])

        self.assertFalse(args.live)
        self.assertFalse(args.dry_run)

    def test_product_factory_cli_live_must_be_explicit(self) -> None:
        args = parse_args(["--live"])

        self.assertTrue(args.live)

    def test_default_runner_uses_configured_medium_openai_quality(self) -> None:
        captured: dict[str, object] = {}

        class FakeImageGenerationEngine:
            def __init__(self, **kwargs: object) -> None:
                captured["provider_config"] = kwargs["provider_config"]
                captured["output_dir"] = kwargs["output_dir"]

            def run(self, **kwargs: object) -> object:
                captured["run_kwargs"] = kwargs
                return SimpleNamespace(status="SUCCESS", generated_files=(), warnings=())

        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(
                jobs_dir=self.base_path / "jobs",
            ),
            image_config=ImageProviderConfig(
                provider="openai",
                quality="medium",
                number_of_images=4,
            ),
        )
        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": self.job.category,
                "style": self.job.style,
                "image_prompt": "Visible test prompt.",
            },
            package_id=self.job.id,
        )

        with patch(
            "project_aurora.image_generation.image_generation_engine.ImageGenerationEngine",
            FakeImageGenerationEngine,
        ):
            result = runner.generate_images(self.job)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(captured["run_kwargs"]["quality"], "medium")
        self.assertEqual(captured["provider_config"].quality, "medium")
        self.assertIn("job_1_woodland_baby_animals", str(captured["output_dir"]))

    def test_clipart_request_uses_explicit_transparent_background_settings(self) -> None:
        captured: dict[str, object] = {}

        class FakeImageGenerationEngine:
            def __init__(self, **kwargs: object) -> None:
                self._output_dir = kwargs["output_dir"]

            def run(self, **kwargs: object) -> object:
                captured["run_kwargs"] = kwargs
                return SimpleNamespace(status="SUCCESS", generated_files=(), warnings=())

        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": self.job.category,
                "style": self.job.style,
                "image_prompt": "Visible transparent clipart prompt.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            image_config=ImageProviderConfig(provider="openai", number_of_images=4),
        )

        with patch(
            "project_aurora.image_generation.image_generation_engine.ImageGenerationEngine",
            FakeImageGenerationEngine,
        ):
            runner.generate_images(self.job)

        self.assertTrue(captured["run_kwargs"]["transparent_background"])
        self.assertEqual(captured["run_kwargs"]["background"], "transparent")
        self.assertEqual(captured["run_kwargs"]["number_of_images"], 4)

    def test_clipped_transparent_generation_is_regenerated_with_safe_area(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeImageGenerationEngine:
            def __init__(self, **kwargs: object) -> None:
                self._output_dir = Path(str(kwargs["output_dir"]))

            def run(self, **kwargs: object) -> ImageResult:
                calls.append(kwargs)
                files: list[str] = []
                for index in range(1, 5):
                    path = self._output_dir / f"customer_{index}.png"
                    if len(calls) == 1:
                        write_edge_touching_clipart_png(path)
                    else:
                        write_transparent_clipart_png(path)
                    files.append(str(path))
                return ImageResult(
                    status="SUCCESS",
                    provider="fake",
                    generated_files=tuple(files),
                    generation_time=0,
                    cost_estimate=0,
                )

        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": self.job.category,
                "style": self.job.style,
                "image_prompt": "Transparent clipart.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            image_config=ImageProviderConfig(provider="openai", number_of_images=4),
        )

        with patch(
            "project_aurora.image_generation.image_generation_engine.ImageGenerationEngine",
            FakeImageGenerationEngine,
        ):
            result = runner.generate_images(self.job)

        retry_package = self.memory.load_prompt_package(self.job.id)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["image_type"], "product_asset_safe_area_retry")
        self.assertIn("15 percent", retry_package["image_prompt"])
        self.assertTrue(any("safe-area" in warning for warning in result.warnings))
        self.assertEqual(
            len(tuple((runner.job_paths(self.job).job_root / "rejected").rglob("*.png"))),
            4,
        )

    def test_storybook_generates_four_customer_pngs_plus_separate_scene(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeImageGenerationEngine:
            def __init__(self, **kwargs: object) -> None:
                self._output_dir = kwargs["output_dir"]

            def run(self, **kwargs: object) -> ImageResult:
                calls.append(kwargs)
                self._output_dir.mkdir(parents=True, exist_ok=True)
                image_type = str(kwargs["image_type"])
                files: list[str] = []
                if image_type == "storybook_scene":
                    for index in range(1, 5):
                        path = self._output_dir / f"scene_{index}.png"
                        write_full_scene_png(path)
                        files.append(str(path))
                else:
                    for index in range(1, 5):
                        path = self._output_dir / f"customer_{index}.png"
                        write_transparent_clipart_png(path)
                        files.append(str(path))
                return ImageResult(
                    status="SUCCESS",
                    provider="fake",
                    generated_files=tuple(files),
                    generation_time=0,
                    cost_estimate=0,
                    warnings=(),
                    errors=(),
                )

        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": "watercolor_animal_collection",
                "style": self.job.style,
                "image_prompt": "Transparent customer clipart prompt.",
                "listing_family": GENERATION_MODE_STORYBOOK,
                "generation_mode": GENERATION_MODE_STORYBOOK,
                "generation_plan": {
                    "resolved_mode": GENERATION_MODE_STORYBOOK,
                    "decision_reason": "test",
                    "customer_png_count": 4,
                    "scene_required": True,
                    "matched_terms": ["woodland"],
                },
                "storybook_scene_prompt": "Full frame storybook scene.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            image_config=ImageProviderConfig(provider="openai", number_of_images=4),
        )

        with patch(
            "project_aurora.image_generation.image_generation_engine.ImageGenerationEngine",
            FakeImageGenerationEngine,
        ):
            result = runner.generate_images(self.job)

        job_paths = runner.job_paths(self.job)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(tuple(job_paths.generated_images_dir.glob("*.png"))), 4)
        self.assertEqual(len(tuple(job_paths.storybook_scenes_dir.glob("*.png"))), 4)
        self.assertEqual(calls[0]["number_of_images"], 4)
        self.assertTrue(calls[0]["transparent_background"])
        self.assertEqual(calls[0]["background"], "transparent")
        self.assertEqual(calls[1]["number_of_images"], 4)
        self.assertFalse(calls[1]["transparent_background"])
        self.assertEqual(calls[1]["background"], "opaque")

    def test_storybook_reuses_existing_customer_pngs_after_safe_area_padding(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeImageGenerationEngine:
            def __init__(self, **kwargs: object) -> None:
                self._output_dir = Path(str(kwargs["output_dir"]))

            def run(self, **kwargs: object) -> ImageResult:
                calls.append(kwargs)
                self._output_dir.mkdir(parents=True, exist_ok=True)
                files: list[str] = []
                for index in range(1, 5):
                    path = self._output_dir / f"scene_{index}.png"
                    write_full_scene_png(path)
                    files.append(str(path))
                return ImageResult(
                    status="SUCCESS",
                    provider="fake",
                    generated_files=tuple(files),
                    generation_time=0,
                    cost_estimate=0,
                    warnings=(),
                    errors=(),
                )

        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": "watercolor_animal_collection",
                "style": self.job.style,
                "image_prompt": "Transparent customer clipart prompt.",
                "listing_family": GENERATION_MODE_STORYBOOK,
                "generation_mode": GENERATION_MODE_STORYBOOK,
                "generation_plan": {
                    "resolved_mode": GENERATION_MODE_STORYBOOK,
                    "decision_reason": "test",
                    "customer_png_count": 4,
                    "scene_required": True,
                    "matched_terms": ["woodland"],
                },
                "storybook_scene_prompt": "Full frame storybook scene.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            image_config=ImageProviderConfig(provider="openai", number_of_images=4),
        )
        job_paths = runner.job_paths(self.job)
        for index in range(1, 5):
            write_edge_touching_clipart_png(
                job_paths.generated_images_dir / f"customer_{index}.png"
            )

        with patch(
            "project_aurora.image_generation.image_generation_engine.ImageGenerationEngine",
            FakeImageGenerationEngine,
        ):
            result = runner.generate_images(self.job)

        from project_aurora.image_generation.clipart_safe_area import (
            validate_clipart_safe_area,
        )

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["image_type"], "storybook_scene")
        self.assertTrue(
            any("Normalized existing" in warning for warning in result.warnings)
        )
        for path in job_paths.generated_images_dir.glob("*.png"):
            self.assertEqual(validate_clipart_safe_area(path), ())
        self.assertEqual(len(tuple(job_paths.storybook_scenes_dir.glob("*.png"))), 4)

    def test_scene_and_clipart_prompts_share_art_direction_package(self) -> None:
        art_package = build_art_direction_package(
            product_name="Rabbit Tea Party Watercolor Clipart",
            product_category="watercolor animal collection",
            style="Whimsical Storybook",
            season="Spring",
            palette="warm cream, sage green, muted blue, soft coral",
            mood="cozy tea party",
        )
        job = ProductionJob(
            id="rabbit_job",
            priority="High",
            product_name="Rabbit Tea Party Watercolor Clipart",
            category="Digital Clipart",
            style="Whimsical Storybook",
            seasonal_theme="Spring",
            keywords=("rabbit", "tea party", "watercolor"),
            confidence_score=0.95,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=150,
            status=READY,
        )

        clipart_prompt = _product_family_prompt(
            job,
            "watercolor animal collection",
            "CLIPART",
            art_package,
        )
        scene_prompt = _storybook_scene_prompt(
            job,
            "watercolor animal collection",
            art_package,
        )

        for expected in (
            "mother rabbit in sage green dress",
            "father rabbit in muted blue jacket",
            "tea table",
            "sage green",
            "muted blue",
            "soft watercolor and gentle gouache",
        ):
            self.assertIn(expected, clipart_prompt)
            self.assertIn(expected, scene_prompt)

    def test_original_scene_prompt_requires_four_cohesive_original_scenes(self) -> None:
        job = ProductionJob(
            id="original-job",
            priority="High",
            product_name="Bunny Garden Tea Original Watercolor Collection",
            category="signature_storybook_animal_collection",
            style="Whimsical Storybook",
            seasonal_theme="Spring",
            keywords=("bunny", "garden", "tea", "original"),
            confidence_score=0.96,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=150,
            status=READY,
            source_evidence=(f"generation_mode={GENERATION_MODE_ORIGINAL}",),
        )

        prompt = _original_scene_prompt(
            job,
            "signature_storybook_animal_collection",
        )

        self.assertIn("ORIGINAL RainbowMilkStudio", prompt)
        self.assertIn("two to four expressive anthropomorphic animals", prompt)
        self.assertIn("four clearly different moments", prompt)
        self.assertIn("complete edge-to-edge scenic illustration", prompt)
        self.assertIn("Avoid an all-orange", prompt)
        self.assertIn("Do not reproduce copyrighted characters", prompt)

    def test_character_prompt_requires_humans_without_animals_or_wings(self) -> None:
        job = ProductionJob(
            id="kids_job",
            priority="High",
            product_name="Magical Garden Kids Watercolor Character Clipart",
            category="watercolor_character_collection",
            style="Whimsical Storybook",
            seasonal_theme="Spring",
            keywords=("magical", "garden", "kids", "characters"),
            confidence_score=0.95,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=150,
            status=READY,
        )

        prompt = _product_family_prompt(
            job,
            "watercolor character collection",
            "CHARACTERS",
        )

        self.assertIn("Human children characters only", prompt)
        self.assertIn("No animals", prompt)
        self.assertIn("No wings", prompt)
        self.assertIn("No fairy wings", prompt)
        self.assertIn("true transparent background", prompt)
        self.assertIn("exactly one small complete full-body child", prompt)
        self.assertIn("no more than 55 percent", prompt)
        self.assertIn("not above the child's head", prompt)
        self.assertNotIn("rabbit baking bread", prompt)
        self.assertNotIn("fairy-garden characters", prompt)

    def test_botanical_prompt_requires_one_complete_central_composition(self) -> None:
        botanical_job = ProductionJob(
            id="botanical-job",
            priority="High",
            product_name="Flowering Tree Branch Botanical Clipart",
            category="watercolor_botanical_collection",
            style="Vintage Botanical",
            seasonal_theme="Spring",
            keywords=("flowering", "tree", "branch", "botanical"),
            confidence_score=0.95,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=120,
            status=READY,
        )

        prompt = _product_family_prompt(
            botanical_job,
            "watercolor botanical collection",
            "BOTANICAL",
        )

        self.assertIn("exactly one cohesive isolated botanical composition", prompt)
        self.assertIn("both natural endpoints of every branch", prompt)
        self.assertIn("central 65 percent", prompt)
        self.assertIn("Do not create a collection sheet", prompt)
        self.assertNotIn("birds, blossoms, nests", prompt)

    def test_listing_preview_fingerprint_mismatch_invalidates_existing_previews(self) -> None:
        preview_dir = self.base_path / "listing_images"
        preview_dir.mkdir()
        for index in range(1, 5):
            write_visible_png(preview_dir / f"preview_{index:02d}.png", size=(3000, 3000))
        (preview_dir / "preview_manifest.json").write_text(
            '{"art_direction_fingerprint": "old-fingerprint"}',
            encoding="utf-8",
        )

        reused = _valid_existing_listing_previews(
            preview_dir,
            art_direction_fingerprint="new-fingerprint",
        )

        self.assertIsNone(reused)

    def test_live_image_path_sends_medium_to_openai_sdk_from_config(self) -> None:
        fake_client = FakeOpenAIClient()
        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": self.job.category,
                "style": self.job.style,
                "image_prompt": "Visible test prompt.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(
                jobs_dir=self.base_path / "jobs",
            ),
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch.object(
            OpenAIImageProvider,
            "_build_client",
            return_value=fake_client,
        ):
            result = runner.generate_images(self.job)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(fake_client.images.calls[0]["quality"], "medium")
        self.assertEqual(fake_client.images.calls[0]["size"], "1024x1024")
        self.assertEqual(fake_client.images.calls[0]["n"], 4)

    def test_product_factory_live_config_builds_etsy_colon_api_key(self) -> None:
        config_path = self.base_path / "etsy.yaml"
        config_path.write_text(
            "\n".join(
                (
                    "mode: mock",
                    "api_base_url: https://example.test/v3/application",
                    "taxonomy_id: 123",
                )
            ),
            encoding="utf-8",
        )
        captured: dict[str, object] = {}

        def fake_urlopen(api_request: object, timeout: int) -> FakeEtsyResponse:
            captured["headers"] = dict(api_request.headers)
            captured["timeout"] = timeout
            return FakeEtsyResponse({"ok": True})

        with patch.dict(
            "os.environ",
            {
                "ETSY_CLIENT_ID": "test-client",
                "ETSY_SHARED_SECRET": "test-secret",
                "ETSY_ACCESS_TOKEN": "test-token",
                "ETSY_SHOP_ID": "987654",
            },
            clear=True,
        ):
            config = EtsyConfig.from_environment(config_path)
            runner = DefaultProductFactoryStageRunner(
                memory=self.memory,
                etsy_config=config,
                paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            )
            EtsyClient(config=runner._etsy_config, urlopen=fake_urlopen).get_json(
                "/users/me"
            )

        headers = captured["headers"]
        self.assertEqual(headers["X-api-key"], "test-client:test-secret")
        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(runner._etsy_config.shop_id, "987654")
        self.assertEqual(runner._etsy_config.taxonomy_id, 123)
        self.assertFalse(runner._etsy_config.is_mock_mode)

    def test_explicit_wedding_mode_bypasses_clipart_brand_score_gate(self) -> None:
        wedding_job = ProductionJob(
            id="wedding-job",
            priority="High",
            product_name="French Country Wedding Invitation",
            category="wedding printable",
            style="Pressed Flowers",
            seasonal_theme="Wedding Season",
            keywords=("wedding", "invitation", "printable"),
            confidence_score=0.96,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=120,
            status=READY,
            source_evidence=(f"generation_mode={GENERATION_MODE_WEDDING}",),
        )
        queue = ProductionQueueManager(queue_path=self.base_path / "wedding_queue.json")
        queue.add_existing_job(wedding_job)
        runner = FakeStageRunner()

        report = ProductFactory(
            queue_manager=queue,
            memory=self.memory,
            stage_runner=runner,
            dry_run=False,
            save_report=False,
        ).execute(wedding_job)

        self.assertTrue(report.success)
        self.assertIn("prompt_composition", runner.calls)
        self.assertEqual(queue.list_jobs()[0].status, COMPLETED)

    def test_explicit_digital_paper_mode_bypasses_clipart_brand_score_gate(self) -> None:
        paper_job = ProductionJob(
            id="digital-paper-job",
            priority="High",
            product_name="Sage Botanical Digital Paper",
            category="digital print",
            style="Vintage Botanical",
            seasonal_theme="Evergreen",
            keywords=("sage", "botanical", "digital", "paper"),
            confidence_score=0.96,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=120,
            status=READY,
            source_evidence=(f"generation_mode={GENERATION_MODE_DIGITAL_PAPER}",),
        )
        queue = ProductionQueueManager(queue_path=self.base_path / "paper_queue.json")
        queue.add_existing_job(paper_job)
        runner = FakeStageRunner()

        report = ProductFactory(
            queue_manager=queue,
            memory=self.memory,
            stage_runner=runner,
            dry_run=False,
            save_report=False,
        ).execute(paper_job)

        self.assertTrue(report.success)
        self.assertIn("prompt_composition", runner.calls)
        self.assertEqual(queue.list_jobs()[0].status, COMPLETED)

    def test_explicit_botanical_mode_bypasses_generic_brand_score_gate(self) -> None:
        botanical_job = ProductionJob(
            id="botanical-brand-job",
            priority="High",
            product_name="Cottage Rose Botanical Clipart",
            category="watercolor_botanical_collection",
            style="Cottagecore",
            seasonal_theme="Summer",
            keywords=("cottage", "rose", "botanical", "clipart"),
            confidence_score=0.94,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=174,
            status=READY,
            source_evidence=(f"generation_mode={GENERATION_MODE_BOTANICAL}",),
        )
        queue = ProductionQueueManager(queue_path=self.base_path / "botanical_queue.json")
        queue.add_existing_job(botanical_job)
        runner = FakeStageRunner()

        report = ProductFactory(
            queue_manager=queue,
            memory=self.memory,
            stage_runner=runner,
            dry_run=False,
            save_report=False,
        ).execute(botanical_job)

        self.assertTrue(report.success)
        self.assertIn("prompt_composition", runner.calls)
        self.assertEqual(queue.list_jobs()[0].status, COMPLETED)

    def test_etsy_diagnostics_do_not_print_secret_values(self) -> None:
        config = EtsyConfig(
            mode="live",
            shop_id="987654",
            client_id="test-client",
            shared_secret="test-secret",
            access_token="test-token",
        )
        with patch("sys.stdout", new_callable=StringIO) as output:
            print_etsy_config_diagnostics(config)

        rendered = output.getvalue()
        self.assertIn("Client ID Present\nyes", rendered)
        self.assertIn("Shared Secret Present\nyes", rendered)
        self.assertIn("Access Token Present\nyes", rendered)
        self.assertIn("Shop ID Present\nyes", rendered)
        self.assertIn("x-api-key Colon Count\n1", rendered)
        self.assertNotIn("test-client", rendered)
        self.assertNotIn("test-secret", rendered)
        self.assertNotIn("test-token", rendered)
        self.assertNotIn("987654", rendered)

    def test_old_shared_images_do_not_affect_new_job_generation(self) -> None:
        fake_client = FakeOpenAIClient()
        shared_dir = self.base_path / "generated_images"
        for index in range(1, 5):
            write_visible_png(shared_dir / f"strawberry_{index}.png")
        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": self.job.category,
                "style": self.job.style,
                "image_prompt": "Visible test prompt.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch.object(
            OpenAIImageProvider,
            "_build_client",
            return_value=fake_client,
        ):
            result = runner.generate_images(self.job)

        job_paths = runner.job_paths(self.job)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(tuple(shared_dir.glob("*.png"))), 4)
        self.assertEqual(len(tuple(job_paths.generated_images_dir.glob("*.png"))), 4)
        self.assertNotEqual(shared_dir, job_paths.generated_images_dir)

    def test_two_jobs_use_different_directories(self) -> None:
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )
        other_job = make_job("job-2")

        first_paths = runner.job_paths(self.job)
        second_paths = runner.job_paths(other_job)

        self.assertNotEqual(first_paths.job_root, second_paths.job_root)
        self.assertIn("job_1_woodland_baby_animals", str(first_paths.job_root))
        self.assertIn("job_2_woodland_baby_animals", str(second_paths.job_root))

    def test_exporter_receives_only_current_job_generated_files(self) -> None:
        captured: dict[str, object] = {}
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )
        job_paths = runner.job_paths(self.job)
        for index in range(1, 5):
            write_visible_png(self.base_path / "generated_images" / f"old_{index}.png")
            write_visible_png(job_paths.generated_images_dir / f"current_{index}.png")

        class FakeCommercialImageExporter:
            def __init__(
                self,
                source_dir: Path,
                output_dir: Path,
                output_prefix: str = "",
                product_family: str = "",
            ) -> None:
                captured["source_dir"] = source_dir
                captured["output_dir"] = output_dir
                captured["output_prefix"] = output_prefix
                captured["product_family"] = product_family
                captured["source_files"] = tuple(source_dir.glob("*.png"))

            def export(self) -> object:
                return SimpleNamespace(
                    status="SUCCESS",
                    exported_files=("final1.png", "final2.png", "final3.png", "final4.png"),
                    warnings=(),
                    errors=(),
                )

        with patch(
            "project_aurora.image_generation.commercial_image_exporter.CommercialImageExporter",
            FakeCommercialImageExporter,
        ):
            result = runner.export_commercial_images(self.job)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(captured["source_dir"], job_paths.generated_images_dir)
        self.assertEqual(len(captured["source_files"]), 4)
        self.assertEqual(captured["product_family"], "CLIPART")

    def test_etsy_upload_generates_listing_previews_from_current_job_final_images(self) -> None:
        captured: dict[str, object] = {}
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )
        job_paths = runner.job_paths(self.job)
        for index in range(1, 5):
            write_visible_png(self.base_path / "final_product_images" / f"old_{index}.png")
            write_visible_png(job_paths.final_images_dir / f"current_{index}.png")

        class FakeEtsyImageUploadService:
            def __init__(self, **kwargs: object) -> None:
                captured["images_dir"] = kwargs["images_dir"]
                captured["files"] = tuple(kwargs["images_dir"].glob("*.png"))

            def upload_latest_draft_images(self) -> object:
                return SimpleNamespace(
                    status="SUCCESS",
                    images_uploaded=4,
                    failed=0,
                    warnings=(),
                    errors=(),
                )

        with patch(
            "project_aurora.integrations.etsy.etsy_image_upload_service.EtsyImageUploadService",
            FakeEtsyImageUploadService,
        ):
            result = runner.upload_listing_images(self.job)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(captured["images_dir"], job_paths.listing_images_dir)
        self.assertEqual(len(captured["files"]), 4)
        self.assertEqual(len(tuple(job_paths.final_images_dir.glob("*.png"))), 4)
        self.assertEqual(len(tuple(job_paths.listing_images_dir.glob("*.png"))), 4)

    def test_customer_download_uploads_four_pngs_and_zip(self) -> None:
        captured: dict[str, object] = {}
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )
        job_paths = runner.job_paths(self.job)
        for index in range(1, 5):
            path = job_paths.final_images_dir / f"current_{index}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGBA", (4000, 4000), (255, 255, 255, 0))
            image.paste((255, 0, 0, 255), (900, 900, 3100, 3100))
            image.save(path, format="PNG", dpi=(300, 300))

        class FakeEtsyDigitalFileService:
            def __init__(self, **kwargs: object) -> None:
                captured["service_kwargs"] = kwargs

            def sync_digital_files(
                self,
                listing_id: str | None,
                final_images_dir: Path,
                product_family: str = "",
            ) -> object:
                captured["sync_listing_id"] = listing_id
                captured["sync_dir"] = final_images_dir
                captured["product_family"] = product_family
                return SimpleNamespace(
                    status="SUCCESS",
                    files_uploaded=4,
                    failed=0,
                    errors=(),
                    warnings=(),
                )

            def upload_digital_file(
                self,
                listing_id: str | None,
                file_path: Path,
            ) -> object:
                captured["zip_listing_id"] = listing_id
                captured["zip_path"] = file_path
                return SimpleNamespace(
                    status="SUCCESS",
                    files_uploaded=1,
                    failed=0,
                    errors=(),
                    warnings=(),
                )

        with patch(
            "project_aurora.integrations.etsy.etsy_digital_file_service.EtsyDigitalFileService",
            FakeEtsyDigitalFileService,
        ):
            result = runner.upload_customer_downloads(self.job, "listing-123")

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.files_uploaded, 5)
        self.assertEqual(captured["sync_listing_id"], "listing-123")
        self.assertEqual(captured["sync_dir"], job_paths.final_images_dir)
        self.assertEqual(captured["product_family"], "CLIPART")
        self.assertEqual(captured["zip_listing_id"], "listing-123")
        self.assertEqual(Path(captured["zip_path"]).parent, job_paths.digital_downloads_dir)

    def test_rerun_reuses_four_generated_images_without_accumulating(self) -> None:
        fake_client = FakeOpenAIClient()
        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "collection": self.job.product_name,
                "product_type": self.job.category,
                "style": self.job.style,
                "image_prompt": "Visible test prompt.",
            },
            package_id=self.job.id,
        )
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch.object(
            OpenAIImageProvider,
            "_build_client",
            return_value=fake_client,
        ):
            first = runner.generate_images(self.job)
            second = runner.generate_images(self.job)

        job_paths = runner.job_paths(self.job)
        self.assertEqual(first.status, "SUCCESS")
        self.assertEqual(second.status, "SUCCESS")
        self.assertEqual(len(fake_client.images.calls), 1)
        self.assertEqual(len(tuple(job_paths.generated_images_dir.glob("*.png"))), 4)
        self.assertEqual(len(tuple(job_paths.storybook_scenes_dir.glob("*.png"))), 0)

    def test_invalid_final_exports_are_archived_and_rebuilt(self) -> None:
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=SimpleNamespace(),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )
        job_paths = runner.job_paths(self.job)
        for index in range(1, 5):
            write_transparent_clipart_png(
                job_paths.generated_images_dir / f"source_{index}.png"
            )
            write_visible_png(
                job_paths.final_images_dir / f"invalid_{index}.png",
                size=(64, 64),
            )

        result = runner.export_commercial_images(self.job)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 4)
        self.assertEqual(len(tuple(job_paths.final_images_dir.glob("*.png"))), 4)
        self.assertEqual(
            len(tuple((job_paths.job_root / "rejected").rglob("invalid_*.png"))),
            4,
        )

    def test_failed_listing_upload_reports_attempt_error(self) -> None:
        result = EtsyImageUploadResult(
            status="PARTIAL_FAILURE",
            etsy_listing_id="listing-123",
            images_found=1,
            images_uploaded=0,
            failed=1,
            attempts=(
                EtsyImageUploadAttempt(
                    image_path="/tmp/preview_01.png",
                    rank=1,
                    status="FAILED",
                    errors=("Etsy API request failed: [Errno 32] Broken pipe",),
                ),
            ),
        )

        with self.assertRaises(ProductFactoryStageError) as context:
            _raise_if_failed("listing_image_upload", result)

        self.assertEqual(context.exception.stage, "listing_image_upload")
        self.assertEqual(
            str(context.exception),
            "preview_01.png: Etsy API request failed: [Errno 32] Broken pipe",
        )


if __name__ == "__main__":
    unittest.main()
