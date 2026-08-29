"""The launch index: every coin the desk has seen, in birth order.

The shipped snapshot (data/coins.sqlite) holds 12,663 launches over roughly
eight days of the Solana launchpad feed. Only on-chain public facts are in
it: mint address, ticker, deployer wallet, birth timestamp, launchpad and the
social link the coin was minted from.

The snapshot is what makes this repository run with no keys and no wallet.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.environ.get("DESK_INDEX", os.path.join(ROOT, "data", "coins.sqlite"))


@dataclass(frozen=True)
class Coin:
    """One launch. `born` is a unix timestamp, `ticker` is upper-cased on read."""

    mint: str
    ticker: str
    deployer: str
    born: float
    launchpad: str
    source: str

    @property
    def age_days(self) -> float:
        import time

        return (time.time() - self.born) / 86400

    def __repr__(self) -> str:
        return f"<{self.ticker} {self.mint[:6]}>"


def _connect(path: str = INDEX_PATH) -> sqlite3.Connection:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"launch index not found at {path}. "
            "Run `python3 desk.py index --check` for what the desk expects."
        )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _coin(row: sqlite3.Row) -> Coin:
    return Coin(
        mint=row["mint"],
        ticker=(row["ticker"] or "").strip().upper(),
        deployer=row["deployer"] or "",
        born=float(row["born"] or 0),
        launchpad=row["launchpad"] or "",
        source=row["source"] or "",
    )


def stream(limit: int | None = None, path: str = INDEX_PATH) -> list[Coin]:
    """Every indexed launch, oldest first."""
    connection = _connect(path)
    query = (
        "select mint, ticker, deployer, born, launchpad, source from coins "
        "where ticker is not null and ticker <> '' and born is not null "
        "order by born"
    )
    if limit:
        query += f" limit {int(limit)}"
    coins = [_coin(row) for row in connection.execute(query)]
    connection.close()
    return coins


def by_ticker(ticker: str, path: str = INDEX_PATH) -> list[Coin]:
    """Every launch that used this ticker, oldest first - originals and clones."""
    connection = _connect(path)
    rows = connection.execute(
        "select mint, ticker, deployer, born, launchpad, source from coins "
        "where upper(ticker) = ? order by born",
        (ticker.strip().upper(),),
    )
    coins = [_coin(row) for row in rows]
    connection.close()
    return coins


def stats(path: str = INDEX_PATH) -> dict[str, float]:
    """Shape of the shipped index, for `desk.py index --check`."""
    connection = _connect(path)
    row = connection.execute(
        "select count(*) as coins, count(distinct upper(ticker)) as tickers, "
        "count(distinct deployer) as deployers, min(born) as first, max(born) as last "
        "from coins"
    ).fetchone()
    connection.close()
    return {
        "coins": row["coins"],
        "tickers": row["tickers"],
        "deployers": row["deployers"],
        "first": row["first"],
        "last": row["last"],
        "days": (row["last"] - row["first"]) / 86400 if row["first"] else 0.0,
    }
