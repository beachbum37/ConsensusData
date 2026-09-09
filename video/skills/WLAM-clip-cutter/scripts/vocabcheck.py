#!/usr/bin/env python3
"""
What the vocabulary ACTUALLY does, measured over a real corpus.

    python3 vocabcheck.py fires              # every term by how often it wins a group
    python3 vocabcheck.py fires --top 40
    python3 vocabcheck.py save <name>        # snapshot the current winners
    python3 vocabcheck.py diff <name>        # what a code change displaced, group by group

WHY THIS EXISTS. Until now the only number that was easy to get about EXPAND was
its SHAPE - 11,864 keys over 2,189 terms, and which terms serve the most words.
That number is nearly useless: measured over the delivered corpus, the
correlation between a term's cohort size and how often it actually wins a group
is r-squared 0.079. Cohort size explains 8% of what a viewer sees.

A whole diagnosis was built on cohort size and had to be thrown away. It targeted
`signing contract documents pen` (89 words), `courthouse columns` (61) and
`copper ore mine` (52) - and across 76 authored slates those three have delivered
ZERO inserts between them, while `man thinking looking out window`, with a cohort
of twelve, fires more than all of them together. Sorting by the easy number put
the wrong five things on the table.

The other half of why: SKILL.md's rule for growing the vocabulary is "adding a
word is not free; test it against the phrase it lives in", and it records eleven
phrases where a new key outranked the right one. That test needed a harness and
did not have one, so it was done by reading. `save` then `diff` is the harness:
it replays the ranking over the whole corpus and prints every group whose winner
changed, so a one-line edit to the sort key is a measurement rather than an
argument.

WHAT IT REPLAYS. The hit -> group -> rank walk out of broll.candidates(), against
delivered caption files rather than live audio - no whisper, no network, seconds
not minutes. It is deliberately the SAME sort key object, imported from broll, so
this cannot drift from the thing it measures.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("WLAM_WORK", str(Path(__file__).parent))

import broll  # noqa: E402
import qmclip as q  # noqa: E402

SNAP = Path(__file__).parent / ".vocabcheck"
GROUP_WINDOW = getattr(broll, "GROUP_WINDOW", 3.0)

# MEMOISED, because the predicates are per-WORD and the corpus is 300k words.
# _is_concrete falls through to `any(_hint_matches(h, c) for h in CONCRETE_HINTS)`
# for every word that is not in EXPAND, which is a scan of the whole hint list -
# so the honest walk is billions of comparisons and takes longer than a render.
# The vocabulary does not change inside a run, so one cache makes it seconds.
from functools import lru_cache


@lru_cache(maxsize=None)
def _concrete(word: str) -> bool:
    return broll._is_concrete(word)


@lru_cache(maxsize=None)
def _entity(word: str, prev: str, blind: bool = False) -> bool:
    return broll._is_entity(word, prev, blind)


@lru_cache(maxsize=None)
def _query(term: str) -> str:
    return broll.query_for(term)


@lru_cache(maxsize=None)
def _bigram_live(bg: str) -> bool:
    if hasattr(broll, "_bigram_is_subject"):
        return broll._bigram_is_subject(bg)
    return bg in broll._MULTI_HINTS


def corpus() -> list[tuple[str, list]]:
    """(name, words) for every delivered caption file we can find."""
    roots = [Path.home() / "Desktop"]
    out = []
    seen = set()
    for root in roots:
        for f in sorted(root.rglob("captions/*.srt")):
            if f.name in seen:
                continue
            seen.add(f.name)
            words = parse_srt(f.read_text(errors="ignore"))
            if len(words) > 40:
                out.append((f.name, words))
    return out


def parse_srt(txt: str) -> list:
    """Cue-level .srt -> word list with interpolated times.

    Word-level timing is not in the file, so a cue's words are spread evenly
    across it. That is exact enough for THIS question: the grouping window is
    3 seconds and a cue is about two, so a word lands in the right group even
    when it is a tenth out inside it.
    """
    Word = q.Word
    out = []
    pat = re.compile(
        r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)\s*\n(.+?)"
        r"(?=\n\s*\n|\Z)", re.S)
    for m in pat.finditer(txt):
        a = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000
        b = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + int(m[8]) / 1000
        toks = [t for t in re.split(r"\s+", " ".join(m[9].split("\n"))) if t]
        if not toks:
            continue
        step = max(0.05, (b - a) / len(toks))
        for i, t in enumerate(toks):
            out.append(Word(a + i * step, a + (i + 1) * step, t))
    return out


def walk(words: list) -> list[tuple[float, str, list[str]]]:
    """The hit -> group -> winner walk, using broll's OWN predicates and key.

    Returns (time, winning term, every term that was in the group).
    """
    hits = []
    i = 0
    blind = broll.caps_blind(words) if hasattr(broll, "caps_blind") else False
    while i < len(words):
        w = words[i]
        prev = words[i - 1].text if i else ""
        ent = _entity(w.text, prev, blind)
        if ent and i + 1 < len(words) and _entity(words[i + 1].text, w.text, blind):
            hits.append((w.start, f"{q.split_token(w.text)[0]} "
                                  f"{q.split_token(words[i + 1].text)[0]}"))
            i += 2
            continue
        if i + 1 < len(words):
            bg = (f"{q.split_token(w.text)[0]} "
                  f"{q.split_token(words[i + 1].text)[0]}").lower()
            if _bigram_live(bg):
                hits.append((w.start, bg))
                i += 2
                continue
        if ent or _concrete(w.text):
            hits.append((w.start, q.split_token(w.text)[0]))
        i += 1

    groups = []
    for t, term in hits:
        if groups and t - groups[-1][0][0] <= GROUP_WINDOW:
            groups[-1].append((t, term))
        else:
            groups.append([(t, term)])

    out = []
    for g in groups:
        terms = [term for _t, term in g]
        best = sorted(terms, key=broll._rank_key)[0]
        out.append((g[0][0], best, terms))
    return out


def collect() -> dict:
    """{file: [(time, winner, group)]} over the whole corpus."""
    return {name: walk(words) for name, words in corpus()}


def cmd_fires(argv: list[str]) -> None:
    import collections
    top = 30
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])
    data = collect()
    wins = collections.Counter()
    groups = 0
    for rows in data.values():
        for _t, best, _terms in rows:
            wins[_query(best)] += 1
            groups += 1
    delivered = delivered_terms()
    print(f"\n  {len(data)} clips, {groups} groups\n")
    print(f"  {'fires':>6} {'%':>6} {'cohort':>7} {'shipped':>8}  term")
    back = cohorts()
    for term, n in wins.most_common(top):
        print(f"  {n:>6} {100 * n / max(1, groups):>5.1f}% {len(back.get(term, [])):>7} "
              f"{delivered.get(term, 0):>8}  {term}")
    print(f"\n  cohort = how many EXPAND words point here (the number that does NOT "
          f"predict this)\n  shipped = inserts actually delivered on this term, "
          f"across every slate on disk\n")


def cohorts() -> dict:
    import collections
    back = collections.defaultdict(list)
    for w, t in broll.EXPAND.items():
        back[t].append(w)
    return back


def delivered_terms() -> dict:
    import collections
    c = collections.Counter()
    for f in (Path.home() / "Desktop").rglob("slate.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        cs = d.get("clips") if isinstance(d, dict) else d
        if not isinstance(cs, list):
            continue
        for clip in cs:
            for b in clip.get("broll") or []:
                if b.get("term"):
                    c[b["term"]] += 1
    return c


def cmd_save(argv: list[str]) -> None:
    name = argv[0] if argv else "base"
    SNAP.mkdir(exist_ok=True)
    data = collect()
    flat = {f"{k}@{t:.2f}": best for k, rows in data.items() for t, best, _ in rows}
    (SNAP / f"{name}.json").write_text(json.dumps(flat, indent=0))
    print(f"  saved {len(flat)} group winners as {name}")


def cmd_diff(argv: list[str]) -> None:
    name = argv[0] if argv else "base"
    p = SNAP / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"no snapshot {name!r} - run: vocabcheck.py save {name}")
    was = json.loads(p.read_text())
    data = collect()
    now = {f"{k}@{t:.2f}": best for k, rows in data.items() for t, best, _ in rows}
    gone = [k for k in was if k not in now]
    new = [k for k in now if k not in was]
    moved = [(k, was[k], now[k]) for k in was if k in now and was[k] != now[k]]
    print(f"\n  {len(was)} groups before, {len(now)} after")
    print(f"  {len(moved)} winners DISPLACED, {len(new)} new groups, {len(gone)} lost\n")
    for k, a, b in moved[:60]:
        clip = k.split("@")[0][:40]
        print(f"    {a:<28} -> {b:<28}  {clip}")
    if len(moved) > 60:
        print(f"    ... and {len(moved) - 60} more")
    if new:
        print(f"\n  NEW groups (a word became a subject that was not one before):")
        import collections
        c = collections.Counter(now[k] for k in new)
        for term, n in c.most_common(20):
            print(f"    {n:>4}  {term}")
    print()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fires"
    rest = sys.argv[2:]
    {"fires": cmd_fires, "save": cmd_save, "diff": cmd_diff}.get(
        cmd, lambda a: (_ for _ in ()).throw(SystemExit(__doc__)))(rest)
