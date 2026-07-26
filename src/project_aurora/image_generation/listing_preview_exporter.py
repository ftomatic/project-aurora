"""Create Etsy listing preview images from transparent customer PNGs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from project_aurora.image_generation.image_inspector import inspect_png


PREVIEW_SIZE = (3000, 3000)
PREVIEW_DPI = 300
ARTWORK_FRAME_RATIO = 0.85
CREAM = (248, 243, 232, 255)


@dataclass(frozen=True, slots=True)
class ListingPreviewExportResult:
    """Result of creating Etsy preview listing images."""

    status: str
    preview_files: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "preview_files", tuple(self.preview_files))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))


class ListingPreviewExporter:
    """Export warm cream-background Etsy listing previews."""

    def __init__(
        self,
        final_images_dir: Path,
        output_dir: Path,
        output_prefix: str,
        required_count: int = 4,
    ) -> None:
        self._final_images_dir = final_images_dir
        self._output_dir = output_dir
        self._output_prefix = output_prefix
        self._required_count = required_count

    def export(self) -> ListingPreviewExportResult:
        """Create preview images from final transparent customer PNGs."""
        source_files = self._source_files()
        errors = self._validate_sources(source_files)
        if errors:
            return ListingPreviewExportResult(status="FAILED", errors=errors)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        preview_files: list[str] = []
        for index, source_path in enumerate(source_files, start=1):
            output_path = self._output_dir / f"{self._output_prefix}_preview_{index:02d}.png"
            self._export_one(source_path, output_path)
            preview_files.append(str(output_path))
        return ListingPreviewExportResult(status="SUCCESS", preview_files=tuple(preview_files))

    def _source_files(self) -> tuple[Path, ...]:
        if not self._final_images_dir.exists():
            return ()
        return tuple(sorted(self._final_images_dir.glob("*.png"), key=lambda item: item.name))

    def _validate_sources(self, source_files: tuple[Path, ...]) -> tuple[str, ...]:
        errors: list[str] = []
        if len(source_files) != self._required_count:
            errors.append(
                f"Expected exactly {self._required_count} final PNG files, found {len(source_files)}."
            )
        for path in source_files:
            inspection = inspect_png(path)
            if not inspection.is_valid:
                errors.append(f"{path.name}: invalid source image ({inspection.classification}).")
        return tuple(errors)

    @staticmethod
    def _export_one(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            artwork = image.convert("RGBA")
            artwork = _trim_transparent_bounds(artwork)
            max_art = int(PREVIEW_SIZE[0] * ARTWORK_FRAME_RATIO)
            artwork.thumbnail((max_art, max_art), Image.Resampling.LANCZOS)
            canvas = _paper_texture()
            left = (PREVIEW_SIZE[0] - artwork.width) // 2
            top = (PREVIEW_SIZE[1] - artwork.height) // 2
            canvas.alpha_composite(artwork, (left, top))
            canvas.save(output_path, format="PNG", dpi=(PREVIEW_DPI, PREVIEW_DPI))


def _trim_transparent_bounds(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def _paper_texture() -> Image.Image:
    canvas = Image.new("RGBA", PREVIEW_SIZE, CREAM)
    draw = ImageDraw.Draw(canvas, "RGBA")
    for offset in range(0, PREVIEW_SIZE[0], 34):
        draw.line(
            ((offset, 0), (offset - PREVIEW_SIZE[0] // 3, PREVIEW_SIZE[1])),
            fill=(255, 255, 255, 12),
            width=2,
        )
    for offset in range(0, PREVIEW_SIZE[1], 41):
        draw.line(
            ((0, offset), (PREVIEW_SIZE[0], offset + PREVIEW_SIZE[1] // 4)),
            fill=(218, 204, 182, 10),
            width=1,
        )
    return canvas
