#!/usr/bin/env python3
"""Tests for the LinkedIn content machine.

    python3 -m unittest discover -s scripts -t scripts

Most of these are properties of the published artefact rather than of the code:
a hook that does not survive the fold is a defect in the post, and the test
suite is where that gets caught rather than the composer.
"""

from __future__ import annotations

import unittest
from datetime import date

from corpus import load
from social import (POST_DAYS, STATUSES, build_queue, char_count, filter_nuggets,
                    filter_posts, fold_fits, load_channel, order_posts,
                    posting_dates, render_body)


class TestPosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_channel()
        cls.spine = {t["theme"] for t in load().spine}

    def test_every_hook_survives_the_fold(self):
        for post in self.channel.posts:
            self.assertTrue(
                fold_fits(post, self.channel.fold_chars),
                f"{post['id']}: hook is {len(post['hook'])} chars",
            )

    def test_every_post_fits_the_platform_limit(self):
        for post in self.channel.posts:
            self.assertLessEqual(char_count(post), self.channel.max_chars, post["id"])

    def test_every_post_is_in_the_target_range(self):
        lo, hi = self.channel.mechanics["target_chars"]
        for post in self.channel.posts:
            self.assertTrue(lo <= char_count(post) <= hi,
                            f"{post['id']}: {char_count(post)} chars")

    def test_every_post_carries_a_spine_theme(self):
        for post in self.channel.posts:
            self.assertTrue(post.get("covers"), f"{post['id']} covers nothing")
            for theme in post["covers"]:
                self.assertIn(theme, self.spine, post["id"])

    def test_the_feed_covers_the_whole_spine(self):
        # Same requirement the arcs carry: an account that only ever says one
        # of the four is a different account.
        covered = {t for p in self.channel.posts for t in p.get("covers", [])}
        self.assertEqual(self.spine, covered & self.spine)

    def test_every_nugget_reference_resolves(self):
        ids = {n["id"] for n in self.channel.nuggets}
        for post in self.channel.posts:
            for nid in post.get("nuggets", []):
                self.assertIn(nid, ids, f"{post['id']} -> {nid}")

    def test_every_source_article_produced_posts(self):
        sources = {p.get("source") for p in self.channel.posts}
        self.assertEqual(
            sources, {"track-trophy", "agent-mgrs", "executor-to-editor"}
        )

    def test_no_engagement_bait(self):
        avoid = [k for k in self.channel.channel["voice"]["avoid_patterns"]
                 if not k.startswith("$")]
        for post in self.channel.posts:
            body = render_body(post).lower()
            for pattern in avoid:
                self.assertNotIn(pattern, body, f"{post['id']}: '{pattern}'")

    def test_no_show_wide_deficit_framing(self):
        # The feed inherits the podcast's register - see data/series.json.
        avoid = [k for k in load().series["voice"]["avoid_patterns"]
                 if not k.startswith("$")]
        for post in self.channel.posts:
            body = render_body(post).lower()
            for pattern in avoid:
                self.assertNotIn(pattern, body, f"{post['id']}: '{pattern}'")

    def test_no_unverified_figure_in_post_copy(self):
        # channel.json: no number unless the nugget behind it is 'verified'.
        for post in self.channel.posts:
            body = render_body(post).lower()
            if "%" in body or " percent" in body:
                backed = any((self.channel.nugget(n) or {}).get("citation_status") == "verified"
                             for n in post.get("nuggets", []))
                self.assertTrue(backed, f"{post['id']} quotes a figure with no verified source")

    def test_post_copy_is_plain_ascii(self):
        for post in self.channel.posts:
            body = render_body(post)
            self.assertTrue(body.isascii(), f"{post['id']} has non-ASCII copy")

    def test_no_links_in_the_body(self):
        for post in self.channel.posts:
            self.assertNotIn("http", render_body(post), post["id"])

    def test_statuses_are_known(self):
        for post in self.channel.posts:
            self.assertIn(post["status"], STATUSES, post["id"])


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.post = {
            "id": "t-01", "hook": "A hook.", "body": ["One.", "Two."],
            "close": "A question?", "hashtags": ["#A", "#B"],
        }

    def test_hook_leads_and_hashtags_trail(self):
        rendered = render_body(self.post)
        self.assertTrue(rendered.startswith("A hook."))
        self.assertTrue(rendered.endswith("#A #B"))

    def test_paragraphs_are_blank_line_separated(self):
        self.assertEqual(
            render_body(self.post), "A hook.\n\nOne.\n\nTwo.\n\nA question?\n\n#A #B"
        )

    def test_char_count_measures_what_gets_pasted(self):
        self.assertEqual(char_count(self.post), len(render_body(self.post)))

    def test_a_post_with_no_hashtags_still_renders(self):
        del self.post["hashtags"]
        self.assertTrue(render_body(self.post).endswith("A question?"))


class TestQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_channel()

    def test_dates_land_on_the_posting_days(self):
        for per_week, days in POST_DAYS.items():
            slots = posting_dates(date(2026, 8, 24), 3, per_week)
            self.assertEqual(len(slots), 3 * per_week)
            for slot in slots:
                self.assertIn(slot.weekday(), days)

    def test_dates_never_precede_the_start(self):
        # A Wednesday start should not schedule that week's Tuesday.
        start = date(2026, 8, 26)
        for slot in posting_dates(start, 2, 2):
            self.assertGreaterEqual(slot, start)

    def test_a_late_week_start_still_gets_the_weeks_asked_for(self):
        # Sunday 23 Aug 2026: the Tuesday of that week is already gone.
        slots = posting_dates(date(2026, 8, 23), 2, 1)
        self.assertEqual(slots, [date(2026, 8, 25), date(2026, 9, 1)])

    def test_an_unknown_cadence_is_refused(self):
        with self.assertRaises(ValueError):
            posting_dates(date(2026, 8, 24), 2, 5)

    def test_queue_never_repeats_a_post(self):
        queue = build_queue(self.channel, weeks=8, per_week=2, start=date(2026, 8, 24))
        used = [p["id"] for _, p in queue if p]
        self.assertEqual(len(used), len(set(used)))

    def test_queue_is_deterministic(self):
        a = build_queue(self.channel, weeks=4, per_week=2, start=date(2026, 8, 24))
        b = build_queue(self.channel, weeks=4, per_week=2, start=date(2026, 8, 24))
        self.assertEqual([p["id"] for _, p in a if p], [p["id"] for _, p in b if p])

    def test_queue_does_not_run_the_same_theme_twice_running(self):
        ordered = order_posts(self.channel.ready())
        themes = [p["covers"][0] for p in ordered]
        for first, second in zip(themes, themes[1:]):
            self.assertNotEqual(first, second, f"{themes}")

    def test_queue_alternates_source_articles_where_it_can(self):
        ordered = order_posts(self.channel.ready())
        sources = [p["source"] for p in ordered]
        repeats = sum(1 for a, b in zip(sources, sources[1:]) if a == b)
        self.assertLessEqual(repeats, 1, sources)

    def test_only_ready_posts_are_scheduled(self):
        for _, post in build_queue(self.channel, weeks=8, per_week=2):
            if post:
                self.assertEqual(post["status"], "ready")

    def test_slots_past_the_queue_are_empty_not_recycled(self):
        # Running out is information: it means write something or go scanning.
        queue = build_queue(self.channel, weeks=40, per_week=2, start=date(2026, 8, 24))
        filled = [p for _, p in queue if p]
        self.assertEqual(len(filled), len(self.channel.ready()))
        self.assertIsNone(queue[-1][1])


class TestNuggets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_channel()
        cls.spine = {t["theme"] for t in load().spine}

    def test_every_nugget_carries_a_counterpoint(self):
        # A nugget with nothing to say against it is a slogan, and posts built
        # from slogans are the ones this audience discounts.
        for n in self.channel.nuggets:
            self.assertTrue(n.get("counterpoint"), n["id"])

    def test_every_nugget_maps_to_the_spine(self):
        for n in self.channel.nuggets:
            self.assertIn(n["theme"], self.spine, n["id"])

    def test_a_flagged_figure_never_reaches_a_post(self):
        flagged = [n for n in self.channel.nuggets if n.get("verify_before_use")]
        self.assertTrue(flagged, "the unattributed survey figure should still be flagged")
        for n in flagged:
            self.assertNotEqual(n["citation_status"], "verified", n["id"])

    def test_filters(self):
        self.assertTrue(filter_nuggets(self.channel, theme="management-redefined"))
        self.assertTrue(filter_nuggets(self.channel, source="agent-mgrs"))
        self.assertTrue(filter_nuggets(self.channel, search="tackle box"))
        self.assertFalse(filter_nuggets(self.channel, search="zzzzz"))

    def test_post_filters(self):
        self.assertTrue(filter_posts(self.channel, status="ready"))
        self.assertTrue(filter_posts(self.channel, nugget="nug-threshold-example"))
        self.assertFalse(filter_posts(self.channel, fmt="playbook", status="held"))


if __name__ == "__main__":
    unittest.main()
