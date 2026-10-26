"""Tests for scripts/scrape_tips.py - the topic filter.

Run with:  python -m unittest discover -s scripts/tests -v
"""

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scrape_tips.py"
_spec = importlib.util.spec_from_file_location("scrape_tips", SCRIPT)
scrape_tips = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scrape_tips)


class TopicFilterTest(unittest.TestCase):
    def test_off_topic_article_is_rejected(self):
        """The real headline that produced 45 travel cards for the beauty page."""
        self.assertFalse(scrape_tips.looks_on_topic(
            "সাধ্যের মধ্যেই স্বপ্নের বিদেশ ভ্রমণ! কম খরচে ঘুরে আসার ৩টি দারুণ দেশের বাজেট ও আইটিনারি"))

    def test_recipe_is_rejected(self):
        self.assertFalse(scrape_tips.looks_on_topic("সেল রোটি তৈরির সহজ রেসিপি"))

    def test_brand_name_alone_is_not_enough(self):
        """\u09b8\u09be\u099c\u0997\u09cb\u099c is the portal's own name and appears on every article."""
        self.assertFalse(scrape_tips.looks_on_topic("সাজগোজের আজকের ফিচার"))

    def test_beauty_headlines_are_kept(self):
        for title in ["শীতে ত্বকের যত্নে যা করবেন",
                      "চুলের যত্নে ৫টি ঘরোয়া টিপস",
                      "মেকআপ করার সহজ নিয়ম",
                      "সানস্ক্রিন ব্যবহারের সঠিক নিয়ম"]:
            with self.subTest(title=title):
                self.assertTrue(scrape_tips.looks_on_topic(title))


if __name__ == "__main__":
    unittest.main()
