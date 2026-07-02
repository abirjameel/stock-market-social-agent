"""Composites the AI-generated background, the data-driven chart, and text
overlays into the final square post image, and writes it to a temp file.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from agent.agent import PostDraftContent
from imaging.ai_background import generate_ai_background
from imaging.chart import render_index_chart

CANVAS_SIZE = (1080, 1080)
PANEL_COLOR = (10, 14, 24, 175)


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    # Reuse the DejaVu Sans font that ships with matplotlib so we get decent
    # typography without bundling extra font files in the repo.
    weight = "bold" if bold else "normal"
    font_path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight=weight))
    return ImageFont.truetype(font_path, size)


def compose_post_image(indices: list[dict], content: PostDraftContent) -> Path:
    background = generate_ai_background(content.image_style_prompt, CANVAS_SIZE)
    canvas = background.convert("RGBA")

    # Darken panel behind text for legibility over an unpredictable AI background.
    top_panel = Image.new("RGBA", (CANVAS_SIZE[0], 260), PANEL_COLOR)
    canvas.alpha_composite(top_panel, (0, 0))

    draw = ImageDraw.Draw(canvas)
    headline_font = _load_font(64)
    subtext_font = _load_font(34, bold=False)
    date_font = _load_font(24, bold=False)

    date_str = datetime.date.today().strftime("%B %d, %Y")
    draw.text((48, 32), f"US MARKET RECAP · {date_str}", font=date_font, fill=(200, 210, 225, 255))
    draw.text((48, 76), content.image_headline, font=headline_font, fill=(255, 255, 255, 255))
    draw.text((48, 170), content.image_subtext, font=subtext_font, fill=(220, 225, 235, 255))

    chart_img = render_index_chart(indices, size_px=(CANVAS_SIZE[0] - 96, CANVAS_SIZE[1] - top_panel.height - 96))
    chart_panel = Image.new("RGBA", (CANVAS_SIZE[0], chart_img.height + 64), PANEL_COLOR)
    chart_panel.alpha_composite(chart_img, (48, 32))
    canvas.alpha_composite(chart_panel, (0, top_panel.height + 32))

    final_image = canvas.convert("RGB")
    output_path = Path(tempfile.gettempdir()) / f"market_post_{datetime.date.today().isoformat()}.jpg"
    final_image.save(output_path, format="JPEG", quality=92)
    return output_path
