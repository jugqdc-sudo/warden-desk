# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org): the rulebook in `rules.json` carries
its own `version`, and a threshold change bumps that too.

## [1.0.0] - 2026-08-28

First public release. Eight agents, seven rules, no execution layer.

### Added
- `rules.json` - the seven rules in one file, each with the question it asks,
  what it denies, its thresholds, and the source of every number.
- `docs/rules.schema.json` - JSON Schema for the rulebook, checked in CI.
- Eight agents behind one interface: `GRAVEYARD`, `MIDWIFE`, `COLLECTOR`,
  `CLOCK`, `TOLL`, `LADDER`, `UNDERTAKER`, and `WARDEN`, which runs the other
  seven and adds the exit questions.
- `data/coins.sqlite` - 12,663 launches over 8.5 days, public on-chain fields
  only, so the whole desk runs offline on a fresh clone with no keys.
- `data/refusals.jsonl` - every refusal recorded with rule, reason, contract
  and the candidate as it looked at the time, so a verdict can be re-judged
  later without trusting today's numbers.
- `tests/test_claims.py` - the thresholds pinned against what was stated
  publicly, so the described desk and the running desk cannot drift apart.

### Known limitations
- Holder counts need an indexed RPC call. Without `DESK_RPC` they read as
  unknown, and unknown is a refusal.
- The bundled index is a historical slice, so `--live` finds few fresh waves in
  it and says so rather than reporting a quiet market.
- The refusal rate on the bundled snapshot is 98%. That is the finders and the
  warden wanting opposite things, and it is printed rather than tuned away.
