"""Tests for Sprint 32 merchant product specifications."""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import ProductionJob  # noqa: E402
from project_aurora.production.merchant_package import MerchantPackage  # noqa: E402
from project_aurora.production.merchant_preflight import MerchantPreflight  # noqa: E402
from project_aurora.production.merchant_specification import (  # noqa: E402
    MerchantSpecificationLibrary,
    MerchantSpecificationQA,
    merchant_prompt_requirements,
)
from project_aurora.prompt_factory.prompt_composer import PromptComposer  # noqa: E402


def _save_jpg(path: Path, size: tuple[int, int], dpi: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (180, 120, 90)).save(path, format="JPEG", dpi=(dpi, dpi))


def _save_png(path: Path, size: tuple[int, int], dpi: int = 300, transparent: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (40, 120, 80, 255))
    if transparent:
        image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(path, format="PNG", dpi=(dpi, dpi))


def _zip_assets(directory: Path, zip_name: str, files: list[Path]) -> None:
    with zipfile.ZipFile(directory / zip_name, "w") as archive:
        for path in files:
            archive.write(path, arcname=path.name)


def _digital_paper(directory: Path, *, dpi: int = 300, wrong_format: bool = False) -> list[Path]:
    files: list[Path] = []
    for index in range(1, 13):
        if wrong_format:
            path = directory / f"paper_{index:02d}.png"
            _save_png(path, (3600, 3600), dpi=dpi)
        else:
            path = directory / f"paper_{index:02d}.jpg"
            _save_jpg(path, (3600, 3600), dpi=dpi)
        files.append(path)
    _save_jpg(directory / "collage_preview.jpg", (1800, 1200), dpi=dpi)
    _zip_assets(directory, "digital_paper.zip", files)
    return files


def _clipart(directory: Path) -> list[Path]:
    files: list[Path] = []
    for index in range(1, 21):
        path = directory / f"clipart_{index:02d}.png"
        _save_png(path, (4000, 100), transparent=True)
        files.append(path)
    _save_png(directory / "grid_preview.png", (1200, 900), transparent=False)
    _zip_assets(directory, "clipart.zip", files)
    return files


def _wall_art(directory: Path) -> list[Path]:
    ratios = {
        "2x3": (2400, 3600),
        "3x4": (2700, 3600),
        "4x5": (2880, 3600),
        "11x14": (3300, 4200),
        "iso": (3508, 4961),
    }
    files: list[Path] = []
    for label, size in ratios.items():
        path = directory / f"nursery_wall_art_{label}.jpg"
        _save_jpg(path, size)
        files.append(path)
    _save_jpg(directory / "lifestyle_preview.jpg", (1800, 1200))
    _zip_assets(directory, "wall_art.zip", files)
    return files


def _stickers(directory: Path) -> list[Path]:
    files: list[Path] = []
    for index in range(1, 9):
        path = directory / f"sticker_{index:02d}.png"
        _save_png(path, (1200, 1200), transparent=True)
        files.append(path)
    _save_png(directory / "sticker_sheet_preview.png", (1800, 1800), transparent=False)
    _zip_assets(directory, "stickers.zip", files)
    return files


def _party_printables(directory: Path) -> list[Path]:
    files: list[Path] = []
    for index in range(1, 5):
        path = directory / f"party_printable_{index:02d}.jpg"
        _save_jpg(path, (2550, 3300))
        files.append(path)
    _save_jpg(directory / "bundle_preview.jpg", (1800, 1200))
    _zip_assets(directory, "party_printables.zip", files)
    return files


def _job(category: str) -> ProductionJob:
    return ProductionJob(
        id="job-spec-1",
        priority="High",
        product_name="Winter Woodland Digital Paper",
        category=category,
        style="Storybook Watercolor",
        seasonal_theme="Winter",
        keywords=("winter", "woodland", "digital", "paper"),
        confidence_score=0.91,
        estimated_competition="Moderate",
        estimated_demand="High",
        estimated_revenue=120,
        demand_score=0.9,
    )


class MerchantSpecificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_library_resolves_every_supported_category(self) -> None:
        library = MerchantSpecificationLibrary()

        self.assertEqual(library.resolve("digital paper").category, "Digital Paper")
        self.assertEqual(library.resolve("clipart").category, "Clipart")
        self.assertEqual(library.resolve("wall art").category, "Printable Wall Art")
        self.assertEqual(library.resolve("sticker sheet").category, "Stickers")
        self.assertEqual(library.resolve("party printable").category, "Party Printables")

    def test_valid_category_packages_pass(self) -> None:
        cases = (
            ("digital paper", _digital_paper),
            ("clipart", _clipart),
            ("wall art", _wall_art),
            ("sticker sheet", _stickers),
            ("party printable", _party_printables),
        )

        for category, writer in cases:
            with self.subTest(category=category):
                directory = self.base_path / category.replace(" ", "_")
                writer(directory)
                result = MerchantSpecificationQA().validate(category, directory)
                self.assertEqual(result.status, "PASS", result.errors)
                self.assertEqual(result.manifest.qa_result, "PASS")
                self.assertTrue(result.manifest.specification_version)
                self.assertTrue(result.manifest.package_files)
                self.assertTrue(result.manifest.previews)

    def test_rejects_incorrect_dimensions(self) -> None:
        directory = self.base_path / "bad_dimensions"
        _digital_paper(directory)
        _save_jpg(directory / "paper_01.jpg", (1024, 1024))

        result = MerchantSpecificationQA().validate("digital paper", directory)

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("Incorrect dimensions" in error for error in result.errors))

    def test_rejects_incorrect_dpi(self) -> None:
        directory = self.base_path / "bad_dpi"
        _digital_paper(directory, dpi=72)

        result = MerchantSpecificationQA().validate("digital paper", directory)

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("Incorrect DPI" in error for error in result.errors))

    def test_rejects_wrong_formats(self) -> None:
        directory = self.base_path / "bad_format"
        _digital_paper(directory, wrong_format=True)

        result = MerchantSpecificationQA().validate("digital paper", directory)

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("requires at least 12 JPG files" in error for error in result.errors))

    def test_rejects_missing_preview(self) -> None:
        directory = self.base_path / "missing_preview"
        _digital_paper(directory)
        (directory / "collage_preview.jpg").unlink()

        result = MerchantSpecificationQA().validate("digital paper", directory)

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("collage preview" in error for error in result.errors))

    def test_rejects_missing_zip(self) -> None:
        directory = self.base_path / "missing_zip"
        _digital_paper(directory)
        (directory / "digital_paper.zip").unlink()

        result = MerchantSpecificationQA().validate("digital paper", directory)

        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("ZIP package" in error for error in result.errors))

    def test_merchant_preflight_blocks_spec_violation_before_etsy_upload(self) -> None:
        directory = self.base_path / "preflight_bad"
        _digital_paper(directory)
        (directory / "digital_paper.zip").unlink()
        current_job = _job("digital paper")
        merchant_package = MerchantPackage(
            job_id=current_job.id,
            product_name=current_job.product_name,
            product_type=current_job.category,
            capability_mode="IMAGE_ONLY",
            etsy_taxonomy_id=123,
            etsy_taxonomy_path="Craft Supplies & Tools > Paper > Digital Paper",
            taxonomy_confidence=95,
            price_range=(3.99, 4.99, 6.99),
            recommended_price=4.99,
            launch_price=4.79,
            pricing_reason="market pricing",
            pricing_source="LIVE_ETSY_MARKET",
            selected_style="Storybook Watercolor",
            style_confidence=92,
            composition="seamless pattern",
            background="pattern",
            product_capability_result={"supported": True},
        )
        seo_package = SimpleNamespace(
            job_id=current_job.id,
            product_name=current_job.product_name,
            style=current_job.style,
        )

        result = MerchantPreflight().run(
            job=current_job,
            merchant_package=merchant_package,
            seo_package=seo_package,
            final_images_dir=directory,
        )

        self.assertEqual(result.status, "PREFLIGHT_FAILED")
        self.assertEqual(result.merchant_qa_status, "FAIL")
        self.assertTrue(any("ZIP package" in error for error in result.errors))

    def test_prompt_composer_includes_merchant_specifications(self) -> None:
        recipe = PromptComposer().compose_art_directed(
            product="Winter Woodland Digital Paper",
            category="digital paper",
            style="Storybook Watercolor",
            palette="Winter forest greens",
            rendering_method="soft watercolor",
            composition="seamless pattern",
            mood="cozy winter woodland",
        )

        self.assertIn("Digital Paper", recipe.final_prompt)
        self.assertIn("3600x3600", recipe.final_prompt)
        self.assertIn("300", recipe.final_prompt)
        self.assertIn("seamless", recipe.final_prompt.casefold())
        self.assertIn("Bundle size: 12", recipe.commercial_requirements)


if __name__ == "__main__":
    unittest.main()
