# Pending patches

Three changes could not be pushed from this session. All are plain
`git diff` output you can apply with `git apply` or `git am`.

## `0001-article-reels-scheduling-tooling-for-blog-repo.patch`

Moves the reel scheduling / page-scraping / dashboard tooling into
[`astro-blog-starter-template`](https://github.com/saonbd1/astro-blog-starter-template),
where the reels it operates on already live.

**Why a patch:** the credentials for this session are scoped to
`bengali-tip-cards` only, so the push to the blog repo was rejected with a 403.

```bash
git clone https://github.com/saonbd1/astro-blog-starter-template.git
cd astro-blog-starter-template
git checkout -b add-reel-scheduling-tooling
git am /path/to/0001-article-reels-scheduling-tooling-for-blog-repo.patch
git push -u origin add-reel-scheduling-tooling
```

It is `git format-patch` output, so `git am` keeps the commit message, and it
applies cleanly to `main` at `33ed80d`. It adds `article-reels/` scripts and
dashboard files, extends that folder's README, and ignores the generated
`dashboard.html`.

## `0002-weekly-cards-persist-queue-state.patch`

Adds `permissions: contents: write` and a final step to
`.github/workflows/weekly-cards.yml` that commits `data/` back to the repo
after each run.

**Why a patch:** GitHub rejects pushes that modify `.github/workflows/**` unless
the pushing app has the `workflows` permission, which this one does not have:

```
! [remote rejected] refusing to allow a GitHub App to create or update
  workflow `.github/workflows/weekly-cards.yml` without `workflows` permission
```

**This one is required for the loop to work at all.** `cards-daily/` is
generated from scratch on every run, so without persisting `data/` the manifest
starts empty each Monday and the whole batch is queued again - the same cards
posted every week. `data/.scrape-seen.txt` is persisted for the same reason: it
stops the scraper re-adding articles it has already seen.

Apply it **before** setting the `FB_PAGE_TOKEN` secret:

```bash
git apply patches/0002-weekly-cards-persist-queue-state.patch
git commit -am "Persist the card queue state across runs"
git push
```

## `0003-self-healing-schedules.patch`

Makes the posting loop survive a bad day instead of draining the queue:

- Runs **twice a week** (Sunday and Wednesday 20:00 UTC = Monday and Thursday
  02:00 Dhaka), eight hours before the first slot, instead of once a week.
- Keeps **14 days** of posts queued (`MAX_AHEAD_DAYS`), so one missed run does
  not stop the page.
- Retries the pipeline **three times** and serialises runs with a concurrency
  group, so a manual dispatch cannot race the scheduled one.
- Adds a final runway check to the pipeline: a run that leaves under four days
  of queue fails loudly instead of going green.
- Adds **`.github/workflows/queue-health.yml`**: daily 00:00 UTC check that
  dispatches a top-up when under five days remain and opens a `queue-health`
  issue until the queue is healthy again.
- Writes `data/.last-run` on every run, so the commit is a heartbeat and GitHub
  does not disable the schedules after 60 quiet days.

**Why a patch:** the credentials for this session do not have the `workflows`
permission, so GitHub rejects any push that touches `.github/workflows/**`:

```
! [remote rejected] refusing to allow a GitHub App to create or update
  workflow `.github/workflows/queue-health.yml` without `workflows` permission
```

Apply it after the queue/beauty fixes in PR #2 are on the branch:

```bash
git apply patches/0003-self-healing-schedules.patch
git add .github/workflows/queue-health.yml
git commit -am "Make the posting loop self-healing"
git push
```

Then top the empty queue up once:

```bash
gh workflow run weekly-cards.yml
```

The daily watchdog takes over from there. If a context line has moved, use
`git apply --3way`.

## Once they are applied

Delete this `patches/` folder - it is only a hand-off artifact.
