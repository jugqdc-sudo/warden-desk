"""CLOCK [R4] - keeps the sell button locked for five minutes.

The lock is not aimed at the market. It is aimed at the operator: the
measured median holding time on this desk was forty two seconds, and almost
every one of those exits was early rather than late.

The only thing that opens the lock before the timer is the stop.

    python3 desk.py clock --held 90
    python3 desk.py clock --held 90 --pnl -30
"""

from __future__ import annotations

import argparse

from agents.base import Agent
from core import term
from core.ledger import Order, Position, Verdict


class Clock(Agent):
    name = "CLOCK"
    rule_id = "R4"
    job = "locks the sell button for the first five minutes of a position"

    def check(self, order: Order) -> Verdict:
        if order.action != "sell":
            return self.ok()

        position = order.position
        if position is None:
            return self.unknown("the position being sold")

        lock = self.rule["lock_seconds"]
        stop = self.rule["stop_loss_pct"]
        stop_wins = self.rule["stop_overrides_lock"]

        held = position.held_seconds
        if held >= lock:
            return self.ok()

        if stop_wins and position.pnl_pct <= stop:
            return self.ok()

        return self.no(
            "sell locked",
            f"${position.ticker} has been held {held:.0f}s of {lock}s and is at "
            f"{position.pnl_pct:+.1f}%, above the {stop:.0f}% stop - "
            "the button stays shut",
        )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--held", type=float, default=42, help="seconds held so far")
        parser.add_argument("--pnl", type=float, default=-4.0, help="open pnl, percent")
        parser.add_argument("--ticker", default="MICHU")

    def demo(self, args: argparse.Namespace) -> int:
        import time

        lock = self.rule["lock_seconds"]
        term.head(
            "CLOCK",
            self.rule.title,
            asks=self.rule.asks,
            bench=f"locked for [bold]{lock}s[/] · only the "
            f"{self.rule['stop_loss_pct']:.0f}% stop opens it early",
            footer="aimed at the operator, not at the market",
        )

        position = Position(
            ticker=args.ticker.upper(),
            mint="",
            size_usd=self.book.position_size,
            entry_price=0.0,
            opened_at=time.time() - args.held,
            pnl_pct=args.pnl,
        )
        order = Order(action="sell", position=position)
        verdict = self.check(order)

        label = f"${position.ticker}  held {args.held:.0f}s  pnl {args.pnl:+.1f}%"
        if verdict.ok:
            term.cleared(label, "the lock is open - sell may go through")
        else:
            term.denied(label, verdict.code, verdict.reason)
        return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(Clock().main())
