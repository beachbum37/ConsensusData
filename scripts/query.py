#!/usr/bin/env python3
"""Retrieval for the question corpus.

    python3 scripts/query.py brief healthcare
    python3 scripts/query.py brief skilled-trades --guest "Dana Reyes" --format md
    python3 scripts/query.py find --theme money --depth probing
    python3 scripts/query.py find --industry law --search billable
    python3 scripts/query.py profile logistics
    python3 scripts/query.py list industries

`brief` is the one to reach for the night before an interview: it prints the
industry profile, then a running order that mixes the universal core with the
industry pack, with vocabulary slots already filled in.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import textwrap

from corpus import Corpus, fill_slots, filter_questions, load

# How many questions of each arc stage a brief aims for, in running order.
BRIEF_SHAPE = [("opener", 2), ("warmup", 2), ("core", 8), ("deep", 5), ("closer", 3)]

WRAP = textwrap.TextWrapper(width=88, initial_indent="  ", subsequent_indent="  ")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def resolve_industry(corpus: Corpus, slug: str) -> dict:
    profile = corpus.profile(slug)
    if not profile:
        die(f"unknown industry '{slug}'. Try: python3 scripts/query.py list industries")
    return profile


# ---------------------------------------------------------------- rendering


def render_text(questions: list[dict], profile: dict | None, show_notes: bool) -> str:
    out = []
    for i, q in enumerate(questions, 1):
        out.append(f"{i:>3}. [{q['id']}] {q['arc']}/{q['depth']}/{q['theme']}")
        out.append(WRAP.fill(fill_slots(q["text"], profile)))
        if show_notes:
            if q.get("lands_because"):
                out.append(WRAP.fill(f"why: {q['lands_because']}"))
            for f in q.get("followups", []):
                out.append(WRAP.fill(f"-> {fill_slots(f, profile)}"))
            if q.get("avoid_if"):
                out.append(WRAP.fill(f"careful: {q['avoid_if']}"))
        out.append("")
    return "\n".join(out)


def render_md(questions: list[dict], profile: dict | None, show_notes: bool) -> str:
    out = []
    for i, q in enumerate(questions, 1):
        out.append(f"{i}. **{fill_slots(q['text'], profile)}**")
        out.append(f"   `{q['id']}` · {q['arc']} · {q['depth']} · {q['theme']}")
        if show_notes:
            if q.get("lands_because"):
                out.append(f"   *Why:* {q['lands_because']}")
            for f in q.get("followups", []):
                out.append(f"   - ↳ {fill_slots(f, profile)}")
            if q.get("avoid_if"):
                out.append(f"   - ⚠ {q['avoid_if']}")
        out.append("")
    return "\n".join(out)


def render(questions: list[dict], profile, fmt: str, show_notes: bool) -> str:
    if fmt == "json":
        return json.dumps(
            [dict(q, text=fill_slots(q["text"], profile)) for q in questions],
            indent=2,
        )
    if fmt == "md":
        return render_md(questions, profile, show_notes)
    return render_text(questions, profile, show_notes)


def render_profile(profile: dict, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(profile, indent=2)
    bullet = "- " if fmt == "md" else "  - "
    head = f"## {profile['label']}" if fmt == "md" else profile["label"].upper()
    out = [head, ""]
    out.append("Status is earned by: " + profile["status_axis"])
    out.append("")
    out.append("You sound like you did the homework when you: " + profile["earns_trust"])
    out.append("")
    out.append("Landmines:" if fmt == "md" else "Landmines:")
    for lm in profile["landmines"]:
        out.append(bullet + lm)
    out.append("")
    out.append("Vocabulary for slotted questions:")
    for slot, word in profile["vocabulary"].items():
        out.append(f"{bullet}{{{slot}}} -> {word}")
    if profile.get("also_called"):
        out.append("")
        out.append("Other native terms worth knowing: " + ", ".join(profile["also_called"]))
    return "\n".join(out)


# ------------------------------------------------------------------ commands


def cmd_find(corpus: Corpus, args) -> int:
    profile = corpus.profile(args.industry) if args.industry else None
    if args.industry and not profile:
        die(f"unknown industry '{args.industry}'")

    questions = filter_questions(
        corpus,
        industry=args.industry,
        theme=args.theme,
        arc=args.arc,
        depth=args.depth,
        tag=args.tag,
        search=args.search,
        universal=not args.no_universal,
    )
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("no questions matched those filters")
        return 1
    if args.format != "json":
        print(f"{len(questions)} question(s)\n")
    print(render(questions, profile, args.format, not args.bare))
    return 0


def cmd_brief(corpus: Corpus, args) -> int:
    profile = resolve_industry(corpus, args.industry)
    rng = random.Random(args.seed)

    def pool(arc: str, industry_only: bool) -> list[dict]:
        qs = [
            q
            for q in corpus.questions
            if q["arc"] == arc
            and (args.industry in q["industries"] if industry_only else "universal" in q["industries"])
        ]
        rng.shuffle(qs)
        return qs

    selected: list[dict] = []
    for arc, want in BRIEF_SHAPE:
        # Industry-specific questions first - they are what makes the interview
        # sound like it was written for this guest - then top up from the core.
        picks = pool(arc, industry_only=True)[: max(1, want // 2)]
        for q in pool(arc, industry_only=False):
            if len(picks) >= want:
                break
            if q not in picks:
                picks.append(q)
        selected.extend(picks)

    if args.no_probing:
        selected = [q for q in selected if q["depth"] != "probing"]

    pivots = [q for q in corpus.questions if q["arc"] == "pivot"]

    title = f"Interview brief: {profile['label']}"
    if args.guest:
        title += f" - {args.guest}"

    if args.format == "json":
        print(json.dumps({
            "industry": args.industry,
            "guest": args.guest,
            "profile": profile,
            "running_order": [dict(q, text=fill_slots(q["text"], profile)) for q in selected],
            "pivots": [dict(q, text=fill_slots(q["text"], profile)) for q in pivots],
        }, indent=2))
        return 0

    rule = "=" * len(title)
    print(title if args.format == "md" else f"{title}\n{rule}")
    if args.format == "md":
        print("=" * 3, "\n")
    print()
    print(render_profile(profile, args.format))
    print("\n" + ("## Running order" if args.format == "md" else "RUNNING ORDER"))
    print()
    print(render(selected, profile, args.format, not args.bare))
    print("## Pivots" if args.format == "md" else "PIVOTS - keep these in view")
    print()
    print(render(pivots, profile, args.format, False))
    return 0


def cmd_profile(corpus: Corpus, args) -> int:
    print(render_profile(resolve_industry(corpus, args.industry), args.format))
    return 0


def cmd_list(corpus: Corpus, args) -> int:
    if args.what == "industries":
        for slug, desc in corpus.taxonomy["industries"].items():
            print(f"  {slug:<20} {desc}")
    elif args.what == "tags":
        tags = sorted({t for q in corpus.questions for t in q.get("tags", [])})
        for t in tags:
            n = sum(1 for q in corpus.questions if t in q.get("tags", []))
            print(f"  {t:<24} {n}")
    elif args.what == "packs":
        for pack, desc in corpus.packs.items():
            n = sum(1 for q in corpus.questions if q["pack"] == pack)
            print(f"  {pack} ({n})")
            print(WRAP.fill(desc))
            print()
    else:  # themes, arcs, depths
        key = {"themes": "theme", "arcs": "arc", "depths": "depth"}[args.what]
        for name, desc in corpus.taxonomy[key].items():
            if name.startswith("$"):
                continue
            print(f"  {name:<12} {desc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["text", "md", "json"], default="text")
    common.add_argument("--bare", action="store_true", help="questions only, no notes or followups")

    f = sub.add_parser("find", parents=[common], help="filter the corpus")
    f.add_argument("--industry")
    f.add_argument("--theme")
    f.add_argument("--arc")
    f.add_argument("--depth")
    f.add_argument("--tag")
    f.add_argument("--search", help="substring match on text, notes, followups and tags")
    f.add_argument("--limit", type=int)
    f.add_argument("--no-universal", action="store_true",
                   help="with --industry, exclude the universal core")
    f.set_defaults(func=cmd_find)

    b = sub.add_parser("brief", parents=[common], help="build a running order for one interview")
    b.add_argument("industry")
    b.add_argument("--guest")
    b.add_argument("--seed", type=int, default=0, help="change for a different draw")
    b.add_argument("--no-probing", action="store_true",
                   help="drop the probing questions - for a guarded or first-time guest")
    b.set_defaults(func=cmd_brief)

    pr = sub.add_parser("profile", parents=[common], help="show one industry profile")
    pr.add_argument("industry")
    pr.set_defaults(func=cmd_profile)

    ls = sub.add_parser("list", help="list the controlled vocabularies")
    ls.add_argument("what", choices=["industries", "themes", "arcs", "depths", "tags", "packs"])
    ls.set_defaults(func=cmd_list)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(load(), args)


if __name__ == "__main__":
    sys.exit(main())
