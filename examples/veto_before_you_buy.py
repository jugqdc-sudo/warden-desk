"""Put the warden in front of an execution layer.

This is the intended shape of the project: your bot decides what it wants to
do, the desk decides whether it is allowed to. Nothing here signs anything -
`submit()` is a stub, and that is where your own trading code would go.

    python3 examples/veto_before_you_buy.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.warden import Warden
from core.ledger import Candidate, Order, Position


def submit(order: Order) -> None:
    """Where a real bot would build, sign and send the transaction."""
    print(f"    → would submit: {order.action} ${order.candidate.ticker}")


def main() -> int:
    warden = Warden()

    # Two things a bot might want to do. The first looks like a find; the
    # second is the move that quietly costs the most money.
    wants = [
        Order(
            action="buy",
            candidate=Candidate(
                mint="CDe9a7WRAAbHc11GvMNtCDv8KkTREQ6mGnR6o6beKHiN",
                ticker="SIA",
                cap_usd=5211,
                holders=2,
                top10_share=0.0,
                silence_days=613,
                age_days=854,
                clones=98,
                wallets_in_wave=31,
                wave_age_minutes=8.8,
                is_original=True,
                moved_pct=0.0,
            ),
        ),
        Order(
            action="add",
            position=Position(
                ticker="MICHU",
                mint="",
                size_usd=50.0,
                entry_price=0.000003,
                opened_at=time.time() - 1800,   # opened half an hour ago
                pnl_pct=-8.0,
            ),
        ),
    ]

    for order in wants:
        subject = order.candidate.ticker if order.candidate else order.position.ticker
        print(f"\n  {order.action.upper()} ${subject}")

        verdict = warden.check(order)
        if verdict.denied:
            # The desk has no manual override, so there is no branch here that
            # submits anyway. That is the whole point of the project.
            print(f"    ✗ {verdict.rule_id} {verdict.code}")
            print(f"      {verdict.reason}")
            continue

        print("    ✓ cleared")
        submit(order)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
