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
COMMERCIAL_IMAGE_SIZE = (3600, 3600)
COMMERCIAL_IMAGE_DPI = 300
COMMERCIAL_FILENAME_PREFIX = "strawberry_birthday_party_printable"


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
    ) -> None:
        self._source_dir = source_dir
        self._output_dir = output_dir
        self._required_count = required_count

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
        return self._output_dir / f"{COMMERCIAL_FILENAME_PREFIX}_{index:02d}.png"

    @staticmethod
    def _export_one(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            resized = image.convert("RGBA").resize(
                COMMERCIAL_IMAGE_SIZE,
                Image.Resampling.LANCZOS,
            )
            resized.save(
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
