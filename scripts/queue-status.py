#!/usr/bin/env python3
"""queue-status.py - is the card queue still healthy?

Answers the one question that matters when nobody is watching: are posts lined
up, and when does the queue run dry?

    python3 scripts/queue-status.py

Exits 0 when the queue is healthy and 1 when it is empty or nearly dry, so it
can be dropped into a cron job or a workflow as a check.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "data", ".photo-schedule-manifest.json")
DHAKA = timezone(timedelta(hours=6))


def load(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid JSON: {exc}")


def scheduled_times(manifest: dict):
    """Every queued publish time, oldest first."""
    out = []
    for key, entry in manifest.items():
        stamp = entry.get("scheduled_publish_time_utc") if isinstance(entry, dict) else None
        if not stamp:
            continue
        try:
            out.append(datetime.fromisoformat(stamp))
        except ValueError:
            continue
    return sorted(out)


def human(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    bits = []
    if days:
        bits.append(f"{days}d")
    if hours or days:
        bits.append(f"{hours}h")
    bits.append(f"{mins}m")
    return " ".join(bits)


def report(manifest: dict, now: datetime, warn_days: float):
    """Return (lines, healthy) so the logic is testable without a clock."""
    entries = scheduled_times(manifest)
    past = [t for t in entries if t <= now]
    future = [t for t in entries if t > now]

    lines = [f"entries        : {len(entries)}  "
             f"({len(past)} published, {len(future)} still queued)"]

    if not future:
        lines += ["", "!! the queue is EMPTY - nothing is lined up to post."]
        return lines, False

    first, last = future[0], future[-1]
    runway = last - now
    lines += [
        f"next post      : {first:%Y-%m-%d %H:%M} UTC "
        f"({first.astimezone(DHAKA):%H:%M} Dhaka, in {human(first - now)})",
        f"last queued    : {last:%Y-%m-%d %H:%M} UTC "
        f"({last.astimezone(DHAKA):%H:%M} Dhaka)",
        f"runway         : {runway.total_seconds() / 86400:.1f} days",
    ]

    if runway < timedelta(days=warn_days):
        lines += ["", f"!! under {warn_days:g} day(s) of queue left - it needs a top-up."]
        return lines, False

    lines += ["", "OK - the queue is healthy; Facebook publishes these on its own."]
    return lines, True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Report the health of the card queue.")
    p.add_argument("--manifest", default=DEFAULT_MANIFEST)
    p.add_argument("--warn-days", type=float, default=3.0,
                   help="warn when less than this much queue remains (default 3)")
    args = p.parse_args(argv)

    manifest = load(args.manifest)
    if manifest is None:
        print(f"no queue manifest at {args.manifest}")
        print("-> nothing has ever been queued, so nothing will post.")
        return 1

    print(f"manifest       : {args.manifest}")
    lines, healthy = report(manifest, datetime.now(timezone.utc), args.warn_days)
    print("\n".join(lines))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
