"""The repository against the claims made in public about this desk.

Every threshold here was stated in a post before it was written in code. If a
rule is retuned, this file fails first - which is the point: the published
version and the running version are not allowed to drift apart silently.
"""

from core import rules


def book():
    return rules.load()


# ── the seven, as described publicly ────────────────────────────────────
def test_graveyard_floor_is_the_published_one():
    assert book()["GRAVEYARD"]["floor_usd"] == 1800


def test_midwife_window_is_six_hours():
    assert book()["MIDWIFE"]["window_seconds"] == 6 * 3600


def test_midwife_never_looks_at_a_price():
    """'counts names, not candles' - no cap or price threshold may appear here."""
    params = book()["MIDWIFE"].params
    assert not [key for key in params if "cap" in key or "price" in key]


def test_collector_takes_the_original_and_never_a_clone():
    collector = book()["COLLECTOR"]
    assert collector["buy_original_only"] is True
    assert collector["max_move_pct_since_wave"] == 0.0


def test_clock_locks_the_sell_for_five_minutes_and_the_stop_overrides_it():
    clock = book()["CLOCK"]
    assert clock["lock_seconds"] == 300
    assert clock["stop_loss_pct"] == -25.0
    assert clock["stop_overrides_lock"] is True


def test_toll_charges_both_sides_and_freezes_at_half_the_hour():
    toll = book()["TOLL"]
    assert toll["fee_rate_per_side"] == 0.0125
    assert toll["freeze_when_fees_exceed_profit_share"] == 0.5


def test_ladder_never_averages_down():
    ladder = book()["LADDER"]
    assert ladder["averaging_down"] is False
    assert ladder["add_only_if_open_pnl_pct_above"] == 0.0


def test_undertaker_thesis_timer_is_six_hours():
    undertaker = book()["UNDERTAKER"]
    assert undertaker["thesis_timeout_seconds"] == 6 * 3600
    assert undertaker["close_at_market"] is True


# ── the eighth ──────────────────────────────────────────────────────────
def test_warden_enforces_all_seven_and_cannot_be_overruled():
    warden = book().warden
    assert warden["enforces"] == [f"R{n}" for n in range(1, 8)]
    assert warden["override"] is False


def test_warden_exit_thresholds_are_the_published_ones():
    exits = book().exit_liquidity
    assert exits["min_holders"] == 25
    assert exits["max_top10_share"] == 0.25
    assert exits["max_silence_days"] == 30
    assert exits["min_cap_usd"] == 5000


def test_every_rule_says_where_its_number_came_from():
    """A threshold nobody can trace is a threshold nobody can argue with."""
    for rule in book():
        assert rule.source, f"{rule.agent} has no source"
