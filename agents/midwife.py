"""MIDWIFE [R2] - counts names, not candles.

One ticker minted dozens of times inside a few hours is not a market. It is
production. Somebody is manufacturing a wave, and the coin they are all
copying is still lying wherever it died.

This agent watches births. It never looks at a chart.

    python3 desk.py midwife
    python3 desk.py midwife --window 6h --min-copies 8
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict

from agents.base import Agent
from core import feed, term
from core.ledger import Order, Verdict


def parse_duration(text: str) -> int:
    """`6h`, `90m` or a raw number of seconds."""
    text = text.strip().lower()
    if text.endswith("h"):
        return int(float(text[:-1]) * 3600)
    if text.endswith("m"):
        return int(float(text[:-1]) * 60)
    return int(text)


def densest_burst(times: list[float], window: int) -> tuple[int, int]:
    """(start index, size) of the tightest cluster of launches inside `window`."""
    best_start, best_size = 0, 0
    for start in range(len(times)):
        end = start
        while end + 1 < len(times) and times[end + 1] - times[start] <= window:
            end += 1
        if end - start + 1 > best_size:
            best_start, best_size = start, end - start + 1
    return best_start, best_size


class Wave:
    """A ticker being minted over and over, and the original underneath it."""

    def __init__(self, ticker: str, copies: list[feed.Coin], original: feed.Coin) -> None:
        self.ticker = ticker
        self.copies = copies
        self.original = original

    @property
    def size(self) -> int:
        return len(self.copies)

    @property
    def wallets(self) -> set[str]:
        return {coin.deployer for coin in self.copies if coin.deployer}

    @property
    def span_minutes(self) -> float:
        return (self.copies[-1].born - self.copies[0].born) / 60

    @property
    def every_minutes(self) -> float:
        return self.span_minutes / max(self.size - 1, 1)

    @property
    def age_minutes(self) -> float:
        """How long ago the last copy was minted - a stale wave is over."""
        return (time.time() - self.copies[-1].born) / 60

    @property
    def head_start_days(self) -> float:
        """How long the original had existed by the time the copying started."""
        return (self.copies[0].born - self.original.born) / 86400


class Midwife(Agent):
    name = "MIDWIFE"
    rule_id = "R2"
    job = "counts how many times a name is being minted right now"

    def check(self, order: Order) -> Verdict:
        """A buy needs a live, wide wave behind it - made by a crowd, not one wallet."""
        candidate = order.candidate
        if candidate is None:
            return self.ok()  # nothing to weigh on a sell

        if candidate.clones is None:
            return self.unknown("the number of copies of this ticker")

        min_copies = self.rule["min_copies"]
        if candidate.clones < min_copies:
            return self.no(
                "wave too thin",
                f"{candidate.clones} copies of ${candidate.ticker} - "
                f"a wave starts at {min_copies}",
            )

        min_wallets = self.rule["min_wallets"]
        if candidate.wallets_in_wave is not None and candidate.wallets_in_wave < min_wallets:
            return self.no(
                "one wallet spamming",
                f"{candidate.wallets_in_wave} wallet(s) minted all "
                f"{candidate.clones} copies - that is one person, not a crowd",
            )

        max_age = self.rule["max_wave_age_minutes"]
        if candidate.wave_age_minutes is not None and candidate.wave_age_minutes > max_age:
            return self.no(
                "wave is over",
                f"last copy minted {candidate.wave_age_minutes:.0f} min ago - "
                f"the production line stopped {max_age} min ago or more",
            )

        return self.ok()

    # ── standalone mode ─────────────────────────────────────────────────
    def find_waves(
        self,
        window: int,
        min_copies: int,
        min_wallets: int,
        original_gap: int,
    ) -> tuple[list[Wave], dict[str, int]]:
        """Scan the whole launch index for tickers being produced in bursts."""
        by_ticker: dict[str, list[feed.Coin]] = defaultdict(list)
        for coin in feed.stream():
            by_ticker[coin.ticker].append(coin)

        waves: list[Wave] = []
        rejected: dict[str, int] = defaultdict(int)

        for ticker, coins in by_ticker.items():
            if len(coins) < min_copies:
                rejected["too few copies"] += 1
                continue

            coins.sort(key=lambda coin: coin.born)
            start, size = densest_burst([coin.born for coin in coins], window)
            if size < min_copies:
                rejected["spread over days"] += 1
                continue

            burst = coins[start : start + size]
            wallets = {coin.deployer for coin in burst if coin.deployer}
            if len(wallets) < min_wallets:
                rejected["one wallet spamming"] += 1
                continue

            older = [coin for coin in coins if coin.born < burst[0].born - original_gap]
            if not older:
                rejected["no original to buy"] += 1
                continue

            waves.append(Wave(ticker, burst, older[0]))

        waves.sort(key=lambda wave: -wave.size)
        return waves, dict(rejected)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--window", default="6h", help="width of the wave window")
        parser.add_argument("--min-copies", type=int, default=None)
        parser.add_argument("--min-wallets", type=int, default=None)
        parser.add_argument("--top", type=int, default=10, help="how many waves to print")

    def demo(self, args: argparse.Namespace) -> int:
        window = parse_duration(args.window)
        min_copies = args.min_copies or self.rule["min_copies"]
        min_wallets = args.min_wallets or self.rule["min_wallets"]
        gap = self.rule["original_older_than_seconds"]

        index = feed.stats()
        term.head(
            "MIDWIFE",
            self.rule.title,
            asks=self.rule.asks,
            bench=f"index [bold]{index['coins']:,}[/] launches · "
            f"[bold]{index['tickers']:,}[/] names · window {args.window} · "
            f"{min_copies}+ copies from {min_wallets}+ wallets",
            footer="never looks at a price",
        )

        waves, rejected = self.find_waves(window, min_copies, min_wallets, gap)

        table = term.VerdictTable(
            ("TICKER", 12, "left"),
            ("COPIES", 7, "right"),
            ("IN", 7, "right"),
            ("EVERY", 8, "right"),
            ("WALLETS", 8, "right"),
            ("HEAD START", 11, "right"),
            ("ORIGINAL", 24, "left"),
        )
        for wave in waves[: args.top]:
            table.add(
                True,
                f"${wave.ticker[:11]}",
                wave.size,
                f"{wave.span_minutes:.0f}m",
                f"{wave.every_minutes:.1f}m",
                len(wave.wallets),
                f"{wave.head_start_days:.1f}d",
                term.short(wave.original.mint, 22),
            )
        table.render()

        term.tally(
            len(waves),
            sum(rejected.values()),
            dict(rejected),
            unit="names",
            kept="waves",
            dropped="rejected",
            wrote=f"index covers {index['days']:.1f} days of launches",
        )

        if not waves:
            term.warn(
                "no waves at these thresholds - widen --window or lower --min-copies "
                "before believing the feed is quiet"
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(Midwife().main())
