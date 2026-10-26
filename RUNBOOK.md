# Runbook

**You should not need to do anything.** This page is for the day you want to
check on it, or something looks wrong.

## What runs, and when

A GitHub Actions workflow (`.github/workflows/weekly-cards.yml`) fires **twice
a week - Sunday and Wednesday at 20:00 UTC / Monday and Thursday 02:00 Dhaka**,
eight hours before that day's first slot. It:

1. scrapes new beauty-topic Bengali tips from the RSS feeds (travel, recipes and
   other off-topic articles are rejected by headline)
2. cleans them into a CSV
3. renders the cards (a deterministic theme per tip)
4. queues **only the cards that are not already queued** to the Face By Sumona
   page, as *scheduled, unpublished* posts
5. commits the queue state back to `data/`

Then it stops. **Facebook publishes each queued card on its own** at its
scheduled time - nothing runs at publish time, so the loop does not need to be
awake for a post to go out.

Posting slots are `04:00`, `09:00`, `14:00` UTC = **10:00, 15:00, 20:00 Dhaka**.

## Instagram

Instagram is **not** in the Facebook queue. It is scheduled in Meta Business
Suite because Instagram has no scheduled-publish API. Build the weekly upload
pack with:

```bash
npm run instagram:export -- --cards cards-daily --future-only
```

That writes JPEGs plus `captions.csv` / `captions.txt` to `instagram-export/`.
Full setup and the five-minute weekly routine: [INSTAGRAM.md](INSTAGRAM.md).

## The 30-second health check

```bash
python3 scripts/queue-status.py
```

Healthy looks like this:

```
entries        : 15  (0 published, 15 still queued)
next post      : 2026-10-14 04:00 UTC (10:00 Dhaka, in 7h 38m)
last queued    : 2026-10-21 04:00 UTC (10:00 Dhaka)
runway         : 7.3 days

OK - the queue is healthy; Facebook publishes these on its own.
```

Exit code `0` = fine. `1` = empty or under 3 days of runway, i.e. the loop has
stalled and needs a look. `runway` is the number that matters: it is how long
the page keeps posting with nobody touching anything.

A **Queue health** workflow runs this same check every day at 00:00 UTC. When
less than five days remain it dispatches a top-up run and opens a
`queue-health` issue; it closes the issue again once the queue is healthy. So a
single failed or delayed pipeline run repairs itself instead of stopping the
page.

## If the runway is short or the queue is empty

The daily watchdog normally handles this. To do it by hand: Actions ->
**Tip cards** -> *Run workflow*, or:

```bash
gh workflow run weekly-cards.yml
```

Then check the run's log for the Facebook step. If it says
`FB_PAGE_TOKEN is not set - skipping the Facebook step`, the secret is missing
or was removed (see below).

## Common failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| Workflow is green but nothing posts | `FB_PAGE_TOKEN` not set | set the secret (below) |
| Workflow fails at *Run the pipeline* | token rejected, Graph API `code 190` | re-mint the token (below) |
| `queue-health` issue opened | under five days of queue left | a top-up was requested automatically; if that run failed, fix the cause above |
| `Nothing to schedule` in the log | every rendered card is already queued | harmless - the buffer and watchdog cover quiet weeks |
| No runs at all for a month+ | GitHub disables schedules after 60 days without repo activity | Actions tab -> enable the workflows |
| Cards posted twice | the queue state is not persisting | confirm the workflow has `permissions: contents: write` |

## The token

`FB_PAGE_TOKEN` is a Page access token for page `111479998247290` with the
`pages_manage_posts` permission. It is a repo secret, so it is write-only - you
can never read it back, only overwrite it.

**When it dies** (Facebook invalidates these if the account password changes, or
the app is removed): the workflow goes green but posts nothing, or fails with
`code 190`. Re-mint it and overwrite the secret:

```bash
read -rs TOK && export TOK        # paste the new token at the prompt

# verify BEFORE storing it - a wrong or dead token fails here, not on Monday
curl -s "https://graph.facebook.com/v19.0/111479998247290?fields=name&access_token=$TOK"
curl -s "https://graph.facebook.com/v19.0/me/permissions?access_token=$TOK"

gh secret set FB_PAGE_TOKEN       # prompts; nothing lands in your shell history
gh secret list                    # confirms the NAMES only
```

A **System User** token from Meta Business is worth the extra setup: it does not
expire and is not killed by a password change, which is exactly how the previous
token died.

## Minting a new token

You need: the Facebook App you use for this (developers.facebook.com -> My Apps),
and to be an **admin of the Face By Sumona page**.

You do **not** need App Review. Permissions work in Development mode for anyone
with a role on the app, and you have one.

**Quick (fine for a one-off test, dies in ~1-2 hours):**

1. https://developers.facebook.com/tools/explorer/ -> pick your app
2. *Generate Access Token* -> log in -> allow `pages_show_list`,
   `pages_manage_posts`, `pages_read_engagement`
3. `GET /me/accounts` -> copy the `access_token` for `111479998247290`

**Long-lived (what you actually want - the page token never expires):**

```bash
APP_ID=... APP_SECRET=...

# 1. the short-lived user token from the Explorer above
SHORT=EAAG...

# 2. trade it for a long-lived user token (~60 days)
curl -s "https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=$APP_ID&client_secret=$APP_SECRET&fb_exchange_token=$SHORT"

# 3. get the PAGE token from that - this one does not expire
curl -s "https://graph.facebook.com/v19.0/me/accounts?access_token=$LONG_LIVED"
```

`fb-oauth.py` automates steps 2 and 3. It lives in the astro-blog-starter-template
repo now, but is still recoverable from this repo's history:

```bash
git show 07a6bbe:article-reels/fb-oauth.py > fb-oauth.py
```

**Best of all**, if you have a Meta Business account: use a **System User** token
(Business Settings -> Users -> System Users -> assign the Page -> generate token).
Those never expire and are not invalidated by a password change - which is
exactly how the previous token died.

## Stopping it

The cleanest kill switch is to **delete the `FB_PAGE_TOKEN` secret**. The
pipeline then renders cards and exits before the Facebook step, so nothing new is
queued while the cards already in the queue still publish. To stop everything,
disable the workflow in the Actions tab.

## Why it keeps going without you

- **The manifest is committed.** `data/.photo-schedule-manifest.json` records
every card that was queued, so a fresh checkout always knows what is already
done. That is what stops re-posts.
- **Card filenames are content-addressed.** A card's name is a digest of the
  card itself, so re-scraping the same tip re-renders the same filename and it is
  skipped. Only genuinely new cards get new names.
- **Every run leaves a commit.** `data/.last-run` is rewritten on each run, so
  the repository always shows activity. GitHub disables scheduled workflows
  after 60 days without repo activity; this heartbeat keeps them enabled even
  when the feeds are quiet.
- **Runs twice a week, with two weeks of buffer.** One failed run is retried on
  the next scheduled day while the 14-day queue keeps publishing. Posting is
  never on the critical path.
- **The daily watchdog self-heals.** `queue-health.yml` checks the runway every
  day and dispatches a top-up if it drops under five days, so a missed run does
  not become an outage.
- **Transient failures are retried.** The pipeline step has three attempts, and
  the manifest makes a retry safe - cards already queued are skipped.
- **The queue has a horizon.** Each run queues at most 14 days ahead
  (`MAX_AHEAD_DAYS`), so the queue cannot grow without bound, and surplus cards
  are simply picked up by a later run.

## The moving parts

| Path | Role |
| --- | --- |
| `.github/workflows/weekly-cards.yml` | twice-weekly scrape -> render -> queue, with retries |
| `.github/workflows/queue-health.yml` | daily runway check, auto top-up and issue |
| `scripts/pipeline.sh` | scrape -> clean -> render -> queue |
| `scripts/schedule-photos.py` | uploads cards as scheduled, unpublished posts |
| `scripts/generate-tip-cards.mjs` | renders the PNGs |
| `data/.photo-schedule-manifest.json` | **the queue** - the one file that matters |
| `scripts/queue-status.py` | the health check above |

If you only remember one thing: **run `python3 scripts/queue-status.py`.**
