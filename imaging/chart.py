"""Renders the factual, data-driven part of the post image: a small bar chart
of index % moves plus a top gainers/losers table, drawn with matplotlib onto
a transparent background so it can be composited over the AI-generated
stylistic layer.
"""

from __future__ import annotations

from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from PIL import Image

POSITIVE_COLOR = "#1DB954"
NEGATIVE_COLOR = "#E03C31"
# Dark, muted text/lines - the chart is composited onto a light "frosted
# glass" panel (see imaging/compose.py), not a dark one.
TEXT_COLOR = "#2A2E38"


def render_index_chart(indices: list[dict], size_px: tuple[int, int] = (960, 480)) -> Image.Image:
    """Render a horizontal bar chart of index % changes as a transparent PNG."""

    names = [i["name"] for i in indices] or ["No data"]
    changes = [i["change_pct"] for i in indices] or [0.0]
    colors = [POSITIVE_COLOR if c >= 0 else NEGATIVE_COLOR for c in changes]

    dpi = 100
    fig_w, fig_h = size_px[0] / dpi, size_px[1] / dpi
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")

    bars = ax.barh(names, changes, color=colors, height=0.5)
    ax.axvline(0, color=TEXT_COLOR, linewidth=1, alpha=0.35)

    # Pad the x-axis well beyond the largest bar so value labels never collide
    # with the y-axis tick labels, even when every bar is small/near zero.
    max_abs_change = max((abs(c) for c in changes), default=1) or 1
    ax.set_xlim(-max_abs_change * 1.8, max_abs_change * 1.8)

    for bar, change in zip(bars, changes):
        label = f"{change:+.2f}%"
        x = bar.get_width()
        offset = 0.12 * max_abs_change
        align = "left" if x >= 0 else "right"
        x_pos = x + offset if x >= 0 else x - offset
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2, label, va="center", ha=align,
                 color=TEXT_COLOR, fontsize=14, fontweight="bold")

    ax.tick_params(colors=TEXT_COLOR, labelsize=13)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.get_xaxis().set_visible(False)
    ax.invert_yaxis()

    buf = BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")
