#!/bin/sh
# One publish cycle: run the desk on the live feed, commit the JSON, push it.
#
#   ./site_publish.sh
#
# The page at docs/index.html reads docs/data/latest.json and nothing else, so
# this script is the whole publishing pipeline. Run it from cron, launchd, or
# by hand. A failed run leaves the last good JSON alone - the page then shows
# its real age instead of a fresh timestamp over stale numbers.
#
# Settings come from .env next to this file (gitignored):
#   DESK_RPC    your Solana node, for live holder counts
#   DESK_PROXY  optional outbound proxy
#   PYTHON      optional interpreter path

set -eu
cd "$(dirname "$0")"

[ -f .env ] && { set -a; . ./.env; set +a; }
PYTHON="${PYTHON:-python3}"

"$PYTHON" site_feed.py --pages "${DESK_PAGES:-20}" --top "${DESK_TOP:-12}" || {
    echo "desk run failed - nothing published" >&2
    exit 1
}

git add docs/data/latest.json data/refusals.jsonl 2>/dev/null || true
git diff --cached --quiet && { echo "nothing changed"; exit 0; }

git -c user.name="${GIT_NAME:-warden-desk}" \
    -c user.email="${GIT_EMAIL:-desk@localhost}" \
    commit -qm "desk: verdicts $(date -u '+%Y-%m-%d %H:%M') UTC"
git push -q origin HEAD && echo "published"
