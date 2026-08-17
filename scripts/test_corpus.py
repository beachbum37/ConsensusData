#!/usr/bin/env python3
"""Tests for corpus loading, filtering, and slot substitution.

    python3 -m unittest discover -s scripts -t scripts
"""

from __future__ import annotations

import unittest

from corpus import BRIEF_SHAPE, build_brief, fill_slots, filter_questions, load, slots_in


def profile(**vocab):
    return {"vocabulary": vocab}


class TestFillSlots(unittest.TestCase):
    def test_substitutes_vocabulary(self):
        self.assertEqual(
            fill_slots("How do you price a {work_unit}?", profile(work_unit="job")),
            "How do you price a job?",
        )

    def test_article_agrees_with_filled_word(self):
        self.assertEqual(fill_slots("a {work_unit}", profile(work_unit="outage")), "an outage")
        self.assertEqual(fill_slots("a {work_unit}", profile(work_unit="case")), "a case")

    def test_article_follows_sound_not_spelling(self):
        self.assertEqual(fill_slots("a {customer}", profile(customer="user")), "a user")
        self.assertEqual(fill_slots("a {work_unit}", profile(work_unit="hour")), "an hour")
        self.assertEqual(fill_slots("a {work_unit}", profile(work_unit="unit")), "a unit")

    def test_capital_article_stays_capital(self):
        self.assertEqual(
            fill_slots("A {work_unit} ends.", profile(work_unit="outage")), "An outage ends."
        )

    def test_value_with_own_determiner_absorbs_the_article(self):
        self.assertEqual(fill_slots("a {craft}", profile(craft="the book")), "the book")

    def test_unknown_slot_is_left_visible(self):
        # {phrase} is deliberately unfilled - it prompts the host for the
        # guest's own words.
        self.assertEqual(fill_slots("You said {phrase}", profile(work_unit="job")), "You said {phrase}")

    def test_no_profile_is_a_passthrough(self):
        self.assertEqual(fill_slots("a {work_unit}", None), "a {work_unit}")


class TestCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load()

    def test_loads_questions_and_profiles(self):
        self.assertGreater(len(self.corpus.questions), 100)
        self.assertEqual(len(self.corpus.profiles), 20)

    def test_ids_are_unique(self):
        ids = [q["id"] for q in self.corpus.questions]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_profile_has_all_declared_slots(self):
        for slug, prof in self.corpus.profiles.items():
            for slot in self.corpus.industries["$slots"]:
                self.assertIn(slot, prof["vocabulary"], f"{slug} is missing {{{slot}}}")

    def test_no_slot_value_produces_a_doubled_article(self):
        # Every value must survive "a {slot}" - either the article agrees with
        # it, or the value carries its own determiner and absorbs ours.
        for slug, prof in self.corpus.profiles.items():
            for slot in prof["vocabulary"]:
                filled = fill_slots(f"a {{{slot}}}", prof).lower()
                for bad in ("a a ", "a an ", "a the ", "an a ", "an the "):
                    self.assertFalse(
                        filled.startswith(bad),
                        f"{slug}.{slot} renders as {filled!r}",
                    )

    def test_slot_values_are_singular(self):
        # "a {customer}" cannot take a plural, so values must be singular.
        for slug, prof in self.corpus.profiles.items():
            for slot, word in prof["vocabulary"].items():
                # {craft} holds a mass noun by design - "engineering",
                # "reporting", "operations" - and never follows an article.
                if slot == "craft" or not word.endswith("s") or word.endswith(("ss", "us")):
                    continue
                self.fail(f"{slug}.{slot} = {word!r} looks plural")

    def test_every_slot_used_in_a_question_is_declared(self):
        declared = set(self.corpus.industries["$slots"]) | {"phrase"}
        for q in self.corpus.questions:
            for slot in slots_in(q["text"]):
                self.assertIn(slot, declared, f"{q['id']} uses undeclared {{{slot}}}")

    def test_industry_filter_includes_universal_by_default(self):
        got = filter_questions(self.corpus, industry="law")
        scopes = {tuple(q["industries"]) for q in got}
        self.assertIn(("universal",), scopes)
        self.assertIn(("law",), scopes)

    def test_industry_filter_can_exclude_universal(self):
        got = filter_questions(self.corpus, industry="law", universal=False)
        self.assertTrue(all("law" in q["industries"] for q in got))
        self.assertTrue(got)

    def test_search_matches_notes_and_tags_not_only_text(self):
        got = filter_questions(self.corpus, search="billable")
        self.assertTrue(any(q["id"] == "law-03" for q in got))

    def test_every_industry_has_its_own_questions(self):
        for slug in self.corpus.profiles:
            own = filter_questions(self.corpus, industry=slug, universal=False)
            self.assertTrue(own, f"{slug} has no industry-specific questions")

    def test_roles_come_from_the_taxonomy(self):
        valid = {k for k in self.corpus.taxonomy["roles"] if not k.startswith("$")}
        for q in self.corpus.questions:
            for role in q.get("roles", []):
                self.assertIn(role, valid, f"{q['id']} uses undeclared role {role!r}")

    def test_role_filter_never_admits_another_role(self):
        for role in ("middle-manager", "ai-leader"):
            for q in filter_questions(self.corpus, role=role):
                roles = q.get("roles", [])
                self.assertTrue(
                    role in roles or not roles,
                    f"{q['id']} ({roles}) surfaced under role {role!r}",
                )

    def test_role_filter_includes_unscoped_questions_by_default(self):
        got = filter_questions(self.corpus, role="middle-manager")
        self.assertTrue(any(not q.get("roles") for q in got))

    def test_role_filter_can_exclude_unscoped_questions(self):
        got = filter_questions(self.corpus, role="ai-leader", general=False)
        self.assertTrue(got)
        self.assertTrue(all("ai-leader" in q.get("roles", []) for q in got))

    def test_role_scoped_questions_are_not_pinned_to_one_industry(self):
        # A role exists in every field, so these must stay industry-universal
        # or they will never surface for most guests.
        for q in self.corpus.questions:
            if q.get("roles"):
                self.assertIn("universal", q["industries"], f"{q['id']} is scoped twice over")

    def test_every_arc_stage_has_universal_coverage(self):
        # A brief must be buildable for any industry from the universal core
        # alone, so every stage needs universal questions in it.
        for arc in ("opener", "warmup", "core", "deep", "closer", "pivot"):
            got = [q for q in self.corpus.questions
                   if q["arc"] == arc and "universal" in q["industries"]]
            self.assertTrue(got, f"no universal questions at stage {arc}")


class TestBuildBrief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load()

    def source(self, q, industry, role):
        if industry and industry in q["industries"]:
            return "industry"
        if role and role in q.get("roles", []):
            return "role"
        return "core"

    def test_brief_is_full_length_and_in_running_order(self):
        brief = build_brief(self.corpus, "healthcare")
        self.assertEqual(len(brief), sum(n for _, n in BRIEF_SHAPE))
        stages = [q["arc"] for q in brief]
        self.assertEqual(stages, sorted(stages, key=[a for a, _ in BRIEF_SHAPE].index))

    def test_brief_has_no_duplicates(self):
        brief = build_brief(self.corpus, "logistics", "middle-manager")
        ids = [q["id"] for q in brief]
        self.assertEqual(len(ids), len(set(ids)))

    def test_brief_is_deterministic(self):
        a = build_brief(self.corpus, "law", "middle-manager", seed=4)
        b = build_brief(self.corpus, "law", "middle-manager", seed=4)
        self.assertEqual([q["id"] for q in a], [q["id"] for q in b])

    def test_brief_never_includes_another_role(self):
        for role in ("middle-manager", "ai-leader"):
            for q in build_brief(self.corpus, "technology", role):
                roles = q.get("roles", [])
                self.assertTrue(role in roles or not roles, f"{q['id']} ({roles}) in {role} brief")

    def test_brief_without_a_role_excludes_all_role_packs(self):
        for q in build_brief(self.corpus, "finance"):
            self.assertFalse(q.get("roles"), f"{q['id']} surfaced in a role-less brief")

    def test_role_packs_do_not_crowd_out_the_industry(self):
        # The role packs are many times larger than any industry pack, so a
        # merged draw would swamp the industry material entirely.
        for industry in ("healthcare", "logistics", "skilled-trades", "education"):
            brief = build_brief(self.corpus, industry, "middle-manager")
            sources = [self.source(q, industry, "middle-manager") for q in brief]
            self.assertGreaterEqual(sources.count("industry"), 2, f"{industry} crowded out")
            self.assertGreaterEqual(sources.count("role"), 2, f"{industry} lost its role questions")

    def test_brief_works_for_every_industry(self):
        for slug in self.corpus.profiles:
            self.assertEqual(len(build_brief(self.corpus, slug)), sum(n for _, n in BRIEF_SHAPE))


if __name__ == "__main__":
    unittest.main()
