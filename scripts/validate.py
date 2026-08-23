#!/usr/bin/env python3
"""Check the corpus for structural problems before you rely on it in a booking.

Catches: missing fields, values outside the controlled vocabularies, duplicate
ids, near-duplicate question text, slots with no definition, and industries
with no profile. Also prints a coverage table so gaps are obvious.

    python3 scripts/validate.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict

from corpus import ANCHORING, REQUIRED_FIELDS, load, slots_in
from social import (NUGGET_FIELDS, POST_FIELDS, STATUSES, char_count,
                    load_channel, render_body)

ARC_BEAT_FIELDS = ("beat", "title", "theme", "purpose", "listener_payoff",
                   "keep_it_approachable", "flavors")


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def vocab(section: dict) -> list[str]:
    """Vocabulary terms in a taxonomy section, minus the $-prefixed notes."""
    return [k for k in section if not k.startswith("$")]


def check_linkedin(spine_themes: set[str], lint_voice, errors: list[str],
                   warnings: list[str]) -> None:
    """Check the LinkedIn machine: posts, nuggets, and the scouring brief.

    The feed and the podcast are the same account talking to the same person,
    so post copy is linted against the show's avoid list as well as the
    feed-specific one - `lint_voice` is passed in already carrying series.json.
    """
    channel = load_channel()
    bible = channel.channel
    valid_formats = set(channel.formats)
    valid_citation = {k for k in bible.get("citation_status", {}) if not k.startswith("$")}
    known_sources = {k for k in channel.sources if not k.startswith("$")}
    nugget_sources = {k for k in load_channel_sources() if not k.startswith("$")}
    lo, hi = bible["mechanics"]["target_chars"]
    long_max = bible["mechanics"]["long_form_max_chars"]
    accepted_gaps = {k for k in bible.get("spine_gaps_accepted", {}) if not k.startswith("$")}
    tags = bible["mechanics"]["hashtags"]

    feed_avoid = {k: v for k, v in bible.get("voice", {})
                  .get("avoid_patterns", {}).items() if not k.startswith("$")}

    def lint_feed(text: str, where: str) -> None:
        low = text.lower()
        for pattern, reason in feed_avoid.items():
            if pattern in low:
                warnings.append(f"{where}: feed voice - '{pattern}'. {reason}")

    def ascii_check(text: str, where: str, field_name: str) -> None:
        stray = sorted({c for c in text if not c.isascii()})
        if stray:
            warnings.append(
                f"{where}: non-ASCII in {field_name}: {' '.join(repr(c) for c in stray)}"
            )

    nugget_ids = set()
    for n in channel.nuggets:
        where = f"nuggets.json:{n.get('id', '<no id>')}"
        for field_name in NUGGET_FIELDS:
            if not n.get(field_name):
                errors.append(f"{where}: missing required field '{field_name}'")
        if n.get("id") in nugget_ids:
            errors.append(f"{where}: duplicate nugget id")
        nugget_ids.add(n.get("id"))
        if n.get("theme") not in spine_themes:
            errors.append(f"{where}: theme '{n.get('theme')}' is not a spine theme")
        if n.get("source") not in nugget_sources:
            errors.append(f"{where}: source '{n.get('source')}' is not declared in nuggets.json")
        if n.get("citation_status") not in valid_citation:
            errors.append(f"{where}: unknown citation_status '{n.get('citation_status')}'")
        for field_name in ("claim", "use_when", "counterpoint"):
            ascii_check(str(n.get(field_name) or ""), where, field_name)

    seen_posts: set[str] = set()
    covered: set[str] = set()
    for post in channel.posts:
        where = f"{post.get('source_file', '?')}:{post.get('id', '<no id>')}"
        for field_name in POST_FIELDS:
            if not post.get(field_name):
                errors.append(f"{where}: missing required field '{field_name}'")
        if post.get("id") in seen_posts:
            errors.append(f"{where}: duplicate post id")
        seen_posts.add(post.get("id"))

        if post.get("format") not in valid_formats:
            errors.append(f"{where}: unknown format '{post.get('format')}'")
        if post.get("status") not in STATUSES:
            errors.append(f"{where}: unknown status '{post.get('status')}'")
        if post.get("source") not in nugget_sources:
            errors.append(f"{where}: source '{post.get('source')}' is not a known article")

        for theme in post.get("covers", []):
            if theme not in spine_themes:
                errors.append(f"{where}: covers unknown spine theme '{theme}'")
        covered.update(post.get("covers", []))

        for nid in post.get("nuggets", []):
            if nid not in nugget_ids:
                errors.append(f"{where}: draws on unknown nugget '{nid}'")

        # The fold is the whole game on a feed: a hook that gets truncated is a
        # hook nobody read.
        hook = post.get("hook", "")
        if len(hook) > channel.fold_chars:
            errors.append(
                f"{where}: hook is {len(hook)} chars, past the {channel.fold_chars}-char "
                "fold - it will be cut mid-sentence"
            )
        for i, alt in enumerate(post.get("alt_hooks", [])):
            if len(alt) > channel.fold_chars:
                errors.append(
                    f"{where}: alt hook {i + 1} is {len(alt)} chars, past the "
                    f"{channel.fold_chars}-char fold"
                )
            if alt.strip() == hook.strip():
                warnings.append(f"{where}: alt hook {i + 1} is the hook again")

        size = char_count(post)
        if size > channel.max_chars:
            errors.append(f"{where}: {size} chars, over the {channel.max_chars} limit")
        elif post.get("long_form"):
            if size > long_max:
                errors.append(
                    f"{where}: {size} chars, over the {long_max} long-form ceiling - "
                    "that leaves no headroom for an edit before the platform limit"
                )
            elif size <= hi:
                warnings.append(
                    f"{where}: declared long_form but only {size} chars, inside the "
                    f"{lo}-{hi} target - drop the flag"
                )
        elif not lo <= size <= hi:
            warnings.append(f"{where}: {size} chars, outside the {lo}-{hi} target")

        hashtags = post.get("hashtags", [])
        if not tags["min"] <= len(hashtags) <= tags["max"]:
            warnings.append(
                f"{where}: {len(hashtags)} hashtags, outside {tags['min']}-{tags['max']}"
            )
        for tag in hashtags:
            if not tag.startswith("#") or " " in tag:
                errors.append(f"{where}: malformed hashtag '{tag}'")

        for i, reply in enumerate(post.get("replies", [])):
            for field_name in ("expect", "reply"):
                if not reply.get(field_name):
                    errors.append(f"{where}: prepared reply {i + 1} has no '{field_name}'")
            lint_feed(str(reply.get("reply", "")), f"{where} [reply {i + 1}]")
            ascii_check(str(reply.get("reply", "")), where, f"reply {i + 1}")
        ascii_check(str(post.get("first_comment") or ""), where, "first_comment")

        body = render_body(post)
        ascii_check(body, where, "post copy")
        lint_voice(body, where)
        lint_feed(body, where)

        # No number without a checked source. The structural arguments do not
        # need one, and a wrong figure is the mistake this audience remembers.
        if "%" in body or " percent" in body.lower():
            backed = any((channel.nugget(nid) or {}).get("citation_status") == "verified"
                         for nid in post.get("nuggets", []))
            if not backed:
                warnings.append(
                    f"{where}: quotes a figure, but no nugget behind it is 'verified'. "
                    "Open the primary source or cut the number"
                )

        # A body link costs reach and the post has to stand alone anyway.
        if "http://" in body or "https://" in body:
            warnings.append(f"{where}: contains a link - put it in the first comment instead")

    # The feed is supposed to say all four themes over time. A gap is allowed
    # when somebody declared it in channel.json, so that cutting posts leaves a
    # visible hole rather than a silent one.
    for theme in sorted(spine_themes - covered):
        if theme in accepted_gaps:
            warnings.append(
                f"linkedin: no post covers spine theme '{theme}' - declared in "
                "channel.json spine_gaps_accepted, so it is a known hole to fill"
            )
        else:
            errors.append(
                f"linkedin: no post covers spine theme '{theme}' - the feed is supposed to "
                "carry the same four themes as the show. Write one, or declare the gap in "
                "channel.json spine_gaps_accepted"
            )
    for theme in sorted(accepted_gaps & covered):
        warnings.append(
            f"linkedin: spine gap '{theme}' is declared in channel.json but a post now "
            "covers it - remove the declaration"
        )

    ready = channel.ready()
    print(f"{len(channel.posts)} LinkedIn post(s) across {len(channel.packs)} pack(s), "
          f"{len(ready)} ready, {len(channel.nuggets)} nugget(s)")
    per_theme: Counter[str] = Counter()
    for post in channel.posts:
        for theme in post.get("covers", []):
            per_theme[theme] += 1
    print("  covers: " + "  ".join(f"{t}={per_theme[t]}" for t in sorted(spine_themes)))
    weeks_at_one = len(ready)
    print(f"  queue depth: {weeks_at_one} week(s) at one a week, "
          f"{weeks_at_one / 2:.1f} at two")
    print()


def load_channel_sources() -> dict:
    """The source articles declared in nuggets.json, used to check references."""
    import json as _json
    from social import LINKEDIN_DIR
    with (LINKEDIN_DIR / "nuggets.json").open(encoding="utf-8") as fh:
        return _json.load(fh).get("sources", {})



def main() -> int:
    corpus = load()
    errors: list[str] = []
    warnings: list[str] = []

    valid_themes = set(vocab(corpus.taxonomy["theme"]))
    valid_arcs = set(vocab(corpus.taxonomy["arc"]))
    valid_depths = set(vocab(corpus.taxonomy["depth"]))
    valid_industries = set(vocab(corpus.taxonomy["industries"]))
    valid_roles = set(vocab(corpus.taxonomy["roles"]))
    known_slots = set(corpus.industries["$slots"])
    profiled = set(corpus.profiles)

    seen_ids: dict[str, str] = {}
    seen_text: dict[str, str] = {}

    for q in corpus.questions:
        qid = q.get("id", "<no id>")
        where = f"{q.get('source_file', '?')}:{qid}"

        for field_name in REQUIRED_FIELDS:
            if not q.get(field_name):
                errors.append(f"{where}: missing required field '{field_name}'")

        if qid in seen_ids:
            errors.append(f"{where}: duplicate id, also in {seen_ids[qid]}")
        else:
            seen_ids[qid] = q.get("source_file", "?")

        key = normalize(q.get("text", ""))
        if key and key in seen_text:
            warnings.append(f"{where}: text nearly identical to {seen_text[key]}")
        elif key:
            seen_text[key] = qid

        if q.get("theme") not in valid_themes:
            errors.append(f"{where}: unknown theme '{q.get('theme')}'")
        if q.get("arc") not in valid_arcs:
            errors.append(f"{where}: unknown arc '{q.get('arc')}'")
        if q.get("depth") not in valid_depths:
            errors.append(f"{where}: unknown depth '{q.get('depth')}'")

        for slug in q.get("industries", []):
            if slug not in valid_industries:
                errors.append(f"{where}: unknown industry '{slug}'")
            elif slug != "universal" and slug not in profiled:
                errors.append(f"{where}: industry '{slug}' has no profile in industries.json")

        # The corpus is deliberately plain ASCII - it gets read aloud, pasted
        # into email, and printed. Smart quotes and stray glyphs surface here.
        for field_name in ("text", "lands_because", "avoid_if"):
            value = q.get(field_name) or ""
            stray = sorted({c for c in value if not c.isascii()})
            if stray:
                warnings.append(
                    f"{where}: non-ASCII in {field_name}: {' '.join(repr(c) for c in stray)}"
                )

        for slug in q.get("roles", []):
            if slug not in valid_roles:
                errors.append(f"{where}: unknown role '{slug}'")

        # A role-scoped question is for that role in any field, so it should
        # not also be pinned to one industry.
        if q.get("roles") and "universal" not in q.get("industries", []):
            warnings.append(
                f"{where}: scoped to role {q['roles']} and to industries "
                f"{q['industries']} - narrow enough that it will rarely surface"
            )

        for slot in slots_in(q.get("text", "")):
            if slot not in known_slots and slot != "phrase":
                warnings.append(
                    f"{where}: slot '{{{slot}}}' is not in industries.json $slots, "
                    "so no profile will fill it"
                )

        if not q.get("lands_because"):
            warnings.append(f"{where}: no 'lands_because' - the note that tells you why to ask it")

    for slug in valid_industries:
        if slug != "universal" and slug not in profiled:
            errors.append(f"taxonomy lists industry '{slug}' with no profile in industries.json")

    # -------------------------------------------------- series voice and spine
    spine_themes = {t["theme"] for t in corpus.spine}
    avoid = {k: v for k, v in corpus.series.get("voice", {})
             .get("avoid_patterns", {}).items() if not k.startswith("$")}

    def lint_voice(text: str, where: str, exempt=()) -> None:
        """Flag deficit framing. The register is a house rule, so it is checked
        like one rather than left to memory.

        A question may quote a phrase in order to criticise it, which is the
        opposite of using it. Those declare `voice_exempt` so the exception is
        visible in the data rather than hidden in the linter.
        """
        low = text.lower()
        for pattern, reason in avoid.items():
            if pattern in low and pattern not in exempt:
                warnings.append(f"{where}: voice - '{pattern}'. {reason}")

    for q in corpus.questions:
        where = f"{q.get('source_file', '?')}:{q.get('id')}"
        exempt = [p.lower() for p in q.get("voice_exempt", [])]
        lint_voice(q.get("text", ""), where, exempt)
        for pattern in exempt:
            if pattern not in q.get("text", "").lower():
                warnings.append(f"{where}: voice_exempt lists '{pattern}', which is not in the text")

    for theme in spine_themes:
        tagged = [q for q in corpus.questions if theme in q.get("tags", [])]
        if not tagged:
            warnings.append(
                f"spine theme '{theme}' has no questions tagged with it - it will only "
                "be reachable through an arc"
            )

    # ------------------------------------------------------------------ arcs
    known_slots_or_prompt = known_slots | {"phrase"}
    for name, arc in corpus.arcs.items():
        for field_name in ("title", "goal", "house_rules", "anchoring", "beats"):
            if not arc.get(field_name):
                errors.append(f"arc '{name}': missing '{field_name}'")

        declared = {k for k in arc.get("anchoring", {}) if not k.startswith("$")}
        if declared != set(ANCHORING):
            errors.append(
                f"arc '{name}': anchoring levels {sorted(declared)} "
                f"do not match {sorted(ANCHORING)}"
            )

        # Every episode is supposed to touch the spine, so an arc that cannot
        # deliver one of its themes is a defect in the arc, not a preference.
        covered = {t for beat in arc.get("beats", []) for t in beat.get("covers", [])}
        for theme in sorted(spine_themes - covered):
            errors.append(f"arc '{name}': no beat covers spine theme '{theme}'")
        for theme in sorted(covered - spine_themes):
            errors.append(f"arc '{name}': beat covers unknown spine theme '{theme}'")

        seen_beats: set[str] = set()
        for beat in arc.get("beats", []):
            slug = beat.get("beat", "<no slug>")
            where = f"arc '{name}':{slug}"

            for field_name in ARC_BEAT_FIELDS:
                if not beat.get(field_name):
                    errors.append(f"{where}: missing '{field_name}'")

            if slug in seen_beats:
                errors.append(f"{where}: duplicate beat slug")
            seen_beats.add(slug)

            if beat.get("theme") not in valid_themes:
                errors.append(f"{where}: unknown theme '{beat.get('theme')}'")

            flavors = beat.get("flavors", {})
            missing = set(ANCHORING) - set(flavors)
            if missing:
                errors.append(
                    f"{where}: no {', '.join(sorted(missing))} flavor - every beat needs "
                    "all four so the arc survives a guest whose situation changed"
                )
            for level, text in flavors.items():
                if level not in ANCHORING:
                    errors.append(f"{where}: unknown anchoring level '{level}'")
                if not str(text).strip():
                    errors.append(f"{where}: empty '{level}' flavor")
                lint_voice(str(text), f"{where} [{level}]")
                for slot in slots_in(str(text)):
                    if slot not in known_slots_or_prompt:
                        warnings.append(f"{where}: slot '{{{slot}}}' has no profile value")

            texts = [str(t).strip() for t in flavors.values()]
            if len(set(texts)) != len(texts):
                warnings.append(f"{where}: two flavors are identical - one is not pulling its weight")

            for field_name in ("purpose", "listener_payoff", "keep_it_approachable", "if_it_stalls"):
                value = str(beat.get(field_name) or "")
                stray = sorted({c for c in value if not c.isascii()})
                if stray:
                    warnings.append(f"{where}: non-ASCII in {field_name}: {' '.join(map(repr, stray))}")
            for level, text in flavors.items():
                stray = sorted({c for c in str(text) if not c.isascii()})
                if stray:
                    warnings.append(f"{where}: non-ASCII in {level} flavor: {' '.join(map(repr, stray))}")

    check_linkedin(spine_themes, lint_voice, errors, warnings)

    # Coverage: every industry should have its own questions on top of the universal core.
    per_industry: Counter[str] = Counter()
    for q in corpus.questions:
        for slug in q["industries"]:
            per_industry[slug] += 1
    for slug in sorted(profiled):
        if per_industry[slug] == 0:
            warnings.append(f"industry '{slug}' has a profile but no specific questions")

    per_role: Counter[str] = Counter()
    for q in corpus.questions:
        for slug in q.get("roles", []):
            per_role[slug] += 1
    for slug in sorted(valid_roles):
        if per_role[slug] == 0:
            warnings.append(f"role '{slug}' is defined in the taxonomy but has no questions")

    universal = per_industry["universal"]
    # A brief for a guest with no role only draws on the unscoped core, so that
    # is the number worth reporting per industry.
    unscoped = sum(1 for q in corpus.questions
                   if "universal" in q["industries"] and not q.get("roles"))
    by_arc: Counter[str] = Counter(q["arc"] for q in corpus.questions)
    by_depth: Counter[str] = Counter(q["depth"] for q in corpus.questions)
    by_theme: defaultdict[str, int] = defaultdict(int)
    for q in corpus.questions:
        by_theme[q["theme"]] += 1

    print(f"{len(corpus.questions)} questions across {len(corpus.packs)} packs, "
          f"{len(corpus.arcs)} arc(s)")
    print(f"  unscoped core: {unscoped}   role-scoped: {universal - unscoped}"
          f"   industry-specific: {len(corpus.questions) - universal}")
    print("  arc:   " + "  ".join(f"{k}={by_arc[k]}" for k in vocab(corpus.taxonomy["arc"])))
    print("  depth: " + "  ".join(f"{k}={by_depth[k]}" for k in vocab(corpus.taxonomy["depth"])))
    print("  theme: " + "  ".join(f"{k}={by_theme[k]}" for k in sorted(by_theme)))
    print()
    print("Per role (role-scoped questions):")
    for slug in sorted(valid_roles):
        print(f"  {slug:<20} {per_role[slug]:>3}")
    print()
    print("Per industry (own questions + unscoped core available):")
    for slug in sorted(profiled):
        print(f"  {slug:<20} {per_industry[slug]:>3} + {unscoped}")
    print()

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK - no errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
