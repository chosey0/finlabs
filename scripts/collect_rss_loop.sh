#!/usr/bin/env bash
# Run `modules.news.main collect-rss` on a fixed interval (default: every minute).
#
# collect-rss is idempotent (ON CONFLICT DO NOTHING), so repeated runs only insert
# newly published items and skip duplicates. Each run reads the Supabase DSN from
# INTELLIGENCE_DATABASE_URL (or the repo-root .env, loaded by the CLI).
#
# Any extra arguments are forwarded to collect-rss, so you can narrow the feeds
# (a full 72-feed run is network-bound and can exceed 60s; the loop never
# overlaps itself, so longer runs simply start again at the next boundary).
#
# Usage:
#   scripts/collect_rss_loop.sh                              # every 60s, all feeds
#   INTERVAL_SECONDS=120 scripts/collect_rss_loop.sh
#   scripts/collect_rss_loop.sh --feed donga=https://rss.donga.com/total.xml
#   scripts/collect_rss_loop.sh >> /var/log/finlabs-collect-rss.log 2>&1 &
#
# Stop with Ctrl-C (SIGINT) or SIGTERM. A single-instance lock prevents overlap.

set -uo pipefail

INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)" || ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }

# Atomic, cross-platform single-instance lock (flock is Linux-only; mkdir works on
# macOS too). Held for the lifetime of the loop and cleaned up on any exit.
LOCK_DIR="${TMPDIR:-/tmp}/finlabs-collect-rss.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "another collect-rss loop is already running (lock: $LOCK_DIR)" >&2
  exit 1
fi

RUNNING=1
cleanup() { RUNNING=0; rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT
trap 'echo "stopping…"; RUNNING=0' INT TERM

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }

log "collect-rss loop started (interval=${INTERVAL_SECONDS}s, root=${ROOT})"
while [[ "$RUNNING" -eq 1 ]]; do
  start_epoch="$(date +%s)"
  # Never let one failed run (network/DB hiccup) kill the loop.
  if uv run --group news python -m modules.news.main collect-rss "$@"; then
    :
  else
    log "collect-rss exited with status $? — continuing"
  fi
  # Re-check after a possibly long run so Ctrl-C during the run exits promptly.
  [[ "$RUNNING" -eq 1 ]] || break
  # Align to the next interval boundary; if a run overran, this skips ahead.
  now="$(date +%s)"
  sleep_for=$(( INTERVAL_SECONDS - ((now - start_epoch) % INTERVAL_SECONDS) ))
  [[ "$sleep_for" -le 0 ]] && sleep_for="$INTERVAL_SECONDS"
  sleep "$sleep_for"
done

log "collect-rss loop stopped"
