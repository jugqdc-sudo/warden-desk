"""Price history from the public pump.fun swap API, cached on disk.

An empty history is a real answer, not a failure: a coin nobody has traded
has no candles. Several rules read exactly that as evidence.

Both "the price then" and "the price now" must come from this module. Mixing
sources means mixing supply conventions, and a market cap from one source
divided by a market cap from another invents a multiple that never happened.
"""

from __future__ import annotations

import json
import os
import time

from core.http import get_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("DESK_CANDLE_CACHE", os.path.join(ROOT, "data", "candles"))
CANDLE_API = "https://swap-api.pump.fun/v1/coins/%s/candles"
CACHE_TTL = 900
MAX_GAP_SECONDS = 2 * 3600

Candle = tuple[float, float, float, float]  # (timestamp, close, high, volume)


def _cache_path(mint: str, interval: str) -> str:
    return os.path.join(CACHE_DIR, f"{mint}_{interval}.json")


def candles(
    mint: str,
    interval: str = "1h",
    limit: int = 500,
    ttl: int = CACHE_TTL,
) -> list[Candle]:
    """Price history, oldest first. Empty list means the coin has no trades."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(mint, interval)

    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, encoding="utf-8") as handle:
                return [tuple(row) for row in json.load(handle)]
        except (json.JSONDecodeError, OSError):
            pass

    raw = get_json(
        CANDLE_API % mint,
        params={"interval": interval, "limit": limit, "currency": "USD"},
    )
    if not isinstance(raw, list):
        return []

    rows: list[Candle] = sorted(
        (
            float(row["timestamp"]) / 1000,
            float(row["close"]),
            float(row["high"]),
            float(row["volume"]),
        )
        for row in raw
    )
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle)
    return rows


def price_at(rows: list[Candle], when: float, max_gap: float = MAX_GAP_SECONDS) -> float | None:
    """Price in the candle nearest to `when`, or None if the gap is too wide.

    Histories have holes many hours wide. Taking the "nearest" candle without
    a tolerance quietly reports one day's price as another day's, and the
    multiple that comes out of it is fiction.
    """
    if not rows:
        return None
    nearest = min(rows, key=lambda row: abs(row[0] - when))
    if abs(nearest[0] - when) > max_gap:
        return None
    return nearest[1]


def last_price(rows: list[Candle]) -> float | None:
    return rows[-1][1] if rows else None


def peak_after(rows: list[Candle], when: float) -> tuple[float | None, float | None]:
    """(timestamp of the high, multiple against the price at `when`)."""
    base = price_at(rows, when)
    after = [row for row in rows if row[0] >= when]
    if not base or not after:
        return None, None
    top = max(after, key=lambda row: row[2])
    return top[0], top[2] / base


def traded_within(rows: list[Candle], seconds: float) -> bool:
    """Has anything traded in the last `seconds`? Used to spot a dead book."""
    return bool(rows) and (time.time() - rows[-1][0]) <= seconds
