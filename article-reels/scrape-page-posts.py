w#!/usr/bin/env python3
"""
scrape-page-posts.py — scrape the first N posts from a public Facebook Page.

Data comes from the official Graph API /{page-id}/feed endpoint:
  * Pages YOU manage: works with your page access token
    (needs the pages_read_engagement permission).
  * ANY public page: your app additionally needs "Page Public Metadata
    Access" (free approval at developers.facebook.com) — without it Meta
    returns error 10 for pages you don't manage.

Usage:
    python scrape-page-posts.py --page 105407425560140 --count 30
    python scrape-page-posts.py --page "Sin City"  --count 20 --csv posts.csv
    python scrape-page-posts.py --page cocacola    --count 25

Set FB_PAGE_TOKEN (or pass --token). Saves JSON (default page-posts.json)
and optionally a CSV. Only the Python standard library is used.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = os.environ.get("FB_API_VERSION", "v19.0")
GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"
DEFAULT_TOKEN = "EAAM4uULUpAUBSu1MJZBzrVqRiSGOceoGzUnMY8uOlYZBj0v6LiGS7XUz2CfBO2Emze0PtMFNrS54sZCtWLUb5HOZCDO6Y01FpJdrjg3czYrYrUEcttTYb4YXwXGAR83ixmep42fvQwm86ZA9gngdZAXIZB7dNOFRZBMTWIbnqw0RpNYMLzlyPrIcNtSriLnz4ZBm8AvC3JtUZD"

# Fields readable with pages_read_engagement on the /feed edge.
# (Inline reactions/comments summaries require pages_read_user_content
# or Page Public Content Access — query the /{post-id}/reactions and
# /{post-id}/comments edges separately instead.)
POST_FIELDS = (
    "id,message,created_time,updated_time,permalink_url,shares"
)


# ---------------------------------------------------------------------------
# Graph API helpers
# ---------------------------------------------------------------------------
def api_get(path, params, retries=3):
    """GET a Graph API endpoint with rate-limit backoff."""
    url = GRAPH_BASE + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (4, 613) and attempt < retries - 1:  # throttling
                time.sleep(5 * (attempt + 1))
                continue
            try:
                detail = json.loads(body).get("error", {}).get("message", body)
            except ValueError:
                detail = body
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    raise RuntimeError("request failed after retries")


def resolve_page(query, token):
    """Turn a page ID, username, or name into (page_id, page_name)."""
    if query.isdigit():
        return query, query
    if " " not in query:  # single word — could be a vanity username
        try:
            data = api_get(f"/{urllib.parse.quote(query)}",
                           {"access_token": token, "fields": "id,name"})
            return data["id"], data.get("name", query)
        except RuntimeError:
            pass
    try:  # search by name (needs a USER access token)
        data = api_get("/search", {
            "access_token": token, "type": "page", "q": query,
            "fields": "id,name", "limit": 5,
        })
        hits = data.get("data", [])
        if hits:
            if len(hits) > 1:
                print("Multiple pages matched — using the first one:")
                for h in hits:
                    print(f"  {h['id']}  {h.get('name')}")
            return hits[0]["id"], hits[0].get("name", query)
    except RuntimeError as e:
        print(f"Search unavailable ({e}); trying pages you manage...")
    # fallback: match by name among the token's own managed pages
    # (only works with a USER access token)
    try:
        data = api_get("/me/accounts", {"access_token": token,
                                             "fields": "id,name",
                                             "limit": 100})
    except RuntimeError:
        data = {"data": []}
    for page in data.get("data", []):
        if page.get("name", "").lower() == query.lower():
            return page["id"], page["name"]
    raise SystemExit(
        f"Could not resolve page '{query}' with this token. "
        f"Pass the numeric page ID (shown in the page's About "
        f"section or URL), a vanity username, or a USER access "
        f"token with pages_read_engagement via --token / FB_PAGE_TOKEN."
    )


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
def fetch_posts(page_id, token, count):
    """Fetch up to `count` most recent posts (newest first)."""
    posts = []
    params = {
        "access_token": token,
        "fields": POST_FIELDS,
        "limit": min(count, 100),
    }
    path = f"/{page_id}/feed"  # /feed works with pages_read_engagement;
    # /posts additionally needs pages_read_user_content
    while len(posts) < count:
        data = api_get(path, params)
        batch = data.get("data", [])
        posts.extend(batch)
        after = data.get("paging", {}).get("cursors", {}).get("after")
        if not batch or not after:
            break  # no more pages
        params["after"] = after
        time.sleep(1)  # stay friendly with rate limits
    return posts[:count]


def write_csv(path, posts):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "created_time", "permalink_url",
                         "message", "shares", "reactions", "comments"])
        for post in posts:
            writer.writerow([
                post.get("id", ""),
                post.get("created_time", ""),
                post.get("permalink_url", ""),
                post.get("message", ""),
                (post.get("shares") or {}).get("count", 0),
                (post.get("reactions") or {})
                    .get("summary", {}).get("total_count", 0),
                (post.get("comments") or {})
                    .get("summary", {}).get("total_count", 0),
            ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    try:  # console may be cp1252 on Windows; keep Unicode output safe
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(
        description="Scrape the first N posts from a public Facebook Page.")
    p.add_argument("--page", required=True,
                   help="page ID, username (e.g. cocacola), or page name")
    p.add_argument("--count", type=int, default=25,
                   help="number of posts to scrape (default 25, max 1000)")
    p.add_argument("--token",
                   default=os.environ.get("FB_PAGE_TOKEN", DEFAULT_TOKEN))
    p.add_argument("--out", default="page-posts.json",
                   help="JSON output file (default: page-posts.json)")
    p.add_argument("--csv", help="also write a CSV file")
    args = p.parse_args()

    count = max(1, min(args.count, 1000))
    page_id, page_name = resolve_page(args.page, args.token)
    print(f"Page: {page_name} (id {page_id})")

    posts = fetch_posts(page_id, args.token, count)
    print(f"Scraped {len(posts)} post(s)")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"page": {"id": page_id, "name": page_name},
                   "posts": posts}, f, indent=2, ensure_ascii=False)
    print(f"Saved -> {args.out}")

    if args.csv:
        write_csv(args.csv, posts)
        print(f"Saved -> {args.csv}")

    print()
    for i, post in enumerate(posts, 1):
        msg = (post.get("message") or "").replace("\n", " ")[:70]
        print(f"{i:>2}. {post.get('created_time', '?')}  {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
