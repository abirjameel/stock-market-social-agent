"""Renders "the MAG10 market movement" section: a compact, color-coded grid
showing every tracked watchlist ticker's daily % change.

Drawn directly with Pillow rather than matplotlib - it's a simple grid of
text/shapes, not a data plot, so plain drawing primitives are simpler and
faster here.
"""

from __future__ import annotations

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

POSITIVE_COLOR = (29, 185, 84, 255)
NEGATIVE_COLOR = (224, 60, 49, 255)
TEXT_DARK = (32, 36, 48, 255)


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    weight = "bold" if bold else "normal"
    path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight=weight))
    return ImageFont.truetype(path, size)


def _draw_triangle(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, color, pointing_up: bool) -> None:
    if pointing_up:
        points = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
    else:
        points = [(cx, cy + size), (cx - size, cy - size), (cx + size, cy - size)]
    draw.polygon(points, fill=color)


def render_movers_grid(moves: list[dict], size_px: tuple[int, int], columns: int = 2) -> Image.Image:
    """Render a transparent-background grid of ticker/% change rows.

    `moves` items need `symbol` and `change_pct` keys (matches the
    `get_market_snapshot` "watchlist" payload shape).
    """

    width, height = size_px
    img = Image.new("RGBA", size_px, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if not moves:
        return img

    symbol_font = _font(23, bold=True)
    pct_font = _font(21, bold=True)

    rows = max(1, -(-len(moves) // columns))
    cell_w = width / columns
    cell_h = height / rows
    row_pad = min(10, cell_h * 0.12)

    for i, move in enumerate(moves):
        col = i % columns
        row = i // columns
        x0 = col * cell_w
        y0 = row * cell_h + row_pad / 2
        cell_h_eff = cell_h - row_pad

        change = float(move.get("change_pct", 0.0))
        color = POSITIVE_COLOR if change >= 0 else NEGATIVE_COLOR
        cy = y0 + cell_h_eff / 2

        _draw_triangle(draw, x0 + 16, cy, 7, color, pointing_up=change >= 0)

        symbol = move.get("symbol", "?")
        draw.text((x0 + 34, cy), symbol, font=symbol_font, fill=TEXT_DARK, anchor="lm")

        pct_label = f"{change:+.2f}%"
        pad_right = 18 if col == columns - 1 else 28
        pct_w = draw.textlength(pct_label, font=pct_font)
        draw.text((x0 + cell_w - pad_right - pct_w, cy), pct_label, font=pct_font, fill=color, anchor="lm")

        if row < rows - 1:
            draw.line(
                [(x0 + 8, y0 + cell_h_eff + row_pad / 2), (x0 + cell_w - 8, y0 + cell_h_eff + row_pad / 2)],
                fill=(0, 0, 0, 20),
                width=1,
            )

    return img
