"""The rules must load, cover all seven agents, and not contradict each other.

That last one is not decoration. An earlier draft had GRAVEYARD demanding 30+
days of silence while WARDEN refused anything silent for more than 30 days -
two rules that between them could never be satisfied, so the desk returned
zero candidates and looked strict rather than broken.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import rules


def test_all_seven_agents_have_a_rule():
    book = rules.load()
    covered = {rule.agent for rule in book}
    assert covered == set(rules.AGENTS)


def test_rule_ids_are_r1_to_r7():
    book = rules.load()
    assert [rule.id for rule in book] == [f"R{n}" for n in range(1, 8)]


def test_every_rule_states_its_question_and_its_source():
    for rule in rules.load():
        assert rule.asks.strip(), f"{rule.id} does not say what it asks"
        assert rule.denies.strip(), f"{rule.id} does not say what it denies"
        assert rule.source.strip(), f"{rule.id} does not say where its numbers came from"


def test_graveyard_does_not_contradict_the_warden_on_silence():
    book = rules.load()
    graveyard = book["GRAVEYARD"]
    assert "min_silence_days" not in graveyard.params, (
        "GRAVEYARD must not require silence: WARDEN refuses coins silent longer "
        "than max_silence_days, and the two rules would cancel out"
    )


def test_floor_band_sits_below_the_wardens_cap_requirement():
    """The desk is allowed to disagree with itself - but knowingly."""
    book = rules.load()
    floor = book["GRAVEYARD"]["floor_usd"]
    warden_min_cap = book.exit_liquidity["min_cap_usd"]
    assert floor < warden_min_cap, (
        "this tension is the honest fact of the project: the collector wants a "
        "corpse, the warden wants a live book"
    )


def test_missing_parameter_fails_loudly():
    book = rules.load()
    try:
        book["CLOCK"]["not_a_real_threshold"]
    except KeyError as error:
        assert "rules.json" in str(error)
    else:
        raise AssertionError("a missing threshold must raise, not default to something")
