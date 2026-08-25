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

from corpus import ANCHORING, APERTURE, REQUIRED_FIELDS, load, slots_in

ARC_BEAT_FIELDS = ("beat", "title", "theme", "purpose", "listener_payoff",
                   "keep_it_approachable", "flavors")


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def vocab(section: dict) -> list[str]:
    """Vocabulary terms in a taxonomy section, minus the $-prefixed notes."""
    return [k for k in section if not k.startswith("$")]


def main() -> int:
    corpus = load()
    errors: list[str] = []
    warnings: list[str] = []

    valid_themes = set(vocab(corpus.taxonomy["theme"]))
    valid_arcs = set(vocab(corpus.taxonomy["arc"]))
    valid_depths = set(vocab(corpus.taxonomy["depth"]))
    valid_industries = set(vocab(corpus.taxonomy["industries"]))
    valid_roles = set(vocab(corpus.taxonomy["roles"]))
    valid_settings = set(vocab(corpus.taxonomy.get("settings", {})))
    # {industry} is derived from each profile's label rather than declared.
    known_slots = set(corpus.industries["$slots"]) | {"industry"}
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

        aperture = q.get("aperture", "narrow")
        if aperture not in APERTURE:
            errors.append(f"{where}: unknown aperture '{aperture}'")
        if aperture == "wide" and not q.get("narrow_to"):
            # A wide question without the follow-up that lands it is just an
            # invitation to a talking point, which is what the rest of the
            # corpus exists to avoid.
            errors.append(
                f"{where}: aperture 'wide' needs a 'narrow_to' - the follow-up that "
                "drives the answer to one specific instance"
            )
        if aperture != "wide" and q.get("narrow_to"):
            warnings.append(f"{where}: has narrow_to but is not a wide question")

        for slug in q.get("settings", []):
            if slug not in valid_settings:
                errors.append(f"{where}: unknown setting '{slug}'")
        if len(q.get("settings", [])) == len(valid_settings) and valid_settings:
            warnings.append(
                f"{where}: lists every setting, which is the same as listing none"
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
    wide = sum(1 for q in corpus.questions if q.get("aperture") == "wide")
    print(f"  unscoped core: {unscoped}   role-scoped: {universal - unscoped}"
          f"   industry-specific: {len(corpus.questions) - universal}"
          f"   (of which wide-aperture: {wide})")
    print("  arc:   " + "  ".join(f"{k}={by_arc[k]}" for k in vocab(corpus.taxonomy["arc"])))
    print("  depth: " + "  ".join(f"{k}={by_depth[k]}" for k in vocab(corpus.taxonomy["depth"])))
    print("  theme: " + "  ".join(f"{k}={by_theme[k]}" for k in sorted(by_theme)))
    print()
    per_setting: Counter[str] = Counter()
    for q in corpus.questions:
        for slug in q.get("settings", []):
            per_setting[slug] += 1
    if valid_settings:
        print("Per setting (setting-scoped questions):")
        for slug in sorted(valid_settings):
            print(f"  {slug:<20} {per_setting[slug]:>3}")
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
