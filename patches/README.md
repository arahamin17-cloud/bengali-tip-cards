# Pending patches

Two changes could not be pushed from this session. Both are plain
`git format-patch` / `git diff` output you can apply with `git apply` or
`git am`.

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

## `0002-weekly-cards-persist-schedule-manifest.patch`

Adds `permissions: contents: write` and a final step to
`.github/workflows/weekly-cards.yml` so the weekly job commits
`data/.photo-schedule-manifest.json` back to the repo.

**Why a patch:** GitHub rejects pushes that modify `.github/workflows/**` unless
the pushing app has the `workflows` permission, which this one does not have:

```
! [remote rejected] refusing to allow a GitHub App to create or update
  workflow `.github/workflows/weekly-cards.yml` without `workflows` permission
```

Without this change the manifest starts empty on every weekly run, so each batch
would be queued again - the same cards posted repeatedly. Apply it before
enabling the `FB_PAGE_TOKEN` secret:

```bash
git apply patches/0002-weekly-cards-persist-schedule-manifest.patch
git commit -am "Persist the photo schedule manifest across runs"
git push
```

## Once they are applied

Delete this `patches/` folder - it is only a hand-off artifact.
