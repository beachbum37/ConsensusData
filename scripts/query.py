#!/usr/bin/env python3
"""Retrieval for the question corpus.

    python3 scripts/query.py brief healthcare
    python3 scripts/query.py brief logistics --role middle-manager
    python3 scripts/query.py brief skilled-trades --guest "Dana Reyes" --format md
    python3 scripts/query.py find --theme money --depth probing
    python3 scripts/query.py find --role ai-leader --no-general
    python3 scripts/query.py profile logistics
    python3 scripts/query.py arc ai-workflow-partner --industry healthcare
    python3 scripts/query.py list roles

`brief` is the one to reach for the night before an interview: it prints the
industry profile, then a running order blending the industry pack, the role
pack and the universal core, with vocabulary slots already filled in.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap

from corpus import ANCHORING, Corpus, build_brief, fill_slots, filter_questions, load

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
        role=args.role,
        theme=args.theme,
        arc=args.arc,
        depth=args.depth,
        tag=args.tag,
        search=args.search,
        universal=not args.no_universal,
        general=not args.no_general,
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

    role = args.role
    if role and role not in corpus.taxonomy["roles"]:
        die(f"unknown role '{role}'. Try: python3 scripts/query.py list roles")

    selected = build_brief(corpus, args.industry, role, seed=args.seed)

    if args.no_probing:
        selected = [q for q in selected if q["depth"] != "probing"]

    pivots = [q for q in corpus.questions if q["arc"] == "pivot"]

    title = f"Interview brief: {profile['label']}"
    if role:
        title += f" / {role}"
    if args.guest:
        title += f" - {args.guest}"

    if args.format == "json":
        print(json.dumps({
            "industry": args.industry,
            "role": role,
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


def cmd_arc(corpus: Corpus, args) -> int:
    if not args.arc:
        for name, blob in corpus.arcs.items():
            print(f"  {name}\n{WRAP.fill(blob['goal'])}\n")
        return 0

    arc = corpus.arcs.get(args.arc)
    if not arc:
        die(f"unknown arc '{args.arc}'. Try: python3 scripts/query.py arc")

    profile = corpus.profile(args.industry) if args.industry else None
    if args.industry and not profile:
        die(f"unknown industry '{args.industry}'")

    pick = args.anchoring
    fill = lambda text: fill_slots(text, profile)

    if args.format == "json":
        beats = []
        for beat in arc["beats"]:
            flavors = {k: fill(v) for k, v in beat["flavors"].items()}
            beats.append(dict(beat,
                              flavors=flavors,
                              ask=flavors[pick] if pick else None,
                              followups=[fill(f) for f in beat.get("followups", [])],
                              if_it_stalls=fill(beat.get("if_it_stalls", ""))))
        print(json.dumps(dict(arc, beats=beats, anchoring_used=pick,
                              industry=args.industry, guest=args.guest), indent=2))
        return 0

    md = args.format == "md"
    head = f"{arc['title']}"
    if args.guest:
        head += f" - {args.guest}"
    print(f"# {head}" if md else f"{head}\n{'=' * len(head)}")
    print()
    print(WRAP.fill(arc["goal"]) if not md else f"**Goal.** {arc['goal']}\n")
    print()

    print("## House rules" if md else "HOUSE RULES")
    print()
    for rule in arc["house_rules"]:
        print(("- " + rule) if md else WRAP.fill("- " + rule))
    print()

    if pick:
        note = arc["anchoring"][pick]
        print((f"**Anchoring: {pick}.** {note}\n") if md else
              f"ANCHORING: {pick}\n{WRAP.fill(note)}\n")
    else:
        print("## Anchoring" if md else "ANCHORING - pick a flavor live, per beat")
        print()
        for level in ANCHORING:
            text = f"{level}: {arc['anchoring'][level]}"
            print(("- " + text) if md else WRAP.fill("- " + text))
        print()

    if profile:
        print(render_profile(profile, args.format))
        print()

    print("## Beats" if md else "BEATS")
    print()
    for i, beat in enumerate(arc["beats"], 1):
        title = f"{i}. {beat['title']}"
        print(f"### {title}" if md else f"{title}  [{beat['beat']} / {beat['theme']}]")
        if md:
            print(f"`{beat['beat']}` · {beat['theme']}\n")

        if pick:
            ask = fill(beat["flavors"][pick])
            print((f"**{ask}**\n") if md else WRAP.fill(ask))
        else:
            for level in ANCHORING:
                line = f"[{level}] {fill(beat['flavors'][level])}"
                print(("- " + line) if md else WRAP.fill(line))
        print()

        for label, value in (("Purpose", beat["purpose"]),
                             ("Listener takes away", beat["listener_payoff"]),
                             ("Keep it approachable", beat["keep_it_approachable"])):
            print((f"*{label}.* {value}\n") if md else WRAP.fill(f"{label}: {value}"))

        for f in beat.get("followups", []):
            print((f"- ↳ {fill(f)}") if md else WRAP.fill(f"-> {fill(f)}"))
        if beat.get("if_it_stalls"):
            text = f"If it stalls: {fill(beat['if_it_stalls'])}"
            print((f"- {text}") if md else WRAP.fill(text))
        print()
    return 0


def cmd_profile(corpus: Corpus, args) -> int:
    print(render_profile(resolve_industry(corpus, args.industry), args.format))
    return 0


def cmd_list(corpus: Corpus, args) -> int:
    if args.what in ("industries", "roles"):
        for slug, desc in corpus.taxonomy[args.what].items():
            if slug.startswith("$"):
                continue
            n = sum(1 for q in corpus.questions
                    if slug in (q["industries"] if args.what == "industries" else q.get("roles", [])))
            print(f"  {slug:<20} {n:>3}  {desc}")
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
    f.add_argument("--role", help="middle-manager, ai-leader")
    f.add_argument("--theme")
    f.add_argument("--arc")
    f.add_argument("--depth")
    f.add_argument("--tag")
    f.add_argument("--search", help="substring match on text, notes, followups and tags")
    f.add_argument("--limit", type=int)
    f.add_argument("--no-universal", action="store_true",
                   help="with --industry, exclude the universal core")
    f.add_argument("--no-general", action="store_true",
                   help="with --role, exclude the role-agnostic questions")
    f.set_defaults(func=cmd_find)

    b = sub.add_parser("brief", parents=[common], help="build a running order for one interview")
    b.add_argument("industry")
    b.add_argument("--role", help="middle-manager, ai-leader")
    b.add_argument("--guest")
    b.add_argument("--seed", type=int, default=0, help="change for a different draw")
    b.add_argument("--no-probing", action="store_true",
                   help="drop the probing questions - for a guarded or first-time guest")
    b.set_defaults(func=cmd_brief)

    a = sub.add_parser("arc", parents=[common],
                       help="a themed interview arc with a flavor of each question per anchoring level")
    a.add_argument("arc", nargs="?", help="omit to list the available arcs")
    a.add_argument("--anchoring", choices=list(ANCHORING),
                   help="print one flavor per beat as a clean read-aloud script. "
                        "Omit to print all four and choose live")
    a.add_argument("--industry", help="fill vocabulary slots and prepend the industry profile")
    a.add_argument("--guest")
    a.set_defaults(func=cmd_arc)

    pr = sub.add_parser("profile", parents=[common], help="show one industry profile")
    pr.add_argument("industry")
    pr.set_defaults(func=cmd_profile)

    ls = sub.add_parser("list", help="list the controlled vocabularies")
    ls.add_argument("what", choices=["industries", "roles", "themes", "arcs", "depths", "tags", "packs"])
    ls.set_defaults(func=cmd_list)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(load(), args)


if __name__ == "__main__":
    sys.exit(main())
