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
                    posting_dates, render_body, resolve_cta,
                    resolve_first_comment)


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
            if post.get("long_form"):
                continue
            self.assertTrue(lo <= char_count(post) <= hi,
                            f"{post['id']}: {char_count(post)} chars")

    def test_long_form_posts_keep_headroom_under_the_limit(self):
        ceiling = self.channel.mechanics["long_form_max_chars"]
        self.assertLess(ceiling, self.channel.max_chars)
        for post in self.channel.posts:
            if post.get("long_form"):
                self.assertLessEqual(char_count(post), ceiling, post["id"])

    def test_alt_hooks_also_survive_the_fold(self):
        for post in self.channel.posts:
            for alt in post.get("alt_hooks", []):
                self.assertLessEqual(len(alt), self.channel.fold_chars,
                                     f"{post['id']}: {alt[:40]}...")

    def test_prepared_replies_are_complete(self):
        for post in self.channel.posts:
            for reply in post.get("replies", []):
                self.assertTrue(reply.get("expect"), post["id"])
                self.assertTrue(reply.get("reply"), post["id"])

    def test_every_post_carries_a_spine_theme(self):
        for post in self.channel.posts:
            self.assertTrue(post.get("covers"), f"{post['id']} covers nothing")
            for theme in post["covers"]:
                self.assertIn(theme, self.spine, post["id"])

    def test_every_spine_gap_is_declared(self):
        # The feed is supposed to say all four themes over time. Cutting posts
        # may open a hole, but the hole has to be written down in channel.json
        # with what would close it - never silent.
        covered = {t for p in self.channel.posts for t in p.get("covers", [])}
        declared = {k for k in self.channel.channel.get("spine_gaps_accepted", {})
                    if not k.startswith("$")}
        self.assertEqual(self.spine - covered, declared & self.spine)
        for theme, note in self.channel.channel.get("spine_gaps_accepted", {}).items():
            if not theme.startswith("$"):
                self.assertTrue(note.strip(), f"{theme} declared with no way to close it")

    def test_every_nugget_reference_resolves(self):
        ids = {n["id"] for n in self.channel.nuggets}
        for post in self.channel.posts:
            for nid in post.get("nuggets", []):
                self.assertIn(nid, ids, f"{post['id']} -> {nid}")

    def test_the_cut_left_every_source_article_represented(self):
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

    def test_first_mention_of_agent_is_labelled(self):
        # On a feed the reader does not expand "agent" into "AI agent".
        for post in self.channel.posts:
            if post.get("agent_label_exempt"):
                continue
            body = render_body(post)
            first = body.lower().find("agent")
            if first >= 0:
                self.assertEqual(body[max(0, first - 3):first].lower(), "ai ",
                                 f"{post['id']}: ...{body[max(0, first - 30):first + 10]}...")

    def test_every_post_ends_on_a_question_then_the_invitation(self):
        # The subscribe line is the toll for the post, never the point of it -
        # a post that ends on a pitch instead of a question gets no comments.
        for post in self.channel.posts:
            parts = render_body(post).split("\n\n")
            self.assertTrue(parts[-3].endswith("?"), post["id"])
            self.assertEqual(parts[-2], post["cta_text"], post["id"])
            self.assertTrue(parts[-1].startswith("#"), post["id"])

    def test_the_invitation_is_not_in_the_hook(self):
        for post in self.channel.posts:
            self.assertNotIn("Follow", post["hook"], post["id"])

    def test_no_links_in_the_body(self):
        for post in self.channel.posts:
            self.assertNotIn("http", render_body(post), post["id"])

    def test_every_post_has_a_first_comment_carrying_the_episode_link(self):
        # Assembled for every post, not just the ones somebody fussed over.
        for post in self.channel.posts:
            comment = post["first_comment_text"]
            self.assertIn("http", comment, post["id"])
            self.assertNotIn("[[", comment, post["id"])

    def test_a_sourcing_note_always_carries_its_link(self):
        # An attribution the reader cannot check plants doubt and buys nothing.
        for post in self.channel.posts:
            note = (post.get("first_comment") or "").strip()
            if note:
                self.assertIn("http", note, post["id"])

    def test_nothing_published_still_shows_a_placeholder(self):
        for post in self.channel.posts:
            self.assertNotIn("[[", render_body(post), post["id"])

    def test_statuses_are_known(self):
        for post in self.channel.posts:
            self.assertIn(post["status"], STATUSES, post["id"])


class TestCta(unittest.TestCase):
    variants = {"default": "Follow {linkedin_page}; {show_name} is on Spotify.", "none": ""}

    def test_identity_is_substituted(self):
        text = resolve_cta("default", self.variants,
                           {"linkedin_page": "@AskAnyone", "show_name": "Ask Anyone"})
        self.assertEqual(text, "Follow @AskAnyone; Ask Anyone is on Spotify.")

    def test_missing_identity_renders_a_visible_placeholder(self):
        # Better a shout than "Follow  for the posts" going out silently.
        text = resolve_cta("default", self.variants, {})
        self.assertIn("[[linkedin page]]", text)
        self.assertIn("[[show name]]", text)

    def test_none_variant_suppresses_it(self):
        self.assertEqual(resolve_cta("none", self.variants, {}), "")

    def test_unknown_variant_falls_back_to_default(self):
        self.assertIn("[[linkedin page]]", resolve_cta("nope", self.variants, {}))

    def test_first_comment_is_lead_then_the_posts_own_note(self):
        text = resolve_first_comment(
            {"first_comment": "Sourcing note."},
            "Episodes: {youtube_url}", {"youtube_url": "https://example.com"},
        )
        self.assertEqual(text, "Episodes: https://example.com\n\nSourcing note.")

    def test_a_post_with_no_note_still_gets_the_link(self):
        text = resolve_first_comment({}, "Episodes: {youtube_url}",
                                     {"youtube_url": "https://example.com"})
        self.assertEqual(text, "Episodes: https://example.com")


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.post = {
            "id": "t-01", "hook": "A hook.", "body": ["One.", "Two."],
            "close": "A question?", "hashtags": ["#A", "#B"],
        }

    def test_the_invitation_sits_between_the_question_and_the_hashtags(self):
        self.post["cta_text"] = "Follow along."
        self.assertEqual(
            render_body(self.post),
            "A hook.\n\nOne.\n\nTwo.\n\nA question?\n\nFollow along.\n\n#A #B",
        )

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

    @staticmethod
    def unavoidable(values: list[str]) -> int:
        """Fewest adjacent repeats any ordering of these values can achieve.

        A queue where one theme outnumbers the rest has to double up somewhere.
        The test is whether the ordering hits that floor, not whether it dodges
        something arithmetic makes impossible.
        """
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return max(0, 2 * max(counts.values()) - len(values) - 1)

    def test_queue_spreads_themes_as_far_as_arithmetic_allows(self):
        themes = [p["covers"][0] for p in order_posts(self.channel.ready())]
        repeats = sum(1 for a, b in zip(themes, themes[1:]) if a == b)
        self.assertEqual(repeats, self.unavoidable(themes), themes)

    def test_queue_spreads_source_articles_the_same_way(self):
        sources = [p["source"] for p in order_posts(self.channel.ready())]
        repeats = sum(1 for a, b in zip(sources, sources[1:]) if a == b)
        self.assertEqual(repeats, self.unavoidable(sources), sources)

    def test_ordering_hits_the_floor_on_a_lopsided_queue(self):
        # Five of one theme and one of another cannot avoid three doublings.
        posts = [{"id": f"p{i}", "covers": ["a"], "source": "s"} for i in range(5)]
        posts.append({"id": "p9", "covers": ["b"], "source": "s"})
        themes = [p["covers"][0] for p in order_posts(posts)]
        repeats = sum(1 for x, y in zip(themes, themes[1:]) if x == y)
        self.assertEqual(repeats, self.unavoidable(themes), themes)

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
