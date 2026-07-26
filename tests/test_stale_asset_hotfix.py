"""Regression tests for job-scoped asset ownership in Product Factory."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import READY, ProductionJob  # noqa: E402
from project_aurora.production.asset_manifest import (  # noqa: E402
    manifest_path_for,
    validate_asset_ownership,
    write_asset_manifest,
)
from project_aurora.production.product_factory import (  # noqa: E402
    DefaultProductFactoryStageRunner,
    ImageGenerationBatchResult,
    ProductFactoryJobPaths,
    ProductFactoryPaths,
    _archive_existing_final_assets,
    _sanitize_final_asset_names,
    _normalize_asset_result_files,
)
from project_aurora.quality.commercial_image_qa import CommercialImageQA  # noqa: E402
from scripts.resume_product_factory_job import _validate_resume_asset_ownership  # noqa: E402


def make_job(job_id: str, name: str) -> ProductionJob:
    """Create a minimal production job."""
    return ProductionJob(
        id=job_id,
        priority="High",
        product_name=name,
        category="Digital Illustration Collection",
        style="Whimsical Storybook",
        seasonal_theme="Evergreen",
        keywords=tuple(name.casefold().split()),
        confidence_score=0.95,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=24.0,
        status=READY,
        required_image_count=4,
    )


def write_png(path: Path) -> None:
    """Write a small visible PNG for deterministic ownership tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16), (20, 120, 200, 255)).save(path, format="PNG")


class StaleAssetHotfixTest(unittest.TestCase):
    """Verify one job cannot inherit or upload another job's assets."""

    def test_wedding_job_cannot_inherit_strawberry_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wedding = make_job(
                "wedding-job",
                "Wedding Planner Sticker Illustration Set",
            )
            final_dir = root / "jobs" / "wedding_job_wedding" / "final_product_images"
            files = tuple(
                final_dir / f"strawberry_birthday_party_printable_{index:02d}.png"
                for index in range(1, 5)
            )
            for file_path in files:
                write_png(file_path)
            write_asset_manifest(
                manifest_path=manifest_path_for(final_dir.parent),
                job_id="strawberry-job",
                product_name="Summer Strawberry Birthday Printable",
                files=files,
                source_stage="commercial_export",
            )

            result = CommercialImageQA().evaluate(
                job=wedding,
                final_files=files,
                prompt_package={"expected_image_count": 4},
                asset_manifest_path=manifest_path_for(final_dir.parent),
                workspace=final_dir.parent,
                manual_visual_approval=True,
            )

            self.assertEqual(result.status, "FAIL")
            self.assertTrue(
                any("STALE_OR_MISMATCHED_ASSET" in issue for issue in result.blocking_issues)
            )

    def test_correct_wedding_sticker_files_pass_commercial_image_qa(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wedding = make_job(
                "wedding-job",
                "Wedding Planner Sticker Illustration Set",
            )
            final_dir = root / "jobs" / "wedding_job_wedding" / "final_product_images"
            files = tuple(final_dir / f"wedding_planner_sticker_{index:02d}.png" for index in range(1, 5))
            for file_path in files:
                write_png(file_path)
            write_asset_manifest(
                manifest_path=manifest_path_for(final_dir.parent),
                job_id=wedding.id,
                product_name=wedding.product_name,
                files=files,
                source_stage="commercial_export",
            )

            result = CommercialImageQA().evaluate(
                job=wedding,
                final_files=files,
                prompt_package={"expected_image_count": 4},
                asset_manifest_path=manifest_path_for(final_dir.parent),
                workspace=final_dir.parent,
                manual_visual_approval=True,
            )

            self.assertEqual(result.status, "PASS")

    def test_two_consecutive_jobs_have_different_asset_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = make_job("job-one", "Summer Strawberry Birthday Printable")
            second = make_job("job-two", "Wedding Planner Sticker Illustration Set")
            first_paths = ProductFactoryPaths(jobs_dir=root / "jobs").for_job(first)
            second_paths = ProductFactoryPaths(jobs_dir=root / "jobs").for_job(second)
            first_file = first_paths.generated_images_dir / "source_01.png"
            second_file = second_paths.generated_images_dir / "source_01.png"
            write_png(first_file)
            write_png(second_file)

            first_result = _normalize_asset_result_files(
                job=first,
                job_paths=first_paths,
                result=SimpleNamespace(status="SUCCESS", generated_files=(str(first_file),)),
                file_attribute="generated_files",
                source_stage="image_generation",
            )
            second_result = _normalize_asset_result_files(
                job=second,
                job_paths=second_paths,
                result=SimpleNamespace(status="SUCCESS", generated_files=(str(second_file),)),
                file_attribute="generated_files",
                source_stage="image_generation",
            )

            self.assertNotEqual(first_result.generated_files, second_result.generated_files)
            self.assertIn("summer_strawberry", first_result.generated_files[0])
            self.assertIn("wedding_planner", second_result.generated_files[0])

    def test_asset_lists_are_not_shared_mutable_defaults(self) -> None:
        first = ImageGenerationBatchResult(status="SUCCESS")
        second = ImageGenerationBatchResult(status="SUCCESS")

        self.assertIsNot(first.metadata, second.metadata)

    def test_job_workspace_is_unique(self) -> None:
        paths = ProductFactoryPaths(jobs_dir=Path("/tmp/aurora-jobs"))
        first = paths.for_job(make_job("job-one", "Wedding Planner Stickers"))
        second = paths.for_job(make_job("job-two", "Wedding Planner Stickers"))

        self.assertNotEqual(first.job_root, second.job_root)
        self.assertIn("job_one", str(first.job_root))
        self.assertIn("job_two", str(second.job_root))

    def test_stale_manifest_references_are_removed_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job = make_job("wedding-job", "Wedding Planner Sticker Illustration Set")
            job_paths = ProductFactoryJobPaths(
                job_root=root / "wedding-job",
                generated_images_dir=root / "wedding-job" / "generated_images",
                final_images_dir=root / "wedding-job" / "final_product_images",
                digital_downloads_dir=root / "wedding-job" / "digital_downloads",
            )
            files = tuple(job_paths.generated_images_dir / f"strawberry_{index}.png" for index in range(4))
            for file_path in files:
                write_png(file_path)
            write_asset_manifest(
                manifest_path=manifest_path_for(job_paths.job_root),
                job_id="strawberry-job",
                product_name="Summer Strawberry Birthday Printable",
                files=files,
                source_stage="image_generation",
            )
            runner = DefaultProductFactoryStageRunner(
                memory=SimpleNamespace(save_image_result=lambda *_args, **_kwargs: None),
                etsy_config=SimpleNamespace(is_mock_mode=True),
            )

            self.assertIsNone(
                runner._reuse_completed_generated_images(job, job_paths, expected_count=4)
            )
            runner._prepare_generated_images_dir(job_paths)

            self.assertFalse(any(job_paths.generated_images_dir.glob("*.png")))
            self.assertTrue(any((job_paths.job_root / "rejected").glob("generated_images_*/*.png")))

    def test_historical_files_remain_untouched_when_final_assets_archived(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_paths = ProductFactoryJobPaths(
                job_root=root / "active",
                generated_images_dir=root / "active" / "generated_images",
                final_images_dir=root / "active" / "final_product_images",
                digital_downloads_dir=root / "active" / "digital_downloads",
            )
            stale = job_paths.final_images_dir / "strawberry_birthday_party_printable_01.png"
            historical = root / "history" / "strawberry_birthday_party_printable_01.png"
            write_png(stale)
            write_png(historical)

            _archive_existing_final_assets(job_paths)

            self.assertFalse(stale.exists())
            self.assertTrue(historical.exists())
            self.assertTrue(any((job_paths.job_root / "rejected").glob("final_product_images_*/*.png")))

    def test_resume_script_rejects_cross_job_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wedding = make_job("wedding-job", "Wedding Planner Sticker Illustration Set")
            final_dir = root / "wedding-job" / "final_product_images"
            files = tuple(final_dir / f"strawberry_{index}.png" for index in range(1, 5))
            for file_path in files:
                write_png(file_path)
            write_asset_manifest(
                manifest_path=manifest_path_for(final_dir.parent),
                job_id="strawberry-job",
                product_name="Summer Strawberry Birthday Printable",
                files=files,
                source_stage="commercial_export",
            )

            with self.assertRaisesRegex(RuntimeError, "STALE_OR_MISMATCHED_ASSET"):
                _validate_resume_asset_ownership(
                    wedding,
                    {"job_paths": {"job_root": str(final_dir.parent)}},
                    files,
                )

    def test_manifest_owner_validation_passes_current_job_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job = make_job("wedding-job", "Wedding Planner Sticker Illustration Set")
            final_dir = root / "wedding-job" / "final_product_images"
            files = tuple(final_dir / f"wedding_{index}.png" for index in range(1, 5))
            for file_path in files:
                write_png(file_path)
            write_asset_manifest(
                manifest_path=manifest_path_for(final_dir.parent),
                job_id=job.id,
                product_name=job.product_name,
                files=files,
                source_stage="commercial_export",
            )

            ownership = validate_asset_ownership(
                manifest_path=manifest_path_for(final_dir.parent),
                job_id=job.id,
                product_name=job.product_name,
                workspace=final_dir.parent,
                files=files,
                source_stage="commercial_export",
            )

            self.assertTrue(ownership.passed)

    def test_active_job_prefix_with_legacy_strawberry_stem_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job = make_job(
                "2c2babec-41e-teacher",
                "Teacher Alphabet Posters Digital Illustration Collection",
            )
            job_paths = ProductFactoryJobPaths(
                job_root=root / "2c2babec_41e_teacher",
                generated_images_dir=root / "2c2babec_41e_teacher" / "generated_images",
                final_images_dir=root / "2c2babec_41e_teacher" / "final_product_images",
                digital_downloads_dir=root / "2c2babec_41e_teacher" / "digital_downloads",
            )
            stale_named = tuple(
                job_paths.final_images_dir
                / (
                    "2c2babec_41e_teacher_alphabet_posters_digital_illustration_collection_"
                    f"strawberry_birthday_party_printable_{index:02d}.png"
                )
                for index in range(1, 5)
            )
            for file_path in stale_named:
                write_png(file_path)
            write_asset_manifest(
                manifest_path=manifest_path_for(job_paths.job_root),
                job_id=job.id,
                product_name=job.product_name,
                files=stale_named,
                source_stage="commercial_export",
            )

            _sanitize_final_asset_names(job, job_paths)

            current_files = tuple(sorted(job_paths.final_images_dir.glob("*.png")))
            self.assertEqual(len(current_files), 4)
            self.assertTrue(all("strawberry_birthday_party_printable" not in path.name for path in current_files))
            result = CommercialImageQA().evaluate(
                job=job,
                final_files=current_files,
                prompt_package={"expected_image_count": 4},
                asset_manifest_path=manifest_path_for(job_paths.job_root),
                workspace=job_paths.job_root,
                manual_visual_approval=True,
            )
            self.assertEqual(result.status, "PASS")


if __name__ == "__main__":
    unittest.main()
