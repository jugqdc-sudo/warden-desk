"""LADDER [R6] - adds to winners, and only to winners.

Averaging down is banned at desk level. Not discouraged, not sized down -
banned, with no override, because it is the one habit that turns a small
loss into the whole account.

The published desk log carries the same fact from the other side: adding to a
losing position happened zero times out of 162 opportunities.

    python3 desk.py ladder --pnl 12
    python3 desk.py ladder --pnl -8
"""

from __future__ import annotations

import argparse
import time

from agents.base import Agent
from core import term
from core.ledger import Order, Position, Verdict


class Ladder(Agent):
    name = "LADDER"
    rule_id = "R6"
    job = "allows adds to a winning position and forbids averaging down"

    def check(self, order: Order) -> Verdict:
        if order.action != "add":
            return self.ok()

        position = order.position
        if position is None:
            return self.unknown("the position being added to")

        threshold = self.rule["add_only_if_open_pnl_pct_above"]
        if not self.rule["averaging_down"] and position.pnl_pct <= threshold:
            return self.no(
                "averaging down",
                f"${position.ticker} is at {position.pnl_pct:+.1f}% - "
                "the desk does not add to a losing position, and this rule "
                "has no override",
            )

        max_adds = self.rule["max_adds"]
        if position.adds >= max_adds:
            return self.no(
                "ladder finished",
                f"{position.adds} adds already made on ${position.ticker} - "
                f"the ladder stops at {max_adds}",
            )

        return self.ok()

    def next_size(self, position: Position) -> float:
        """How much the next rung is worth, given how many are already placed."""
        fraction = self.rule["add_size_fraction"]
        return position.size_usd * (fraction ** (position.adds + 1))

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--pnl", type=float, default=-8.0, help="open pnl, percent")
        parser.add_argument("--adds", type=int, default=0, help="rungs already placed")
        parser.add_argument("--ticker", default="MICHU")

    def demo(self, args: argparse.Namespace) -> int:
        term.head(
            "LADDER",
            self.rule.title,
            asks=self.rule.asks,
            bench=f"adds only above [bold]{self.rule['add_only_if_open_pnl_pct_above']:+.0f}%[/] · "
            f"maximum {self.rule['max_adds']} rungs",
            footer="averaging down is banned at desk level",
        )

        position = Position(
            ticker=args.ticker.upper(),
            mint="",
            size_usd=self.book.position_size,
            entry_price=0.0,
            opened_at=time.time() - 600,
            adds=args.adds,
            pnl_pct=args.pnl,
        )
        verdict = self.check(Order(action="add", position=position))
        label = f"${position.ticker}  pnl {args.pnl:+.1f}%  rungs placed {args.adds}"

        if verdict.ok:
            term.cleared(label, f"next rung ${self.next_size(position):,.2f}")
        else:
            term.denied(label, verdict.code, verdict.reason)
        return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(Ladder().main())
