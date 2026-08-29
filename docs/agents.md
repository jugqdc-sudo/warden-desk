# The eight agents, one at a time

Seven agents look for a reason to buy. The eighth exists to refuse, and the
desk has no manual override.

Every agent implements the same interface. It owns one rule out of
[`rules.json`](../rules.json), reads its thresholds from there, and answers a
single question about an order:

```python
class Agent(ABC):
    name: str        # GRAVEYARD, MIDWIFE, ...
    rule_id: str     # R1, R2, ...

    def check(self, order: Order) -> Verdict:
        """Judge one order. Never raises on a missing number - refuses instead."""
```

A verdict is either `ok()` or `no(code, reason)`. There is a third helper,
`unknown(what)`, which is a refusal with a specific meaning: the rule could
not see its input. That distinction matters and is covered at the bottom.

---

## R1 · GRAVEYARD - indexes the dead

A coin that runs out of buyers does not disappear. It sinks to the bottom of
an empty bonding curve, sits around $1,800, and stays there. Nobody is
defending a position in it and nobody is watching. That is the only inventory
this desk wants.

**Asks:** is this coin actually on the floor of an empty curve?
**Refuses:** the coin is still bid, or it is too young to be a corpse.

```json
"params": {
  "floor_usd": 1800,
  "floor_band_usd": 700,
  "max_cap_usd": 60000,
  "min_age_days": 365
}
```

```bash
python3 desk.py graveyard --ticker MICHU
python3 desk.py graveyard --scan 40
```

```
GRAVEYARD  indexing the dead · floor $1,800 ±$700 · 365+ days old · under $60,000

  CLEARED  $MICHU          $2,986     870d old     870d silent
  buried - eligible inventory
  3wVYuML2nsQb3VNRoPYBhygaVoSzmpFhUS8Q9nBCewgp
```

**Note on what is deliberately missing.** GRAVEYARD does not test how long a
coin has been silent, even though silence sounds like the most obvious sign of
death. WARDEN refuses anything silent for more than 30 days, so a graveyard
rule demanding 30+ days of silence made a pair nothing could satisfy. See
[the contradiction](#the-two-rules-that-cancelled-each-other-out) below.

---

## R2 · MIDWIFE - counts names, not candles

The one agent here that never looks at a price.

When the same ticker is minted forty nine times in six hours, that is not a
market, it is production. Somebody is running a line, and the coin they are
all copying is lying wherever it died.

MIDWIFE groups every launch in the index by name, finds the densest burst
inside the window, and checks the copies came from different wallets - thirty
copies from one wallet is a person talking to himself, not a crowd.

**Asks:** is someone manufacturing a wave on this ticker right now?
**Refuses:** thin wave, copies spread over days, one wallet spamming itself,
or a wave that already finished.

```json
"params": {
  "window_seconds": 21600,
  "min_copies": 8,
  "min_wallets": 5,
  "original_older_than_seconds": 7200,
  "max_wave_age_minutes": 20
}
```

```bash
python3 desk.py midwife --window 6h --min-copies 8
```

```
MIDWIFE  watching births, not charts · index 12,663 launches / 4,883 names
         window 6h · 8+ copies from 5+ wallets

  WAVE  $DOLLY
  49 copies in 345 min - a fresh one every 7.2 min
  from 30 different wallets
  the name existed 3.4 days before the copying started
  7dLXJMPyg3tfm4fFPHCYiTrAeEvxNhXSBx67emFBpump

42 waves out of 4,883 names
rejected:
   4,620  too few copies
     103  spread over days
      93  no original to buy
      24  one wallet spamming
```

The burst finder is the only real algorithm in the agent - it looks for the
tightest cluster, not the widest span, because eight copies over three days is
not a wave:

```python
def densest_burst(times: list[float], window: int) -> tuple[int, int]:
    """(start index, size) of the tightest cluster of launches inside `window`."""
    best_start, best_size = 0, 0
    for start in range(len(times)):
        end = start
        while end + 1 < len(times) and times[end + 1] - times[start] <= window:
            end += 1
        if end - start + 1 > best_size:
            best_start, best_size = start, end - start + 1
    return best_start, best_size
```

Every rejection reason is printed with a count at the end of the run. A filter
that does not say what it threw away is indistinguishable from a broken one.

---

## R3 · COLLECTOR - takes the original, never the clone

MIDWIFE says a name is being manufactured. GRAVEYARD says what counts as a
corpse. COLLECTOR joins them: it takes the wave, finds the first coin ever
minted under that ticker, and prices it live.

The local index only reaches back as far as the desk has been watching, so the
true original is looked up on the launchpad instead - `market.search()` over
the public pump.fun endpoint, filtered down to an exact ticker match, because
a search for `SIA` also returns `SIAMESE`.

**Asks:** am i about to buy the corpse, or a copy of it?
**Refuses:** the target is a clone, or the original already moved.

```bash
python3 desk.py collector --top 5 --save
```

```
COLLECTOR  the original, never the clone · refuses anything more than 0% off the floor

  CATCH  $DOLLY
  wave: 49 copies from 30 wallets, last one 2406 min ago
  original: 865 days old, $3,045 cap, silent 407 days
  6osQCgfWSWwt8oof4iVXXDy9rFKQBgnY6j2gQRPtFuho
```

Forty nine copies of the name; the original is 865 days old, $3,045 cap, no
trade in 407 days. That is the whole thesis in four numbers.

Chasing is the operator's instinct, not the desk's - so `max_move_pct_since_wave`
is `0.0`. If it already ran, it is not a candidate.

---

## R4 · CLOCK - keeps the sell button locked

This rule is aimed at the operator, not at the market. The measured median
holding time on this desk was **42 seconds**, and almost every one of those
exits was early rather than late.

Five minutes, locked. The only thing that opens it early is the stop.

**Asks:** has the position been held long enough to be allowed to close?
**Refuses:** a manual exit inside the lock while the stop has not fired.

```json
"params": {
  "lock_seconds": 300,
  "stop_loss_pct": -25.0,
  "stop_overrides_lock": true
}
```

```bash
python3 desk.py clock --held 42 --pnl -4
```

```
  DENIED   $MICHU  held 42s  pnl -4.0%
  rule: sell locked
  $MICHU has been held 42s of 300s and is at -4.0%, above the -25% stop -
  the button stays shut
```

---

## R5 · TOLL - counts the fee while you trade

On a bonding curve you pay 1.25% going in and 1.25% coming out. TOLL counts
the bill in real time, and when an hour of fees has eaten half of that hour's
profit, entries freeze for an hour.

It never blocks an exit. A rule that traps you in a position to save on fees
is not risk management.

**Asks:** is the hour's fee bill eating the hour's profit?
**Refuses:** new entries while fees this hour exceed half the profit this hour.

```bash
python3 desk.py toll --profit 6 --fees 4
```

```
TOLL  1.25% in, 1.25% out · freezes entries when fees pass 50% of the hour's profit

  position size        $50.00
  fee in               $0.62
  fee out              $0.62
  network, both ways   $0.11
  round trip           $1.36
  the position has to gain 2.71% just to come back to flat

  DENIED   hour: $6.00 profit against $4.00 fees
  rule: fees are winning
  $4.00 in fees against $6.00 of profit this hour - entries frozen for 60 min
```

TOLL does **not** check position size against market cap. That is WARDEN's
question (`min_cap_usd`), and having both agents ask it produced two different
names for one refusal.

---

## R6 · LADDER - adds to winners, and only to winners

Averaging down is banned at desk level. Not discouraged, not sized down.
Banned, with no override.

**Asks:** is this position already in profit before i add to it?
**Refuses:** any add to a losing position, and any rung past the last one.

```python
def check(self, order: Order) -> Verdict:
    if order.action != "add":
        return self.ok()

    position = order.position
    if position is None:
        return self.unknown("the position being added to")

    threshold = self.rule["add_only_if_open_pnl_pct_above"]
    if not self.rule["averaging_down"] and position.pnl_pct <= threshold:
        return self.no(
            "averaging down",
            f"${position.ticker} is at {position.pnl_pct:+.1f}% - "
            "the desk does not add to a losing position, and this rule "
            "has no override",
        )

    max_adds = self.rule["max_adds"]
    if position.adds >= max_adds:
        return self.no(
            "ladder finished",
            f"{position.adds} adds already made on ${position.ticker} - "
            f"the ladder stops at {max_adds}",
        )

    return self.ok()
```

That is the entire agent. It reads the threshold from `rules.json`, and the
refusal is written as a full sentence: six months from now `DENY_R6` tells you
nothing, and "the desk does not add to a losing position" tells you everything.

```bash
python3 desk.py ladder --pnl -8      # DENIED, averaging down
python3 desk.py ladder --pnl 12      # CLEARED, next rung $25.00
```

---

## R7 · UNDERTAKER - the thesis has a clock

A position here is opened for one stated reason: a wave is being manufactured
on a name and the original is cheap. That reason has a shelf life of six
hours. When the timer runs out the position closes at market - not when the
chart looks better, not when the operator has a feeling.

CLOCK stops an exit that comes too early. UNDERTAKER stops one that never
comes.

**Asks:** has the reason for this trade expired?
**Refuses:** holding past the thesis timer.

```bash
python3 desk.py undertaker --held 7h
```

```
  DENIED   $MICHU  open 7.0h  pnl -11.0%
  rule: thesis expired
  $MICHU has been open 7.0h against a 6h thesis at -11.0% - closing at market
```

---

## WARDEN - the one that says no

The eighth agent owns no rule of its own. It runs all seven in R1..R7 order on
every order, and then asks the one question none of them ask:

**if i buy this, who buys it from me.**

```python
def check(self, order: Order) -> Verdict:
    """Run the seven, then the exit questions. First refusal wins and is final."""
    for agent in self.bench:
        verdict = agent.check(order)
        if verdict.denied:
            return verdict

    if order.action in ("buy", "add") and order.candidate is not None:
        return self.exit_check(order.candidate, order.at)

    return self.ok()
```

Every check it owns is about the exit. None is about whether the coin goes up:

| check | threshold | refusal |
|---|---|---|
| `min_holders` | 25 | no counterparty - there is nobody to sell to |
| `max_top10_share` | 0.25 | exit is one wallet |
| `max_silence_days` | 30 | book is dead - the exit is theoretical |
| `min_cap_usd` | $5,000 | size moves it - own sell is the movement |
| `verdict_cooldown_hours` | 24 | already ruled - one verdict per ticker per day |
| `max_open_positions` | 3 | book is full - a fourth exit cannot be worked |

Refusals are written to `data/refusals.jsonl` with the rule, the reason and
the contract address. They are the output of this desk: a month later anyone
can check what those coins actually did and tell the desk its rules were wrong.

```bash
python3 desk.py warden           # judge the bundled candidates
python3 desk.py warden --log     # one verdict at a time
python3 desk.py warden --table   # csv, contracts included
python3 desk.py warden --live    # find fresh waves and rule on them
```

```
WARDEN  reviewing 128 candidates · seven rules, then one question: who buys this from me

  DENIED   $GOOB        12:34:35
  rule: R0 no counterparty
  2 holders - there is nobody to sell to
  BgmCuReJVhJ7k8BzSvqqVovWxobRKpVrTw1cT7GZQHoA

  DENIED   $TRUMP       20:33:01
  rule: R0 book is dead
  no trade in 123 days - the exit is theoretical
  5147jVC5SBeYUWQoo6NTSQodGB8ZMDp7JhVRSkv2nA4W

──────────────────────────────────────────────────────────────
  128 candidates in · 3 cleared · 125 denied
  refusal rate 98%
```

---

## Unknown is a no

Holder counts need `getTokenLargestAccounts`, an indexed RPC call that every
free Solana endpoint either throttles or gates behind a token. On a fresh
clone with no `DESK_RPC` set, the desk cannot read how many holders a coin has.

It does not shrug and pass:

```python
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
```

A rule that quietly stops applying whenever an API is down is not a rule - it
is a rule-shaped hole that opens exactly when things are going badly.

---

## The two rules that cancelled each other out

The first draft gave GRAVEYARD a rule that a coin must be silent for **30+
days** to count as dead. WARDEN already refused anything silent for **more
than 30 days**, because a dead book means no exit.

Two sensible rules that between them could never be satisfied. The desk
returned **zero candidates out of 128** and looked strict rather than broken -
which is the dangerous kind of wrong, because a strict machine and a dead
machine print the same screenshot.

Silence now belongs to WARDEN alone; GRAVEYARD judges by price and age. After
the fix: 3 cleared out of 128, and the one that got through has 756 holders.

It is held in place by a test, not a comment:

```python
def test_graveyard_does_not_contradict_the_warden_on_silence():
    graveyard = rules.load()["GRAVEYARD"]
    assert "min_silence_days" not in graveyard.params
```

**The general form:** any set of filters written one at a time needs a test
asking whether an object satisfying all of them can exist at all. Without it,
zero output reads as quality.

---

## Adding an agent

1. Add the rule to `rules.json` with its `asks`, `denies`, `params`, `source`.
2. Write the class - subclass `Agent`, set `name` and `rule_id`, implement
   `check`.
3. Add it to `BENCH` in `agents/warden.py` and to `AGENTS` in `desk.py`.
4. Add a test that the agent refuses the thing it exists to refuse.

The warden enforces it on every order from then on.
