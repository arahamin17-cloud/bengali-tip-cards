# Instagram

Instagram is scheduled through **Meta Business Suite** (or another scheduler),
not through the Facebook queue. This is deliberate:

- Instagram's Content Publishing API has **no scheduled-publish field** — a
  container expires after 24 hours, so something must publish at each slot.
- The Graph API does **not** expose Business Suite's “Share to Instagram”
  crosspost toggle for API-created Page posts.

Scheduling in Business Suite avoids a second token, a public image host, and an
always-on publisher. Facebook keeps running unattended; Instagram is a short
weekly step.

## One-time setup

1. The Instagram account must be a **Business or Creator** account.
2. Link it to the Facebook Page:
   **Meta Business Suite → Settings → Accounts → Instagram accounts**, then
   **Page Settings → Linked accounts → Instagram → Connect**.
3. Enable **Share to Instagram** / **Allow crossposting** for the Page.
4. Test with one post: Business Suite → Planner → Create post → select the
   Facebook Page **and** Instagram → schedule a few minutes ahead → confirm it
   appears on both.

If the test only reaches Facebook, that is expected for API-created posts:
schedule the Instagram side explicitly using the pack below.

## Weekly routine (about five minutes)

1. After the **Tip cards** workflow runs, download the `cards` artifact from
   the Actions run (or use your local `cards-daily/`).
2. Build the Instagram pack:

   ```bash
   npm run instagram:export -- --cards cards-daily --future-only
   ```

   This writes `instagram-export/` containing:

   | File | Purpose |
   | --- | --- |
   | `*.jpg` | JPEG cards, named with the UTC slot, ready to upload |
   | `captions.csv` | `scheduled_utc,dhaka,image,caption` — for bulk schedulers |
   | `captions.txt` | the same captions in copy/paste blocks |
   | `README.txt` | a short reminder of the steps |

   Without `--future-only`, every card in the folder is exported. With it, only
   cards whose manifest time is still in the future are included.

3. In **Meta Business Suite → Planner → Create post**:
   - select the Facebook Page **and** the Instagram account
   - upload the matching `.jpg`
   - paste the caption from `captions.csv`
   - schedule it for the `dhaka` time in the CSV

4. If your scheduler supports bulk import, import `captions.csv` and map the
   `image` column to the JPEG files.

## Why JPEG, and other limits

Instagram rejects PNG. It accepts JPEG only, maximum 8 MB, aspect ratio from
4:5 to 1.91:1, width 320–1440 px. The cards are 1080×1350 (4:5), so the export
converts them to JPEG at their existing size.

Instagram's API allows 50 published posts per 24 hours; this page uses 3.

## What is still automatic

- Facebook posts continue through `weekly-cards.yml` exactly as before.
- `data/.photo-schedule-manifest.json` still tracks **Facebook** posts only.
- The export reads that manifest for times and captions, but Instagram posts
  are tracked in Business Suite/your scheduler, not in this repo.

## If you later want full automation

The API route is still possible: re-mint the Page token with `instagram_basic`,
`instagram_content_publish`, and `pages_read_engagement`, add an `IG_USER_ID`,
host JPEGs publicly, and run a small publisher at each slot. It is a larger
change than the Business Suite routine above.
