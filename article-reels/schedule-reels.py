#!/usr/bin/env python3
"""
schedule-reels.py — Schedule all reels in this folder to a Facebook Page.

The TITLE and DESCRIPTION of each reel are generated from the video file
name (the article slug), e.g.:

    how-to-fix-windows-11-stuck-on-getting-updates-loop.mp4
      -> "How to Fix Windows 11 Stuck on Getting Updates Loop"

Each reel is uploaded as a SCHEDULED (unpublished) video post, so nothing
goes live immediately — Facebook publishes each one at its scheduled time.

Only the Python standard library is used (no pip installs needed).

Usage:
    python schedule-reels.py --dry-run                  # preview only
    python schedule-reels.py                            # schedule all reels
    python schedule-reels.py --start-date 2026-10-20 --time 09:30 \
                             --interval-days 2 --limit 5

Notes:
  * All times are UTC. Facebook only allows scheduled times between
    ~10 minutes and ~6 months in the future.
  * Set FB_PAGE_ID / FB_PAGE_TOKEN / FB_API_VERSION env vars to override
    the defaults below.
  * A .reel-schedule-manifest.json remembers what was already scheduled so
    re-running the script never double-posts (use --force to ignore it).
"""

import argparse
import json
import os
import re
import sys
import time as time_module
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, time as dtime, timezone

# ---------------------------------------------------------------------------
# Defaults — override with env vars (FB_PAGE_ID, FB_PAGE_TOKEN, FB_API_VERSION)
# ---------------------------------------------------------------------------
DEFAULT_PAGE_ID = "105407425560140"  # "Sin City" page
DEFAULT_TOKEN = "EAAM4uULUpAUBSu1MJZBzrVqRiSGOceoGzUnMY8uOlYZBj0v6LiGS7XUz2CfBO2Emze0PtMFNrS54sZCtWLUb5HOZCDO6Y01FpJdrjg3czYrYrUEcttTYb4YXwXGAR83ixmep42fvQwm86ZA9gngdZAXIZB7dNOFRZBMTWIbnqw0RpNYMLzlyPrIcNtSriLnz4ZBm8AvC3JtUZD"
API_VERSION = os.environ.get("FB_API_VERSION", "v19.0")
GRAPH_VIDEO_BASE = f"https://graph-video.facebook.com/{API_VERSION}"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
MANIFEST_NAME = ".reel-schedule-manifest.json"
UPLOAD_DELAY_SECONDS = 2  # be gentle with Graph API rate limits

# Nicer casing for tech acronyms / brands that plain title-case would mangle.
ACRONYMS = {
    "tpm": "TPM", "oauth": "OAuth", "html": "HTML", "css": "CSS",
    "usb": "USB", "ssd": "SSD", "hdd": "HDD", "cpu": "CPU", "gpu": "GPU",
    "ram": "RAM", "bios": "BIOS", "dns": "DNS", "vpn": "VPN", "url": "URL",
    "http": "HTTP", "ai": "AI", "pc": "PC", "it": "IT", "wifi": "Wi-Fi",
}
BRANDS = {
    "linkedin": "LinkedIn", "github": "GitHub", "astro": "Astro",
    "netlify": "Netlify", "vercel": "Vercel", "ollama": "Ollama",
}
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "for", "so", "yet",
    "of", "in", "on", "at", "to", "from", "by", "with", "vs", "via",
    "per", "as",
}


# ---------------------------------------------------------------------------
# File name -> Title / Description
# ---------------------------------------------------------------------------
def slug_to_title(slug: str) -> str:
    """Convert a file-name slug into a human-readable title."""
    slug = re.sub(r"\s*\(\d+\)\s*$", "", slug).strip()  # drop duplicate markers like " (1)"
    words = [w for w in re.split(r"[-_\s]+", slug.replace("_", "-")) if w]
    titled = []
    n = len(words)
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in ACRONYMS:                                 # acronyms first
            titled.append(ACRONYMS[lw])
        elif lw in BRANDS:
            titled.append(BRANDS[lw])
        elif (m := re.fullmatch(r"windows(\d+)", lw)):     # windows11 -> Windows 11
            titled.append(f"Windows {m.group(1)}")
        elif i == 0 or i == n - 1 or lw not in STOP_WORDS:
            titled.append(w.capitalize())
        else:
            titled.append(lw)
    return " ".join(titled)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def natural_key(name: str):
    """Sort key so windows-10 sorts before windows-11."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_videos(folder: str):
    videos = [
        os.path.join(folder, n)
        for n in os.listdir(folder)
        if os.path.splitext(n)[1].lower() in VIDEO_EXTENSIONS
    ]
    videos.sort(key=lambda p: natural_key(os.path.basename(p)))
    return videos


def load_manifest(folder: str):
    path = os.path.join(folder, MANIFEST_NAME)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(folder: str, manifest):
    with open(os.path.join(folder, MANIFEST_NAME), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# Facebook: upload a video as a scheduled post
# ---------------------------------------------------------------------------
def build_multipart(fields, filename: str, file_bytes: bytes):
    """Build a multipart/form-data body (stdlib-only file upload)."""
    boundary = uuid.uuid4().hex
    chunks = []
    for key, value in fields.items():
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}".encode()
        )
    chunks.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n".encode() + file_bytes
    )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"\r\n".join(chunks), boundary


def schedule_reel(page_id: str, token: str, path: str,
                  title: str, description: str, when_utc: datetime,
                  dry_run: bool = False):
    sched_epoch = int(when_utc.timestamp())
    now = datetime.now(timezone.utc)
    if not (now + timedelta(minutes=10) <= when_utc <= now + timedelta(days=180)):
        raise ValueError(
            f"scheduled time {when_utc.isoformat()} must be between "
            f"10 minutes and 180 days in the future"
        )
    if dry_run:
        return {"dry_run": True, "scheduled_publish_time": sched_epoch}

    with open(path, "rb") as f:
        data = f.read()

    fields = {
        "access_token": token,
        "title": title,
        "description": description,
        "published": "false",
        "scheduled_publish_time": str(sched_epoch),
    }
    body, boundary = build_multipart(fields, os.path.basename(path), data)
    url = f"{GRAPH_VIDEO_BASE}/{page_id}/videos"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Schedule every reel in a folder to a Facebook Page "
                    "(title & description come from the file name).")
    p.add_argument("--folder", default=os.path.dirname(os.path.abspath(__file__)),
                   help="folder containing the reel videos (default: script folder)")
    p.add_argument("--page-id", default=os.environ.get("FB_PAGE_ID", DEFAULT_PAGE_ID))
    p.add_argument("--token", default=os.environ.get("FB_PAGE_TOKEN", DEFAULT_TOKEN))
    p.add_argument("--start-date",
                   help="first publish date YYYY-MM-DD (UTC); default: tomorrow")
    p.add_argument("--time", default="18:00",
                   help="publish time HH:MM in UTC (default: 18:00)")
    p.add_argument("--interval-days", type=float, default=1.0,
                   help="days between each reel (default: 1)")
    p.add_argument("--limit", type=int, default=0,
                   help="schedule only the first N reels (0 = all)")
    p.add_argument("--hashtags", default="",
                   help="optional hashtags appended to every description")
    p.add_argument("--dry-run", action="store_true", help="print the plan, post nothing")
    p.add_argument("--force", action="store_true",
                   help="ignore the manifest and re-schedule everything")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    hh, mm = args.time.split(":")
    pub_time = dtime(int(hh), int(mm))

    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start = (datetime.now(timezone.utc) + timedelta(days=1)).date()

    videos = list_videos(args.folder)
    if not videos:
        print(f"No video files found in {args.folder}")
        return 1

    manifest = load_manifest(args.folder)

    # ---- build the plan ----
    plan = []
    for path in videos:
        name = os.path.basename(path)
        if not args.force and name in manifest:
            print(f"skip (already scheduled): {name}")
            continue
        title = slug_to_title(os.path.splitext(name)[0])
        description = title + (f"\n{args.hashtags}" if args.hashtags else "")
        when = datetime.combine(
            start + timedelta(days=args.interval_days * len(plan)),
            pub_time, tzinfo=timezone.utc,
        )
        plan.append({"path": path, "title": title,
                     "description": description, "when": when})

    if args.limit > 0:
        plan = plan[:args.limit]

    if not plan:
        print("Nothing to schedule "
              "(all reels are already in the manifest; use --force to redo).")
        return 0

    # ---- show the plan ----
    print(f"\n{'#':>2}  {'Scheduled (UTC)':<22}  {'File':<58}  Title")
    print("-" * 150)
    for i, item in enumerate(plan, 1):
        print(f"{i:>2}  {item['when'].isoformat():<22}  "
              f"{os.path.basename(item['path']):<58}  {item['title']}")
    print(f"\n{len(plan)} reel(s) -> Page ID {args.page_id} "
          f"({'DRY RUN' if args.dry_run else 'WILL BE SCHEDULED'})\n")

    if args.dry_run:
        return 0

    # ---- upload & schedule ----
    failures = 0
    for item in plan:
        name = os.path.basename(item["path"])
        print(f"Scheduling {name} for {item['when'].isoformat()} ...", flush=True)
        try:
            result = schedule_reel(
                args.page_id, args.token, item["path"],
                item["title"], item["description"], item["when"],
            )
            print(f"  OK -> {json.dumps(result)}", flush=True)
            manifest[name] = {
                "title": item["title"],
                "description": item["description"],
                "scheduled_publish_time_utc": item["when"].isoformat(),
                "response": result,
            }
        except Exception as e:  # keep going; report at the end
            failures += 1
            print(f"  FAILED: {e}", flush=True)
        save_manifest(args.folder, manifest)
        time_module.sleep(UPLOAD_DELAY_SECONDS)

    print(f"\nDone: {len(plan) - failures} scheduled, {failures} failed. "
          f"Manifest: {os.path.join(args.folder, MANIFEST_NAME)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
