"""Loading, rendering and scheduling for the LinkedIn content machine.

The podcast corpus lives in corpus.py; this is its sibling for the social
channel. Same rules: standard library only, one definition of what a post is,
and every other script goes through here.

Three data files under data/linkedin/ do the work:

  channel.json   the channel bible - cadence, mechanics of the fold, register
  nuggets.json   claims distilled from the source articles, which are both the
                 raw material for posts and the matching set for a news scan
  sources.json   the weekly scouring brief - where to look, what counts, scoring
  posts/*.json   the posts themselves, one pack per source article

Posts inherit the show's register from data/series.json. That is deliberate:
the feed and the podcast are the same account talking to the same person, so
validate.py lints post copy against the same avoid list as question text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LINKEDIN_DIR = DATA_DIR / "linkedin"
POST_DIR = LINKEDIN_DIR / "posts"

POST_FIELDS = ("id", "title", "format", "status", "covers", "nuggets",
               "hook", "body", "close", "hashtags", "why_it_lands")
NUGGET_FIELDS = ("id", "claim", "theme", "source", "use_when",
                 "counterpoint", "citation_status")

# A post is publishable, still being written, or deliberately parked.
STATUSES = ("ready", "draft", "held")

# Posting days for a one-a-week and a two-a-week cadence. Tuesday and Thursday
# because the audience is at a desk and not yet in Friday.
POST_DAYS = {1: (1,), 2: (1, 3)}


@dataclass
class Channel:
    channel: dict
    nuggets: list[dict]
    sources: dict
    posts: list[dict]
    packs: dict[str, str] = field(default_factory=dict)

    @property
    def mechanics(self) -> dict:
        return self.channel.get("mechanics", {})

    @property
    def max_chars(self) -> int:
        return int(self.mechanics.get("max_chars", 3000))

    @property
    def fold_chars(self) -> int:
        return int(self.mechanics.get("fold_chars", 210))

    @property
    def formats(self) -> list[str]:
        return [k for k in self.channel.get("formats", {}) if not k.startswith("$")]

    def post(self, pid: str) -> dict | None:
        return next((p for p in self.posts if p["id"] == pid), None)

    def nugget(self, nid: str) -> dict | None:
        return next((n for n in self.nuggets if n["id"] == nid), None)

    def ready(self) -> list[dict]:
        return [p for p in self.posts if p.get("status") == "ready"]


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_channel() -> Channel:
    channel = _read_json(LINKEDIN_DIR / "channel.json")
    nuggets_blob = _read_json(LINKEDIN_DIR / "nuggets.json")
    sources = _read_json(LINKEDIN_DIR / "sources.json")

    posts: list[dict] = []
    packs: dict[str, str] = {}
    for path in sorted(POST_DIR.glob("*.json")):
        blob = _read_json(path)
        pack = blob.get("pack", path.stem)
        packs[pack] = blob.get("description", "")
        for post in blob.get("posts", []):
            post["pack"] = pack
            post.setdefault("source", blob.get("source", ""))
            post["source_file"] = str(path.relative_to(DATA_DIR.parent))
            posts.append(post)

    for nugget in nuggets_blob.get("nuggets", []):
        nugget["source_file"] = "data/linkedin/nuggets.json"

    return Channel(channel=channel, nuggets=nuggets_blob.get("nuggets", []),
                   sources=sources, posts=posts, packs=packs)


# ------------------------------------------------------------------ rendering


def render_body(post: dict) -> str:
    """The post exactly as it should be pasted into the composer.

    Paragraphs are separated by a blank line because LinkedIn collapses single
    newlines inconsistently across clients, and a post that renders as a wall
    of text on a phone does not get read.
    """
    parts = [post["hook"].strip()]
    parts.extend(str(p).strip() for p in post.get("body", []))
    if post.get("close"):
        parts.append(post["close"].strip())
    if post.get("hashtags"):
        parts.append(" ".join(post["hashtags"]))
    return "\n\n".join(parts)


def char_count(post: dict) -> int:
    return len(render_body(post))


def above_fold(post: dict, limit: int = 210) -> str:
    """What a scroller sees before deciding whether to tap 'see more'."""
    text = render_body(post)
    if len(text) <= limit:
        return text
    return text[:limit]


def fold_fits(post: dict, limit: int = 210) -> bool:
    """True when the hook survives the fold whole.

    The hook is the unit that has to land, so the test is on the hook rather
    than on wherever the truncation happens to fall.
    """
    return len(post["hook"].strip()) <= limit


# ------------------------------------------------------------------ scheduling


def _next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def posting_dates(start: date, weeks: int, per_week: int) -> list[date]:
    days = POST_DAYS.get(per_week)
    if not days:
        raise ValueError(f"cadence of {per_week} a week is not one of {sorted(POST_DAYS)}")
    # Count a week as used only once it actually yields a slot, so asking for
    # four weeks on a Friday gets four posting weeks rather than three and a
    # bit.
    monday = start - timedelta(days=start.weekday())
    out: list[date] = []
    week = 0
    used = 0
    while used < weeks:
        slots = [monday + timedelta(days=week * 7 + day) for day in days]
        slots = [slot for slot in slots if slot >= start]
        if slots:
            out.extend(slots)
            used += 1
        week += 1
    return out


def order_posts(posts: list[dict]) -> list[dict]:
    """Sequence ready posts so consecutive ones do not repeat themselves.

    Two rules, in priority order: never two posts in a row whose primary spine
    theme is the same, and never two in a row from the same source article.

    After those, take from the theme with the *most* posts still waiting. That
    is what keeps a heavily stocked theme from bunching up at the end - spend
    the plentiful material while there is still something to alternate it with.
    Deterministic, because a schedule that reshuffles overnight is not one.
    """
    remaining = sorted(posts, key=lambda p: p["id"])
    out: list[dict] = []

    def primary(post: dict) -> str:
        return (post.get("covers") or [""])[0]

    while remaining:
        prev = out[-1] if out else None
        left: dict[str, int] = {}
        for post in remaining:
            left[primary(post)] = left.get(primary(post), 0) + 1

        def penalty(post: dict) -> tuple:
            same_theme = bool(prev) and primary(post) == primary(prev)
            same_source = bool(prev) and post.get("source") == prev.get("source")
            return (same_theme, same_source, -left[primary(post)], post["id"])

        pick = min(remaining, key=penalty)
        remaining.remove(pick)
        out.append(pick)
    return out


def build_queue(channel: Channel, weeks: int = 4, per_week: int = 1,
                start: date | None = None) -> list[tuple[date, dict | None]]:
    """Pair posting slots with ready posts.

    Slots past the end of the queue come back with None rather than recycling a
    post. An empty slot is information: it is the signal to run a scouring pass
    or write something new, and hiding it behind a repeat would lose that.
    """
    ordered = order_posts(channel.ready())
    slots = posting_dates(start or date.today(), weeks, per_week)
    return [(slot, ordered[i] if i < len(ordered) else None)
            for i, slot in enumerate(slots)]


# ------------------------------------------------------------------ filtering


def matches(post: dict, *, theme=None, fmt=None, status=None, source=None,
            nugget=None, search=None) -> bool:
    if theme and theme not in post.get("covers", []):
        return False
    if fmt and post.get("format") != fmt:
        return False
    if status and post.get("status") != status:
        return False
    if source and post.get("source") != source:
        return False
    if nugget and nugget not in post.get("nuggets", []):
        return False
    if search:
        needle = search.lower()
        haystack = " ".join([
            post.get("title", ""), post.get("hook", ""),
            " ".join(str(b) for b in post.get("body", [])),
            post.get("close", ""), post.get("why_it_lands", ""),
        ]).lower()
        if needle not in haystack:
            return False
    return True


def filter_posts(channel: Channel, **kwargs) -> list[dict]:
    return [p for p in channel.posts if matches(p, **kwargs)]


def filter_nuggets(channel: Channel, *, theme=None, source=None, search=None) -> list[dict]:
    out = []
    for n in channel.nuggets:
        if theme and n.get("theme") != theme:
            continue
        if source and n.get("source") != source:
            continue
        if search:
            hay = " ".join([n.get("claim", ""), n.get("use_when", ""),
                            n.get("counterpoint", ""),
                            " ".join(n.get("vocabulary", []))]).lower()
            if search.lower() not in hay:
                continue
        out.append(n)
    return out
