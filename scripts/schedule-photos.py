#!/usr/bin/env python3
"""
schedule-photos.py — Schedule PNG/JPG images as Facebook Page photo posts.

Each image is uploaded as a SCHEDULED (unpublished) photo post, so nothing goes
live immediately — Facebook publishes each one at its scheduled time.

Only the Python standard library is used (no pip installs needed).

Credentials
    This script never hardcodes a token. Set FB_PAGE_TOKEN (a *Page* access
    token with pages_manage_posts) and optionally FB_PAGE_ID / FB_API_VERSION.
    Mint a page token with fb-oauth.py (astro-blog-starter-template repo).

Usage
    export FB_PAGE_TOKEN="EAAG..."
    python schedule-photos.py --dry-run                 # preview only
    python schedule-photos.py                           # schedule all images
    python schedule-photos.py --folder ../cards-tip --start-date 2026-10-20 \
        --time 09:30 --interval-days 1 --limit 2

Notes
    * All times are UTC. Facebook accepts scheduled_publish_time between
      ~10 minutes and ~75 days in the future.
    * A manifest remembers what was already scheduled so re-running never
      double-posts (use --force to ignore it). It is kept at data/ by default,
      NOT inside the cards folder - those folders are gitignored build output
      that gets regenerated, so a manifest stored there would be lost and every
      run would re-queue the same cards. Override with --manifest.
"""

import argparse
import json
import mimetypes
import os
import sys
import time as time_module
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, time as dtime, timezone

# ---------------------------------------------------------------------------
# Defaults — override with env vars (FB_PAGE_ID, FB_PAGE_TOKEN, FB_API_VERSION)
# ---------------------------------------------------------------------------
DEFAULT_PAGE_ID = "111479998247290"  # "Face By Sumona" page
API_VERSION = os.environ.get("FB_API_VERSION", "v19.0")
GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MANIFEST_NAME = ".photo-schedule-manifest.json"
UPLOAD_DELAY_SECONDS = 2  # be gentle with Graph API rate limits

# The queue state deliberately lives OUTSIDE the cards folder. Those folders are
# gitignored build output, and CI regenerates cards-daily/ from scratch on every
# run - a manifest kept inside one would vanish between runs, and the same cards
# would be queued again every week.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "data", MANIFEST_NAME)

DEFAULT_MESSAGE = "Face By Sumona ✨\n#beauty #skincare #facebysumona"


def list_images(folder: str):
    out = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS:
            out.append(path)
    return out


def load_manifest(path: str) -> dict:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_manifest(path: str, manifest: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)


def load_captions(folder: str, explicit):
    """Return {filename: caption} from a captions file, if one is available."""
    path = explicit or os.path.join(folder, "captions.txt")
    if not os.path.exists(path):
        return {}
    text = open(path, "r", encoding="utf-8").read()
    captions, current, buf = {}, None, []
    for line in text.splitlines():
        if line.startswith("---") and line.rstrip().endswith("---"):
            if current:
                captions[current] = "\n".join(buf).strip()
            # "--- 1. 01-skincare.png ---" -> "01-skincare.png"
            current = line.strip("- ").split(". ", 1)[-1].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current:
        captions[current] = "\n".join(buf).strip()
    return captions


def _multipart(fields: dict, file_field: str, file_path: str):
    boundary = "----fbsched" + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())
    ctype = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{os.path.basename(file_path)}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode())
    with open(file_path, "rb") as fh:
        parts.append(fh.read())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def schedule_photo(page_id: str, token: str, path: str, message: str, when: datetime):
    fields = {
        "published": "false",
        "scheduled_publish_time": str(int(when.timestamp())),
        "message": message,
        "access_token": token,
    }
    body, content_type = _multipart(fields, "source", path)
    req = urllib.request.Request(
        f"{GRAPH_BASE}/{page_id}/photos",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode(errors="replace"))


def parse_args():
    p = argparse.ArgumentParser(description="Schedule images to a Facebook Page.",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--folder",
                   default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cards-tip"),
                   help="folder of images to schedule")
    # `or` rather than a get() default: an unset GitHub Actions secret arrives as
    # an EMPTY string, and os.environ.get("FB_PAGE_ID", DEFAULT) would hand back
    # "" instead of the default - posting to /v19.0//photos.
    p.add_argument("--page-id", default=os.environ.get("FB_PAGE_ID") or DEFAULT_PAGE_ID)
    p.add_argument("--token", default=os.environ.get("FB_PAGE_TOKEN"))
    p.add_argument("--start-date", default=None, help="YYYY-MM-DD (default: tomorrow UTC)")
    p.add_argument("--time", default="18:00", help="HH:MM UTC (default 18:00)")
    p.add_argument("--times", default=None,
                   help="comma-separated HH:MM UTC slots, cycled one per post "
                        "(e.g. '04:00,14:00' for 10:00 & 20:00 Dhaka)")
    p.add_argument("--interval-days", type=int, default=1)
    p.add_argument("--interval-minutes", type=int, default=0,
                   help="space posts N minutes apart, starting now (overrides --interval-days)")
    p.add_argument("--start-in-minutes", type=int, default=0,
                   help="minutes from now for the first post (used with --interval-minutes)")
    p.add_argument("--limit", type=int, default=0, help="only the first N images (0 = all)")
    p.add_argument("--max-ahead-days", type=int, default=0,
                   help="do not queue further ahead than this many days "
                        "(0 = no limit). Keeps a recurring run from building a "
                        "runaway queue; the rest is picked up by the next run.")
    p.add_argument("--message", default=None, help="caption for every image (overrides captions.txt)")
    p.add_argument("--captions", default=None, help="captions file to read")
    p.add_argument("--manifest", default=DEFAULT_MANIFEST,
                   help="queue state file, so re-runs never double-post "
                        f"(default: {MANIFEST_NAME} under data/)")
    p.add_argument("--dry-run", action="store_true", help="print the plan, post nothing")
    p.add_argument("--force", action="store_true", help="ignore the manifest")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print(f"error: no such folder: {folder}")
        return 1

    hh, mm = args.time.split(":")
    pub_time = dtime(int(hh), int(mm))
    slots = None
    if args.times:
        slots = [dtime(int(t.split(":")[0]), int(t.split(":")[1]))
                 for t in args.times.split(",") if t.strip()]
    now = datetime.now(timezone.utc)
    use_minutes = args.interval_minutes > 0

    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start = (datetime.now(timezone.utc) + timedelta(days=1)).date()

    images = list_images(folder)
    if not images:
        print(f"No images found in {folder}")
        return 1

    captions = {} if args.message else load_captions(folder, args.captions)
    manifest = load_manifest(args.manifest)

    # Every publish time an earlier run already claimed. New posts are never
    # given one of these, so a top-up run continues past the existing queue
    # instead of stacking two posts on the same minute (the old code guessed the
    # offset from len(manifest), which only worked if --start-date never moved).
    used = set()
    if not args.force:
        for entry in manifest.values():
            stamp = entry.get("scheduled_publish_time_utc") if isinstance(entry, dict) else None
            if not stamp:
                continue
            try:
                used.add(datetime.fromisoformat(stamp))
            except ValueError:
                pass

    def slot_at(index: int):
        """The index-th candidate publish time, before collision checks."""
        if slots:
            return datetime.combine(
                start + timedelta(days=index // len(slots)),
                slots[index % len(slots)], tzinfo=timezone.utc,
            )
        if use_minutes:
            return now + timedelta(
                minutes=args.start_in_minutes + args.interval_minutes * index)
        return datetime.combine(
            start + timedelta(days=args.interval_days * index),
            pub_time, tzinfo=timezone.utc,
        )

    plan = []
    for path in images:
        name = os.path.basename(path)
        if not args.force and name in manifest:
            print(f"skip (already scheduled): {name}")
            continue

        index = len(plan)
        when = slot_at(index)
        while when in used:
            index += 1
            when = slot_at(index)
        used.add(when)
        plan.append({
            "path": path,
            "message": args.message or captions.get(name, DEFAULT_MESSAGE),
            "when": when,
        })

    # Keep the queue bounded. A weekly run renders more cards than the slots
    # consume, so without a horizon it would build an ever-deeper queue until it
    # hit Facebook's ~6-month scheduling limit. Anything past the horizon is left
    # for a later run (its content is not in the manifest, so it is picked up
    # again).
    if args.max_ahead_days > 0 and plan:
        horizon = now + timedelta(days=args.max_ahead_days)
        deferred = [it for it in plan if it["when"] > horizon]
        if deferred:
            plan = [it for it in plan if it["when"] <= horizon]
            print(f"{len(deferred)} card(s) left for a later run - the queue is "
                  f"already {args.max_ahead_days} days deep")

    if args.limit > 0:
        plan = plan[:args.limit]

    if not plan:
        print("Nothing to schedule (all images already in the manifest; use --force).")
        return 0

    too_soon = [it for it in plan
                if it["when"] < datetime.now(timezone.utc) + timedelta(minutes=10, seconds=30)]
    if too_soon:
        print("error: Facebook requires scheduled times at least ~10 minutes ahead; "
              "these are too soon:")
        for it in too_soon:
            print(f"  {it['when'].isoformat()}  {os.path.basename(it['path'])}")
        return 1

    print(f"\n{'#':>2}  {'Scheduled (UTC)':<22}  File")
    print("-" * 90)
    for i, item in enumerate(plan, 1):
        print(f"{i:>2}  {item['when'].isoformat():<22}  {os.path.basename(item['path'])}")
    print(f"\n{len(plan)} image(s) -> Page ID {args.page_id} "
          f"({'DRY RUN' if args.dry_run else 'WILL BE SCHEDULED'})")
    print(f"Manifest: {args.manifest}\n")

    if args.dry_run:
        return 0

    if not args.token:
        print("error: no Page access token. Set FB_PAGE_TOKEN "
              "(mint one with fb-oauth.py, in the blog repo).")
        return 1

    failures = 0
    for item in plan:
        name = os.path.basename(item["path"])
        print(f"Scheduling {name} for {item['when'].isoformat()} ...", flush=True)
        try:
            result = schedule_photo(args.page_id, args.token, item["path"],
                                    item["message"], item["when"])
            print(f"  OK -> {json.dumps(result)}", flush=True)
            manifest[name] = {
                "message": item["message"],
                "scheduled_publish_time_utc": item["when"].isoformat(),
                "response": result,
            }
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e}", flush=True)
        save_manifest(args.manifest, manifest)
        time_module.sleep(UPLOAD_DELAY_SECONDS)

    print(f"\nDone: {len(plan) - failures} scheduled, {failures} failed. "
          f"Manifest: {args.manifest}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

