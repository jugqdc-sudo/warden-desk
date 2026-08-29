"""Loader for rules.json - the seven rules that are the whole project.

Nothing in this repository hard-codes a threshold. Every agent asks this
module for its rule and reads the numbers from the file, so the rules can be
read, diffed and argued with in one place.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.environ.get("DESK_RULES", os.path.join(ROOT, "rules.json"))

AGENTS = (
    "GRAVEYARD",
    "MIDWIFE",
    "COLLECTOR",
    "CLOCK",
    "TOLL",
    "LADDER",
    "UNDERTAKER",
)


@dataclass(frozen=True)
class Rule:
    """One rule: who enforces it, what it asks, and the numbers behind it."""

    id: str
    agent: str
    title: str
    asks: str
    denies: str
    source: str
    params: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        """Read a parameter, failing loudly when it is missing.

        A typo in a threshold name must not silently become a default that
        lets everything through.
        """
        if key not in self.params:
            raise KeyError(f"{self.id}/{self.agent}: no parameter {key!r} in rules.json")
        return self.params[key]


class RuleBook:
    """The seven rules plus WARDEN's own exit checks."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.raw = document
        self.version: str = document["version"]
        self.manifest: str = document["manifest"]
        self.money: dict[str, Any] = document["money"]
        self.warden: dict[str, Any] = document["warden"]
        self._by_agent: dict[str, Rule] = {}
        for entry in document["rules"]:
            rule = Rule(
                id=entry["id"],
                agent=entry["agent"],
                title=entry["title"],
                asks=entry["asks"],
                denies=entry["denies"],
                source=entry["source"],
                params=entry["params"],
            )
            self._by_agent[rule.agent] = rule
        self._validate()

    def _validate(self) -> None:
        missing = [name for name in AGENTS if name not in self._by_agent]
        if missing:
            raise ValueError(f"rules.json is missing rules for: {', '.join(missing)}")
        enforced = set(self.warden["enforces"])
        known = {rule.id for rule in self._by_agent.values()}
        if enforced != known:
            raise ValueError(
                f"WARDEN enforces {sorted(enforced)} but the file defines {sorted(known)}"
            )

    def __getitem__(self, agent: str) -> Rule:
        return self._by_agent[agent.upper()]

    def __iter__(self):
        """Rules in R1..R7 order, which is also the order WARDEN applies them."""
        return iter(sorted(self._by_agent.values(), key=lambda r: r.id))

    @property
    def position_size(self) -> float:
        return float(self.money["position_size_usd"])

    @property
    def exit_liquidity(self) -> dict[str, Any]:
        return self.warden["exit_liquidity"]


_cached: RuleBook | None = None


def load(path: str = RULES_PATH) -> RuleBook:
    """Read rules.json once and keep it for the life of the process."""
    global _cached
    if _cached is None:
        with open(path, encoding="utf-8") as handle:
            _cached = RuleBook(json.load(handle))
    return _cached


def raw(path: str = RULES_PATH) -> dict:
    """The rulebook as plain data, for `desk.py rules --json` and other tools."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
