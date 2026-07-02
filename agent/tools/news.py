"""Market news tool backed by Finnhub's free news endpoint.

If no `FINNHUB_API_KEY` is configured, this degrades gracefully to an empty
headline list rather than failing the whole pipeline - the content agent is
instructed to fall back to describing price action only in that case.
"""

from __future__ import annotations

import json

import requests

from services.config import config

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"


def get_market_news(max_headlines: int = 5) -> str:
    """Fetch the latest general US market news headlines.

    Args:
        max_headlines: Maximum number of headlines to return (default 5).

    Returns a JSON string: `{"headlines": [{"headline": str, "source": str,
    "url": str}, ...]}`. Use this alongside `get_market_snapshot` so post copy
    can reference *why* the market moved, not just the numbers.
    """

    api_key = config.finnhub_api_key()
    if not api_key:
        return json.dumps({"headlines": [], "note": "FINNHUB_API_KEY not configured"})

    try:
        response = requests.get(
            FINNHUB_NEWS_URL,
            params={"category": "general", "token": api_key},
            timeout=10,
        )
        response.raise_for_status()
        articles = response.json()
    except requests.RequestException as exc:
        return json.dumps({"headlines": [], "note": f"news fetch failed: {exc}"})

    headlines = [
        {
            "headline": article.get("headline", ""),
            "source": article.get("source", ""),
            "url": article.get("url", ""),
        }
        for article in articles[:max_headlines]
        if article.get("headline")
    ]
    return json.dumps({"headlines": headlines})
