#!/usr/bin/env python3
"""
fb-oauth.py — Facebook OAuth helper for the reels/scheduler scripts.

Step 1 — build the login URL (no network access needed):
    python fb-oauth.py auth-url --app-id YOUR_APP_ID

Step 2 — open the printed URL, log in, approve the permissions,
         then copy the `code` query parameter from the redirect URL.

Step 3 — exchange the code for a long-lived user token and list
         the page access tokens for all your pages:
    python fb-oauth.py exchange --app-id YOUR_APP_ID \
        --app-secret YOUR_APP_SECRET --code THE_CODE

The long-lived user token (~60 days) and page tokens are printed;
save a page token as FB_PAGE_TOKEN for schedule-reels.py /
scrape-page-posts.py.

Only the Python standard library is used.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = os.environ.get("FB_API_VERSION", "v19.0")
GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"

# Everything the reels scheduler + page scraper need.
DEFAULT_SCOPE = [
    "public_profile",
    "email",
    "pages_show_list",        # list your pages
    "pages_read_engagement",   # read a page's /feed
    "pages_read_user_content", # read reactions/comments, /posts edge
    "pages_manage_posts",      # upload videos, schedule posts
    "pages_manage_engagement", # like / hide comments
    "pages_messaging",         # Messenger
    "read_insights",           # page analytics
]


def api_get(path, params):
    url = GRAPH_BASE + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def build_auth_url(app_id, redirect_uri, scope):
    # The OAuth dialog lives on www.facebook.com, not graph.facebook.com
    base = f"https://www.facebook.com/{API_VERSION}"
    return (
        f"{base}/dialog/oauth?"
        + urllib.parse.urlencode({
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(scope),
        })
    )


def exchange_code(app_id, app_secret, redirect_uri, code):
    """code -> short-lived user token -> long-lived user token."""
    short = api_get("/oauth/access_token", {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "client_secret": app_secret,
        "code": code,
    })
    short_token = short["access_token"]

    long_lived = api_get("/oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    return long_lived["access_token"]


def list_page_tokens(user_token):
    data = api_get("/me/accounts", {
        "access_token": user_token,
        "fields": "id,name,access_token,category,tasks",
        "limit": 100,
    })
    return data.get("data", [])


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("auth-url", help="print the Facebook login URL")
    a.add_argument("--app-id", required=True)
    a.add_argument("--redirect-uri", default="https://localhost/")
    a.add_argument("--scope", default=",".join(DEFAULT_SCOPE),
                   help="comma-separated permission list")

    e = sub.add_parser("exchange",
                       help="exchange the `code` for tokens")
    e.add_argument("--app-id", required=True)
    e.add_argument("--app-secret",
                   default=os.environ.get("FB_APP_SECRET"),
                   help="or set FB_APP_SECRET")
    e.add_argument("--redirect-uri", default="https://localhost/")
    e.add_argument("--code", required=True)

    args = p.parse_args()

    if args.cmd == "auth-url":
        scope = args.scope.split(",")
        print("Open this URL, approve, and copy the `code` "
              "parameter from the redirect:\n")
        print(build_auth_url(args.app_id, args.redirect_uri, scope))
        return 0

    if not args.app_secret:
        raise SystemExit("Pass --app-secret or set FB_APP_SECRET")

    print("Exchanging code for a long-lived user token ...")
    user_token = exchange_code(
        args.app_id, args.app_secret, args.redirect_uri, args.code)
    print(f"\nUSER TOKEN (save it, valid ~60 days):\n{user_token}\n")

    print("PAGE TOKENS for your pages:\n")
    for page in list_page_tokens(user_token):
        print(f"  {page.get('name')}  (id {page['id']})")
        print(f"    token: {page['access_token']}")
    print("\nSet the one you want as FB_PAGE_TOKEN, e.g.:")
    print('  $env:FB_PAGE_TOKEN = "EAAG..."')
    return 0


if __name__ == "__main__":
    sys.exit(main())