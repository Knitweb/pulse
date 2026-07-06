#!/usr/bin/env bash
# deploy.sh — assemble & publish the 5mart.ml site from the repo /web folders.
#
# Serves every Knitweb web property at a canonical path under one web root, with
# the shared hop-menu, so 5mart.ml stays in sync with the repositories and forms
# one connected whole (no dead ends):
#
#     5mart.ml/            → landing (this bundle's index.html)
#     5mart.ml/wnw/        ← Knitweb/pulse        web/
#     5mart.ml/lens/       ← Knitweb/lens         web/
#     5mart.ml/molgang/    ← Knitweb/molgang      web/
#     5mart.ml/quantum/    ← Knitweb/k.nitweb.art quantum/
#     5mart.ml/nav.js      ← the shared menu
#
# Idempotent, secret-free, and atomic (builds into a temp dir, then swaps). Safe
# to run from a cron for continuous sync. Requires: bash, git, rsync.
#
# Usage:
#     WEBROOT=/var/www/5mart ./deploy.sh
#     WEBROOT=/var/www/5mart RELOAD='sudo systemctl reload nginx' ./deploy.sh
set -euo pipefail

WEBROOT="${WEBROOT:-/var/www/5mart}"
WORK="${WORK:-$(mktemp -d)}"
RELOAD="${RELOAD:-}"                 # e.g. 'sudo systemctl reload nginx' (optional)
BRANCH="${BRANCH:-main}"
ORG="https://github.com/Knitweb"

say(){ printf '\033[36m▸\033[0m %s\n' "$1"; }
die(){ printf '\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

for bin in git rsync; do command -v "$bin" >/dev/null || die "missing dependency: $bin"; done

# repo → (subdir in repo, path under web root)
# shellcheck disable=SC2016
MAP=(
  "pulse|web|wnw"
  "lens|web|lens"
  "molgang|web|molgang"
  "k.nitweb.art|quantum|quantum"
  "chemfield|web|chemfield"
)

STAGE="$WORK/stage"
mkdir -p "$STAGE"

# shared menu at the web root (relative includes in each property resolve up to it
# via their own copy; we also drop one at the root for the landing page)
cp "$(dirname "$0")/nav.js" "$STAGE/nav.js"
cp "$(dirname "$0")/index.html" "$STAGE/index.html" 2>/dev/null || true
cp "$(dirname "$0")/robots.txt" "$STAGE/robots.txt" 2>/dev/null || true

for entry in "${MAP[@]}"; do
  IFS='|' read -r repo sub dest <<<"$entry"
  say "fetch $repo/$sub → /$dest"
  src="$WORK/src/$repo"
  if [ -d "$src/.git" ]; then git -C "$src" fetch -q origin "$BRANCH" && git -C "$src" reset -q --hard "origin/$BRANCH"
  else git clone -q --depth 1 --branch "$BRANCH" "$ORG/$repo" "$src" \
    || { say "skip $repo (clone failed — repo missing or unreachable)"; continue; }; fi
  [ -d "$src/$sub" ] || { say "skip $repo (no $sub/ folder)"; continue; }
  mkdir -p "$STAGE/$dest"
  rsync -a --delete "$src/$sub/" "$STAGE/$dest/"
  # ensure a nav.js is reachable next to the property's pages
  cp "$STAGE/nav.js" "$STAGE/$dest/nav.js"
done

# atomic publish
say "publishing to $WEBROOT"
mkdir -p "$WEBROOT"
rsync -a --delete "$STAGE/" "$WEBROOT/"

[ -n "$RELOAD" ] && { say "reloading web server"; eval "$RELOAD"; }

printf '\n\033[32m✓ 5mart.ml is in sync\033[0m — served: / · /wnw · /lens · /molgang · /quantum · /chemfield\n'
say "clean up: rm -rf $WORK   (or keep it to speed up the next sync)"
