# bengali-tip-cards

Turn messy scraped text (Bengali or any language) into a clean CSV, render
social-media photo cards from each row, and schedule them to the Facebook Page
— unattended.

## Layout

| Path | What it is |
| --- | --- |
| `scripts/clean_text_to_csv.py` | Scraped text → `category,title,tip` CSV |
| `scripts/generate-tip-cards.mjs` | CSV rows → PNG cards (SVG rendered with sharp) |
| `scripts/scrape_tips.py` | Collects Bengali beauty-topic tips from RSS feeds (off-topic articles are skipped) |
| `scripts/pipeline.sh` | The unattended end-to-end run |
| `scripts/schedule-photos.py` | Uploads cards as scheduled Facebook photo posts |
| `scripts/queue-status.py` | Health check: is the queue still healthy? |
| `scripts/assets/fonts/` | Bundled Noto fonts, so Bengali renders anywhere |
| `tools-hub/` | Generated catalog of every tool across both repos |
| `.github/workflows/` | CI: the weekly pipeline and a manual card render |
| `assets/`, `cards-*/` | Brand photo and sample card output |
| `data/` | Queue state (`data/.photo-schedule-manifest.json`) |

## Quick start

```bash
npm ci                                    # installs sharp
npm test                                  # Python unit tests

# raw text -> CSV
python3 scripts/clean_text_to_csv.py scripts/examples/beauty_tips_raw.txt \
    -o scripts/examples/beauty_tips.csv

# CSV -> cards
node scripts/generate-tip-cards.mjs --captions --out-dir cards
```

`node scripts/generate-tip-cards.mjs --help` lists every option: the `photo`,
`og` and `royal` templates, arbitrary sizes, background photos, the five color
themes, and the brand overrides.

## The unattended pipeline

`scripts/pipeline.sh` runs scrape → clean → render → schedule. Every step is
idempotent — the scheduler keeps a manifest, so re-running never double-posts.

```bash
FB_PAGE_TOKEN=... bash scripts/pipeline.sh
```

| Env var | Purpose |
| --- | --- |
| `FB_PAGE_TOKEN` | Page token with `pages_manage_posts` (required to post) |
| `SCRAPE_CMD` | Shell command that refreshes the raw tips file |
| `RAW_TIPS` / `TIPS_CSV` / `CARDS_DIR` | Where each step reads and writes |
| `THEME` | `navy` \| `rose` \| `emerald` \| `plum` \| `random` |
| `SLOT_TIMES` | Daily UTC slots (default `04:00,14:00`) |
| `LIMIT` | Cap new cards scheduled per run (default `0` = all) |

## Scheduling the photo cards

Cards are queued exactly the way the reels are: each one is uploaded as a
**scheduled (unpublished)** Facebook photo post, and Facebook publishes it at
its own time. Nothing has to keep running once they are queued.

```bash
# preview the queue first - a dry run needs no token
python3 scripts/schedule-photos.py --folder cards-batch2 \
    --times "04:00,14:00" --start-date 2026-10-14 --dry-run

# then queue it for real
export FB_PAGE_TOKEN="EAAG..."   # Page token with pages_manage_posts
python3 scripts/schedule-photos.py --folder cards-batch2 \
    --times "04:00,14:00" --start-date 2026-10-14
```

`--times "04:00,14:00"` is 10:00 and 20:00 Dhaka; **all times are UTC**.

Queue state lives in **`data/.photo-schedule-manifest.json`**, deliberately not
inside the cards folder: `cards-*/` is gitignored build output (and CI
regenerates `cards-daily/` on every run), so a manifest kept there would be lost
and the same cards queued a second time. Re-running only queues cards that are
not already in the manifest, and never reuses a publish time that is taken.

## Running it as a loop

With `FB_PAGE_TOKEN` / `FB_PAGE_ID` set as repo secrets and the workflow patch
in `patches/` applied, the pipeline runs itself every Monday: scrape new tips,
clean them, render cards, queue the ones that are not queued yet, and commit the
queue state back to `data/`.

Two properties make it safe to leave alone:

- **Card filenames are content-addressed** - `<sha256-12>-<slug>.png`, a digest
  of the card that was drawn. So "already queued" is decided by what the card
  *is*, not by where it sat in the CSV. Re-scraping the same tips re-renders
  byte-identical files and they are skipped; a genuinely new tip gets a new name
  and is queued. The row index is deliberately **not** part of the name: if it
  were, scraping one new tip would shift every row and rename unchanged cards,
  and they would all be queued a second time.
- **Themes are deterministic.** `--theme random` derives the theme from the
  card's own text instead of `Math.random()`, so the same tip always renders the
  same image. Without that, every render produced different bytes for the same
  tip and nothing could be deduplicated.
- **The queue has a horizon** - `MAX_AHEAD_DAYS` (default 10). A run renders
  more cards than the slots consume, so without a horizon the queue would grow
  every week until it hit Facebook's ~6-month scheduling limit. The surplus is
  picked up by a later run.

Nothing has to run at publish time: Facebook publishes each queued post itself.

### Checking on it

```bash
python3 scripts/queue-status.py     # exit 0 = healthy, 1 = needs a top-up
```

**If you come back to this months from now, read [RUNBOOK.md](RUNBOOK.md)** -
what runs when, how to tell it is alive, what each failure looks like, and how to
rotate the token.

## Workflows

- **Weekly tip cards** (`.github/workflows/weekly-cards.yml`) — Mondays 02:00
  UTC. Runs the whole pipeline and schedules the batch across the coming week.
- **Generate cards** (`.github/workflows/cards.yml`) — manual only; renders
  cards (plus `captions.txt`) as a downloadable artifact.

The Facebook steps need `FB_PAGE_TOKEN` and `FB_PAGE_ID` secrets. Mint a page
token with `fb-oauth.py`, which now lives in the
[astro-blog-starter-template](https://github.com/saonbd1/astro-blog-starter-template)
repo alongside the rest of the reel tooling.

## Tool Hub

`tools-hub/` is a generated single page listing every tool across this repo and
the Astro blog repo — what it does, how to run it, and where it lives.

```bash
cd tools-hub && python3 generate_hub.py    # writes tools-hub/index.html
```

See [`tools-hub/README.md`](tools-hub/README.md) for the registry format and
how to add a tool.

## Notes

- Bengali glyphs render on any machine: the Noto fonts in
  `scripts/assets/fonts/` are registered through a temporary `fonts.conf`
  before sharp is imported — no system font packages needed.
