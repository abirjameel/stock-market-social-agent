"""Generates the stylistic accent/background layer using Gemini's native
image generation model (`gemini-2.5-flash-image`, aka "Nano Banana").

Imagen (the old `generate_images` API) was deprecated in August 2026, so we
use `generate_content` with `response_modalities=["IMAGE"]` instead.
"""

from __future__ import annotations

from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

from services.config import config

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        # If GOOGLE_GENAI_USE_VERTEXAI=true (recommended for Cloud Run, uses the
        # service account's ADC), no API key is needed. Otherwise pass GEMINI_API_KEY.
        api_key = config.gemini_api_key()
        _client = genai.Client(api_key=api_key) if api_key else genai.Client()
    return _client


def generate_ai_background(style_prompt: str, size_px: tuple[int, int] = (1080, 1080)) -> Image.Image:
    """Generate a square abstract background image from a text prompt.

    Falls back to a plain dark navy background if generation fails, so a
    transient model error never blocks the whole daily pipeline.
    """

    prompt = (
        f"{style_prompt}. Abstract, professional, minimalistic financial design, "
        "no readable text, no numbers, no charts, no logos, subtle gradient, "
        f"square composition {size_px[0]}x{size_px[1]}."
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.image_model,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                return image.resize(size_px)
    except Exception:  # noqa: BLE001 - never let image generation kill the pipeline
        pass

    return Image.new("RGB", size_px, color=(12, 20, 38))
