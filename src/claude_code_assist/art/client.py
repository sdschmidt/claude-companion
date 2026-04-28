"""Minimal Google Gemini image generation client."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-image-preview"


class GeminiImageClient:
    """Minimal client for generating images via the Google Gemini API.

    Uses the ``GEMINI_API_KEY`` environment variable for authentication
    when ``api_key`` is not passed explicitly.
    """

    def __init__(self, model: str = DEFAULT_GEMINI_MODEL, api_key: str | None = None) -> None:
        from google import genai  # noqa: PLC0415 — defer the heavy import

        resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "API key is required for Gemini art generation. "
                "Pass api_key explicitly or set GEMINI_API_KEY environment variable."
            )
        self._client = genai.Client(api_key=resolved_key)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def generate_sprite(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "9:16",
        resolution: str = "1k",
    ) -> Path:
        """Generate an image sprite sheet via Gemini and save as PNG."""
        from google.genai import types as gx  # noqa: PLC0415

        resolution_map = {"4k": "4K", "2k": "2K", "1k": "1K", "high": "1K"}
        image_size = resolution_map.get(resolution.lower(), "1K")

        image_config = gx.ImageConfig(image_size=image_size)
        if aspect_ratio:
            image_config.aspect_ratio = aspect_ratio

        config = gx.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=image_config,
        )

        logger.debug(
            "Calling Gemini API: model=%s, aspect_ratio=%s, resolution=%s",
            self._model,
            aspect_ratio,
            resolution,
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt],
                config=config,
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc

        image_bytes = self._extract_images(response)
        if not image_bytes:
            raise RuntimeError("Gemini API returned no images")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes[0])
        logger.info("Generated sprite saved to %s (%d bytes)", output_path, len(image_bytes[0]))
        return output_path

    @staticmethod
    def _extract_images(response: object) -> list[bytes]:
        images: list[bytes] = []
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return images

        first_candidate = candidates[0]
        content = getattr(first_candidate, "content", None)
        if not content:
            return images

        parts = getattr(content, "parts", [])
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and hasattr(inline_data, "data") and inline_data.data:
                images.append(inline_data.data)
        return images
