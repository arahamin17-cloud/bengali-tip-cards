# Pending cross-repo patch

`0001-article-reels-scheduling-tooling-for-blog-repo.patch` moves the reel
scheduling / page-scraping / dashboard tooling back into
[`astro-blog-starter-template`](https://github.com/saonbd1/astro-blog-starter-template),
where the reels it operates on already live.

## Why it is a patch and not a PR

The tooling was pushed out of this repo (see the commit that removed
`article-reels/`), but it could not be pushed to the blog repo directly: this
session's credentials are scoped to `bengali-tip-cards` only, so the push was
rejected with a 403.

## Applying it

```bash
git clone https://github.com/saonbd1/astro-blog-starter-template.git
cd astro-blog-starter-template
git checkout -b add-reel-scheduling-tooling
git am /path/to/0001-article-reels-scheduling-tooling-for-blog-repo.patch
git push -u origin add-reel-scheduling-tooling
# then open the PR
```

The patch is `git format-patch` output, so `git am` preserves the commit message.
It applies cleanly to `main` at `33ed80d`.

## What it contains

Adds under `article-reels/`:

| File | Purpose |
| --- | --- |
| `schedule-reels.py` | Uploads reels as scheduled (unpublished) Facebook video posts |
| `scrape-page-posts.py` | Pulls posts + engagement from tracked Pages |
| `generate_dashboard.py` | Builds the offline `dashboard.html` |
| `fb-oauth.py` | Mints a long-lived page token |
| `dashboard.css`, `dashboard.js` | The dashboard's stylesheet and behaviour |
| `.reel-schedule-manifest.json` | Current reel schedule |
| `page-posts.json`, `sumona-posts.json`, `boho-posts.csv` | Scraped page data |

It also extends `article-reels/README.md` with sections for scheduling, page
tracking, the dashboard and tokens, and adds the generated `dashboard.html` to
`.gitignore`.

## Once it is merged

Delete this `patches/` folder — it is only a hand-off artifact.
