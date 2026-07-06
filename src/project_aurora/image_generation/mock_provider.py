"""Mock image provider for local Aurora pipeline testing."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.image_request import ImageRequest
from project_aurora.image_generation.image_result import ImageResult


PLACEHOLDER_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
    b"\x02\xfeA\xd8\x8f\x8d\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MockImageProvider(ImageProvider):
    """Create local placeholder image files without external APIs."""

    def __init__(self, output_dir: Path | None = None, image_count: int = 8) -> None:
        self._output_dir = output_dir or Path("data") / "aurora" / "generated_images"
        self._image_count = image_count

    def generate_image(self, request: ImageRequest) -> ImageResult:
        """Generate placeholder PNG files for a request."""
        started_at = perf_counter()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        slug = self._slugify(request.product_name)
        generated_files: list[str] = []

        for index in range(1, self._image_count + 1):
            path = self._output_dir / f"{slug}_{index:02d}.png"
            with path.open("wb") as image_file:
                image_file.write(PLACEHOLDER_PNG_BYTES)
            generated_files.append(str(path))

        return ImageResult(
            status="SUCCESS",
            provider=self.provider_name(),
            generated_files=tuple(generated_files),
            generation_time=perf_counter() - started_at,
            cost_estimate=0.0,
            warnings=("Mock provider generated placeholder files only.",),
            metadata={
                "image_count": self._image_count,
                "image_type": request.image_type,
                "width": request.width,
                "height": request.height,
                "dpi": request.dpi,
                "transparent_background": request.transparent_background,
            },
        )

    def health_check(self) -> bool:
        """Return whether the mock provider can run locally."""
        return True

    def provider_name(self) -> str:
        """Return the provider display name."""
        return "Mock Provider"

    @staticmethod
    def _slugify(value: str) -> str:
        return (
            value.casefold()
            .replace("&", "and")
            .replace("/", "_")
            .replace(" ", "_")
        )
