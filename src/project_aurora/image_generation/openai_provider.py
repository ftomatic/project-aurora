"""OpenAI GPT Image provider adapter."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.image_request import ImageRequest
from project_aurora.image_generation.image_result import ImageResult


class OpenAIImageProvider(ImageProvider):
    """Generate images through OpenAI GPT Image models."""

    def __init__(
        self,
        output_dir: Path | None = None,
        api_key: str | None = None,
        model: str = "gpt-image-1",
        client: Any | None = None,
    ) -> None:
        self._output_dir = output_dir or Path("data") / "aurora" / "generated_images"
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        self._client = client

    def generate_image(self, request: ImageRequest) -> ImageResult:
        """Generate image files through OpenAI and save them locally."""
        if not self.health_check():
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI image generation.")

        started_at = perf_counter()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or self._build_client()
        response = client.images.generate(
            model=self._model,
            prompt=request.prompt,
            size=request.size,
            quality=request.quality,
            background=request.background,
            output_format=request.output_format,
            n=request.number_of_images,
        )
        generated_files = self._save_response_images(response, request)

        return ImageResult(
            status="SUCCESS",
            provider=self.provider_name(),
            generated_files=tuple(generated_files),
            generation_time=perf_counter() - started_at,
            cost_estimate=0.0,
            estimated_cost=0.0,
            image_paths=tuple(generated_files),
            prompt_version="openai-gpt-image-v1",
            metadata={
                "model": self._model,
                "size": request.size,
                "quality": request.quality,
                "background": request.background,
                "output_format": request.output_format,
                "number_of_images": request.number_of_images,
                "prompt": request.prompt,
            },
        )

    def health_check(self) -> bool:
        """Return whether the provider has enough configuration to run."""
        return bool(self._api_key or self._client)

    def provider_name(self) -> str:
        """Return the provider display name."""
        return "OpenAI GPT Image"

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "OpenAI image generation requires the openai package. "
                "Install dependencies with python3.14 -m pip install -r requirements.txt."
            ) from error
        return OpenAI(api_key=self._api_key)

    def _save_response_images(
        self,
        response: Any,
        request: ImageRequest,
    ) -> tuple[str, ...]:
        data_items = getattr(response, "data", [])
        generated_files: list[str] = []
        slug = self._slugify(request.product_name)

        for index, item in enumerate(data_items, start=1):
            image_base64 = getattr(item, "b64_json", None)
            if image_base64 is None and isinstance(item, dict):
                image_base64 = item.get("b64_json")
            if not image_base64:
                continue

            path = self._output_dir / f"{slug}_{index:02d}.{request.output_format}"
            path.write_bytes(base64.b64decode(image_base64))
            generated_files.append(str(path))

        if not generated_files:
            raise RuntimeError("OpenAI response did not contain image data.")
        return tuple(generated_files)

    @staticmethod
    def _slugify(value: str) -> str:
        return (
            value.casefold()
            .replace("&", "and")
            .replace("/", "_")
            .replace(" ", "_")
        )
