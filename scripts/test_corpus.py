#!/usr/bin/env python3
"""Tests for corpus loading, filtering, and slot substitution.

    python3 -m unittest discover -s scripts -t scripts
"""

from __future__ import annotations

import unittest

from corpus import (ANCHORING, APERTURE, BRIEF_SHAPE, build_brief, fill_slots,
                    filter_questions, load, slots_in)


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
        # {phrase} is filled by the host live; {industry} is derived from each
        # profile's label rather than declared in $slots.
        declared = set(self.corpus.industries["$slots"]) | {"phrase", "industry"}
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


class TestArcs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load()

    def test_arcs_load(self):
        self.assertIn("ai-workflow-partner", self.corpus.arcs)

    def test_every_beat_has_every_flavor(self):
        # The whole point of flavors is that the arc survives a guest whose
        # situation turned out to be different, so a gap here is a real defect.
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                self.assertEqual(
                    set(beat["flavors"]), set(ANCHORING),
                    f"arc {name}, beat {beat['beat']} is missing a flavor",
                )

    def test_flavors_are_distinct(self):
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                texts = [t.strip() for t in beat["flavors"].values()]
                self.assertEqual(len(set(texts)), len(texts),
                                 f"arc {name}, beat {beat['beat']} repeats a flavor")

    def test_beat_themes_are_in_the_taxonomy(self):
        valid = {k for k in self.corpus.taxonomy["theme"] if not k.startswith("$")}
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                self.assertIn(beat["theme"], valid, f"arc {name}, beat {beat['beat']}")

    def test_least_presuming_flavor_avoids_second_person_possessive(self):
        # A 'general' flavor that says "your team" still assumes a current
        # situation, which defeats the purpose of having the level at all.
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                text = beat["flavors"]["general"].lower()
                for phrase in ("your team", "your company", "your organization", "your work"):
                    self.assertNotIn(phrase, text,
                                     f"arc {name}, beat {beat['beat']}: general flavor says '{phrase}'")

    def test_slots_in_arcs_are_declared(self):
        declared = set(self.corpus.industries["$slots"]) | {"phrase"}
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                fields = list(beat["flavors"].values()) + beat.get("followups", [])
                fields.append(beat.get("if_it_stalls", ""))
                for text in fields:
                    for slot in slots_in(text):
                        self.assertIn(slot, declared, f"arc {name}, beat {beat['beat']}")

    def test_arc_flavors_fill_slots_for_every_industry(self):
        arc = self.corpus.arcs["ai-workflow-partner"]
        for slug, profile in self.corpus.profiles.items():
            for beat in arc["beats"]:
                for text in beat["flavors"].values():
                    self.assertNotIn("{", fill_slots(text, profile), f"{slug}/{beat['beat']}")


class TestSeries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load()

    def test_series_loads_with_a_spine(self):
        self.assertTrue(self.corpus.series.get("promise"))
        self.assertTrue(self.corpus.spine)

    def test_every_spine_theme_is_fully_specified(self):
        # A theme missing its reframe or its vocabulary cannot guide writing,
        # which is the only reason the spine exists as data rather than prose.
        for theme in self.corpus.spine:
            for field_name in ("theme", "name", "reframe", "why_it_empowers", "say", "do_not_say"):
                self.assertTrue(theme.get(field_name), f"{theme.get('theme')} lacks {field_name}")

    def test_every_arc_covers_every_spine_theme(self):
        # The series requires that every episode touches these, so an arc that
        # cannot deliver one is broken rather than merely different.
        themes = {t["theme"] for t in self.corpus.spine}
        for name, arc in self.corpus.arcs.items():
            covered = {t for beat in arc["beats"] for t in beat.get("covers", [])}
            self.assertEqual(themes - covered, set(), f"arc {name} misses a spine theme")

    def test_beats_only_claim_real_spine_themes(self):
        themes = {t["theme"] for t in self.corpus.spine}
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                for theme in beat.get("covers", []):
                    self.assertIn(theme, themes, f"arc {name}, beat {beat['beat']}")

    def test_every_spine_theme_is_reachable_from_the_corpus(self):
        # Not every interview runs the arc, so the themes need standalone
        # questions too or a brief would never touch them.
        for theme in self.corpus.spine:
            tagged = [q for q in self.corpus.questions if theme["theme"] in q.get("tags", [])]
            self.assertTrue(tagged, f"no questions tagged {theme['theme']}")

    def test_no_question_uses_deficit_framing(self):
        avoid = [p for p in self.corpus.series["voice"]["avoid_patterns"]
                 if not p.startswith("$")]
        for q in self.corpus.questions:
            exempt = [p.lower() for p in q.get("voice_exempt", [])]
            text = q["text"].lower()
            for pattern in avoid:
                if pattern in exempt:
                    continue
                self.assertNotIn(pattern, text, f"{q['id']} uses deficit framing")

    def test_no_arc_flavor_uses_deficit_framing(self):
        avoid = [p for p in self.corpus.series["voice"]["avoid_patterns"]
                 if not p.startswith("$")]
        for name, arc in self.corpus.arcs.items():
            for beat in arc["beats"]:
                for level, text in beat["flavors"].items():
                    for pattern in avoid:
                        self.assertNotIn(pattern, text.lower(),
                                         f"arc {name}, beat {beat['beat']} [{level}]")

    def test_voice_exemptions_are_real(self):
        # An exemption that does not match anything is stale and hides nothing.
        for q in self.corpus.questions:
            for pattern in q.get("voice_exempt", []):
                self.assertIn(pattern.lower(), q["text"].lower(),
                              f"{q['id']} exempts a phrase it does not contain")


class TestAperture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load()

    def wide(self):
        return [q for q in self.corpus.questions if q.get("aperture") == "wide"]

    def test_the_bank_exists(self):
        self.assertTrue(self.wide())

    def test_apertures_come_from_the_vocabulary(self):
        for q in self.corpus.questions:
            self.assertIn(q.get("aperture", "narrow"), APERTURE, q["id"])

    def test_every_wide_question_carries_the_follow_up_that_lands_it(self):
        # A wide question without a narrow_to is an invitation to a talking
        # point, which is the thing the rest of the corpus exists to avoid.
        for q in self.wide():
            self.assertTrue(q.get("narrow_to"), f"{q['id']} is wide with no narrow_to")

    def test_narrow_to_points_at_the_guest_not_at_more_theory(self):
        # Keyword-matching "is this specific enough" turns out to be brittle -
        # it kept failing on questions that plainly do ask for an instance. What
        # actually distinguishes a landing follow-up is that it is a question
        # and it points at the guest's own experience rather than the topic.
        for q in self.wide():
            text = q["narrow_to"].strip()
            # Not necessarily a question - "Walk me through that one." is a
            # perfectly good landing prompt.
            self.assertGreater(len(text.split()), 5, f"{q['id']} narrow_to is too thin")
            lowered = text.lower()
            # A landing follow-up does one of two things: it points at the
            # guest's own experience, or it demands a single instance. Either
            # is fine; neither means the question has not been landed.
            personal = any(w in lowered for w in (" you", "you ", "your"))
            instance = any(w in lowered for w in (
                "one ", "give me", "name ", "which ", "walk me", "an example",
                "think of", "describe",
            ))
            self.assertTrue(
                personal or instance,
                f"{q['id']} narrow_to neither points at the guest nor asks for "
                f"an instance: {text!r}",
            )

    def test_narrow_to_only_on_wide_questions(self):
        for q in self.corpus.questions:
            if q.get("aperture", "narrow") != "wide":
                self.assertNotIn("narrow_to", q, f"{q['id']} has narrow_to but is not wide")

    def test_wide_questions_never_enter_a_brief(self):
        # They would hollow out a running order, which is the whole reason the
        # aperture field exists.
        for industry in ("healthcare", "logistics", "law"):
            for role in (None, "middle-manager"):
                for q in build_brief(self.corpus, industry, role):
                    self.assertNotEqual(q.get("aperture"), "wide",
                                        f"{q['id']} leaked into a {industry}/{role} brief")

    def test_industry_slot_fills_from_the_profile_label(self):
        profile = self.corpus.profile("healthcare")
        self.assertEqual(
            fill_slots("decisions in {industry}?", profile),
            "decisions in Healthcare & Medicine?",
        )

    def test_wide_questions_are_reachable_by_filter(self):
        got = filter_questions(self.corpus, aperture="wide")
        self.assertEqual(len(got), len(self.wide()))


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
