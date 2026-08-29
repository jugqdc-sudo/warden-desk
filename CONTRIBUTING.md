# Contributing

The useful contribution to this project is not a feature. It is evidence that
a rule is wrong.

## Arguing with a rule

Every refusal is written to `data/refusals.jsonl` with the rule, the reason and
the contract address. That makes the desk falsifiable: pick a refusal, look up
what the coin did afterwards, and bring both.

```bash
python3 desk.py warden --table > verdicts.csv
```

A good issue looks like this:

> `R0 no counterparty` refused `$X` on 2026-08-20 at 4 holders. Thirty days
> later it traded $NN,NNN of volume with NNN holders. Contract: `...`. Sample
> of 40 similar refusals attached - 12 of them did the same.

A weak issue looks like this:

> 25 holders is too strict, most good coins start with fewer.

The difference is a base rate. One coin that got away is a story; forty
refusals with what happened next is an argument, and the rules were built to
lose that argument when it is made properly.

## Changing a threshold

Thresholds live in [`rules.json`](rules.json) and nowhere else. No agent may
hard-code a number that belongs there - `tests/test_rules.py` fails if one does.

1. Change the number in `rules.json`.
2. Update its `source` field to say where the new number came from.
3. Run `python3 -m pytest`. `tests/test_claims.py` will fail, because it pins
   the published thresholds on purpose - update it in the same commit so the
   public description and the running code move together.
4. Put the refusal rate before and after in the pull request.

## Adding a rule

1. Add it to `rules.json` with `id`, `agent`, `title`, `asks`, `denies`,
   `params`, `source`. `asks` must end in a question mark - a rule that cannot
   be phrased as a question is a preference.
2. Subclass `Agent` in `agents/`, set `name` and `rule_id`, implement `check`.
3. Register it in `BENCH` in `agents/warden.py` and `AGENTS` in `desk.py`.
4. Write a test that it refuses the thing it exists to refuse.
5. Check it does not contradict an existing rule. Two sensible rules can be
   jointly unsatisfiable - that happened here once and the desk returned zero
   candidates while looking strict rather than broken.

The schema in `docs/rules.schema.json` allows exactly seven rules. An eighth
means you are proposing a change to the shape of the desk, which is fine, but
say so in the pull request.

## House rules for code

- **Fail closed.** A rule that cannot read its input refuses. Use
  `self.unknown(what)` - never pass because an API was down.
- **Reasons are sentences.** `DENY_R6` tells nobody anything six months later.
  `"$MICHU is at -8.0% - the desk does not add to a losing position"` does.
- **Filters report what they dropped.** A filter that does not say what it
  threw away is indistinguishable from a broken one.
- **No execution.** No transaction building, no signing, no key handling. That
  belongs outside this repository, on purpose.
- **The desk describes, `core/term.py` draws.** Agents never print colours.

## Running the checks

```bash
pip install -e ".[dev]"
python3 -m pytest          # 43 tests, all offline
python3 -m ruff check .
python3 -m tests.check_schema
```

CI runs the same on Python 3.10 through 3.13, plus a fresh-clone run of every
command in the README with no keys and no configuration.
