"""UNDERTAKER [R7] - the thesis has a clock.

A position on this desk is opened for one stated reason: a wave is being
manufactured on a name and the original is cheap. That reason has a shelf
life of six hours. When the timer runs out the position closes at market,
whatever the chart is doing and whatever the operator now believes.

CLOCK stops an exit that is too early. UNDERTAKER stops one that never comes.

    python3 desk.py undertaker --held 7h
    python3 desk.py undertaker --held 2h --pnl 40
"""

from __future__ import annotations

import argparse
import time

from agents.base import Agent
from core import term
from core.ledger import Order, Position, Verdict


def parse_held(text: str) -> float:
    """`7h`, `45m`, or seconds."""
    text = text.strip().lower()
    if text.endswith("h"):
        return float(text[:-1]) * 3600
    if text.endswith("m"):
        return float(text[:-1]) * 60
    return float(text)


class Undertaker(Agent):
    name = "UNDERTAKER"
    rule_id = "R7"
    job = "closes a position at market when its thesis timer runs out"

    def check(self, order: Order) -> Verdict:
        """UNDERTAKER never blocks anything - it forces a close, so a hold is what it refuses."""
        position = order.position
        if position is None or order.action != "hold":
            return self.ok()

        timeout = self.rule["thesis_timeout_seconds"]
        if position.held_seconds > timeout:
            return self.no(
                "thesis expired",
                f"${position.ticker} has been open {position.held_seconds / 3600:.1f}h "
                f"against a {timeout / 3600:.0f}h thesis at {position.pnl_pct:+.1f}% - "
                "closing at market",
            )
        return self.ok()

    def expired(self, position: Position) -> bool:
        return position.held_seconds > self.rule["thesis_timeout_seconds"]

    def time_left(self, position: Position) -> float:
        return max(self.rule["thesis_timeout_seconds"] - position.held_seconds, 0.0)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--held", default="7h", help="how long the position is open")
        parser.add_argument("--pnl", type=float, default=-11.0)
        parser.add_argument("--ticker", default="MICHU")

    def demo(self, args: argparse.Namespace) -> int:
        timeout = self.rule["thesis_timeout_seconds"]
        term.head(
            "UNDERTAKER",
            self.rule.title,
            asks=self.rule.asks,
            bench=f"thesis timer [bold]{timeout / 3600:.0f}h[/] · closes at market",
            footer="CLOCK stops an early exit, this one stops a missing exit",
        )

        held = parse_held(args.held)
        position = Position(
            ticker=args.ticker.upper(),
            mint="",
            size_usd=self.book.position_size,
            entry_price=0.0,
            opened_at=time.time() - held,
            pnl_pct=args.pnl,
        )
        verdict = self.check(Order(action="hold", position=position))
        label = f"${position.ticker}  open {held / 3600:.1f}h  pnl {args.pnl:+.1f}%"

        if verdict.ok:
            term.cleared(
                label,
                f"{self.time_left(position) / 60:.0f} min left on the thesis",
            )
        else:
            term.denied(label, verdict.code, verdict.reason)
        return 0


if __name__ == "__main__":
    raise SystemExit(Undertaker().main())
