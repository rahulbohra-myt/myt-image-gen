"""Nano Banana Pro (Gemini 3 Pro Image) implementation of BaseImageProvider."""

import os
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image
from rich.console import Console

from providers.base import BaseImageProvider, GenerationResult, ImageOutcome
from utils.retry import call_with_retry

console = Console()


class NanoBananaProProvider(BaseImageProvider):
    """Generates images via Gemini 3 Pro Image, called through the google-genai SDK."""

    SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = (
        "1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9",
    )

    def __init__(self, model_name: str) -> None:
        """Store the model name and build the google-genai client from GEMINI_API_KEY."""
        super().__init__(model_name)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set. Add it to .env before generating images.")
        self.client = genai.Client(api_key=api_key)

    def generate(
        self,
        prompt: str,
        campaign: str,
        reference_images: list[Path],
        count: int,
        aspect_ratio: str,
        resolution: str,
        output_dir: Path,
    ) -> GenerationResult:
        """Generate `count` images, one API call per image, saving successes and recording failures."""
        self.validate_params(aspect_ratio, resolution)

        contents: list = [prompt] + [Image.open(p) for p in reference_images]
        config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=resolution),
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        outcomes: list[ImageOutcome] = []
        for i in range(1, count + 1):
            with console.status(f"[bold cyan]Generating image {i}/{count}..."):
                try:
                    response = self._call_with_retry(contents, config)
                    image = _extract_image(response)
                    if image is None:
                        outcomes.append(ImageOutcome(success=False, error="No image returned in API response"))
                        continue
                    out_path = self.build_output_path(campaign, timestamp, i, output_dir)
                    image.save(out_path)
                    outcomes.append(ImageOutcome(success=True, path=out_path))
                except Exception as e:
                    outcomes.append(ImageOutcome(success=False, error=str(e)))

        return GenerationResult(outcomes=outcomes)

    def _call_with_retry(self, contents: list, config: types.GenerateContentConfig) -> types.GenerateContentResponse:
        """Call generate_content, retrying (via the shared retry util) on transient errors."""
        return call_with_retry(
            lambda: self.client.models.generate_content(model=self.model_name, contents=contents, config=config),
            console=console,
        )


def _extract_image(response: types.GenerateContentResponse) -> Image.Image | None:
    """Pull the first inline image out of a generate_content response, or None if there isn't one."""
    for part in response.parts:
        image = part.as_image()
        if image is not None:
            return image
    return None
