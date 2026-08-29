"""WARDEN - the agent that says no.

The other seven spend the day looking for a reason to buy. This one exists
to refuse, and it refuses far more often than it clears. It owns no rule of
its own: it runs all seven in R1..R7 order and then adds the only question
nobody else on the desk asks -

    if i buy this, who buys it from me?

Every check in `exit_liquidity` is about the exit. None of them is about
whether the coin goes up. That is deliberate: an entry filter answers "will
this move", and a warden answers "can i get out".

There is no manual override. A refusal is final, and it is written down.

    python3 desk.py warden --rules      the seven rules in one screen
    python3 desk.py warden              judge everything the collector caught
    python3 desk.py warden --log        the same, slowly, one verdict at a time
    python3 desk.py warden --table      csv of the verdicts, contracts included
"""

from __future__ import annotations

import argparse
import json
import os
import time

from agents.base import Agent
from agents.clock import Clock
from agents.collector import Collector
from agents.graveyard import Graveyard
from agents.ladder import Ladder
from agents.midwife import Midwife
from agents.toll import Toll
from agents.undertaker import Undertaker
from core import term
from core.ledger import REFUSALS_PATH, Candidate, Order, Verdict, record_refusal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATCH_PATH = os.environ.get("DESK_CATCH", os.path.join(ROOT, "data", "catch.jsonl"))

#: the seven, in the order WARDEN applies them
BENCH = (Graveyard, Midwife, Collector, Clock, Toll, Ladder, Undertaker)


class Warden(Agent):
    name = "WARDEN"
    rule_id = "R0"
    job = "checks every order against all seven rules and cannot be overruled"

    def __init__(self, book=None) -> None:
        super().__init__(book)
        self.bench = [agent_class(self.book) for agent_class in BENCH]
        self.exit_rules = self.book.exit_liquidity
        self.ruled_at: dict[str, float] = {}
        self.open_positions = 0

    # ── the exit questions, WARDEN's own ────────────────────────────────
    def exit_check(self, candidate: Candidate, at: float) -> Verdict:
        """Can this position be got out of? Order: impossible first, expensive second."""
        min_holders = self.exit_rules["min_holders"]
        if candidate.holders is None:
            return self.no(
                "counterparty unknown",
                f"holders of ${candidate.ticker} could not be read - "
                "an unknown counterparty is refused like a missing one",
            )
        if candidate.holders < min_holders:
            return self.no(
                "no counterparty",
                f"{candidate.holders} holders - there is nobody to sell to",
            )

        max_top10 = self.exit_rules["max_top10_share"]
        if candidate.top10_share is not None and candidate.top10_share >= max_top10:
            return self.no(
                "exit is one wallet",
                f"top 10 hold {candidate.top10_share:.0%} - "
                "one wallet is the whole bid",
            )

        max_silence = self.exit_rules["max_silence_days"]
        if candidate.silence_days is not None and candidate.silence_days > max_silence:
            return self.no(
                "book is dead",
                f"no trade in {candidate.silence_days:.0f} days - "
                "the exit is theoretical",
            )

        min_cap = self.exit_rules["min_cap_usd"]
        size = self.book.position_size
        if candidate.cap_usd is not None and candidate.cap_usd < min_cap:
            cost = size * self.book["TOLL"]["fee_rate_per_side"] * 2
            return self.no(
                "size moves it",
                f"cap {term.money(candidate.cap_usd)} - ${size:.0f} in and out "
                f"costs ${cost:.2f} before the price moves at all",
            )

        cooldown = self.exit_rules["verdict_cooldown_hours"] * 3600
        last = self.ruled_at.get(candidate.ticker)
        if last is not None and (at - last) < cooldown:
            return self.no(
                "already ruled",
                f"${candidate.ticker} was ruled on {(at - last) / 3600:.1f}h ago - "
                f"one verdict per ticker per {cooldown / 3600:.0f}h",
            )

        max_open = self.exit_rules["max_open_positions"]
        if self.open_positions >= max_open:
            return self.no(
                "book is full",
                f"{self.open_positions} positions already open - "
                "a fourth exit cannot be worked in time",
            )

        return self.ok()

    # ── the contract ────────────────────────────────────────────────────
    def check(self, order: Order) -> Verdict:
        """Run the seven, then the exit questions. First refusal wins and is final."""
        for agent in self.bench:
            verdict = agent.check(order)
            if verdict.denied:
                return verdict

        if order.action in ("buy", "add") and order.candidate is not None:
            return self.exit_check(order.candidate, order.at)

        return self.ok()

    def review(self, candidates: list[Candidate], save: bool = True) -> tuple[list, list]:
        """Judge a batch in arrival order. Returns (cleared, denied)."""
        cleared: list[tuple[Candidate, Verdict]] = []
        denied: list[tuple[Candidate, Verdict]] = []

        for candidate in candidates:
            order = Order(action="buy", candidate=candidate, at=candidate.seen_at)
            verdict = self.check(order)
            self.ruled_at[candidate.ticker] = candidate.seen_at

            if verdict.denied:
                denied.append((candidate, verdict))
                if save:
                    record_refusal(order, verdict)
            else:
                cleared.append((candidate, verdict))
                self.open_positions += 1

        return cleared, denied


# ── loading candidates ──────────────────────────────────────────────────
def load_catch(path: str = CATCH_PATH) -> list[Candidate]:
    """Read the candidates the collector has stored."""
    if not os.path.exists(path):
        return []
    found = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            found.append(
                Candidate(
                    mint=row["mint"],
                    ticker=row["ticker"],
                    cap_usd=row.get("cap_usd"),
                    holders=row.get("holders"),
                    top10_share=row.get("top10_share"),
                    silence_days=row.get("silence_days"),
                    age_days=row.get("age_days"),
                    clones=row.get("clones"),
                    wallets_in_wave=row.get("wallets_in_wave"),
                    wave_age_minutes=row.get("wave_age_minutes"),
                    seen_at=row.get("at", time.time()),
                )
            )
    return found


# ── output modes ────────────────────────────────────────────────────────
def print_rules(warden: Warden) -> None:
    """The whole rulebook in one screen - one panel per rule."""
    term.head(
        "RULES",
        f"the seven rules of the desk · v{warden.book.version}",
        asks=warden.book.manifest,
        footer="rules.json",
    )

    for rule in warden.book:
        term.rule_card(
            rule.id,
            rule.agent,
            rule.title,
            asks=rule.asks,
            denies=rule.denies,
            params=rule.params,
        )

    term.rule_card(
        "R0",
        "WARDEN",
        "the agent that says no",
        asks=warden.book.warden["asks"],
        denies="anything the seven refused, and anything it cannot sell",
        params={k: v for k, v in warden.exit_rules.items() if k not in ("note", "source")},
        accent=True,
    )
    term.note("the desk has no manual override. a denial is final.")


def print_table(cleared, denied) -> None:
    """CSV of every verdict - the refusals are the point of publishing it."""
    print("verdict,ticker,rule,agent,code,holders,top10,silent_days,cap_usd,contract")
    rows = [("DENIED", c, v) for c, v in denied] + [("CLEARED", c, v) for c, v in cleared]
    rows.sort(key=lambda row: row[1].seen_at)
    for label, candidate, verdict in rows:
        print(
            f"{label},{candidate.ticker},{verdict.rule_id},{verdict.agent},"
            f'"{verdict.code}",{candidate.holders if candidate.holders is not None else ""},'
            f'{candidate.top10_share if candidate.top10_share is not None else ""},'
            f'{candidate.silence_days if candidate.silence_days is not None else ""},'
            f'{candidate.cap_usd if candidate.cap_usd is not None else ""},{candidate.mint}'
        )


def print_verdicts(cleared, denied) -> None:
    """Every verdict as one table row - the desk's main view."""
    table = term.VerdictTable(
        ("TICKER", 12, "left"),
        ("VERDICT", 8, "left"),
        ("RULE", 20, "left"),
        ("HOLDERS", 8, "right"),
        ("TOP10", 6, "right"),
        ("SILENT", 7, "right"),
        ("CAP", 10, "right"),
        ("CONTRACT", 14, "left"),
    )
    rows = [(False, c, v) for c, v in denied] + [(True, c, v) for c, v in cleared]
    rows.sort(key=lambda row: row[1].seen_at)

    for passed, candidate, verdict in rows:
        holders = candidate.holders
        table.add(
            passed,
            f"${candidate.ticker[:11]}",
            term.verdict(passed, "CLEARED" if passed else "DENIED"),
            term.value("" if passed else verdict.code, good=None if passed else False),
            term.value("?" if holders is None else holders,
                       good=None if holders is None else holders >= 25),
            "-" if candidate.top10_share is None else f"{candidate.top10_share:.0%}",
            "-" if candidate.silence_days is None else f"{candidate.silence_days:.0f}d",
            term.money(candidate.cap_usd),
            term.short(candidate.mint),
        )
    table.render()


def print_stream(cleared, denied, gap: float) -> None:
    by_mint = {c.mint: ("DENY", c, v) for c, v in denied}
    by_mint.update({c.mint: ("PASS", c, v) for c, v in cleared})
    ordered = sorted(by_mint.values(), key=lambda row: row[1].seen_at)

    for kind, candidate, verdict in ordered:
        clock = time.strftime("%H:%M:%S", time.localtime(candidate.seen_at))
        title = f"${candidate.ticker:<12} {clock}"
        if kind == "DENY":
            term.denied(title, f"{verdict.rule_id} {verdict.code}", verdict.reason, candidate.mint)
        else:
            term.cleared(
                title,
                f"{candidate.holders} holders · silent "
                f"{(candidate.silence_days or 0):.0f}d · cap {term.money(candidate.cap_usd)}",
                candidate.mint,
            )
        time.sleep(gap)


class WardenCLI(Warden):
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--rules", action="store_true", help="print the seven rules")
        parser.add_argument("--log", action="store_true", help="one verdict at a time")
        parser.add_argument("--table", action="store_true", help="csv of every verdict")
        parser.add_argument("--gap", type=float, default=0.8, help="pause in --log mode")
        parser.add_argument(
            "--live", action="store_true", help="ask the collector for fresh candidates"
        )
        parser.add_argument("--top", type=int, default=5, help="waves to work in --live mode")
        parser.add_argument("--no-save", action="store_true", help="do not write refusals.jsonl")

    def demo(self, args: argparse.Namespace) -> int:
        if args.rules:
            print_rules(self)
            return 0

        candidates = Collector(self.book).collect(args.top) if args.live else load_catch()

        if not candidates:
            term.warn(
                "no candidates to judge. Run `python3 desk.py collector --save`, "
                "or `python3 desk.py warden --live`."
            )
            return 1

        if not args.table:
            term.head(
                "WARDEN",
                self.book.warden["title"],
                asks=self.book.warden["asks"],
                bench="  ".join(f"[dim]{rule.id}[/] {rule.agent}" for rule in self.book),
                footer=f"{len(candidates)} candidates · a denial is final",
            )

        cleared, denied = self.review(candidates, save=not args.no_save)

        if args.table:
            print_table(cleared, denied)
            return 0

        if args.log:
            print_stream(cleared, denied, args.gap)
        else:
            print_verdicts(cleared, denied)

        reasons: dict[str, int] = {}
        for _, verdict in denied:
            key = f"{verdict.rule_id} {verdict.code}"
            reasons[key] = reasons.get(key, 0) + 1
        wrote = "" if args.no_save else f"written to {os.path.relpath(REFUSALS_PATH, ROOT)}"
        term.tally(len(cleared), len(denied), reasons, wrote=wrote)

        if not denied:
            term.warn(
                f"zero refusals on {len(candidates)} candidates - check the "
                "thresholds, that does not happen on this market"
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(WardenCLI().main())
