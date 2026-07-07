"""Composites the WTR-branded post image: logo badge, headline/subtext, the
data-driven index chart, the "MAG10 market movement" grid, the bull mascot,
and a footer branding bar - and writes the final square JPEG to a temp file.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from agent.agent import PostDraftContent
from imaging.background import generate_brand_background
from imaging.chart import render_index_chart
from imaging.movers import render_movers_grid

CANVAS_SIZE = (1080, 1080)
MARGIN = 48
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "branding"

# Light "frosted glass" panels over the brand watercolor background - opaque
# enough for text legibility, translucent enough that the blob colors still
# show through as a subtle tint rather than being fully hidden.
PANEL_COLOR = (255, 255, 255, 215)
TEXT_DARK = (32, 36, 48, 255)
TEXT_MUTED = (100, 105, 120, 255)
ACCENT_BULLISH = (214, 122, 63, 255)
ACCENT_BEARISH = (74, 100, 158, 255)

LOGO_SIZE = 108
MASCOT_HEIGHT = 240


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    weight = "bold" if bold else "normal"
    font_path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight=weight))
    return ImageFont.truetype(font_path, size)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    """Word-wrap `text` to fit within `max_width` px, hard-capped at
    `max_lines` (ellipsizing the last line if content still doesn't fit).

    This is the actual overflow guardrail: the agent's word-count guidance is
    only a soft hint the LLM sometimes ignores, and a raw `draw.text()` call
    has no wrapping/overflow protection at all.
    """

    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    i = 0
    while i < len(words) and len(lines) < max_lines:
        word = words[i]
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            i += 1
        else:
            lines.append(current)
            current = ""
    if current and len(lines) < max_lines:
        lines.append(current)
        current = ""

    if i < len(words) or current:
        last = lines[-1] if lines else ""
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else ""
        lines = (lines[:-1] if lines else []) + [f"{last}…" if last else "…"]

    return lines or [""]


def _panel(width: int, height: int) -> Image.Image:
    return Image.new("RGBA", (width, height), PANEL_COLOR)


def _primary_index_change(indices: list[dict]) -> float:
    for idx in indices:
        if idx.get("name") == "S&P 500":
            return float(idx.get("change_pct", 0.0))
    return float(indices[0].get("change_pct", 0.0)) if indices else 0.0


def compose_post_image(snapshot: dict, content: PostDraftContent) -> Path:
    indices = snapshot.get("indices", [])
    watchlist = snapshot.get("watchlist", [])

    mood = "bullish" if _primary_index_change(indices) >= 0 else "bearish"
    logo = Image.open(ASSETS_DIR / f"logo_{'peach' if mood == 'bullish' else 'blue'}.png").convert("RGBA")
    mascot = Image.open(ASSETS_DIR / "mascot.png").convert("RGBA")
    accent = ACCENT_BULLISH if mood == "bullish" else ACCENT_BEARISH

    canvas = generate_brand_background(mood, CANVAS_SIZE).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    date_font = _load_font(22, bold=False)
    headline_font = _load_font(46)
    subtext_font = _load_font(26, bold=False)
    heading_font = _load_font(26)

    # ---- Header: logo badge + date/headline/subtext -----------------------
    text_x = MARGIN + LOGO_SIZE + 24
    safe_width = CANVAS_SIZE[0] - text_x - MARGIN
    date_str = datetime.date.today().strftime("%B %d, %Y")
    headline_lines = _wrap_text(draw, content.image_headline, headline_font, safe_width, max_lines=2)
    subtext_lines = _wrap_text(draw, content.image_subtext, subtext_font, safe_width, max_lines=2)

    date_row_h = 34
    headline_line_h = 56
    subtext_line_h = 36
    text_block_h = date_row_h + len(headline_lines) * headline_line_h + len(subtext_lines) * subtext_line_h
    header_h = max(text_block_h + 40, LOGO_SIZE + 40)

    canvas.alpha_composite(_panel(CANVAS_SIZE[0], header_h), (0, 0))
    logo_y = (header_h - LOGO_SIZE) // 2
    canvas.alpha_composite(logo.resize((LOGO_SIZE, LOGO_SIZE)), (MARGIN, logo_y))

    y = (header_h - text_block_h) // 2
    draw.text((text_x, y), f"US MARKET RECAP · {date_str}", font=date_font, fill=TEXT_MUTED)
    y += date_row_h
    for line in headline_lines:
        draw.text((text_x, y), line, font=headline_font, fill=TEXT_DARK)
        y += headline_line_h
    for line in subtext_lines:
        draw.text((text_x, y), line, font=subtext_font, fill=TEXT_MUTED)
        y += subtext_line_h

    cursor_y = header_h + 20

    # ---- Index chart panel --------------------------------------------------
    chart_img = render_index_chart(indices, size_px=(CANVAS_SIZE[0] - MARGIN * 2, 240))
    chart_panel_h = chart_img.height + 56
    canvas.alpha_composite(_panel(CANVAS_SIZE[0], chart_panel_h), (0, cursor_y))
    canvas.alpha_composite(chart_img, (MARGIN, cursor_y + 28))
    cursor_y += chart_panel_h + 20

    # ---- "The MAG10 market movement" section --------------------------------
    heading_h = 56
    grid_rows = max(1, -(-len(watchlist) // 2))
    grid_h = grid_rows * 44
    mag10_panel_h = heading_h + grid_h + 20
    canvas.alpha_composite(_panel(CANVAS_SIZE[0], mag10_panel_h), (0, cursor_y))

    draw.text((MARGIN, cursor_y + 18), "THE MAG10 MARKET MOVEMENT", font=heading_font, fill=accent)
    draw.line(
        [(MARGIN, cursor_y + heading_h - 2), (CANVAS_SIZE[0] - MARGIN, cursor_y + heading_h - 2)],
        fill=(*accent[:3], 60),
        width=1,
    )
    movers_img = render_movers_grid(watchlist, size_px=(CANVAS_SIZE[0] - MARGIN * 2, grid_h), columns=2)
    canvas.alpha_composite(movers_img, (MARGIN, cursor_y + heading_h))
    mag10_panel_bottom = cursor_y + mag10_panel_h

    # ---- Footer branding bar -------------------------------------------------
    footer_h = 96
    footer_y = CANVAS_SIZE[1] - footer_h
    canvas.alpha_composite(_panel(CANVAS_SIZE[0], footer_h), (0, footer_y))
    footer_logo_size = 56
    canvas.alpha_composite(
        logo.resize((footer_logo_size, footer_logo_size)), (MARGIN, footer_y + (footer_h - footer_logo_size) // 2)
    )
    brand_font = _load_font(24)
    tagline_font = _load_font(18, bold=False)
    brand_x = MARGIN + footer_logo_size + 18
    draw.text((brand_x, footer_y + 22), "Wonder Trading Research (WTR)", font=brand_font, fill=TEXT_DARK)
    draw.text((brand_x, footer_y + 54), "Learn. Connect. Grow.", font=tagline_font, fill=TEXT_MUTED)

    # ---- Mascot: confined to the gap between the MAG10 panel and the footer
    # so it can never overlap/obscure real data, however long the day's copy is.
    mascot_zone_top = mag10_panel_bottom + 12
    mascot_zone_bottom = footer_y + 36  # small deliberate overlap into the footer only
    mascot_target_h = max(60, min(MASCOT_HEIGHT, mascot_zone_bottom - mascot_zone_top))
    mascot_w = int(mascot_target_h * (mascot.width / mascot.height))
    mascot_resized = mascot.resize((mascot_w, mascot_target_h))
    mascot_x = CANVAS_SIZE[0] - mascot_w - 16
    mascot_y = mascot_zone_bottom - mascot_target_h
    canvas.alpha_composite(mascot_resized, (mascot_x, mascot_y))

    final_image = canvas.convert("RGB")
    output_path = Path(tempfile.gettempdir()) / f"market_post_{datetime.date.today().isoformat()}.jpg"
    final_image.save(output_path, format="JPEG", quality=92)
    return output_path
