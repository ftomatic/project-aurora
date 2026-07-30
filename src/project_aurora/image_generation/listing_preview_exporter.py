"""Create Etsy listing preview images from transparent customer PNGs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from project_aurora.image_generation.image_inspector import inspect_png


PREVIEW_SIZE = (3000, 3000)
PREVIEW_DPI = 300
ARTWORK_FRAME_RATIO = 0.85
SCENE_FRAME_RATIO = 0.96
CREAM = (248, 243, 232, 255)
LISTING_FAMILY_AUTO = "AUTO"
LISTING_FAMILY_CLIPART = "CLIPART"
LISTING_FAMILY_STORYBOOK = "STORYBOOK"
SUPPORTED_LISTING_FAMILIES = {
    LISTING_FAMILY_AUTO,
    LISTING_FAMILY_CLIPART,
    LISTING_FAMILY_STORYBOOK,
}


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
        storybook_scenes_dir: Path | None = None,
        required_count: int = 4,
        listing_family: str = LISTING_FAMILY_AUTO,
    ) -> None:
        self._final_images_dir = final_images_dir
        self._storybook_scenes_dir = storybook_scenes_dir
        self._output_dir = output_dir
        self._output_prefix = output_prefix
        self._required_count = required_count
        self._listing_family = listing_family.strip().upper()
        if self._listing_family not in SUPPORTED_LISTING_FAMILIES:
            raise ValueError(f"Unsupported listing family: {listing_family}.")

    def export(self) -> ListingPreviewExportResult:
        """Create preview images from final transparent customer PNGs."""
        source_files = self._source_files()
        errors = self._validate_sources(source_files)
        if errors:
            return ListingPreviewExportResult(status="FAILED", errors=errors)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        preview_files: list[str] = []
        scene_file = self._storybook_scene_file()
        listing_family = self._resolved_listing_family(scene_file)
        start_index = 1
        if listing_family == LISTING_FAMILY_STORYBOOK:
            if scene_file is None:
                return ListingPreviewExportResult(
                    status="FAILED",
                    errors=("Storybook listing family requires a completed storybook scene.",),
                )
            output_path = self._output_dir / f"{self._output_prefix}_preview_01.png"
            self._export_scene(scene_file, output_path)
            preview_files.append(str(output_path))
            start_index = 2
        for index, source_path in enumerate(source_files, start=start_index):
            output_path = self._output_dir / f"{self._output_prefix}_preview_{index:02d}.png"
            self._export_one(source_path, output_path)
            preview_files.append(str(output_path))
        return ListingPreviewExportResult(status="SUCCESS", preview_files=tuple(preview_files))

    def _source_files(self) -> tuple[Path, ...]:
        if not self._final_images_dir.exists():
            return ()
        return tuple(sorted(self._final_images_dir.glob("*.png"), key=lambda item: item.name))

    def _resolved_listing_family(self, scene_file: Path | None) -> str:
        if self._listing_family != LISTING_FAMILY_AUTO:
            return self._listing_family
        return LISTING_FAMILY_STORYBOOK if scene_file is not None else LISTING_FAMILY_CLIPART

    def _storybook_scene_file(self) -> Path | None:
        if self._storybook_scenes_dir is None or not self._storybook_scenes_dir.exists():
            return None
        scenes = tuple(sorted(self._storybook_scenes_dir.glob("*.png"), key=lambda item: item.name))
        return scenes[0] if scenes else None

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

    @staticmethod
    def _export_scene(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            scene = image.convert("RGBA")
            max_scene = int(PREVIEW_SIZE[0] * SCENE_FRAME_RATIO)
            scene.thumbnail((max_scene, max_scene), Image.Resampling.LANCZOS)
            canvas = _paper_texture()
            left = (PREVIEW_SIZE[0] - scene.width) // 2
            top = (PREVIEW_SIZE[1] - scene.height) // 2
            canvas.alpha_composite(scene, (left, top))
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
