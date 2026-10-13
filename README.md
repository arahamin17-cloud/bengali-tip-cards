# bengali-tip-cards

Turn messy scraped text (Bengali or any language) into a clean CSV, render
social-media photo cards from each row, and schedule them to the Facebook Page
— unattended.

## Layout

| Path | What it is |
| --- | --- |
| `scripts/clean_text_to_csv.py` | Scraped text → `category,title,tip` CSV |
| `scripts/generate-tip-cards.mjs` | CSV rows → PNG cards (SVG rendered with sharp) |
| `scripts/scrape_tips.py` | Collects Bengali tips from RSS feeds |
| `scripts/pipeline.sh` | The unattended end-to-end run |
| `scripts/assets/fonts/` | Bundled Noto fonts, so Bengali renders anywhere |
| `article-reels/` | Article reels, Facebook scheduling, dashboard |
| `tools-hub/` | Generated catalog of every tool across both repos |
| `.github/workflows/` | CI: the weekly pipeline and a manual card render |
| `assets/`, `cards-*/` | Brand photo and sample card output |

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

## Workflows

- **Weekly tip cards** (`.github/workflows/weekly-cards.yml`) — Mondays 02:00
  UTC. Runs the whole pipeline and schedules the batch across the coming week.
- **Generate cards** (`.github/workflows/cards.yml`) — manual only; renders
  cards (plus `captions.txt`) as a downloadable artifact.

The Facebook steps need `FB_PAGE_TOKEN` and `FB_PAGE_ID` secrets. Mint a page
token with `article-reels/fb-oauth.py`.

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
- `article-reels/schedule-run.log` contains a 32-char hex value and an
  `sk-or-v1-…` key taken from OpenRouter's public documentation examples. An
  inline `# NOTE` marks them as placeholders; they are not live credentials,
  but the file will always trip naive secret scanners.
