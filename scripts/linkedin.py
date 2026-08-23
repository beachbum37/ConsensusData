#!/usr/bin/env python3
"""The LinkedIn content machine: what to post, when, and what to look for.

    python3 scripts/linkedin.py list
    python3 scripts/linkedin.py post li-onboard-01
    python3 scripts/linkedin.py post li-onboard-01 --bare | pbcopy
    python3 scripts/linkedin.py queue --weeks 6 --per-week 2
    python3 scripts/linkedin.py nuggets --theme management-redefined
    python3 scripts/linkedin.py scan --format md
    python3 scripts/linkedin.py channel

`post --bare` prints the post and nothing else, so it can go straight into the
composer. Everything else prints the notes as well: why it lands, what it
risks, and where the claims came from.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import date

from social import (STATUSES, Channel, above_fold, build_queue, char_count,
                    filter_nuggets, filter_posts, fold_fits, load_channel,
                    render_body)

WRAP = textwrap.TextWrapper(width=88, initial_indent="  ", subsequent_indent="  ")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def wrap(text: str) -> str:
    return "\n".join(WRAP.fill(line) if line.strip() else ""
                     for line in str(text).splitlines())


# ---------------------------------------------------------------- rendering


def post_text(channel: Channel, post: dict, notes: bool) -> str:
    body = render_body(post)
    if not notes:
        return body

    fold = channel.fold_chars
    out = [
        f"[{post['id']}] {post['title']}",
        f"  {post['format']} / {post['status']} / {post['pack']}",
        f"  covers: {', '.join(post.get('covers', []))}",
        f"  {char_count(post)} chars (limit {channel.max_chars}), "
        f"hook {len(post['hook'])} (fold at {fold})",
        "",
        "--- paste from here " + "-" * 48,
        body,
        "-" * 68,
        "",
        "Above the fold:",
        wrap(above_fold(post, fold)),
        "",
    ]
    if post.get("why_it_lands"):
        out += ["Why it lands:", wrap(post["why_it_lands"]), ""]
    if post.get("risk"):
        out += ["Careful:", wrap(post["risk"]), ""]
    if post.get("nuggets"):
        out.append("Drawn from:")
        for nid in post["nuggets"]:
            nugget = channel.nugget(nid)
            if nugget:
                out.append(f"  {nid} ({nugget['citation_status']}) {nugget['claim'][:70]}...")
                if nugget.get("verify_before_use"):
                    out.append(wrap(f"  ! {nugget['verify_before_use']}"))
        out.append("")
    return "\n".join(out)


def post_md(channel: Channel, post: dict, notes: bool) -> str:
    out = [f"### {post['title']}  `{post['id']}`", ""]
    if notes:
        out += [f"*{post['format']} - {post['status']} - covers "
                f"{', '.join(post.get('covers', []))} - {char_count(post)} chars*", ""]
    out += ["```", render_body(post), "```", ""]
    if notes:
        if post.get("why_it_lands"):
            out += [f"**Why it lands.** {post['why_it_lands']}", ""]
        if post.get("risk"):
            out += [f"**Careful.** {post['risk']}", ""]
    return "\n".join(out)


def render_posts(channel: Channel, posts: list[dict], fmt: str, notes: bool) -> str:
    if fmt == "json":
        return json.dumps([dict(p, rendered=render_body(p), chars=char_count(p))
                           for p in posts], indent=2)
    if fmt == "md":
        return "\n".join(post_md(channel, p, notes) for p in posts)
    return "\n".join(post_text(channel, p, notes) for p in posts)


# ------------------------------------------------------------------ commands


def cmd_list(channel: Channel, args) -> int:
    posts = filter_posts(channel, theme=args.theme, fmt=args.format_,
                         status=args.status, source=args.source,
                         nugget=args.nugget, search=args.search)
    if args.format == "json":
        print(json.dumps([{k: p[k] for k in ("id", "title", "format", "status",
                                             "covers", "source") if k in p}
                          for p in posts], indent=2))
        return 0
    if not posts:
        print("no posts match")
        return 0
    print(f"{len(posts)} post(s)\n")
    for p in posts:
        flag = "" if fold_fits(p, channel.fold_chars) else "  FOLD"
        print(f"  {p['id']:<16} {p['status']:<6} {p['format']:<11} "
              f"{char_count(p):>5}c  {p['title']}{flag}")
        print(f"  {'':<16} {', '.join(p.get('covers', []))}")
    print()
    return 0


def cmd_post(channel: Channel, args) -> int:
    post = channel.post(args.id)
    if not post:
        die(f"unknown post '{args.id}'. Try: python3 scripts/linkedin.py list")
    print(render_posts(channel, [post], args.format, not args.bare))
    return 0


def cmd_queue(channel: Channel, args) -> int:
    start = date.fromisoformat(args.start) if args.start else date.today()
    try:
        queue = build_queue(channel, weeks=args.weeks, per_week=args.per_week, start=start)
    except ValueError as exc:
        die(str(exc))

    if args.format == "json":
        print(json.dumps([{"date": d.isoformat(),
                           "post": p["id"] if p else None,
                           "title": p["title"] if p else None}
                          for d, p in queue], indent=2))
        return 0

    filled = [p for _, p in queue if p]
    heading = (f"{args.per_week} a week for {args.weeks} week(s) from {start.isoformat()}"
               f"  -  {len(filled)} of {len(queue)} slots filled")
    print(heading)
    print("-" * len(heading))
    for slot, post in queue:
        day = slot.strftime("%a %d %b")
        if not post:
            print(f"  {day}   -- empty. Run a scouring pass: "
                  f"python3 scripts/linkedin.py scan")
            continue
        print(f"  {day}   {post['id']:<16} {post['title']}")
        print(f"  {'':<12} {', '.join(post.get('covers', []))}")
    if len(filled) < len(queue):
        print()
        print(wrap("An empty slot is information, not a bug. It means the queue is "
                   "short and the next post has to be written or found. Publishing a "
                   "weaker one twice is worse than posting once."))
    print()
    return 0


def cmd_nuggets(channel: Channel, args) -> int:
    nuggets = filter_nuggets(channel, theme=args.theme, source=args.source,
                             search=args.search)
    if args.format == "json":
        print(json.dumps(nuggets, indent=2))
        return 0
    if args.format == "md":
        for n in nuggets:
            print(f"### {n['id']}  *{n['theme']}*\n")
            print(f"{n['claim']}\n")
            print(f"- **Use when.** {n['use_when']}")
            print(f"- **Counterpoint.** {n['counterpoint']}")
            print(f"- **Citation.** {n['citation_status']}"
                  + (f" - {n['attribution']}" if n.get("attribution") else ""))
            if n.get("verify_before_use"):
                print(f"- **Verify first.** {n['verify_before_use']}")
            print()
        return 0
    print(f"{len(nuggets)} nugget(s)\n")
    for n in nuggets:
        print(f"[{n['id']}] {n['theme']}  ({n['citation_status']}, from {n['source']})")
        print(wrap(n["claim"]))
        print(wrap(f"use when: {n['use_when']}"))
        print(wrap(f"counterpoint: {n['counterpoint']}"))
        if n.get("verify_before_use"):
            print(wrap(f"! {n['verify_before_use']}"))
        if n.get("vocabulary"):
            print(wrap("words: " + ", ".join(n["vocabulary"])))
        print()
    return 0


def cmd_scan(channel: Channel, args) -> int:
    brief = channel.sources
    if args.format == "json":
        print(json.dumps(brief, indent=2))
        return 0

    md = args.format == "md"
    h1 = "# " if md else ""
    h2 = "## " if md else ""
    bullet = "- " if md else "  - "

    print(f"{h1}Weekly scouring pass")
    print()
    print(brief["what_we_are_looking_for"] if md else wrap(brief["what_we_are_looking_for"]))
    print()
    print(f"{h2}The novelty test - all five have to hold")
    print()
    for key, test in brief["novelty_test"].items():
        if key.startswith("$"):
            continue
        print(f"{bullet}**{key}**: {test}" if md else f"  - {key}: {test}")
    print()
    print(f"{h2}Disqualifiers")
    print()
    for item in brief["disqualifiers"]:
        print(f"{bullet}{item}")
    print()
    print(f"{h2}Where to look")
    print()
    for src in brief["sources"]:
        print(f"{bullet}**{src['name']}** ({src['kind']}): {src['good_for']}"
              if md else f"  - {src['name']} ({src['kind']})")
        if not md:
            print(wrap(f"  {src['good_for']}"))
        print(f"    e.g. {', '.join(src['examples'])}")
        print(f"    watch for: {src['watch_for']}")
        print()
    print(f"{h2}Queries")
    print()
    for group, queries in brief["queries"].items():
        if group.startswith("$") or not isinstance(queries, list):
            continue
        print(f"  {group}:")
        for q in queries:
            print(f"    {q}")
    print()
    print(wrap(brief["queries"]["note"]) if not md else brief["queries"]["note"])
    print()
    print(f"{h2}Scoring - 0 to 3 each, six or better is worth drafting")
    print()
    for key, meaning in brief["scoring"].items():
        if key.startswith("$"):
            continue
        print(f"{bullet}**{key}**: {meaning}" if md else f"  - {key}: {meaning}")
    print()
    print(f"{h2}The pass")
    print()
    for step in brief["workflow"]:
        print(f"{bullet}{step}" if md else f"  {step}")
    print()
    print(f"{h2}What to match against")
    print()
    for n in channel.nuggets:
        print(f"{bullet}`{n['id']}` {n['claim'][:100]}..." if md
              else f"  {n['id']:<26} {n['claim'][:64]}...")
    print()
    return 0


def cmd_channel(channel: Channel, args) -> int:
    bible = channel.channel
    if args.format == "json":
        print(json.dumps(bible, indent=2))
        return 0
    cadence = bible["cadence"]
    lo, hi = cadence["posts_per_week"]
    print("LINKEDIN CHANNEL")
    print()
    print(f"Cadence: {lo} to {hi} posts a week, starting at {cadence['start_at']}.")
    print(wrap(cadence["note"]))
    print(wrap(cadence["scan_rhythm"]))
    print()
    print("Reader:")
    print(wrap(bible["audience"]["who"]))
    print(wrap("They are: " + bible["audience"]["what_they_are_doing_when_they_see_it"]))
    print(wrap("They stop because: " + bible["audience"]["why_they_stop"]))
    print(wrap("They leave when: " + bible["audience"]["what_makes_them_leave"]))
    print()
    print(f"Mechanics: {channel.max_chars} chars max, fold at {channel.fold_chars}, "
          f"target {channel.mechanics['target_chars'][0]}-{channel.mechanics['target_chars'][1]}.")
    print(wrap(channel.mechanics["links"]))
    print()
    print("Shape of a post:")
    for part, rule in bible["shape"].items():
        if part.startswith("$"):
            continue
        print(f"  {part}:")
        print(wrap(f"  {rule}"))
    print()
    print("Formats:")
    for name, meaning in bible["formats"].items():
        if name.startswith("$"):
            continue
        print(f"  {name:<12} {meaning}")
    print()
    print("On a feed, additionally invite:")
    for item in bible["voice"]["invites"]:
        print(wrap(f"  + {item}"))
    print()
    print("And avoid:")
    for item in bible["voice"]["avoids"]:
        print(wrap(f"  - {item}"))
    print()
    print(wrap("Statistics: " + bible["voice"]["statistics"]))
    print()
    print("Never post:")
    for item in bible["do_not_post"]:
        print(wrap(f"  - {item}"))
    print()
    print(wrap("The register itself comes from data/series.json and is shared with "
               "the podcast. validate.py lints post copy against the same avoid list."))
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["text", "md", "json"], default="text")

    ls = sub.add_parser("list", parents=[common], help="the posts in the queue")
    ls.add_argument("--theme", help="a spine theme the post covers")
    ls.add_argument("--format-", dest="format_", metavar="FORMAT",
                    help="argument, reframe, field-note, playbook, question")
    ls.add_argument("--status", choices=list(STATUSES))
    ls.add_argument("--source", help="which article it came from")
    ls.add_argument("--nugget", help="posts drawing on one nugget")
    ls.add_argument("--search")
    ls.set_defaults(func=cmd_list)

    po = sub.add_parser("post", parents=[common], help="one post, ready to paste")
    po.add_argument("id")
    po.add_argument("--bare", action="store_true", help="the post and nothing else")
    po.set_defaults(func=cmd_post)

    q = sub.add_parser("queue", parents=[common], help="a posting schedule")
    q.add_argument("--weeks", type=int, default=4)
    q.add_argument("--per-week", type=int, default=1, choices=[1, 2])
    q.add_argument("--start", help="ISO date, defaults to today")
    q.set_defaults(func=cmd_queue)

    n = sub.add_parser("nuggets", parents=[common],
                       help="the claims distilled from the source articles")
    n.add_argument("--theme")
    n.add_argument("--source")
    n.add_argument("--search")
    n.set_defaults(func=cmd_nuggets)

    s = sub.add_parser("scan", parents=[common],
                       help="the weekly brief for finding new material")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("channel", parents=[common], help="the channel bible")
    c.set_defaults(func=cmd_channel)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(load_channel(), args)


if __name__ == "__main__":
    sys.exit(main())
