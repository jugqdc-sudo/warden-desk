"""The interface every agent on this desk implements.

Eight agents, one job each. Seven of them own a rule out of rules.json and
answer a single question about an order. The eighth, WARDEN, owns no rule of
its own - it runs the other seven and adds the exit checks, and its refusal
is final.

An agent never fetches its thresholds from anywhere but rules.json, and never
returns a soft answer: `check` gives a clear verdict or a clear refusal.
"""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod

from core import rules as rulebook
from core.ledger import Order, Verdict, clear, deny


class Agent(ABC):
    """One agent. Subclasses set `name` and `rule_id` and implement `check`."""

    name: str = ""
    rule_id: str = ""
    #: one line, printed under the banner and in `desk.py rules`
    job: str = ""

    def __init__(self, book: rulebook.RuleBook | None = None) -> None:
        self.book = book or rulebook.load()
        self.rule = self.book[self.name] if self.name in rulebook.AGENTS else None

    # ── the contract ────────────────────────────────────────────────────
    @abstractmethod
    def check(self, order: Order) -> Verdict:
        """Judge one order. Never raises for a missing number - refuses instead."""

    # ── helpers shared by every agent ───────────────────────────────────
    def ok(self) -> Verdict:
        return clear(self.rule_id, self.name)

    def no(self, code: str, reason: str) -> Verdict:
        return deny(self.rule_id, self.name, code, reason)

    def unknown(self, what: str) -> Verdict:
        """Refuse on a number the desk could not read.

        The desk is fail-closed by design: an unreadable input is treated the
        same as a bad one, because the alternative is a rule that quietly
        stops applying whenever an API is down.
        """
        return self.no(
            "unknown input",
            f"{what} is unknown - the rule cannot be checked, so the answer is no",
        )

    def headline(self) -> str:
        rule = self.rule
        if rule is None:
            return f"{self.name} - {self.job}"
        return f"{self.name} [{rule.id}] - {rule.title}"

    # ── CLI plumbing, so every agent is runnable on its own ─────────────
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:  # noqa: B027
        """Extra flags for this agent's demo mode. Optional."""

    def demo(self, args: argparse.Namespace) -> int:
        """Run the agent against the shipped snapshot. Returns an exit code."""
        raise SystemExit(f"{self.name} has no standalone mode - run it through desk.py warden")

    def main(self, argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(prog=self.name.lower(), description=self.headline())
        self.add_arguments(parser)
        return self.demo(parser.parse_args(argv))
