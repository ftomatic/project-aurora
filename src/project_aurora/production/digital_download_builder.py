"""Build customer digital download ZIP packages for Aurora products."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from project_aurora.image_generation.commercial_image_exporter import (
    validate_commercial_png,
)


DIGITAL_DOWNLOAD_FILENAME = "Summer_Strawberry_Birthday_Collection.zip"


@dataclass(frozen=True, slots=True)
class DigitalDownloadPackageResult:
    """Result of building a customer download package."""

    status: str
    zip_path: str | None
    file_count: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "errors", tuple(self.errors))


class DigitalDownloadBuilder:
    """Package exactly four final PNG files into a customer ZIP."""

    def __init__(
        self,
        final_images_dir: Path,
        output_dir: Path,
        required_count: int = 4,
    ) -> None:
        self._final_images_dir = final_images_dir
        self._output_dir = output_dir
        self._required_count = required_count

    def build(self) -> DigitalDownloadPackageResult:
        """Build and validate the customer download ZIP."""
        image_files = self._image_files()
        errors = self._validate_image_files(image_files)
        if errors:
            return DigitalDownloadPackageResult(
                status="FAILED",
                zip_path=None,
                file_count=len(image_files),
                errors=errors,
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self._output_dir / DIGITAL_DOWNLOAD_FILENAME
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for image_path in image_files:
                archive.write(image_path, arcname=image_path.name)

        validation_errors = self.validate_zip(zip_path)
        return DigitalDownloadPackageResult(
            status="FAILED" if validation_errors else "SUCCESS",
            zip_path=str(zip_path),
            file_count=len(image_files),
            errors=validation_errors,
        )

    def _image_files(self) -> tuple[Path, ...]:
        if not self._final_images_dir.exists():
            return ()
        return tuple(
            sorted(self._final_images_dir.glob("*.png"), key=lambda path: path.name)
        )

    def _validate_image_files(self, image_files: tuple[Path, ...]) -> tuple[str, ...]:
        errors: list[str] = []
        if len(image_files) != self._required_count:
            errors.append(
                f"Expected exactly {self._required_count} final PNG files, "
                f"found {len(image_files)}."
            )
        for image_path in image_files:
            if "mock_generated_images" in image_path.parts:
                errors.append(f"Mock file is not allowed: {image_path.name}.")
            if "generated_images" in image_path.parts:
                errors.append(f"Source image is not allowed: {image_path.name}.")
            errors.extend(
                f"{image_path.name}: {error}"
                for error in validate_commercial_png(image_path)
            )
        return tuple(errors)

    def validate_zip(self, zip_path: Path) -> tuple[str, ...]:
        """Validate the ZIP contains only the four final PNG files."""
        errors: list[str] = []
        if not zip_path.exists():
            return (f"ZIP does not exist: {zip_path}",)
        if zip_path.stat().st_size <= 0:
            errors.append("ZIP file is empty.")
        try:
            with ZipFile(zip_path, "r") as archive:
                entries = archive.namelist()
        except OSError as error:
            return (f"ZIP is invalid: {error}",)
        png_entries = [entry for entry in entries if entry.endswith(".png")]
        if len(entries) != self._required_count or len(png_entries) != self._required_count:
            errors.append("ZIP must contain exactly 4 PNG entries.")
        for entry in entries:
            if "/" in entry or "\\" in entry:
                errors.append(f"ZIP entry must not include directories: {entry}.")
            if not entry.endswith(".png"):
                errors.append(f"ZIP entry must be a PNG file: {entry}.")
            lowered = entry.casefold()
            if lowered.endswith(".json") or "metadata" in lowered or "temp" in lowered:
                errors.append(f"ZIP entry is not allowed: {entry}.")
        return tuple(errors)
