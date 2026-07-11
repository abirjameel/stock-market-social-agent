"""Gemini-powered social post image generation tool.

The agent calls `generate_post_image` after fetching market data and news.
The tool encodes the WTR logo and mascot as inline multimodal parts, sends
them alongside a structured prompt to the Gemini image generation model, and
writes the resulting image to a temp file — returning the path so the pipeline
can upload it directly to Cloud Storage.
"""

from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path

from google import genai
from google.genai import types

from services.config import config

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "branding"


def _make_genai_client() -> genai.Client:
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"
    if use_vertex:
        return genai.Client(
            vertexai=True,
            project=config.gcp_project,
            location=config.gcp_location,
        )
    api_key = config.gemini_api_key()
    return genai.Client(api_key=api_key) if api_key else genai.Client()


def generate_post_image(
    headline: str,
    subtext: str,
    mood: str,
    market_summary: str,
) -> str:
    """Generate a branded 1080×1080 social post image using Gemini image generation.

    Call this tool after `get_market_snapshot` and `get_market_news` once you
    have decided on the headline, subtext, and overall market mood. The model
    is given the WTR logo and bull mascot as visual references and asked to
    design a complete, publish-ready post image. The image is written to a
    temp file and the absolute path is returned.

    Args:
        headline: Very short headline stat for the image (max 5 words),
            e.g. "S&P 500 +1.2% Today".
        subtext: One short supporting line (max 8 words),
            e.g. "NVDA leads MAG10 with +3.4%".
        mood: Overall market mood — "bullish" if the S&P 500 closed up,
            "bearish" if it closed down.
        market_summary: Two or three sentences covering the key index moves
            and the standout MAG10 mover, using the real numbers from
            `get_market_snapshot`. This text is embedded in the generation
            prompt so the model can render accurate data callouts.

    Returns:
        Absolute path string to the generated JPEG file in the system temp dir.
    """
    logo_file = "logo_peach.png" if mood.lower() == "bullish" else "logo_blue.png"
    logo_path = ASSETS_DIR / logo_file
    mascot_path = ASSETS_DIR / "mascot.png"

    if not logo_path.exists():
        raise FileNotFoundError(f"Logo asset not found: {logo_path}")
    if not mascot_path.exists():
        raise FileNotFoundError(f"Mascot asset not found: {mascot_path}")

    logo_bytes = logo_path.read_bytes()
    mascot_bytes = mascot_path.read_bytes()

    accent_desc = "warm orange and peach tones" if mood.lower() == "bullish" else "cool blue and navy tones"
    mood_label = "bullish (green/positive market/happy bull mascot)" if mood.lower() == "bullish" else "bearish (red/negative market)/sad bull mascot"

    prompt = f"""Design a professional, modern 1080×1080 pixel square social media post image for \
Wonder Trading Research (WTR), a US stock market research and education brand.

You are provided two brand assets:
• Image 1 (logo): Place it prominently in the top-left corner, roughly 90–110px square, \
inside a clean header panel.
• Image 2 (mascot): A WTR bull character. Place it large and expressive in the lower-right \
quadrant; it should feel like the centrepiece of the visual — let it occupy at least 30% of \
the image height. Match its expression and pose to the {mood_label} mood.

Layout (top to bottom):
1. Header panel — logo top-left, beside it: date label "US MARKET RECAP · {datetime.date.today().strftime('%B %d, %Y')}", \
then the bold headline "{headline}", then the subtext "{subtext}".
2. Data panel — clean, minimal card showing the key index moves and one standout stock move \
using these real numbers: {market_summary}. Use small green/red badges for percentage changes.
3. Lower section — WTR bull mascot (Image 2) on the right; left side can carry a subtle brand \
tagline "Learn. Connect. Grow." and "Wonder Trading Research (WTR)".
4. Footer branding bar — subtle, with "WTR" wordmark.

Visual style:
• Dominant palette: {accent_desc}
• Background: abstract watercolour-style financial blobs or soft gradient — not a plain solid colour
• Clean frosted-glass panels over the background for text legibility
• Bold, modern sans-serif typography
• No placeholder text, no lorem ipsum, no watermarks
• The final image must look ready to post on Instagram and LinkedIn — polished and on-brand"""

    client = _make_genai_client()

    response = client.models.generate_content(
        model=config.image_model,
        contents=[
            types.Part(inline_data=types.Blob(mime_type="image/png", data=logo_bytes)),
            types.Part(inline_data=types.Blob(mime_type="image/png", data=mascot_bytes)),
            types.Part(text=prompt),
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    image_data: bytes | None = None
    for part in response.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob and getattr(blob, "mime_type", "").startswith("image/"):
            raw = blob.data
            image_data = raw if isinstance(raw, bytes) else raw.encode("latin-1")
            break

    if not image_data:
        raise RuntimeError(
            "Gemini image generation returned no image part. "
            "Check that the model supports image output and that the prompt "
            "did not trigger a safety filter."
        )

    output_path = (
        Path(tempfile.gettempdir()) / f"market_post_{datetime.date.today().isoformat()}.jpg"
    )
    output_path.write_bytes(image_data)
    return str(output_path)
