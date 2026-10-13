#!/usr/bin/env bash
#
# pipeline.sh — the daily, unattended work process.
#
#   1. (optional) run the tips scraper
#   2. clean the raw text -> CSV
#   3. render cards (random theme, tip-only, royal layout)
#   4. schedule the new cards to the Facebook page (2/day by default)
#
# Every step is idempotent: the scheduler keeps a manifest, so re-running never
# double-posts. Safe to run on a timer (cron / GitHub Actions).
#
# Config (env vars, all optional except FB_PAGE_TOKEN):
#   FB_PAGE_TOKEN   Page access token with pages_manage_posts  (required)
#   FB_PAGE_ID      defaults to the Face By Sumona page
#   SCRAPE_CMD      shell command that refreshes the raw tips file
#   RAW_TIPS        raw text file                 (default scripts/examples/beauty_tips_raw.txt)
#   TIPS_CSV        cleaned CSV                   (default data/tips.csv)
#   CARDS_DIR       card output folder            (default cards-daily)
#   THEME           navy|rose|emerald|plum|random (default random)
#   SLOT_TIMES      daily UTC slots               (default 04:00,14:00 = 10:00 & 20:00 Dhaka)
#   LIMIT           max new cards to schedule per run (default 0 = all)
#
set -euo pipefail
cd "$(dirname "$0")/.."

RAW_TIPS="${RAW_TIPS:-scripts/examples/beauty_tips_raw.txt}"
TIPS_CSV="${TIPS_CSV:-data/tips.csv}"
CARDS_DIR="${CARDS_DIR:-cards-daily}"
THEME="${THEME:-random}"
SLOT_TIMES="${SLOT_TIMES:-04:00,14:00}"
LIMIT="${LIMIT:-0}"

echo "== pipeline start $(date -u +%FT%TZ) =="

# -- 1. scrape (optional) ----------------------------------------------------
if [ -n "${SCRAPE_CMD:-}" ]; then
  echo "-- scraping tips: $SCRAPE_CMD"
  eval "$SCRAPE_CMD"
else
  echo "-- no SCRAPE_CMD set, using existing $RAW_TIPS"
fi

# -- 2. clean text -> CSV ----------------------------------------------------
mkdir -p "$(dirname "$TIPS_CSV")"
echo "-- cleaning $RAW_TIPS -> $TIPS_CSV"
python3 scripts/clean_text_to_csv.py "$RAW_TIPS" -o "$TIPS_CSV"

# -- 3. render cards ---------------------------------------------------------
mkdir -p "$CARDS_DIR"
echo "-- rendering cards (theme=$THEME)"
node scripts/generate-tip-cards.mjs \
  --template royal --tip-only \
  --csv "$TIPS_CSV" --theme "$THEME" \
  --out-dir "$CARDS_DIR"

# -- 4. schedule new cards to the page ---------------------------------------
if [ -z "${FB_PAGE_TOKEN:-}" ]; then
  echo "!! FB_PAGE_TOKEN is not set - skipping the Facebook step"
  exit 0
fi

echo "-- scheduling new cards ($SLOT_TIMES UTC)"
sched_args=(--folder "$CARDS_DIR" --times "$SLOT_TIMES" --start-date "$(date -u +%F)")
if [ "$LIMIT" != "0" ]; then
  sched_args+=(--limit "$LIMIT")
fi
FB_PAGE_TOKEN="$FB_PAGE_TOKEN" python3 scripts/schedule-photos.py "${sched_args[@]}"

echo "== pipeline done $(date -u +%FT%TZ) =="
