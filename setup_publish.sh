#!/bin/sh
# One-time wiring so site_publish.sh can push. Run once, after putting a GitHub
# token with `repo` scope in ~/.warden_gh_token:
#
#   ./setup_publish.sh
#
# The token is written to a credential file readable only by this user and is
# never printed, never committed and never passed on a command line where it
# would show up in `ps`.

set -eu
cd "$(dirname "$0")"

TOKEN_FILE="$HOME/.warden_gh_token"
CRED_FILE="$HOME/.warden_git_creds"
OWNER="jugqdc-sudo"
REPO="warden-desk"

[ -f "$TOKEN_FILE" ] || {
    echo "no token at $TOKEN_FILE - create one at" >&2
    echo "https://github.com/settings/tokens/new?scopes=repo&description=warden%20site" >&2
    exit 1
}

TOKEN=$(tr -d ' \t\n\r' < "$TOKEN_FILE")
[ -n "$TOKEN" ] || { echo "token file is empty" >&2; exit 1; }

umask 077
printf 'https://%s:%s@github.com\n' "$OWNER" "$TOKEN" > "$CRED_FILE"

git remote set-url origin "https://github.com/$OWNER/$REPO.git"
git config credential.helper "store --file=$CRED_FILE"
git config user.name "ventry"
git config user.email "kostyrikplay7@gmail.com"

# Does the token actually reach the repository?
if git ls-remote --exit-code origin > /dev/null 2>&1; then
    echo "token works - remote reachable"
else
    echo "token did not authenticate against $OWNER/$REPO" >&2
    exit 1
fi
