"""Export validated source images into commercial Etsy PNG files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat

from project_aurora.image_generation.image_inspector import (
    GeneratedImageInspection,
    inspect_png,
)


COMMERCIAL_IMAGE_COUNT = 4
COMMERCIAL_IMAGE_SIZE = (4000, 4000)
COMMERCIAL_IMAGE_DPI = 300
COMMERCIAL_FILENAME_PREFIX = "strawberry_birthday_party_printable"
WALL_ART_RATIOS: tuple[tuple[str, tuple[int, int]], ...] = (
    ("2x3", (2667, 4000)),
    ("3x4", (3000, 4000)),
    ("4x5", (3200, 4000)),
    ("11x14", (3143, 4000)),
    ("iso", (2828, 4000)),
)
WALL_ART_PREVIEW_SIZE = (1800, 1200)
WALL_ART_MIN_SHARPNESS = 30.0
DIGITAL_PAPER_IMAGE_SIZE = (3600, 3600)
DIGITAL_PAPER_PREVIEW_SIZE = (1800, 1800)
DIGITAL_PAPER_JPEG_QUALITY = 90
DIGITAL_PAPER_MIN_SHARPNESS = 20.0
PARTY_PRINTABLE_IMAGE_SIZE = (2550, 3300)
PARTY_PRINTABLE_PREVIEW_SIZE = (1800, 1200)
STICKER_IMAGE_SIZE = (4000, 4000)
STICKER_PREVIEW_SIZE = (1800, 1800)


@dataclass(frozen=True, slots=True)
class CommercialImageExportResult:
    """Result of exporting final commercial PNG files."""

    status: str
    exported_files: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    inspections: tuple[GeneratedImageInspection, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "exported_files", tuple(self.exported_files))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "inspections", tuple(self.inspections))


class CommercialImageExporter:
    """Create final commercial-ready PNG exports from valid source images."""

    def __init__(
        self,
        source_dir: Path,
        output_dir: Path,
        required_count: int = COMMERCIAL_IMAGE_COUNT,
        category: str = "",
    ) -> None:
        self._source_dir = source_dir
        self._output_dir = output_dir
        self._required_count = required_count
        self._category = category

    def export(self) -> CommercialImageExportResult:
        """Export the exact category-specific commercial deliverables."""
        source_files = self._valid_source_files()
        if len(source_files) != self._required_count:
            return CommercialImageExportResult(
                status="FAILED",
                errors=(
                    "Expected exactly "
                    f"{self._required_count} valid source PNG files, found "
                    f"{len(source_files)}.",
                ),
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._clear_existing_final_files()
        if self._is_printable_wall_art:
            return self._export_printable_wall_art(source_files)
        if self._is_digital_paper:
            return self._export_digital_paper(source_files)
        if self._is_party_printable:
            return self._export_party_printable(source_files)
        if self._is_stickers:
            return self._export_stickers(source_files)
        exported_files: list[str] = []
        inspections: list[GeneratedImageInspection] = []
        errors: list[str] = []
        for index, source_path in enumerate(source_files, start=1):
            output_path = self._output_path(index)
            self._export_one(source_path, output_path)
            validation_errors = validate_commercial_png(output_path)
            if validation_errors:
                errors.extend(
                    f"{output_path.name}: {error}" for error in validation_errors
                )
            exported_files.append(str(output_path))
            inspections.append(inspect_png(output_path))

        return CommercialImageExportResult(
            status="FAILED" if errors else "SUCCESS",
            exported_files=tuple(exported_files),
            errors=tuple(errors),
            inspections=tuple(inspections),
        )

    def _valid_source_files(self) -> list[Path]:
        if not self._source_dir.exists():
            return []
        valid_files: list[Path] = []
        for path in sorted(self._source_dir.glob("*.png"), key=lambda item: item.name):
            if inspect_png(path).is_valid:
                valid_files.append(path)
        return valid_files

    def _output_path(self, index: int) -> Path:
        return self._output_dir / f"{COMMERCIAL_FILENAME_PREFIX}_{index:02d}.png"

    def _clear_existing_final_files(self) -> None:
        for path in self._output_dir.glob("*"):
            if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".zip"}:
                path.unlink()

    @staticmethod
    def _export_one(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            converted = image.convert("RGBA")
            converted.thumbnail(COMMERCIAL_IMAGE_SIZE, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", COMMERCIAL_IMAGE_SIZE, (255, 255, 255, 0))
            x = (COMMERCIAL_IMAGE_SIZE[0] - converted.width) // 2
            y = (COMMERCIAL_IMAGE_SIZE[1] - converted.height) // 2
            canvas.paste(converted, (x, y), converted)
            canvas.save(
                output_path,
                format="PNG",
                dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
            )

    @property
    def _is_printable_wall_art(self) -> bool:
        return self._category.casefold() == "printable wall art"

    @property
    def _is_digital_paper(self) -> bool:
        return self._category.casefold() == "digital paper"

    @property
    def _is_party_printable(self) -> bool:
        return self._category.casefold() == "party printables"

    @property
    def _is_stickers(self) -> bool:
        return self._category.casefold() == "stickers"

    def _export_stickers(
        self,
        source_files: list[Path],
    ) -> CommercialImageExportResult:
        exported_files: list[str] = []
        inspections: list[GeneratedImageInspection] = []
        errors: list[str] = []
        for index, source_path in enumerate(source_files, start=1):
            output_path = self._output_dir / f"sticker_{index:02d}.png"
            self._export_transparent_sticker_png(source_path, output_path)
            validation_errors = validate_commercial_png(output_path)
            if validation_errors:
                errors.extend(
                    f"{output_path.name}: {error}" for error in validation_errors
                )
            exported_files.append(str(output_path))
            inspections.append(inspect_png(output_path))
        preview_path = self._output_dir / "sticker_sheet_preview.png"
        self._export_sticker_preview(tuple(Path(path) for path in exported_files), preview_path)
        return CommercialImageExportResult(
            status="FAILED" if errors else "SUCCESS",
            exported_files=tuple(exported_files),
            errors=tuple(errors),
            inspections=tuple(inspections),
        )

    def _export_digital_paper(
        self,
        source_files: list[Path],
    ) -> CommercialImageExportResult:
        exported_files: list[str] = []
        errors: list[str] = []
        for index, source_path in enumerate(source_files, start=1):
            output_path = self._output_dir / f"digital_paper_{index:02d}.jpg"
            self._export_square_jpg(
                source_path,
                output_path,
                DIGITAL_PAPER_IMAGE_SIZE,
                quality=DIGITAL_PAPER_JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
            validation_errors = validate_commercial_jpg(
                output_path,
                DIGITAL_PAPER_IMAGE_SIZE,
                minimum_sharpness=DIGITAL_PAPER_MIN_SHARPNESS,
            )
            if validation_errors:
                errors.extend(
                    f"{output_path.name}: {error}" for error in validation_errors
                )
            exported_files.append(str(output_path))
        preview_path = self._output_dir / "collage_preview.jpg"
        self._export_square_jpg(
            source_files[0],
            preview_path,
            DIGITAL_PAPER_PREVIEW_SIZE,
            quality=DIGITAL_PAPER_JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        return CommercialImageExportResult(
            status="FAILED" if errors else "SUCCESS",
            exported_files=tuple(exported_files),
            errors=tuple(errors),
            inspections=(),
        )

    def _export_party_printable(
        self,
        source_files: list[Path],
    ) -> CommercialImageExportResult:
        exported_files: list[str] = []
        errors: list[str] = []
        for index, source_path in enumerate(source_files, start=1):
            output_path = self._output_dir / f"party_printable_{index:02d}.jpg"
            self._export_contained_jpg(source_path, output_path, PARTY_PRINTABLE_IMAGE_SIZE)
            validation_errors = validate_commercial_jpg(
                output_path,
                PARTY_PRINTABLE_IMAGE_SIZE,
            )
            if validation_errors:
                errors.extend(
                    f"{output_path.name}: {error}" for error in validation_errors
                )
            exported_files.append(str(output_path))
        preview_path = self._output_dir / "bundle_preview.jpg"
        self._export_wall_art_jpg(source_files[0], preview_path, PARTY_PRINTABLE_PREVIEW_SIZE)
        return CommercialImageExportResult(
            status="FAILED" if errors else "SUCCESS",
            exported_files=tuple(exported_files),
            errors=tuple(errors),
            inspections=(),
        )

    def _export_printable_wall_art(
        self,
        source_files: list[Path],
    ) -> CommercialImageExportResult:
        exported_files: list[str] = []
        errors: list[str] = []
        for source_path, (label, size) in zip(source_files, WALL_ART_RATIOS):
            output_path = self._output_dir / f"printable_wall_art_{label}.jpg"
            self._export_contained_jpg(source_path, output_path, size)
            validation_errors = validate_commercial_jpg(
                output_path,
                size,
                minimum_sharpness=WALL_ART_MIN_SHARPNESS,
            )
            if validation_errors:
                errors.extend(
                    f"{output_path.name}: {error}" for error in validation_errors
                )
            exported_files.append(str(output_path))
        preview_path = self._output_dir / "lifestyle_preview.jpg"
        self._export_wall_art_jpg(source_files[0], preview_path, WALL_ART_PREVIEW_SIZE)
        return CommercialImageExportResult(
            status="FAILED" if errors else "SUCCESS",
            exported_files=tuple(exported_files),
            errors=tuple(errors),
            inspections=(),
        )

    @staticmethod
    def _export_wall_art_jpg(
        source_path: Path,
        output_path: Path,
        size: tuple[int, int],
    ) -> None:
        with Image.open(source_path) as image:
            rendered = _cover_resize(image.convert("RGB"), size)
            rendered.save(
                output_path,
                format="JPEG",
                dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
                quality=95,
            )

    @staticmethod
    def _export_contained_jpg(
        source_path: Path,
        output_path: Path,
        size: tuple[int, int],
    ) -> None:
        with Image.open(source_path) as image:
            rendered = _contain_resize_on_canvas(image.convert("RGB"), size)
            rendered.save(
                output_path,
                format="JPEG",
                dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
                quality=95,
            )

    @staticmethod
    def _export_square_jpg(
        source_path: Path,
        output_path: Path,
        size: tuple[int, int],
        quality: int = 95,
        optimize: bool = False,
        progressive: bool = False,
    ) -> None:
        with Image.open(source_path) as image:
            rendered = image.convert("RGB").resize(
                size,
                Image.Resampling.LANCZOS,
            )
            rendered.save(
                output_path,
                format="JPEG",
                dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
                quality=quality,
                optimize=optimize,
                progressive=progressive,
            )

    @staticmethod
    def _export_transparent_sticker_png(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            rendered = image.convert("RGBA").resize(
                STICKER_IMAGE_SIZE,
                Image.Resampling.LANCZOS,
            )
            alpha = rendered.getchannel("A")
            light_background_mask = rendered.convert("L").point(
                lambda value: 0 if value >= 245 else 255,
                mode="L",
            )
            rendered.putalpha(ImageChops.multiply(alpha, light_background_mask))
            rendered.save(
                output_path,
                format="PNG",
                dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
            )

    @staticmethod
    def _export_sticker_preview(
        sticker_files: tuple[Path, ...],
        output_path: Path,
    ) -> None:
        canvas = Image.new("RGBA", STICKER_PREVIEW_SIZE, (255, 255, 255, 255))
        columns = 4
        rows = max(1, (len(sticker_files) + columns - 1) // columns)
        cell_width = STICKER_PREVIEW_SIZE[0] // columns
        cell_height = STICKER_PREVIEW_SIZE[1] // rows
        for index, sticker_path in enumerate(sticker_files):
            with Image.open(sticker_path) as image:
                sticker = image.convert("RGBA")
                sticker.thumbnail(
                    (int(cell_width * 0.78), int(cell_height * 0.78)),
                    Image.Resampling.LANCZOS,
                )
                column = index % columns
                row = index // columns
                left = column * cell_width + (cell_width - sticker.width) // 2
                top = row * cell_height + (cell_height - sticker.height) // 2
                canvas.alpha_composite(sticker, (left, top))
        canvas.save(
            output_path,
            format="PNG",
            dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
        )


def validate_commercial_png(path: Path) -> tuple[str, ...]:
    """Return validation errors for one final commercial PNG."""
    errors: list[str] = []
    inspection = inspect_png(path)
    if not path.exists():
        return (f"File does not exist: {path}",)
    if path.stat().st_size <= 0:
        errors.append("File is empty.")
    if not inspection.is_valid:
        errors.append(f"Image is not visually valid: {inspection.classification}.")
    if inspection.dimensions != COMMERCIAL_IMAGE_SIZE:
        errors.append(
            "Image dimensions must be "
            f"{COMMERCIAL_IMAGE_SIZE[0]}x{COMMERCIAL_IMAGE_SIZE[1]} pixels."
        )
    try:
        with Image.open(path) as image:
            dpi = image.info.get("dpi")
    except OSError:
        dpi = None
    if not _dpi_is_acceptable(dpi):
        errors.append("Image must include 300-DPI metadata.")
    return tuple(errors)


def validate_commercial_jpg(
    path: Path,
    expected_size: tuple[int, int],
    minimum_sharpness: float | None = None,
) -> tuple[str, ...]:
    """Return validation errors for one final commercial JPG."""
    errors: list[str] = []
    if not path.exists():
        return (f"File does not exist: {path}",)
    if path.stat().st_size <= 0:
        errors.append("File is empty.")
    try:
        with Image.open(path) as image:
            size = image.size
            mode = image.mode
            fmt = (image.format or "").casefold()
            dpi = image.info.get("dpi")
    except OSError:
        return ("File is not a readable image.",)
    if fmt != "jpeg" or path.suffix.casefold() not in {".jpg", ".jpeg"}:
        errors.append("File must be a JPG image.")
    if mode != "RGB":
        errors.append("JPG files must be RGB.")
    if size != expected_size:
        errors.append(
            f"Image dimensions must be {expected_size[0]}x{expected_size[1]} pixels."
        )
    if not _dpi_is_acceptable(dpi):
        errors.append("Image must include 300-DPI metadata.")
    if minimum_sharpness is not None:
        sharpness = image_sharpness_score(path)
        if sharpness < minimum_sharpness:
            errors.append(
                "Image is too blurry for commercial delivery: "
                f"sharpness score {sharpness:.2f}, minimum {minimum_sharpness:.2f}."
            )
    return tuple(errors)


def image_sharpness_score(path: Path) -> float:
    """Return a deterministic edge sharpness score for a rendered image."""
    try:
        with Image.open(path) as image:
            grayscale = image.convert("L")
            if max(grayscale.size) < 64:
                return 100.0
            if max(grayscale.size) > 512:
                grayscale.thumbnail((512, 512), Image.Resampling.LANCZOS)
            laplacian = grayscale.filter(
                ImageFilter.Kernel(
                    (3, 3),
                    (0, 1, 0, 1, -4, 1, 0, 1, 0),
                    scale=1,
                    offset=128,
                )
            )
            return float(ImageStat.Stat(laplacian).stddev[0])
    except OSError:
        return 0.0


def _cover_resize(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    target_width, target_height = target_size
    source_width, source_height = image.size
    scale = max(target_width / source_width, target_height / source_height)
    resized = image.resize(
        (
            max(1, round(source_width * scale)),
            max(1, round(source_height * scale)),
        ),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _contain_resize_on_canvas(
    image: Image.Image,
    target_size: tuple[int, int],
    background: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    target_width, target_height = target_size
    source_width, source_height = image.size
    scale = min(target_width / source_width, target_height / source_height)
    resized = image.resize(
        (
            max(1, round(source_width * scale)),
            max(1, round(source_height * scale)),
        ),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", target_size, background)
    left = max(0, (target_width - resized.width) // 2)
    top = max(0, (target_height - resized.height) // 2)
    canvas.paste(resized, (left, top))
    return canvas


def _dpi_is_acceptable(dpi: object, tolerance: float = 1.0) -> bool:
    if not isinstance(dpi, tuple) or len(dpi) < 2:
        return False
    try:
        horizontal = float(dpi[0])
        vertical = float(dpi[1])
    except (TypeError, ValueError):
        return False
    return (
        abs(horizontal - COMMERCIAL_IMAGE_DPI) <= tolerance
        and abs(vertical - COMMERCIAL_IMAGE_DPI) <= tolerance
    )
