"""COLLECTOR [R3] - takes the original, never the clone.

MIDWIFE says a name is being manufactured. GRAVEYARD says where the old coin
under that name is lying. COLLECTOR is the one that puts the two together and
builds the candidate: the first coin ever minted with that ticker, still on
the floor, while a crowd is busy minting copies of its name somewhere else.

Two things are forbidden here, both of them the expensive kind of mistake:
buying one of the copies, and touching an original that already moved.

    python3 desk.py collector --top 5
    python3 desk.py collector --top 20 --save
"""

from __future__ import annotations

import argparse
import json
import os
import time

from agents.base import Agent
from agents.midwife import Midwife, Wave, parse_duration
from core import market, term
from core.ledger import Candidate, Order, Verdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATCH_PATH = os.environ.get("DESK_CATCH", os.path.join(ROOT, "data", "catch.jsonl"))


class Collector(Agent):
    name = "COLLECTOR"
    rule_id = "R3"
    job = "builds candidates: the original under a wave, never a copy of it"

    def check(self, order: Order) -> Verdict:
        candidate = order.candidate
        if candidate is None:
            return self.ok()

        if self.rule["buy_original_only"] and not candidate.is_original:
            return self.no(
                "that is a clone",
                f"this mint is one of the {candidate.clones or 0} copies of "
                f"${candidate.ticker}, not the coin they are copying",
            )

        max_move = self.rule["max_move_pct_since_wave"]
        if candidate.moved_pct > max_move:
            return self.no(
                "already moved",
                f"${candidate.ticker} is {candidate.moved_pct:+.0f}% since the wave "
                f"started - the desk does not chase what already left",
            )

        min_holders = self.rule["min_holders"]
        if candidate.holders is not None and candidate.holders < min_holders:
            return self.no(
                "nothing to collect",
                f"{candidate.holders} holders - there is no float to buy from",
            )

        return self.ok()

    # ── building candidates ─────────────────────────────────────────────
    def original_of(self, wave: Wave) -> Candidate | None:
        """Find the oldest coin ever minted under this ticker and price it live.

        The launch index only reaches back as far as the desk has been
        watching, so the true original is looked up on the launchpad instead.
        """
        listings = market.search(wave.ticker)
        if not listings:
            return None

        original = listings[0]
        cap_now = original.cap_usd
        return Candidate(
            mint=original.mint,
            ticker=original.ticker,
            cap_usd=cap_now,
            age_days=original.age_days,
            silence_days=original.silence_days,
            clones=wave.size,
            wallets_in_wave=len(wave.wallets),
            wave_age_minutes=wave.age_minutes,
            is_original=True,
            url=f"https://pump.fun/coin/{original.mint}",
        )

    def collect(self, top: int, window_text: str = "6h") -> list[Candidate]:
        """Run MIDWIFE over the index, then price each original on the launchpad."""
        midwife = Midwife(self.book)
        waves, _ = midwife.find_waves(
            window=parse_duration(window_text),
            min_copies=midwife.rule["min_copies"],
            min_wallets=midwife.rule["min_wallets"],
            original_gap=midwife.rule["original_older_than_seconds"],
        )

        candidates: list[Candidate] = []
        for wave in waves[:top]:
            candidate = self.original_of(wave)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--top", type=int, default=5, help="how many waves to work")
        parser.add_argument("--window", default="6h")
        parser.add_argument(
            "--save",
            action="store_true",
            help=f"append the candidates to {os.path.relpath(CATCH_PATH, ROOT)}",
        )

    def demo(self, args: argparse.Namespace) -> int:
        term.head(
            "COLLECTOR",
            self.rule.title,
            asks=self.rule.asks,
            footer=f"refuses anything more than "
            f"{self.rule['max_move_pct_since_wave']:.0f}% off the floor",
        )

        candidates = self.collect(args.top, args.window)
        if not candidates:
            term.warn(
                "no candidates built - either no wave cleared MIDWIFE, or the "
                "launchpad search returned nothing. Neither means the market is quiet."
            )
            return 1

        table = term.VerdictTable(
            ("TICKER", 12, "left"),
            ("COPIES", 7, "right"),
            ("WALLETS", 8, "right"),
            ("WAVE AGE", 9, "right"),
            ("ORIGINAL", 9, "right"),
            ("SILENT", 7, "right"),
            ("CAP", 10, "right"),
            ("CONTRACT", 24, "left"),
        )
        for candidate in candidates:
            table.add(
                True,
                f"${candidate.ticker[:11]}",
                candidate.clones,
                candidate.wallets_in_wave,
                f"{(candidate.wave_age_minutes or 0):.0f}m",
                f"{(candidate.age_days or 0):.0f}d",
                f"{(candidate.silence_days or 0):.0f}d",
                term.money(candidate.cap_usd),
                term.short(candidate.mint, 22),
            )
        table.render()

        if args.save:
            os.makedirs(os.path.dirname(CATCH_PATH), exist_ok=True)
            with open(CATCH_PATH, "a", encoding="utf-8") as handle:
                for candidate in candidates:
                    handle.write(
                        json.dumps(
                            {
                                "at": time.time(),
                                "mint": candidate.mint,
                                "ticker": candidate.ticker,
                                "cap_usd": candidate.cap_usd,
                                "age_days": candidate.age_days,
                                "silence_days": candidate.silence_days,
                                "clones": candidate.clones,
                                "wallets_in_wave": candidate.wallets_in_wave,
                                "wave_age_minutes": candidate.wave_age_minutes,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            term.note(f"{len(candidates)} candidates written to {CATCH_PATH}")
        return 0


if __name__ == "__main__":
    raise SystemExit(Collector().main())
