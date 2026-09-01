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
LAUNCH_API = "https://frontend-api-v3.pump.fun/coins"
COOLDOWN_SECONDS = rules.load().warden["exit_liquidity"]["verdict_cooldown_hours"] * 3600


def newest_launches(pages: int = 3, per_page: int = 100) -> list[dict]:
    """The most recent mints on the launchpad, newest first."""
    rows: list[dict] = []
    for page in range(pages):
        batch = get_json(
            LAUNCH_API,
            params={
                "offset": page * per_page,
                "limit": per_page,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "true",
            },
        )
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(row for row in batch if isinstance(row, dict) and row.get("mint"))
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
    listings = market.search(wave["ticker"], limit=50, oldest_first=True)
    if not listings:
        return None

    original = listings[0]
    holders = chain.holders(original.mint)

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

    session = payload["session"]
    print(
        f"{session['candidates']} judged · {session['cleared']} cleared · "
        f"{session['denied']} denied · {payload['run_seconds']}s · -> "
        f"{os.path.relpath(OUT_PATH, ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
