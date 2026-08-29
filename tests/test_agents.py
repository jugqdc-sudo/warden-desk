"""Each agent refuses the thing it exists to refuse, and clears the rest.

These run offline: no network, no node, no keys.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.clock import Clock
from agents.graveyard import Graveyard
from agents.ladder import Ladder
from agents.midwife import Midwife, densest_burst, parse_duration
from agents.toll import HourBook, Toll
from agents.undertaker import Undertaker
from agents.warden import Warden
from core.ledger import Candidate, Order, Position


def corpse(**overrides) -> Candidate:
    """A candidate that passes everything unless a test breaks it on purpose."""
    base = dict(
        mint="So11111111111111111111111111111111111111112",
        ticker="TEST",
        cap_usd=9000.0,
        holders=120,
        top10_share=0.10,
        silence_days=3.0,
        age_days=800.0,
        clones=14,
        wallets_in_wave=9,
        wave_age_minutes=4.0,
        is_original=True,
    )
    base.update(overrides)
    return Candidate(**base)


def position(**overrides) -> Position:
    base = dict(
        ticker="TEST",
        mint="",
        size_usd=50.0,
        entry_price=1.0,
        opened_at=time.time() - 60,
        pnl_pct=5.0,
    )
    base.update(overrides)
    return Position(**base)


# ── R1 GRAVEYARD ────────────────────────────────────────────────────────
def test_graveyard_refuses_a_coin_that_is_still_trading():
    verdict = Graveyard().check(Order(action="buy", candidate=corpse(cap_usd=250_000)))
    assert verdict.denied and verdict.code == "still alive"


def test_graveyard_refuses_a_young_coin():
    verdict = Graveyard().check(Order(action="buy", candidate=corpse(age_days=30)))
    assert verdict.denied and verdict.code == "too young to be dead"


def test_graveyard_clears_an_old_cheap_coin():
    assert Graveyard().check(Order(action="buy", candidate=corpse())).ok


# ── R2 MIDWIFE ──────────────────────────────────────────────────────────
def test_midwife_refuses_a_thin_wave():
    verdict = Midwife().check(Order(action="buy", candidate=corpse(clones=3)))
    assert verdict.denied and verdict.code == "wave too thin"


def test_midwife_refuses_one_wallet_pretending_to_be_a_crowd():
    verdict = Midwife().check(Order(action="buy", candidate=corpse(wallets_in_wave=1)))
    assert verdict.denied and verdict.code == "one wallet spamming"


def test_midwife_refuses_when_the_number_of_copies_is_unknown():
    verdict = Midwife().check(Order(action="buy", candidate=corpse(clones=None)))
    assert verdict.denied and verdict.code == "unknown input"


def test_densest_burst_finds_the_cluster_not_the_span():
    times = [0, 10, 20, 100_000, 100_010, 100_020, 100_030]
    start, size = densest_burst(times, window=3600)
    assert (start, size) == (3, 4)


def test_parse_duration():
    assert parse_duration("6h") == 21600
    assert parse_duration("90m") == 5400
    assert parse_duration("45") == 45


# ── R4 CLOCK ────────────────────────────────────────────────────────────
def test_clock_locks_an_early_exit():
    verdict = Clock().check(
        Order(action="sell", position=position(opened_at=time.time() - 42, pnl_pct=-4))
    )
    assert verdict.denied and verdict.code == "sell locked"


def test_clock_opens_for_the_stop():
    verdict = Clock().check(
        Order(action="sell", position=position(opened_at=time.time() - 42, pnl_pct=-30))
    )
    assert verdict.ok


def test_clock_opens_once_the_lock_expires():
    verdict = Clock().check(
        Order(action="sell", position=position(opened_at=time.time() - 400, pnl_pct=-4))
    )
    assert verdict.ok


# ── R5 TOLL ─────────────────────────────────────────────────────────────
def test_toll_round_trip_costs_both_sides():
    toll = Toll()
    cost = toll.round_trip_cost(50.0, sol_usd=100.0)
    assert 1.25 < cost < 1.40  # 1.25% each way plus two network fees


def test_toll_freezes_when_fees_eat_the_hour():
    toll = Toll(hour=HourBook(fees_usd=4.0, profit_usd=6.0))
    verdict = toll.check(Order(action="buy", size_usd=50.0))
    assert verdict.denied and verdict.code == "fees are winning"


def test_toll_never_blocks_an_exit():
    toll = Toll(hour=HourBook(fees_usd=40.0, profit_usd=1.0))
    assert toll.check(Order(action="sell", position=position())).ok


# ── R6 LADDER ───────────────────────────────────────────────────────────
def test_ladder_refuses_to_average_down():
    verdict = Ladder().check(Order(action="add", position=position(pnl_pct=-8)))
    assert verdict.denied and verdict.code == "averaging down"


def test_ladder_allows_an_add_to_a_winner():
    assert Ladder().check(Order(action="add", position=position(pnl_pct=12))).ok


def test_ladder_stops_at_the_last_rung():
    verdict = Ladder().check(Order(action="add", position=position(pnl_pct=12, adds=3)))
    assert verdict.denied and verdict.code == "ladder finished"


# ── R7 UNDERTAKER ───────────────────────────────────────────────────────
def test_undertaker_closes_an_expired_thesis():
    verdict = Undertaker().check(
        Order(action="hold", position=position(opened_at=time.time() - 7 * 3600))
    )
    assert verdict.denied and verdict.code == "thesis expired"


def test_undertaker_leaves_a_live_thesis_alone():
    verdict = Undertaker().check(
        Order(action="hold", position=position(opened_at=time.time() - 3600))
    )
    assert verdict.ok


# ── WARDEN ──────────────────────────────────────────────────────────────
def test_warden_refuses_when_there_is_nobody_to_sell_to():
    verdict = Warden().check(Order(action="buy", candidate=corpse(holders=4)))
    assert verdict.denied and verdict.code == "no counterparty"


def test_warden_refuses_an_unknown_holder_count():
    """Fail-closed: an unreadable input is refused like a bad one."""
    verdict = Warden().check(Order(action="buy", candidate=corpse(holders=None)))
    assert verdict.denied and verdict.code == "counterparty unknown"


def test_warden_refuses_when_the_exit_is_one_wallet():
    verdict = Warden().check(Order(action="buy", candidate=corpse(top10_share=0.61)))
    assert verdict.denied and verdict.code == "exit is one wallet"


def test_warden_stops_at_the_first_refusal_and_names_the_rule():
    verdict = Warden().check(Order(action="buy", candidate=corpse(clones=2, holders=4)))
    assert verdict.rule_id == "R2"  # MIDWIFE runs before the exit checks


def test_warden_clears_a_candidate_that_survives_all_seven():
    assert Warden().check(Order(action="buy", candidate=corpse())).ok


def test_warden_closes_the_book_after_three_positions():
    warden = Warden()
    candidates = [corpse(ticker=f"T{n}", mint=f"m{n}") for n in range(5)]
    cleared, denied = warden.review(candidates, save=False)
    assert len(cleared) == 3
    assert all(verdict.code == "book is full" for _, verdict in denied)
