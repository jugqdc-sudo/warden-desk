#!/usr/bin/env python3
"""Feeds the public page: runs the desk on the live launchpad and writes JSON.

    python3 site_feed.py                 one run, writes docs/data/latest.json
    python3 site_feed.py --top 12        judge this many candidates
    python3 site_feed.py --dry           print the JSON, write nothing

The page at docs/index.html reads that one file. Nothing else is live, and
the file carries the timestamp of the run that produced it, so a stale page
is visibly stale rather than quietly wrong.

What one run does:

  1. pulls the newest launches off pump.fun (public, no key)
  2. groups them by ticker - a ticker minted many times is a wave
  3. for each wave, looks up the oldest coin ever minted under that name
  4. hands those candidates to WARDEN and writes down every verdict

That is the same path `desk.py warden --live` walks, with the launch feed
read live instead of from the bundled snapshot. The rules are untouched:
every threshold still comes from rules.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.warden import Warden
from core import chain, feed, market, rules
from core.http import get_json
from core.ledger import REFUSALS_PATH, Candidate, load_refusals

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.environ.get("DESK_SITE_JSON", os.path.join(ROOT, "docs", "data", "latest.json"))
RULED_PATH = os.environ.get("DESK_RULED", os.path.join(ROOT, "data", "ruled.json"))
HISTORY_PATH = os.environ.get(
    "DESK_SITE_HISTORY", os.path.join(ROOT, "docs", "data", "history.json")
)
HISTORY_KEEP = 300
LOG_PATH = os.environ.get("DESK_SITE_LOG", os.path.join(ROOT, "docs", "data", "log.json"))
LOG_KEEP = 400
FEED_PATH = os.environ.get("DESK_SITE_FEED", os.path.join(ROOT, "docs", "data", "feed.json"))
FEED_KEEP = 150
LAUNCH_API = "https://frontend-api-v3.pump.fun/coins"
COOLDOWN_SECONDS = rules.load().warden["exit_liquidity"]["verdict_cooldown_hours"] * 3600

#: Everything the desk did this run, in order, for the public log on the page.
EVENTS: list[dict] = []


def note(kind: str, text: str, mint: str = "") -> None:
    """Write one line of the desk's own log. `kind` colours it on the page."""
    EVENTS.append({"at": time.time(), "kind": kind, "text": text, "mint": mint})


def newest_launches(pages: int = 3, per_page: int = 100) -> list[dict]:
    """The most recent mints on the launchpad, newest first.

    The endpoint answers with fewer rows than `limit` asks for, so the offset
    walks by what actually came back. Stepping by the requested size instead
    skips whatever the gap is - a hole in the middle of the window that the
    wave counts would then be blind to.

    It also refuses to page much past a thousand rows, which is why the window
    this returns is roughly forty minutes and not the six hours R2 talks about.
    """
    rows: list[dict] = []
    offset = 0
    for _ in range(pages):
        batch = get_json(
            LAUNCH_API,
            params={
                "offset": offset,
                "limit": per_page,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "true",
            },
        )
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(row for row in batch if isinstance(row, dict) and row.get("mint"))
        offset += len(batch)
    return rows


def waves(launches: list[dict], min_copies: int = 2) -> list[dict]:
    """Tickers minted more than once in the pulled window, busiest first."""
    by_ticker: dict[str, list[dict]] = {}
    for row in launches:
        ticker = (row.get("symbol") or "").strip().upper()
        if not ticker or len(ticker) > 15:
            continue
        by_ticker.setdefault(ticker, []).append(row)

    found = []
    for ticker, copies in by_ticker.items():
        if len(copies) < min_copies:
            continue
        stamps = [float(row.get("created_timestamp") or 0) / 1000 for row in copies]
        stamps = [stamp for stamp in stamps if stamp > 0]
        wallets = {row.get("creator") or "" for row in copies}
        found.append(
            {
                "ticker": ticker,
                "copies": len(copies),
                "wallets": len({wallet for wallet in wallets if wallet}),
                "started_at": min(stamps) if stamps else 0.0,
                "age_minutes": ((time.time() - max(stamps)) / 60) if stamps else 0.0,
            }
        )
    found.sort(key=lambda wave: (wave["copies"], wave["wallets"]), reverse=True)
    return found


def candidate_for(wave: dict) -> Candidate | None:
    """The oldest coin ever minted under this ticker, priced and read live."""
    note(
        "scan",
        f"wave ${wave['ticker']} - {wave['copies']} mints from {wave['wallets']} "
        f"wallet{'s' if wave['wallets'] != 1 else ''}, looking up the original",
    )
    listings = market.search(wave["ticker"], limit=50, oldest_first=True)
    if not listings:
        note("scan", f"${wave['ticker']} - launchpad returned no match, skipped")
        return None

    original = listings[0]
    holders = chain.holders(original.mint)
    note(
        "read",
        f"${original.ticker or wave['ticker']} original {original.mint[:6]}… - "
        f"cap {'unknown' if original.cap_usd is None else '$' + format(int(original.cap_usd), ',')}, "
        f"{'holders unknown' if holders is None else str(holders.count) + ('' if holders.exact else '+') + ' holders'}, "
        f"silent {0 if original.silence_days is None else int(original.silence_days)}d",
        original.mint,
    )

    return Candidate(
        mint=original.mint,
        ticker=original.ticker or wave["ticker"],
        cap_usd=original.cap_usd,
        holders=holders.count if holders else None,
        holders_exact=holders.exact if holders else True,
        top10_share=holders.top10_share if holders else None,
        silence_days=original.silence_days,
        age_days=original.age_days,
        clones=wave["copies"],
        wallets_in_wave=wave["wallets"],
        wave_age_minutes=wave["age_minutes"],
        is_original=True,
        moved_pct=0.0,
        url=f"https://pump.fun/coin/{original.mint}",
    )


def load_ruled(path: str = RULED_PATH) -> dict[str, float]:
    """When each ticker was last ruled on. Keeps R0's cooldown alive between runs."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            return {str(k): float(v) for k, v in json.load(handle).items()}
    except Exception:
        return {}


def save_ruled(ruled: dict[str, float], path: str = RULED_PATH) -> None:
    """Forget anything older than the cooldown, then write the rest."""
    cutoff = time.time() - COOLDOWN_SECONDS
    fresh = {ticker: at for ticker, at in ruled.items() if at > cutoff}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(fresh, handle)


def collect(top: int, pages: int = 20) -> tuple[list[Candidate], dict]:
    """Build candidates off the live feed. Returns them plus what was seen."""
    note("scan", "pulling the newest mints off pump.fun")
    launches = newest_launches(pages=pages)
    if not launches:
        raise RuntimeError("launchpad did not answer - nothing was judged")

    all_waves = waves(launches)
    # One verdict per ticker per cooldown window, exactly as rules.json says.
    # Without this the same names would be re-judged every run and the page
    # would show motion that is really just a loop.
    ruled = load_ruled()
    cutoff = time.time() - COOLDOWN_SECONDS
    found = [wave for wave in all_waves if ruled.get(wave["ticker"], 0) <= cutoff]
    stamps = [
        float(row.get("created_timestamp") or 0) / 1000
        for row in launches
        if row.get("created_timestamp")
    ]
    seen = {
        "launches_pulled": len(launches),
        "distinct_tickers": len({(row.get("symbol") or "").strip().upper() for row in launches}),
        "waves_found": len(all_waves),
        "waves_on_cooldown": len(all_waves) - len(found),
        "window_minutes": ((max(stamps) - min(stamps)) / 60) if len(stamps) > 1 else 0.0,
    }
    note(
        "scan",
        f"{seen['launches_pulled']} mints over {seen['window_minutes']:.0f} minutes, "
        f"{seen['distinct_tickers']} distinct names - {seen['waves_found']} tickers minted "
        f"more than once, {seen['waves_on_cooldown']} of them already ruled on today",
    )

    candidates: list[Candidate] = []
    for wave in found:
        if len(candidates) >= top:
            break
        candidate = candidate_for(wave)
        if candidate is not None:
            candidates.append(candidate)
    return candidates, seen


def verdict_rows(cleared, denied) -> list[dict]:
    """Every verdict of this run, newest first, contracts attached."""
    rows = [("DENY", c, v) for c, v in denied] + [("PASS", c, v) for c, v in cleared]
    rows.sort(key=lambda row: row[1].seen_at, reverse=True)
    return [
        {
            "verdict": kind,
            "ticker": candidate.ticker,
            "mint": candidate.mint,
            "rule": verdict.rule_id,
            "agent": verdict.agent,
            "code": verdict.code or "cleared",
            "reason": verdict.reason or "every rule cleared it",
            "at": candidate.seen_at,
            "cap_usd": candidate.cap_usd,
            "holders": candidate.holders,
            # False means the RPC hit its twenty-account ceiling and the real
            # number is higher. The page prints "20+" rather than "20".
            "holders_exact": candidate.holders_exact,
            "top10_share": candidate.top10_share,
            "silence_days": candidate.silence_days,
            "clones": candidate.clones,
        }
        for kind, candidate, verdict in rows
    ]


def ledger_totals() -> dict:
    """The whole refusal book, not just this run."""
    refusals = load_refusals()
    by_code: dict[str, int] = {}
    for row in refusals:
        key = row.get("code") or "?"
        by_code[key] = by_code.get(key, 0) + 1
    stamps = [float(row.get("at") or 0) for row in refusals if row.get("at")]
    return {
        "refusals_recorded": len(refusals),
        "first_at": min(stamps) if stamps else None,
        "last_at": max(stamps) if stamps else None,
        "by_code": dict(sorted(by_code.items(), key=lambda item: -item[1])),
        "path": os.path.relpath(REFUSALS_PATH, ROOT),
    }


def snapshot_stats() -> dict:
    try:
        stats = feed.stats()
    except Exception:
        return {}
    return {
        "launches": int(stats["coins"]),
        "tickers": int(stats["tickers"]),
        "deployers": int(stats["deployers"]),
        "days": round(stats["days"], 1),
    }


def build(top: int, save_refusals: bool, pages: int = 20) -> dict:
    started = time.time()
    book = rules.load()
    warden = Warden(book)

    candidates, seen = collect(top, pages=pages)
    if not candidates:
        raise RuntimeError("no candidates built - the feed answered but held no wave")

    cleared, denied = warden.review(candidates, save=save_refusals)

    ruled_rows = [("DENY", c, v) for c, v in denied] + [("PASS", c, v) for c, v in cleared]
    ruled_rows.sort(key=lambda row: row[1].seen_at)
    for kind, candidate, verdict in ruled_rows:
        if kind == "DENY":
            note(
                "deny",
                f"DENY ${candidate.ticker} - {verdict.rule_id} {verdict.agent} "
                f"{verdict.code}: {verdict.reason}",
                candidate.mint,
            )
        else:
            note(
                "pass",
                f"PASS ${candidate.ticker} - cleared all seven and the exit checks",
                candidate.mint,
            )
    note(
        "done",
        f"run finished - {len(candidates)} judged, {len(cleared)} cleared, "
        f"{len(denied)} refused and written to data/refusals.jsonl",
    )

    if save_refusals:
        ruled = load_ruled()
        ruled.update({candidate.ticker: candidate.seen_at for candidate in candidates})
        save_ruled(ruled)

    return {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_seconds": round(time.time() - started, 1),
        "rules_version": book.version,
        "sources": {
            "launches": "pump.fun public API, read only",
            "holders": "rpc node" if chain.configured() else "unknown - no node set",
        },
        "seen": seen,
        "session": {
            "candidates": len(candidates),
            "cleared": len(cleared),
            "denied": len(denied),
            "refusal_rate": round(len(denied) / len(candidates), 4),
        },
        "verdicts": verdict_rows(cleared, denied),
        "ledger": ledger_totals(),
        "snapshot": snapshot_stats(),
    }


def append_history(payload: dict, path: str = HISTORY_PATH) -> None:
    """One line per run, so the page can draw what the desk has been doing.

    Kept short on purpose: this file is fetched by every visitor.
    """
    history = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                history = json.load(handle)
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []

    session = payload["session"]
    history.append(
        {
            "at": round(payload["generated_at"]),
            "judged": session["candidates"],
            "denied": session["denied"],
            "cleared": session["cleared"],
            "rate": session["refusal_rate"],
            "waves": payload["seen"].get("waves_found", 0),
            "book": payload["ledger"].get("refusals_recorded", 0),
        }
    )
    history = history[-HISTORY_KEEP:]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(history, handle, separators=(",", ":"))


def _load_list(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _write_list(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, separators=(",", ":"), ensure_ascii=False)


def append_log(path: str = LOG_PATH) -> None:
    """The desk's own log, kept across runs - what the page streams as it happened."""
    _write_list(path, (_load_list(path) + EVENTS)[-LOG_KEEP:])


def append_feed(verdicts: list[dict], path: str = FEED_PATH) -> None:
    """Every verdict the desk has published lately, newest last, no duplicates."""
    rows = _load_list(path)
    seen = {row.get("mint") for row in rows}
    rows.extend(row for row in reversed(verdicts) if row.get("mint") not in seen)
    _write_list(path, rows[-FEED_KEEP:])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="write the live JSON the public page reads")
    parser.add_argument("--top", type=int, default=12, help="candidates to judge this run")
    parser.add_argument("--pages", type=int, default=20, help="pages of the live feed to pull")
    parser.add_argument("--dry", action="store_true", help="print, write nothing")
    parser.add_argument(
        "--no-save", action="store_true", help="do not append to refusals.jsonl"
    )
    args = parser.parse_args(argv)

    try:
        payload = build(args.top, save_refusals=not args.no_save, pages=args.pages)
    except Exception as error:
        # A failed run must not overwrite a good file: the page would then show
        # a fresh timestamp over stale numbers, which is the one lie it cannot tell.
        print(f"run failed, {OUT_PATH} left untouched: {error}", file=sys.stderr)
        return 1

    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.dry:
        print(text)
        return 0

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    append_history(payload)
    append_log()
    append_feed(payload["verdicts"])

    session = payload["session"]
    print(
        f"{session['candidates']} judged · {session['cleared']} cleared · "
        f"{session['denied']} denied · {payload['run_seconds']}s · -> "
        f"{os.path.relpath(OUT_PATH, ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
