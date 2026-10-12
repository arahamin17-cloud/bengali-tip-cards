# article-reels

Vertical 1080x1920 reels, one MP4 per published article, generated
automatically by the **Generate article reels** workflow
([source](../reels/ci/article-reels.yml) — install it with
`git mv reels/ci/article-reels.yml .github/workflows/` before the first run).

- File name is the article slug: `article-reels/<slug>.mp4`.
- Produced from the Markdown in `src/content/blog/` - no extra input needed, so
  re-running the workflow regenerates the same video from the same article.
- The newest article is always rendered first; automatic runs are capped so a
  large backfill cannot run for hours. Automatic runs render at most 3 reels
  per run; manual runs choose their own `max`.

## Triggering it

It runs by itself when a post is published:

- when a commit adds a file under `src/content/blog/` (a normal push), and
- when the **Schedule post publishing** workflow finishes (scheduled publishes
  are pushed with `GITHUB_TOKEN`, which does not fire `push` events - hence the
  second trigger).

Manual runs (Actions -> Generate article reels -> Run workflow):

| Input | Effect |
| --- | --- |
| `slug` | Render just that one article |
| `max` | How many missing reels to render in this run (default 5) |
| `force` | Re-render even if a reel already exists |

To backfill everything at once, run it manually with `max: 100`.

## Rendering locally instead

```bash
cd reels
npm run reel -- --latest                                   # newest article
node scripts/render-reel.mjs --slug <slug> --out "$PWD/../article-reels/<slug>.mp4"
node scripts/list-missing-reels.mjs --limit 5              # what the workflow would pick
```

See [`reels/README.md`](../reels/README.md) for the pipeline, or run the GUI
with `npm run gui`.

## Repo size

Each reel is roughly 1-3 MB. GitHub blocks files over 100 MB and warns once a
repo passes ~1 GB, so this is fine for years of posts; if it ever matters,


## Dashboard

`generate_dashboard.py` builds a self-contained web dashboard that
visualizes the scheduled reels (from `schedule-reels.py`'s
`.reel-schedule-manifest.json`) and the posts scraped by
`scrape-page-posts.py` (`page-posts.json`, `sumona-posts.json`).

```bash
python generate_dashboard.py
# then open dashboard.html in a browser
```

The dashboard shows:

- **Stats row** - scheduled reel count, upcoming count, next publish
  countdown, tracking pages, total shares/reactions, recent posts.
- **Upcoming Scheduled Reels** - one card per reel with title, scheduled
  time, Facebook post ID, and a live countdown timer.
- **Recent Scraped Posts** - per-page cards with the latest posts,
  engagement counts, and links.
- **Pages** - overview of the tracked Facebook pages.

Files:

| File | Purpose |
| --- | --- |
| `generate_dashboard.py` | Reads the manifest + scraped JSON, writes `dashboard.html` |
| `dashboard.html` | Generated page (re-run the generator to refresh) |
| `dashboard.css` | Dark-themed stylesheet |
| `dashboard.js` | Live countdown timers, post-age updates, refresh button |

The generated `dashboard.html` embeds the data as JSON, so it works
fully offline. The **Refresh data** button re-fetches the page and
updates the live view without a full reload.

switch the workflow to artifacts only, or move this folder to Git LFS.

## Scheduling photo cards to the Page

`schedule-photos.py` uploads PNG/JPG cards from a folder as **scheduled**
(unpublished) photo posts to the Face By Sumona page (`111479998247290`), so
Facebook publishes each one at its scheduled time.

```bash
export FB_PAGE_TOKEN="EAAG..."     # Page token with pages_manage_posts
python schedule-photos.py --dry-run
python schedule-photos.py --folder ../cards-tip --time 18:00 --interval-days 1

# two posts a day at 10:00 & 20:00 Dhaka (04:00 & 14:00 UTC)
python schedule-photos.py --folder ../cards-batch2 --times "04:00,14:00" --start-date 2026-10-13
```

It reads a `captions.txt` in the folder (per-file captions) when present, keeps a
`.photo-schedule-manifest.json` so re-runs never double-post, and never hardcodes
a token — mint one with `fb-oauth.py`.

## `schedule-run.log`

A captured run of `schedule-reels.py`. Its tail contains a few secret-looking
strings (a 32-char hex value and an `sk-or-v1-…` key) plus OpenRouter SDK/curl
snippets. These are **test / placeholder values taken from OpenRouter's public
documentation examples — not real, active credentials.** An inline `# NOTE`
comment in the file marks them as such. Keep this in mind when scanning the
repo for secrets: this file will always trip naive scanners.

