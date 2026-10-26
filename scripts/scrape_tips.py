#!/usr/bin/env python3
"""
scrape_tips.py — collect Bengali beauty/health tips from RSS feeds.

Pulls the newest articles from a list of Bengali feeds, extracts their readable
text, and appends the parts that look like tips to a raw text file that
scripts/clean_text_to_csv.py can then turn into a CSV.

Only the Python standard library is used (no pip installs).

Usage
    python3 scripts/scrape_tips.py --out data/tips_raw.txt --max 4
    python3 scripts/scrape_tips.py --feeds https://a/feed/,https://b/feed/

Notes
    * Article URLs already scraped are remembered in --seen (default
      data/.scrape-seen.txt) so re-running never re-adds the same article.
    * Please respect each site's terms/robots and rewrite tips in your own
      words before publishing.
"""

import argparse
import html
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

DEFAULT_FEEDS = [
    "https://shajgoj.com/feed/",        # largest Bengali beauty portal
    "https://glowstar.com.bd/feed/",    # Bengali skincare/hair
]
BENGALI = re.compile(r"[\u0980-\u09FF]")

# The feed alone is not a good enough filter. shajgoj.com is a lifestyle portal,
# so alongside skincare it also publishes travel, food and recipe articles - and
# every line in those that "looks like a tip" was harvested and posted to the
# beauty page (a single travel piece produced 45 cards). An article is now kept
# only when its headline is actually about beauty.
TOPIC_TERMS = (
    "ত্বক", "চুল", "মুখ", "সৌন্দর্য", "রূপচর্চা", "মেকআপ", "স্কিন",
    "সানস্ক্রিন", "ময়েশ্চারাইজ", "ফেসওয়াশ", "ফেসিয়াল", "ফেসপ্যাক",
    "ব্রণ", "খুশকি", "লিপস্টিক", "কাজল", "শ্যাম্পু", "হেয়ার",
    "স্ক্রাব", "সিরাম", "লোশন", "নখ", "পার্লার", "ডারমাটোলজি",
)


def looks_on_topic(headline: str) -> bool:
    """Is this article actually about beauty?"""
    return any(term in headline for term in TOPIC_TERMS)

BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section"}


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; tip-cards-bot/1.0)",
        "Accept-Language": "bn,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = TextExtractor()
    parser.feed(markup)
    text = html.unescape("".join(parser.parts))
    return re.sub(r"[ \t\u00a0]+", " ", text)


def looks_like_tip(line: str) -> bool:
    line = line.strip()
    if not (30 <= len(line) <= 320):
        return False
    if not BENGALI.search(line):
        return False
    # Nav menus are long, space-less runs of concatenated words.
    if line.count(" ") < 3:
        return False
    # Real tips read like sentences.
    if not line.endswith(("।", ".", "?", "!")):
        return False
    # Drop meta / author / ad / breadcrumb lines.
    bad = ("©", "কপিরাইট", "●", "|", "Shajgoj", "বিজ্ঞাপন", "সাবস্ক্রাইব",
           "আমাদের অ্যাপ", "শেয়ার করুন", "লিখেছেন", "টিউটোরিয়াল", "রেসিপি",
           "সোয়াচ", "ডারমাটোলজিস্ট")
    return not any(b in line for b in bad)


def feed_items(feed_url: str):
    root = ET.fromstring(fetch(feed_url))
    out = []
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if link:
            out.append((title, link))
    return out


def load_seen(path: str) -> set:
    if os.path.exists(path):
        return {ln.strip() for ln in open(path, encoding="utf-8") if ln.strip()}
    return set()


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect Bengali tips from RSS feeds.")
    ap.add_argument("--feeds", default=",".join(DEFAULT_FEEDS))
    ap.add_argument("--no-topic-filter", action="store_true",
                   help="keep every article, not just beauty/skincare ones")
    ap.add_argument("--out", default="data/tips_raw.txt")
    ap.add_argument("--seen", default="data/.scrape-seen.txt")
    ap.add_argument("--target-tips", type=int, default=24,
                    help="collect roughly this many tip lines per run")
    ap.add_argument("--max-articles", type=int, default=12,
                    help="safety cap on how many articles to fetch")
    ap.add_argument("--min-tips", type=int, default=3,
                    help="only keep an article if it yields at least this many tip lines")
    args = ap.parse_args()

    seen = load_seen(args.seen)
    feeds = [f.strip() for f in args.feeds.split(",") if f.strip()]

    candidates = []
    for feed in feeds:
        try:
            for title, link in feed_items(feed):
                if link not in seen:
                    candidates.append((title, link, feed))
        except Exception as e:
            print(f"  feed failed: {feed}: {str(e)[:70]}", file=sys.stderr)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.seen) or ".", exist_ok=True)

    added_articles = 0
    added_tips = 0
    with open(args.out, "a", encoding="utf-8") as fh, open(args.seen, "a", encoding="utf-8") as sf:
        for title, link, feed in candidates:
            if added_tips >= args.target_tips or added_articles >= args.max_articles:
                break
            try:
                text = html_to_text(fetch(link))
            except Exception as e:
                print(f"  article failed: {link}: {str(e)[:70]}", file=sys.stderr)
                continue
            seen.add(link)
            sf.write(link + "\n")
            if not args.no_topic_filter and not looks_on_topic(title):
                print(f"  skip (off topic): {title[:60]}")
                continue
            tips = []
            for line in text.splitlines():
                line = line.strip()
                if looks_like_tip(line) and line not in tips:
                    tips.append(line)
            if len(tips) < args.min_tips:
                print(f"  skip (too few tips): {title[:60]}")
                continue
            fh.write("\n" + title + "\n")
            for t in tips:
                fh.write("- " + t + "\n")
            added_articles += 1
            added_tips += len(tips)
            print(f"  + {len(tips)} tip lines from: {title[:60]}")

    print(f"\nAdded {added_articles} article(s), {added_tips} tip line(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
