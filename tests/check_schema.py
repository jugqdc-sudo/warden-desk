"""Validate rules.json against docs/rules.schema.json.

Runnable on its own (`python -m tests.check_schema`) so CI can fail on a bad
rulebook without pulling in the rest of the suite, and imported by
test_schema.py so a local `pytest` run covers it too.

If `jsonschema` is not installed the check reports that and exits clean - a
missing dev dependency is not a broken rulebook, and pretending otherwise
would train people to ignore the failure.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(ROOT, "rules.json")
SCHEMA = os.path.join(ROOT, "docs", "rules.schema.json")


def validate() -> list[str]:
    """Return a list of problems. Empty means the rulebook is well formed."""
    try:
        import jsonschema
    except ImportError:
        print("jsonschema not installed - skipping (pip install -e '.[dev]')")
        return []

    with open(RULES, encoding="utf-8") as handle:
        rules = json.load(handle)
    with open(SCHEMA, encoding="utf-8") as handle:
        schema = json.load(handle)

    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(rules)
    ]


def main() -> int:
    problems = validate()
    if problems:
        print(f"rules.json does not match its schema ({len(problems)} problems):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("rules.json matches docs/rules.schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
