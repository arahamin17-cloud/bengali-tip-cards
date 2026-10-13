"""Tests for scripts/schedule-photos.py - the photo-card queue planner.

The planner is exercised through its CLI in ``--dry-run`` mode, which needs no
Facebook token and writes nothing, so the whole slot/manifest contract is
testable offline.

Run with:  python -m unittest discover -s scripts/tests -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS_DIR / "schedule-photos.py"
REPO_ROOT = SCRIPTS_DIR.parent


def run_planner(folder, manifest=None, *extra):
    """Run the planner in dry-run mode and return (rows, stdout).

    rows is a list of (iso_time, filename) in plan order.
    """
    cmd = [sys.executable, str(SCRIPT), "--folder", str(folder), "--dry-run", *extra]
    if manifest is not None:
        cmd += ["--manifest", str(manifest)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"planner failed: {proc.stdout}\n{proc.stderr}")
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if (len(parts) == 3 and parts[0].isdigit()
                and "T" in parts[1] and parts[2].endswith(".png")):
            rows.append((parts[1], parts[2]))
    return rows, proc.stdout


def manifest_path_from(stdout):
    for line in stdout.splitlines():
        if line.startswith("Manifest: "):
            return line.split("Manifest: ", 1)[1].strip()
    raise AssertionError(f"no Manifest: line in output:\n{stdout}")


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cards = self.tmp / "cards-batch"
        self.cards.mkdir()
        self.manifest = self.tmp / "manifest.json"

    def tearDown(self):
        self._tmp.cleanup()

    def add_cards(self, *names):
        for name in names:
            (self.cards / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    def write_manifest(self, entries):
        """entries: {filename: iso_time}"""
        self.manifest.write_text(json.dumps(
            {n: {"scheduled_publish_time_utc": t, "response": {"id": "x"}}
             for n, t in entries.items()}), encoding="utf-8")

    def queued(self):
        return {v["scheduled_publish_time_utc"]
                for v in json.loads(self.manifest.read_text()).values()}

    # -- slot layout ------------------------------------------------------

    def test_fresh_run_cycles_through_the_slots(self):
        self.add_cards("01-a.png", "02-a.png", "03-a.png")
        rows, _ = run_planner(self.cards, self.manifest,
                              "--times", "04:00,14:00", "--start-date", "2026-10-14")
        self.assertEqual([t for t, _ in rows], [
            "2026-10-14T04:00:00+00:00",
            "2026-10-14T14:00:00+00:00",
            "2026-10-15T04:00:00+00:00",
        ])

    def test_single_time_slot_steps_one_day_at_a_time(self):
        self.add_cards("01-a.png", "02-a.png")
        rows, _ = run_planner(self.cards, self.manifest,
                              "--time", "18:00", "--start-date", "2026-10-14")
        self.assertEqual([t for t, _ in rows],
                         ["2026-10-14T18:00:00+00:00", "2026-10-15T18:00:00+00:00"])

    # -- the manifest -----------------------------------------------------

    def test_already_scheduled_cards_are_skipped(self):
        self.add_cards("01-a.png", "02-a.png")
        self.write_manifest({"01-a.png": "2026-10-14T04:00:00+00:00"})
        rows, out = run_planner(self.cards, self.manifest,
                                "--times", "04:00,14:00", "--start-date", "2026-10-14")
        self.assertEqual([n for _, n in rows], ["02-a.png"])
        self.assertIn("skip (already scheduled): 01-a.png", out)

    def test_top_up_uses_the_next_free_slot(self):
        """A card added after a batch is queued must not reuse a taken time."""
        self.add_cards("01-a.png", "02-a.png", "03-a.png")
        self.write_manifest({
            "01-a.png": "2026-10-14T04:00:00+00:00",
            "02-a.png": "2026-10-14T14:00:00+00:00",
        })
        rows, _ = run_planner(self.cards, self.manifest,
                              "--times", "04:00,14:00", "--start-date", "2026-10-14")
        self.assertEqual(rows, [("2026-10-15T04:00:00+00:00", "03-a.png")])

    def test_planned_times_never_collide_when_start_date_moves(self):
        """CI passes --start-date=today, so it moves between runs.

        The old code offset by len(manifest), which skipped a whole week of
        empty slots once the start date moved forward.
        """
        self.add_cards(*[f"{i:02d}-a.png" for i in range(1, 16)])
        entries, start = {}, datetime(2026, 10, 14, 4, tzinfo=timezone.utc)
        for i in range(15):
            t = start + timedelta(days=i // 2, hours=10 * (i % 2))
            entries[f"{i + 1:02d}-a.png"] = t.isoformat()
        self.write_manifest(entries)
        self.add_cards("99-new.png")

        rows, _ = run_planner(self.cards, self.manifest,
                              "--times", "04:00,14:00", "--start-date", "2026-10-21")
        self.assertEqual([n for _, n in rows], ["99-new.png"])
        planned = {t for t, _ in rows}
        self.assertEqual(planned, {"2026-10-21T14:00:00+00:00"})
        self.assertEqual(planned & self.queued(), set(),
                         "a planned time collided with one already queued")

    def test_force_ignores_the_manifest(self):
        self.add_cards("01-a.png")
        self.write_manifest({"01-a.png": "2026-10-14T04:00:00+00:00"})
        rows, _ = run_planner(self.cards, self.manifest, "--force",
                              "--times", "04:00", "--start-date", "2026-10-14")
        self.assertEqual([n for _, n in rows], ["01-a.png"])

    # -- environment handling ---------------------------------------------

    def test_empty_fb_page_id_falls_back_to_the_default(self):
        """An unset GitHub Actions secret arrives as an EMPTY string.

        os.environ.get("FB_PAGE_ID", DEFAULT) then returns "" rather than the
        default, and the upload would POST to /v19.0//photos.
        """
        self.add_cards("01-a.png")
        cmd = [sys.executable, str(SCRIPT), "--folder", str(self.cards),
               "--manifest", str(self.manifest), "--dry-run",
               "--times", "04:00", "--start-date", "2026-10-14"]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              env=dict(os.environ, FB_PAGE_ID=""))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Page ID 111479998247290", proc.stdout)

    # -- keeping the queue bounded ----------------------------------------

    def test_max_ahead_days_defers_the_surplus(self):
        """A recurring run must not build an ever-deeper queue."""
        self.add_cards(*[f"{i:02d}-a.png" for i in range(1, 11)])
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        rows, out = run_planner(self.cards, self.manifest,
                                "--times", "04:00,14:00", "--start-date", tomorrow,
                                "--max-ahead-days", "2")
        self.assertTrue(rows, "nothing was planned at all")
        horizon = datetime.now(timezone.utc) + timedelta(days=2)
        for stamp, _ in rows:
            self.assertLessEqual(datetime.fromisoformat(stamp), horizon)
        self.assertIn("left for a later run", out)

    def test_without_a_horizon_everything_is_planned(self):
        self.add_cards(*[f"{i:02d}-a.png" for i in range(1, 11)])
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        rows, out = run_planner(self.cards, self.manifest,
                                "--times", "04:00,14:00", "--start-date", tomorrow)
        self.assertEqual(len(rows), 10)
        self.assertNotIn("left for a later run", out)

    # -- where the queue state lives --------------------------------------

    def test_default_manifest_is_outside_the_cards_folder(self):
        """Cards folders are gitignored build output; the queue must survive."""
        self.add_cards("01-a.png")
        _, out = run_planner(self.cards, None,  # no --manifest -> default
                             "--times", "04:00", "--start-date", "2026-10-14")
        default = Path(manifest_path_from(out))
        self.assertFalse(
            default.is_relative_to(self.cards),
            f"default manifest {default} is inside the cards folder")
        self.assertEqual(default, REPO_ROOT / "data" / ".photo-schedule-manifest.json")


if __name__ == "__main__":
    unittest.main()
