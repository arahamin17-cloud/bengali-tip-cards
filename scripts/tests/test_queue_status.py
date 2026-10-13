"""Tests for scripts/queue-status.py.

`report()` takes the clock as an argument, so the health logic is tested
without depending on the real time.

Run with:  python -m unittest discover -s scripts/tests -v
"""

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "queue-status.py"
_spec = importlib.util.spec_from_file_location("queue_status", SCRIPT)
queue_status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(queue_status)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def manifest(*offsets_days):
    """A manifest with one entry per day offset from NOW."""
    return {
        f"card-{i}.png": {
            "scheduled_publish_time_utc": (NOW + timedelta(days=d)).isoformat(),
        }
        for i, d in enumerate(offsets_days)
    }


class ReportTest(unittest.TestCase):
    def test_healthy_queue(self):
        lines, healthy = queue_status.report(manifest(1, 2, 3, 4, 5), NOW, 3)
        self.assertTrue(healthy)
        self.assertIn("runway         : 5.0 days", lines)
        self.assertIn("OK - the queue is healthy", " ".join(lines))

    def test_empty_queue_is_unhealthy(self):
        lines, healthy = queue_status.report({}, NOW, 3)
        self.assertFalse(healthy)
        self.assertIn("EMPTY", " ".join(lines))

    def test_queue_with_only_past_entries_is_unhealthy(self):
        lines, healthy = queue_status.report(manifest(-5, -4, -3), NOW, 3)
        self.assertFalse(healthy)
        self.assertIn("EMPTY", " ".join(lines))

    def test_short_runway_warns(self):
        lines, healthy = queue_status.report(manifest(-2, 0.5), NOW, 3)
        self.assertFalse(healthy)
        self.assertIn("needs a top-up", " ".join(lines))

    def test_counts_published_separately(self):
        lines, _ = queue_status.report(manifest(-3, -1, 2, 4), NOW, 3)
        self.assertIn("2 published, 2 still queued", " ".join(lines))

    def test_ignores_entries_without_a_time(self):
        m = manifest(5)
        m["broken.png"] = {"response": {"id": "x"}}
        lines, healthy = queue_status.report(m, NOW, 3)
        self.assertTrue(healthy)
        self.assertIn("entries        : 1", " ".join(lines))

    def test_next_post_is_reported_in_utc_and_dhaka(self):
        lines, _ = queue_status.report(manifest(1), NOW, 3)
        joined = " ".join(lines)
        self.assertIn("next post", joined)
        self.assertIn("Dhaka", joined)


if __name__ == "__main__":
    unittest.main()
