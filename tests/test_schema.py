"""The rulebook against its own schema."""

from tests.check_schema import validate


def test_rules_json_matches_its_schema():
    problems = validate()
    assert not problems, "\n".join(problems)
