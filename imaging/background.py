"""Deterministic, brand-consistent background generator: a soft "watercolor
blob" gradient using WTR's exact peach/blue palette (sampled directly from
the brand logo files), rendered procedurally with Pillow.

Deliberately NOT AI-generated. Earlier iterations asked an image model for
an abstract background and it kept hallucinating readable text, fake
numbers, and dashboard-style UI elements no matter how the prompt was
worded. A hand-drawn gradient is 100% deterministic, guarantees exact brand
color matching, costs nothing, and can never hallucinate.
"""

from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageFilter

CREAM = (246, 244, 240)

# Sampled directly from assets/branding/logo_peach.png / logo_blue.png so the
# generated background always reads as "the same brand" as the logo badge.
PALETTES = {
    "bullish": [(245, 205, 180), (246, 223, 207), (246, 230, 219), (250, 214, 165)],
    "bearish": [(186, 202, 232), (213, 222, 235), (224, 230, 237), (170, 190, 225)],
}


def generate_brand_background(
    mood: str,
    size_px: tuple[int, int] = (1080, 1080),
    seed: int | None = None,
) -> Image.Image:
    """Render a soft, brand-colored watercolor-blob background.

    `mood` selects the palette family: "bullish" (warm peach/coral, matches
    the warm WTR logo variant) or "bearish" (soft blue, matches the cool WTR
    logo variant). Any other value falls back to "bullish".
    """

    colors = PALETTES.get(mood, PALETTES["bullish"])
    rng = random.Random(seed if seed is not None else 7)

    w, h = size_px
    blob_layer = Image.new("RGBA", size_px, (0, 0, 0, 0))
    draw = ImageDraw.Draw(blob_layer)

    for _ in range(6):
        color = rng.choice(colors)
        radius = rng.uniform(0.22, 0.42) * max(w, h)
        cx = rng.uniform(-0.15, 1.15) * w
        cy = rng.uniform(-0.15, 1.15) * h
        alpha = rng.randint(70, 130)
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        draw.ellipse(bbox, fill=(*color, alpha))

    blob_layer = blob_layer.filter(ImageFilter.GaussianBlur(radius=max(w, h) * 0.06))

    canvas = Image.new("RGBA", size_px, (*CREAM, 255))
    canvas.alpha_composite(blob_layer)
    return canvas.convert("RGB")
