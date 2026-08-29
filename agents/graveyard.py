"""GRAVEYARD [R1] - indexes the dead.

A coin that ran out of buyers sits at the bottom of an empty bonding curve,
around $1,800, and stays there. That is the only inventory this desk is
interested in: something already finished, cheap, and untouched long enough
that nobody is defending a position in it.

The agent asks one thing - is this actually a corpse, or something still
falling.

    python3 desk.py graveyard --ticker MICHU
    python3 desk.py graveyard --scan 40
"""

from __future__ import annotations

import argparse

from agents.base import Agent
from core import feed, market, term
from core.ledger import Candidate, Order, Verdict


class Graveyard(Agent):
    name = "GRAVEYARD"
    rule_id = "R1"
    job = "keeps the index of coins that already died on an empty curve"

    def check(self, order: Order) -> Verdict:
        candidate = order.candidate
        if candidate is None:
            return self.ok()

        floor = self.rule["floor_usd"]
        band = self.rule["floor_band_usd"]
        cap_ceiling = self.rule["max_cap_usd"]
        min_age = self.rule["min_age_days"]

        if candidate.cap_usd is None:
            return self.unknown("the market cap")
        if candidate.cap_usd > cap_ceiling:
            return self.no(
                "still alive",
                f"cap {term.money(candidate.cap_usd)} is above the "
                f"{term.money(cap_ceiling)} ceiling - this coin is still trading, "
                "not buried",
            )
        if candidate.cap_usd < floor - band:
            return self.no(
                "below the floor",
                f"cap {term.money(candidate.cap_usd)} is under the "
                f"{term.money(floor - band)} floor - there is no curve left to stand on",
            )

        if candidate.age_days is None:
            return self.unknown("the age of the coin")
        if candidate.age_days < min_age:
            return self.no(
                "too young to be dead",
                f"{candidate.age_days:.0f} days old - a corpse on this desk is "
                f"{min_age}+ days old",
            )

        # No silence check here on purpose - see the note on R1 in rules.json.
        return self.ok()

    # ── standalone mode ─────────────────────────────────────────────────
    def inspect(self, ticker: str) -> list[Candidate]:
        """Look up every coin carrying this ticker and describe each one."""
        found = []
        for item in market.search(ticker):
            found.append(
                Candidate(
                    mint=item.mint,
                    ticker=item.ticker,
                    cap_usd=item.cap_usd,
                    age_days=item.age_days,
                    silence_days=item.silence_days,
                    url=f"https://pump.fun/coin/{item.mint}",
                )
            )
        return found

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--ticker", help="index every coin under this ticker")
        parser.add_argument(
            "--scan",
            type=int,
            default=0,
            help="take N tickers off the local launch index and look them up live",
        )

    def demo(self, args: argparse.Namespace) -> int:
        floor = self.rule["floor_usd"]
        term.head(
            "GRAVEYARD",
            self.rule.title,
            asks=self.rule.asks,
            bench=f"floor [bold]{term.money(floor)}[/] "
            f"±{term.money(self.rule['floor_band_usd'])} · "
            f"{self.rule['min_age_days']}+ days old · "
            f"under {term.money(self.rule['max_cap_usd'])}",
            footer="the only inventory this desk wants",
        )

        tickers: list[str] = []
        if args.ticker:
            tickers = [args.ticker.strip().upper()]
        elif args.scan:
            seen: list[str] = []
            for coin in reversed(feed.stream()):
                if coin.ticker and coin.ticker not in seen:
                    seen.append(coin.ticker)
                if len(seen) >= args.scan:
                    break
            tickers = seen
        else:
            print("nothing to do: pass --ticker SYMBOL or --scan N")
            return 2

        buried = alive = 0
        reasons: dict[str, int] = {}
        table = term.VerdictTable(
            ("TICKER", 12, "left"),
            ("STATUS", 8, "left"),
            ("RULE", 20, "left"),
            ("CAP", 10, "right"),
            ("AGE", 8, "right"),
            ("SILENT", 8, "right"),
            ("CONTRACT", 22, "left"),
        )
        for ticker in tickers:
            for candidate in self.inspect(ticker):
                verdict = self.check(Order(action="buy", candidate=candidate))
                if verdict.ok:
                    buried += 1
                else:
                    alive += 1
                    reasons[verdict.code] = reasons.get(verdict.code, 0) + 1
                table.add(
                    verdict.ok,
                    f"${candidate.ticker[:11]}",
                    term.verdict(verdict.ok, "BURIED" if verdict.ok else "ALIVE"),
                    term.value("" if verdict.ok else verdict.code, good=verdict.ok or None),
                    term.money(candidate.cap_usd),
                    f"{(candidate.age_days or 0):.0f}d",
                    f"{(candidate.silence_days or 0):.0f}d",
                    term.short(candidate.mint, 20),
                )
        table.render()

        term.tally(buried, alive, reasons, unit="looked up", kept="buried", dropped="alive")
        if buried == 0:
            term.warn(
                "no corpses found in this slice - check the tickers before "
                "concluding the graveyard is empty"
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(Graveyard().main())
