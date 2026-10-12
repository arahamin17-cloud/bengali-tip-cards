#!/usr/bin/env python3
"""
schedule-photos.py — Schedule PNG/JPG images as Facebook Page photo posts.

Each image is uploaded as a SCHEDULED (unpublished) photo post, so nothing goes
live immediately — Facebook publishes each one at its scheduled time.

Only the Python standard library is used (no pip installs needed).

Credentials
    This script never hardcodes a token. Set FB_PAGE_TOKEN (a *Page* access
    token with pages_manage_posts) and optionally FB_PAGE_ID / FB_API_VERSION.
    Mint a page token with article-reels/fb-oauth.py.

Usage
    export FB_PAGE_TOKEN="EAAG..."
    python schedule-photos.py --dry-run                 # preview only
    python schedule-photos.py                           # schedule all images
    python schedule-photos.py --folder ../cards-tip --start-date 2026-10-20 \
        --time 09:30 --interval-days 1 --limit 2

Notes
    * All times are UTC. Facebook accepts scheduled_publish_time between
      ~10 minutes and ~75 days in the future.
    * A .photo-schedule-manifest.json remembers what was already scheduled so
      re-running never double-posts (use --force to ignore it).
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

DEFAULT_MESSAGE = "Face By Sumona ✨\n#beauty #skincare #facebysumona"


def list_images(folder: str):
    out = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS:
            out.append(path)
    return out


def load_manifest(folder: str) -> dict:
    path = os.path.join(folder, MANIFEST_NAME)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_manifest(folder: str, manifest: dict) -> None:
    path = os.path.join(folder, MANIFEST_NAME)
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
    p.add_argument("--page-id", default=os.environ.get("FB_PAGE_ID", DEFAULT_PAGE_ID))
    p.add_argument("--token", default=os.environ.get("FB_PAGE_TOKEN"))
    p.add_argument("--start-date", default=None, help="YYYY-MM-DD (default: tomorrow UTC)")
    p.add_argument("--time", default="18:00", help="HH:MM UTC (default 18:00)")
    p.add_argument("--interval-days", type=int, default=1)
    p.add_argument("--interval-minutes", type=int, default=0,
                   help="space posts N minutes apart, starting now (overrides --interval-days)")
    p.add_argument("--start-in-minutes", type=int, default=0,
                   help="minutes from now for the first post (used with --interval-minutes)")
    p.add_argument("--limit", type=int, default=0, help="only the first N images (0 = all)")
    p.add_argument("--message", default=None, help="caption for every image (overrides captions.txt)")
    p.add_argument("--captions", default=None, help="captions file to read")
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
    manifest = load_manifest(folder)

    plan = []
    for path in images:
        name = os.path.basename(path)
        if not args.force and name in manifest:
            print(f"skip (already scheduled): {name}")
            continue
        if use_minutes:
            when = now + timedelta(
                minutes=args.start_in_minutes + args.interval_minutes * len(plan))
        else:
            when = datetime.combine(
                start + timedelta(days=args.interval_days * len(plan)),
                pub_time, tzinfo=timezone.utc,
            )
        plan.append({
            "path": path,
            "message": args.message or captions.get(name, DEFAULT_MESSAGE),
            "when": when,
        })

    if args.limit > 0:
        plan = plan[:args.limit]

    if not plan:
        print("Nothing to schedule (all images already in the manifest; use --force).")
        return 0

    print(f"\n{'#':>2}  {'Scheduled (UTC)':<22}  File")
    print("-" * 90)
    for i, item in enumerate(plan, 1):
        print(f"{i:>2}  {item['when'].isoformat():<22}  {os.path.basename(item['path'])}")
    print(f"\n{len(plan)} image(s) -> Page ID {args.page_id} "
          f"({'DRY RUN' if args.dry_run else 'WILL BE SCHEDULED'})\n")

    if args.dry_run:
        return 0

    if not args.token:
        print("error: no Page access token. Set FB_PAGE_TOKEN (see fb-oauth.py).")
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
        save_manifest(folder, manifest)
        time_module.sleep(UPLOAD_DELAY_SECONDS)

    print(f"\nDone: {len(plan) - failures} scheduled, {failures} failed. "
          f"Manifest: {os.path.join(folder, MANIFEST_NAME)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

