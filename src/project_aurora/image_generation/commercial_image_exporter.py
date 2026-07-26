"""Export validated source images into commercial Etsy PNG files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from project_aurora.image_generation.image_inspector import (
    GeneratedImageInspection,
    inspect_png,
)


COMMERCIAL_IMAGE_COUNT = 4
COMMERCIAL_IMAGE_SIZE = (4000, 4000)
COMMERCIAL_IMAGE_DPI = 300
COMMERCIAL_FILENAME_PREFIX = "aurora_watercolor_clipart"
COMMERCIAL_ARTWORK_RATIO = 0.85
MAX_SINGLE_PNG_SIZE_BYTES = 4_500_000


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
        output_prefix: str = COMMERCIAL_FILENAME_PREFIX,
    ) -> None:
        self._source_dir = source_dir
        self._output_dir = output_dir
        self._required_count = required_count
        self._output_prefix = output_prefix

    def export(self) -> CommercialImageExportResult:
        """Export exactly four valid source images to commercial PNG files."""
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
        return self._output_dir / f"{self._output_prefix}_{index:02d}.png"

    @staticmethod
    def _export_one(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            working = _trim_transparent_bounds(image.convert("RGBA"))
            max_artwork = int(COMMERCIAL_IMAGE_SIZE[0] * COMMERCIAL_ARTWORK_RATIO)
            scale = min(max_artwork / working.width, max_artwork / working.height)
            resized_size = (
                max(1, int(round(working.width * scale))),
                max(1, int(round(working.height * scale))),
            )
            working = working.resize(resized_size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", COMMERCIAL_IMAGE_SIZE, (255, 255, 255, 0))
            left = (COMMERCIAL_IMAGE_SIZE[0] - working.width) // 2
            top = (COMMERCIAL_IMAGE_SIZE[1] - working.height) // 2
            canvas.alpha_composite(working, dest=(left, top))
            _save_optimized_png(canvas, output_path)


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


def _trim_transparent_bounds(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def _save_optimized_png(image: Image.Image, output_path: Path) -> None:
    image.save(
        output_path,
        format="PNG",
        dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
        optimize=True,
        compress_level=9,
    )
    if output_path.stat().st_size <= MAX_SINGLE_PNG_SIZE_BYTES:
        return
    image.quantize(colors=192, method=Image.Quantize.FASTOCTREE).save(
        output_path,
        format="PNG",
        dpi=(COMMERCIAL_IMAGE_DPI, COMMERCIAL_IMAGE_DPI),
        optimize=True,
        compress_level=9,
    )
