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
from project_aurora.production.product_factory import (  # noqa: E402
    REPORT_COLLECTION,
    DefaultProductFactoryStageRunner,
    DryRunProductFactoryStageRunner,
    ProductFactoryPaths,
    ProductFactory,
)
from project_aurora.production.production_report import (  # noqa: E402
    ProductionReport,
)
from project_aurora.image_generation.openai_provider import (  # noqa: E402
    OpenAIImageProvider,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
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


def write_visible_png(path: Path, size: tuple[int, int] = (2, 2)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 0, 0, 255)).save(path, format="PNG")


class FakeOpenAIImagesClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        count = int(kwargs["n"])
        return SimpleNamespace(
            data=[
                {"b64_json": make_visible_png_base64()}
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

    def test_missing_product_type_expectation_fails_before_paid_generation(self) -> None:
        runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=EtsyConfig(mode="mock"),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
            image_config=ImageProviderConfig(provider="openai", number_of_images=4),
        )
        self.memory.save_prompt_package(
            {
                "product_name": self.job.product_name,
                "style": "Storybook Watercolor",
                "image_prompt": "prompt",
            },
            package_id=self.job.id,
        )

        with self.assertRaisesRegex(RuntimeError, "Missing product-type expectation"):
            runner.generate_images(self.job)

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
            def __init__(self, source_dir: Path, output_dir: Path) -> None:
                captured["source_dir"] = source_dir
                captured["output_dir"] = output_dir
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

    def test_etsy_upload_uses_only_current_job_final_files(self) -> None:
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
        self.assertEqual(captured["images_dir"], job_paths.final_images_dir)
        self.assertEqual(len(captured["files"]), 4)

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


if __name__ == "__main__":
    unittest.main()
