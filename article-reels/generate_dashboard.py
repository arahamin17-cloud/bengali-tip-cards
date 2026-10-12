#!/usr/bin/env python3
"""generate_dashboard.py - Build the web dashboard for the article-reels project.

Reads the schedule manifest (.reel-schedule-manifest.json from schedule-reels.py)
and the scraped post JSON files (page-posts.json, sumona-posts.json from
scrape-page-posts.py), then writes dashboard.html plus reads dashboard.css and
dashboard.js for a live, auto-refreshing dashboard.

Usage:
    python generate_dashboard.py
    # then open dashboard.html in a browser
"""

import json
import os
import re
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, ".reel-schedule-manifest.json")
PAGE_POSTS_PATH = os.path.join(BASE_DIR, "page-posts.json")
SUMONA_POSTS_PATH = os.path.join(BASE_DIR, "sumona-posts.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "dashboard.html")

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
BRAND_ICONS = {
    "linkedin": "&#128190;", "github": "&#128025;", "astro": "&#10022;",
    "netlify": "&#128309;", "vercel": "&#127760;", "ollama": "&#149974;",
}
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "for", "so", "yet",
    "of", "in", "on", "at", "to", "from", "by", "with", "vs", "via",
    "per", "as",
}


def slug_to_title(slug):
    slug = re.sub(r"\s*\(\d+\)\s*$", "", slug).strip()
    words = [w for w in re.split(r"[-_\s]+", slug.replace("_", "-")) if w]
    titled = []
    n = len(words)
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in ACRONYMS:
            titled.append(ACRONYMS[lw])
        elif lw in BRANDS:
            titled.append(BRANDS[lw])
        elif re.fullmatch(r"windows(\d+)", lw):
            titled.append("Windows " + re.fullmatch(r"windows(\d+)", lw).group(1))
        elif i == 0 or i == n - 1 or lw not in STOP_WORDS:
            titled.append(w.capitalize())
        else:
            titled.append(lw)
    return " ".join(titled)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def escape_html(s):
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def format_dt_utc(dt_str):
    if not dt_str:
        return None
    try:
        if dt_str.endswith("Z"):
            return datetime.fromisoformat(dt_str[:-1] + "+00:00") \
                .astimezone(timezone.utc)
        if dt_str.endswith("+00:00"):
            return datetime.fromisoformat(dt_str).astimezone(timezone.utc)
        if dt_str.endswith("+0000"):
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S+0000") \
                .replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(dt_str).astimezone(timezone.utc)
    except ValueError:
        return None


def time_ago(dt):
    if dt is None:
        return "-"
    now = datetime.now(timezone.utc)
    total_seconds = int((now - dt).total_seconds())
    if total_seconds < 0:
        return "future"
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        return str(total_seconds // 60) + " min ago"
    if total_seconds < 86400:
        return str(total_seconds // 3600) + " hr ago"
    if total_seconds < 86400 * 30:
        return str(total_seconds // 86400) + " days ago"
    return str(total_seconds // 86400 // 30) + " mo ago"


def time_until(dt):
    if dt is None:
        return "-"
    now = datetime.now(timezone.utc)
    total_seconds = int((dt - now).total_seconds())
    if total_seconds < 0:
        return "past"
    if total_seconds < 60:
        return "in " + str(total_seconds) + "s"
    if total_seconds < 3600:
        return "in " + str(total_seconds // 3600) + "h " \
            + str((total_seconds % 3600) // 60) + "m"
    if total_seconds < 86400:
        return "in " + str(total_seconds // 3600) + "h"
    if total_seconds < 86400 * 30:
        return "in " + str(total_seconds // 86400) + "d"
    return "in " + str(total_seconds // 86400 // 30) + "mo"


def format_datetime(dt_str):
    dt = format_dt_utc(dt_str)
    if dt is None:
        return escape_html(dt_str or "")
    return dt.strftime("%b %d, %Y %H:%M UTC")


def format_status(dt_str):
    dt = format_dt_utc(dt_str)
    if dt is None:
        return "unknown"
    diff = (dt - datetime.now(timezone.utc)).total_seconds()
    if diff < 0:
        return "published"
    if diff < 60:
        return "now"
    if diff < 3600:
        return "upcoming"
    if diff < 86400:
        return "today"
    if diff < 86400 * 7:
        return "week"
    return "later"


def preprocess_posts(posts):
    for post in posts:
        dt = format_dt_utc(post.get("created_time", ""))
        post["_dt"] = dt
        post["_age"] = time_ago(dt) if dt else "unknown"
        post["_share"] = (post.get("shares") or {}).get("count", 0)
        post["_reaction"] = (post.get("reactions") or {}) \
            .get("summary", {}).get("total_count", 0)
        post["_comment"] = (post.get("comments") or {}) \
            .get("summary", {}).get("total_count", 0)
    posts.sort(
        key=lambda p: p.get("_dt") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return posts


def build_reel_card(reel, index):
    name = os.path.basename(reel["path"])
    title = escape_html(reel["title"])
    description = escape_html(reel.get("description", ""))
    when = escape_html(format_datetime(reel["when"]))
    status = escape_html(format_status(reel["when"]))
    post_id = escape_html(str(reel.get("response", {}).get("id", "")))

    icon = "&#127852;"
    first = name.lower().split()[0] if name else ""
    if first in BRAND_ICONS:
        icon = BRAND_ICONS[first]

    desc_html = ""
    if description:
        desc_html = '<p class="reel-desc">' + description + "</p>"
    post_id_html = ""
    if post_id:
        post_id_html = ('<span class="post-id" title="Facebook post ID">'
                        "&#128206; " + post_id + "</span>")

    return (
        '<div class="reel-card">'
        '<div class="reel-card-top">'
        '<span class="reel-icon">' + icon + "</span>"
        '<span class="reel-index">#' + str(index) + "</span>"
        "</div>"
        '<h3 class="reel-title">' + title + "</h3>"
        + desc_html +
        '<div class="reel-meta">'
        '<span class="reel-when">&#128245; ' + when + "</span>"
        '<span class="reel-status badge badge-' + status + '">' + status + "</span>"
        + post_id_html +
        "</div>"
        '<div class="countdown" id="cd-' + str(index) + '">-</div>'
        "</div>"
    )


def build_page_card(page_key, page_data):
    page = page_data.get("page", {})
    page_id = page.get("id", "")
    page_name = page.get("name", page_id)
    processed = preprocess_posts(page_data.get("posts") or [])
    recent = processed[:8]
    title = slug_to_title(page_id.split("_")[0].replace("-", " ").strip()) \
        if page_id else page_name

    post_html = ""
    if not recent:
        post_html = '<p class="empty">No posts scraped yet.</p>'
    for p in recent:
        message = escape_html((p.get("message") or "").strip()[:200])
        permalink = escape_html(p.get("permalink_url", ""))
        pid = escape_html(p.get("id", ""))
        post_html += (
            '<div class="post-item">'
            '<div class="post-body">'
            '<div class="post-message">' + message + "</div>"
            '<div class="post-meta">'
            '<a href="' + permalink + '" target="_blank" rel="noopener">'
            + pid + "</a>"
            '<span class="post-age">' + escape_html(p["_age"]) + "</span>"
            '<span class="post-reactions"><i class="heart"></i> '
            + str(p["_reaction"]) + "</span>"
            '<span class="post-shares"><i class="share"></i>'
            + str(p["_share"]) + "</span>"
            "</div></div></div>"
        )

    stats = (
        '<div class="stat"><span class="stat-value">' + str(len(processed))
        + '</span><span class="stat-label">posts</span></div>'
        '<div class="stat"><span class="stat-value">'
        + str(sum(p["_share"] for p in processed))
        + '</span><span class="stat-label">shares</span></div>'
        '<div class="stat"><span class="stat-value">'
        + str(sum(p["_reaction"] for p in processed))
        + '</span><span class="stat-label">reactions</span></div>'
        '<div class="stat"><span class="stat-value">'
        + str(sum(p["_comment"] for p in processed))
        + '</span><span class="stat-label">comments</span></div>'
    )

    return (
        '<div class="page-card" data-page-key="' + escape_html(page_key) + '">'
        '<div class="page-card-head">'
        "<h3>" + escape_html(title) + "</h3>"
        '<span class="badge">' + escape_html(page_name) + "</span>"
        "</div>"
        '<div class="page-stats">' + stats + "</div>"
        '<div class="post-list">' + post_html + "</div>"
        "</div>"
    )



def build_html(data):
    reels = data["reels"]
    pages_data = data["pages_data"]
    recent_posts = data["recent_posts"]

    now = datetime.now(timezone.utc)
    upcoming = [r for r in reels
                if format_dt_utc(r.get("when", ""))
                and format_dt_utc(r["when"]) > now]
    upcoming_7 = [r for r in upcoming
                  if (format_dt_utc(r["when"]) - now).total_seconds()
                  < 7 * 86400]
    total_shares = sum(p.get("_share", 0) for p in recent_posts)
    total_reactions = sum(p.get("_reaction", 0) for p in recent_posts)
    next_dt = max((format_dt_utc(r["when"]) for r in upcoming),
                  default=None)
    next_in = time_until(next_dt) if next_dt else "-"

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="UTF-8">')
    parts.append('<meta name="viewport" '
                 'content="width=device-width, initial-scale=1.0">')
    parts.append("<title>Article Reels Dashboard</title>")
    parts.append('<link rel="stylesheet" href="dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<header><div class=\"inner\">")
    parts.append("<h1><span class=\"logo\">&#128194;</span>"
                 "Article Reels Dashboard</h1>")
    parts.append('<span class="subtitle">'
                 "Facebook post scheduler &amp; scraper</span>")
    parts.append("</div></header>")
    parts.append("<main>")

    # Stats row
    parts.append('<div class="stats">')
    stats = [
        (len(reels), "Scheduled reels"),
        (len(upcoming), "Still upcoming"),
        (len(upcoming_7), "In next 7 days"),
        (next_in, "Next publish"),
        (len(pages_data), "Tracking pages"),
        (total_shares, "Total shares"),
        (total_reactions, "Total reactions"),
        (len(recent_posts), "Recent posts"),
    ]
    for value, label in stats:
        parts.append('<div class="stat-card">')
        parts.append('<span class="stat-card-value">'
                     + escape_html(str(value)) + "</span>")
        parts.append('<span class="stat-card-label">'
                     + escape_html(label) + "</span>")
        parts.append("</div>")
    parts.append("</div>")

    # Scheduled reels section
    parts.append('<section class="panel">')
    parts.append("<h2>&#128245; Upcoming Scheduled Reels</h2>")
    parts.append("<p class=\"panel-sub\">Facebook will publish these "
                 "videos at their scheduled times.</p>")
    parts.append('<div class="reel-grid">')
    for i, reel in enumerate(reels, 1):
        parts.append(build_reel_card(reel, i))
    parts.append("</div></section>")

    # Recent scraped posts section
    parts.append('<section class="panel">')
    parts.append("<h2>&#128243; Recent Scraped Posts</h2>")
    parts.append('<p class="panel-sub">Data from '
                 "<code>scrape-page-posts.py</code>.</p>")
    parts.append('<div class="pages-grid">')
    for key, page_data in pages_data.items():
        parts.append(build_page_card(key, page_data))
    parts.append("</div></section>")

    # Pages overview section
    parts.append('<section class="panel">')
    parts.append("<h2>&#128196; Pages</h2>")
    parts.append("<p class=\"panel-sub\">Facebook pages tracked by "
                 "this project.</p>")
    parts.append('<div class="pages-grid">')
    for key, page_data in pages_data.items():
        page = page_data.get("page", {})
        page_id = page.get("id", "")
        page_name = page.get("name", page_id)
        parts.append(
            '<div class="page-card" data-page-key="'
            + escape_html(key) + '">'
            '<div class="page-card-head"><h3>'
            + escape_html(page_name) + "</h3>"
            '<span class="badge">' + escape_html(page_id) + "</span>"
            "</div>"
            '<div class="page-meta">'
            "<span>ID: " + escape_html(page_id) + "</span><br>"
            "<span>Created: "
            + format_datetime(page.get("created_time", ""))
            + "</span></div></div>"
        )
    parts.append("</div></section>")
    parts.append("</main>")

    # Footer + embedded JSON for the JS layer
    parts.append('<footer class="footer">')
    parts.append('<span id="last-updated">Last updated: '
                 '<time id="last-updated-time">-</time></span>')
    parts.append('<button id="refresh-btn" class="btn">'
                 "&#10227; Refresh data</button>")
    parts.append('<span class="hint">Auto-refreshes every 30s. '
                 "Generated by <code>generate_dashboard.py</code></span>")
    parts.append("</footer>")
    # Embedded data as valid JSON (quoted keys) so the browser
    # can JSON.parse it. Placed BEFORE dashboard.js so the
    # external script can read window.__dashboardData on load.
    parts.append("<script>")
    parts.append("  window.__dashboardData = {")
    parts.append('    "reels": '
                 + json.dumps(reels, ensure_ascii=False,
                              default=str)
                 + ",")
    parts.append('    "pages_data": '
                 + json.dumps(pages_data, ensure_ascii=False,
                              default=str)
                 + ",")
    parts.append('    "recent_posts": '
                 + json.dumps(recent_posts, ensure_ascii=False,
                              default=str))
    parts.append("  };")
    parts.append("</script>")
    parts.append('<script src="dashboard.js"></script>')
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)



def collect_data():
    manifest = load_json(MANIFEST_PATH) or {}
    page_posts = load_json(PAGE_POSTS_PATH) or {}
    sumona_posts = load_json(SUMONA_POSTS_PATH) or {}

    reels = []
    for name, entry in sorted(
        manifest.items(),
        key=lambda kv: kv[1].get("scheduled_publish_time_utc", ""),
    ):
        when = entry.get("scheduled_publish_time_utc", "")
        if format_dt_utc(when) is None:
            continue
        reels.append({
            "path": name,
            "title": entry.get(
                "title", slug_to_title(os.path.splitext(name)[0])),
            "description": entry.get("description", ""),
            "when": when,
            "response": entry.get("response", {}),
        })

    pages_data = {
        "page-posts": page_posts,
        "sumona-posts": sumona_posts,
    }

    recent_posts = []
    for page_data in pages_data.values():
        recent_posts.extend(preprocess_posts(page_data.get("posts") or []))

    return {
        "reels": reels,
        "pages_data": pages_data,
        "recent_posts": recent_posts,
    }


def main():
    html_data = collect_data()
    html = build_html(html_data)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] Dashboard generated: " + OUTPUT_PATH)
    print("  - Reels scheduled:   " + str(len(html_data["reels"])))
    print("  - Page post sources: "
          + str(list(html_data["pages_data"].keys())))
    print("  - Total posts:       "
          + str(len(html_data["recent_posts"])))


if __name__ == "__main__":
    main()


