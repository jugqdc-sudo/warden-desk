"""Positions and orders the desk reasons about. Nothing here signs anything.

A Position is what an operator claims to be holding; an Order is what they
are about to do. Both are plain data, so the same objects work for a paper
run, for a replay of a recorded session, and for a real desk whose execution
layer lives outside this repository.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFUSALS_PATH = os.environ.get(
    "DESK_REFUSALS", os.path.join(ROOT, "data", "refusals.jsonl")
)

BUY, ADD, SELL = "buy", "add", "sell"


@dataclass
class Candidate:
    """A coin someone wants to buy, with everything the rules ask about.

    Unknown numbers stay None on purpose. A rule that cannot see its input
    must say so rather than assume a comfortable default.
    """

    mint: str
    ticker: str
    cap_usd: float | None = None
    holders: int | None = None
    holders_exact: bool = True
    top10_share: float | None = None
    silence_days: float | None = None
    age_days: float | None = None
    clones: int | None = None          # copies of this ticker in the wave
    wallets_in_wave: int | None = None
    wave_age_minutes: float | None = None
    is_original: bool = True           # False when this mint is one of the copies
    moved_pct: float = 0.0             # how far it already ran since the wave started
    url: str = ""
    seen_at: float = field(default_factory=time.time)


@dataclass
class Position:
    """An open position. `opened_at` is what CLOCK and UNDERTAKER measure."""

    ticker: str
    mint: str
    size_usd: float
    entry_price: float
    opened_at: float
    adds: int = 0
    pnl_pct: float = 0.0
    fees_paid_usd: float = 0.0

    @property
    def held_seconds(self) -> float:
        return time.time() - self.opened_at

    @property
    def in_profit(self) -> bool:
        return self.pnl_pct > 0


@dataclass
class Order:
    """One intent: buy this candidate, add to this position, or sell it.

    WARDEN takes exactly this object and answers yes or no.
    """

    action: str                       # BUY / ADD / SELL
    candidate: Candidate | None = None
    position: Position | None = None
    size_usd: float | None = None
    manual: bool = True               # True when a human typed it
    at: float = field(default_factory=time.time)

    @property
    def ticker(self) -> str:
        if self.candidate:
            return self.candidate.ticker
        if self.position:
            return self.position.ticker
        return "?"


@dataclass(frozen=True)
class Verdict:
    """The answer of one rule. `ok=False` is a refusal that cannot be argued."""

    ok: bool
    rule_id: str
    agent: str
    code: str = ""       # short machine-readable reason, e.g. "no counterparty"
    reason: str = ""     # the same thing in a sentence, for the log

    @property
    def denied(self) -> bool:
        return not self.ok


def clear(rule_id: str, agent: str) -> Verdict:
    return Verdict(ok=True, rule_id=rule_id, agent=agent)


def deny(rule_id: str, agent: str, code: str, reason: str) -> Verdict:
    return Verdict(ok=False, rule_id=rule_id, agent=agent, code=code, reason=reason)


def record_refusal(order: Order, verdict: Verdict, path: str = REFUSALS_PATH) -> None:
    """Append one refusal to data/refusals.jsonl.

    Refusals are the output of this desk. They are written down for the same
    reason trades are: so the record can be checked later against what the
    coin actually did.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {
        "at": order.at,
        "action": order.action,
        "ticker": order.ticker,
        "mint": order.candidate.mint if order.candidate else (
            order.position.mint if order.position else ""
        ),
        "rule": verdict.rule_id,
        "agent": verdict.agent,
        "code": verdict.code,
        "reason": verdict.reason,
    }
    if order.candidate:
        row["candidate"] = {
            key: value
            for key, value in asdict(order.candidate).items()
            if key not in ("url", "seen_at")
        }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_refusals(path: str = REFUSALS_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
