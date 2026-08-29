"""TOLL [R5] - counts the fee in real time and freezes the desk when it wins.

Every round trip on a bonding curve pays 1.25% in and 1.25% out. On a $50
position that is $1.25 before the price has moved at all, and on a coin with
a $2,100 cap the desk's own sell is a large part of the movement it is
selling into.

The rule is not "fees are bad". It is: when an hour of fees has eaten half of
that hour's profit, entries stop for an hour. The agent counts, and then it
shuts the door.

    python3 desk.py toll --size 50
    python3 desk.py toll --profit 6 --fees 4
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from agents.base import Agent
from core import term
from core.ledger import Order, Verdict


@dataclass
class HourBook:
    """Running total of what this hour has cost and what it has made."""

    fees_usd: float = 0.0
    profit_usd: float = 0.0
    started_at: float = field(default_factory=time.time)
    frozen_until: float = 0.0

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    @property
    def frozen(self) -> bool:
        return time.time() < self.frozen_until


class Toll(Agent):
    name = "TOLL"
    rule_id = "R5"
    job = "counts fees against profit and freezes entries when fees are winning"

    def __init__(self, book=None, hour: HourBook | None = None) -> None:
        super().__init__(book)
        self.hour = hour or HourBook()

    # ── the arithmetic ──────────────────────────────────────────────────
    def round_trip_cost(self, size_usd: float, sol_usd: float = 105.38) -> float:
        """What one full in-and-out costs on this size, fees plus network."""
        rate = self.rule["fee_rate_per_side"]
        network = self.rule["network_fee_sol"] * sol_usd * 2
        return size_usd * rate * 2 + network

    def check(self, order: Order) -> Verdict:
        if order.action not in ("buy", "add"):
            return self.ok()  # the toll never blocks an exit

        share = self.rule["freeze_when_fees_exceed_profit_share"]
        freeze_for = self.rule["freeze_seconds"]

        if self.hour.frozen:
            left = self.hour.frozen_until - time.time()
            return self.no(
                "entries frozen",
                f"fees took more than {share:.0%} of the hour's profit - "
                f"entries reopen in {left / 60:.0f} min",
            )

        if self.hour.profit_usd > 0 and self.hour.fees_usd > self.hour.profit_usd * share:
            self.hour.frozen_until = time.time() + freeze_for
            return self.no(
                "fees are winning",
                f"${self.hour.fees_usd:.2f} in fees against "
                f"${self.hour.profit_usd:.2f} of profit this hour - "
                f"entries frozen for {freeze_for // 60} min",
            )

        # Whether the position is too large for the coin is WARDEN's question,
        # not this one: TOLL counts what the desk pays, it does not size trades.
        return self.ok()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--size", type=float, default=None, help="position size, usd")
        parser.add_argument("--profit", type=float, default=0.0, help="profit this hour")
        parser.add_argument("--fees", type=float, default=0.0, help="fees paid this hour")

    def demo(self, args: argparse.Namespace) -> int:
        rate = self.rule["fee_rate_per_side"]
        size = args.size or self.book.position_size
        term.head(
            "TOLL",
            self.rule.title,
            asks=self.rule.asks,
            bench=f"[bold]{rate:.2%}[/] in, [bold]{rate:.2%}[/] out · freezes entries "
            f"when fees pass {self.rule['freeze_when_fees_exceed_profit_share']:.0%} "
            "of the hour's profit",
            footer="never blocks an exit",
        )

        cost = self.round_trip_cost(size)
        term.ledger(
            "what a round trip costs",
            [
                ("position size", f"${size:,.2f}", False),
                ("fee in", f"${size * rate:,.2f}", False),
                ("fee out", f"${size * rate:,.2f}", False),
                ("network, both ways",
                 f"${self.rule['network_fee_sol'] * 105.38 * 2:,.2f}", False),
                ("round trip", f"${cost:,.2f}", True),
            ],
            footer=f"the position has to gain {cost / size:.2%} just to come back to flat",
        )

        self.hour.profit_usd = args.profit
        self.hour.fees_usd = args.fees
        verdict = self.check(Order(action="buy", size_usd=size))
        label = f"hour: ${args.profit:,.2f} profit against ${args.fees:,.2f} fees"
        if verdict.ok:
            term.cleared(label, "entries stay open")
        else:
            term.denied(label, verdict.code, verdict.reason)
        return 0


if __name__ == "__main__":
    raise SystemExit(Toll().main())
