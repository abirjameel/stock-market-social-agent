"""Market data tool backed by yfinance.

`yfinance` pulls from Yahoo Finance and needs no API key, which keeps the
happy path free. Swap this module out for Polygon.io/Alpha Vantage later if
you need real-time intraday data or higher reliability guarantees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import yfinance as yf

from services.config import config


@dataclass
class TickerMove:
    symbol: str
    name: str
    last_price: float
    change: float
    change_pct: float


def _fetch_change(symbol: str) -> TickerMove | None:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty or len(hist) < 2:
        return None
    last_close = float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2])
    change = last_close - prev_close
    change_pct = (change / prev_close) * 100 if prev_close else 0.0
    name = ticker.info.get("shortName", symbol) if hasattr(ticker, "info") else symbol
    return TickerMove(symbol=symbol, name=name, last_price=last_close, change=change, change_pct=change_pct)


def get_market_snapshot() -> str:
    """Fetch the latest daily close vs. previous close for the major US indices
    (S&P 500, Dow Jones, Nasdaq Composite) and the MAG10 watchlist, and return
    the top 3 gainers, top 3 losers, and every MAG10 ticker's move.

    Returns a JSON string with keys: `indices`, `top_gainers`, `top_losers`,
    `watchlist` (all MAG10 tickers, sorted best-to-worst by change_pct), each
    numeric field rounded to 2 decimal places. Use this tool first to ground
    any commentary about "what happened in the market today" in real numbers
    instead of guessing.
    """

    indices = []
    for symbol, label in config.market_indices:
        move = _fetch_change(symbol)
        if move:
            indices.append(
                {
                    "symbol": symbol,
                    "name": label,
                    "last_price": round(move.last_price, 2),
                    "change": round(move.change, 2),
                    "change_pct": round(move.change_pct, 2),
                }
            )

    watchlist_moves: list[TickerMove] = []
    for symbol in config.watchlist:
        symbol = symbol.strip()
        if not symbol:
            continue
        move = _fetch_change(symbol)
        if move:
            watchlist_moves.append(move)

    watchlist_moves.sort(key=lambda m: m.change_pct, reverse=True)
    top_gainers = watchlist_moves[:3]
    top_losers = list(reversed(watchlist_moves[-3:])) if watchlist_moves else []

    def _serialize(move: TickerMove) -> dict:
        return {
            "symbol": move.symbol,
            "name": move.name,
            "last_price": round(move.last_price, 2),
            "change": round(move.change, 2),
            "change_pct": round(move.change_pct, 2),
        }

    payload = {
        "indices": indices,
        "top_gainers": [_serialize(m) for m in top_gainers],
        "top_losers": [_serialize(m) for m in top_losers],
        "watchlist": [_serialize(m) for m in watchlist_moves],
    }
    return json.dumps(payload)
