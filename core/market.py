"""Live quotes from the public pump.fun API. No key, no wallet, read only.

One request per mint returns the market cap in USD, the timestamp of the last
trade and the bonding-curve reserves. That is enough for four of the seven
rules; holders and the top-ten share need an indexed RPC and live in chain.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core.http import get_json

COIN_API = "https://frontend-api-v3.pump.fun/coins/"
SEARCH_API = "https://frontend-api-v3.pump.fun/coins"


@dataclass(frozen=True)
class Quote:
    """A live look at one coin. Every field can be None when the API omits it."""

    mint: str
    ticker: str
    cap_usd: float | None
    created_at: float | None
    last_trade_at: float | None
    migrated: bool
    creator: str

    @property
    def age_days(self) -> float | None:
        if not self.created_at:
            return None
        return (time.time() - self.created_at) / 86400

    @property
    def silence_days(self) -> float | None:
        """Days since the last recorded trade - the width of the empty book."""
        if not self.last_trade_at:
            return None
        return (time.time() - self.last_trade_at) / 86400


def _stamp(value: object) -> float | None:
    """pump.fun sends milliseconds; zero means 'never happened'."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value) / 1000


def _as_quote(data: dict) -> Quote:
    return Quote(
        mint=data["mint"],
        ticker=(data.get("symbol") or "").strip().upper(),
        cap_usd=data.get("usd_market_cap"),
        created_at=_stamp(data.get("created_timestamp")),
        last_trade_at=_stamp(data.get("last_trade_timestamp")),
        migrated=bool(data.get("complete")),
        creator=data.get("creator") or "",
    )


def quote(mint: str) -> Quote | None:
    """Fetch one coin, or None when the endpoint did not answer."""
    data = get_json(COIN_API + mint)
    if not isinstance(data, dict) or "mint" not in data:
        return None
    return _as_quote(data)


def search(ticker: str, limit: int = 50, oldest_first: bool = True) -> list[Quote]:
    """Every coin on the launchpad carrying this exact ticker, oldest first.

    The endpoint matches loosely - a search for SIA also returns SIAMESE - so
    the result is filtered down to an exact ticker match. That filtering is
    the difference between finding the original and finding a coincidence.
    """
    data = get_json(
        SEARCH_API,
        params={
            "searchTerm": ticker,
            "limit": limit,
            "sort": "created_timestamp",
            "order": "ASC" if oldest_first else "DESC",
            "includeNsfw": "true",
        },
    )
    if not isinstance(data, list):
        return []

    wanted = ticker.strip().upper()
    found = [
        _as_quote(row)
        for row in data
        if isinstance(row, dict)
        and "mint" in row
        and (row.get("symbol") or "").strip().upper() == wanted
    ]
    found.sort(key=lambda item: item.created_at or 0, reverse=not oldest_first)
    return found
