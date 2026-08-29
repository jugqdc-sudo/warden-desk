#!/usr/bin/env python3
"""warden-desk - eight agents, one job each, and one of them only says no.

    python3 desk.py rules              the seven rules in one screen
    python3 desk.py <agent> [flags]    run a single agent
    python3 desk.py warden --live      build fresh candidates and judge them
    python3 desk.py index --check      what data the desk is standing on

This repository finds, measures and refuses. It never signs a transaction and
holds no keys - execution is somebody else's layer, on purpose.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.clock import Clock
from agents.collector import Collector
from agents.graveyard import Graveyard
from agents.ladder import Ladder
from agents.midwife import Midwife
from agents.toll import Toll
from agents.undertaker import Undertaker
from agents.warden import WardenCLI, print_rules
from core import chain, feed, rules, term

__version__ = "1.0.0"

AGENTS = {
    "graveyard": Graveyard,
    "midwife": Midwife,
    "collector": Collector,
    "clock": Clock,
    "toll": Toll,
    "ladder": Ladder,
    "undertaker": Undertaker,
    "warden": WardenCLI,
}


def show_index() -> int:
    """What the desk is standing on: the snapshot, the live endpoints, the node."""
    import time

    book = rules.load()

    try:
        stats = feed.stats()
    except FileNotFoundError as error:
        term.warn(str(error))
        return 1

    term.head(
        "INDEX",
        "what the desk is standing on",
        asks="is the data under these verdicts what i think it is?",
        footer=f"rules v{book.version}",
    )

    span = (
        f"{stats['days']:.1f} days, "
        f"{time.strftime('%Y-%m-%d', time.localtime(stats['first']))} to "
        f"{time.strftime('%Y-%m-%d', time.localtime(stats['last']))}"
    )
    term.ledger(
        "launch snapshot",
        [
            ("launches", f"{stats['coins']:,}", False),
            ("distinct names", f"{stats['tickers']:,}", False),
            ("deployer wallets", f"{stats['deployers']:,}", False),
            ("covering", span, True),
        ],
        footer="public on-chain facts only - no keys were used to build this",
    )

    live = [
        ("pump.fun coin + search", "cap, age, last trade", False),
        ("pump.fun candles", "price history", False),
    ]
    if chain.configured():
        live.append(("rpc node", "set - holders and top-10 read live", True))
        note = ""
    else:
        live.append(("rpc node", "not set", True))
        note = (
            "getTokenLargestAccounts is an indexed call and every free endpoint gates "
            "it. Without DESK_RPC holders read as unknown - and WARDEN refuses on unknown."
        )
    term.ledger("live endpoints, no key required", live, footer=note)
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        print("agents: " + ", ".join(AGENTS))
        return 0

    command, rest = argv[0].lower(), argv[1:]

    if command in ("--version", "-V", "version"):
        book = rules.load()
        print(f"warden-desk {__version__}  ·  rulebook v{book.version}")
        return 0

    if command == "rules":
        if "--json" in rest:
            print(json.dumps(rules.raw(), indent=2, ensure_ascii=False))
            return 0
        print_rules(WardenCLI())
        return 0

    if command == "index":
        return show_index()

    if command not in AGENTS:
        print(f"unknown agent {command!r}. known: {', '.join(AGENTS)}")
        return 2

    return AGENTS[command]().main(rest)


def cli() -> None:
    """Console entry point, installed as `warden-desk` by pip."""
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
