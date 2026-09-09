#!/usr/bin/env python3
"""
Merge agent vocabulary output into one validated set of additions.

NOTHING IS TRUSTED. Every entry is checked against the same rules the agents
were given, because a rule stated in a prompt is a request and a rule enforced
here is a guarantee - and this vocabulary decides what appears on screen while
a real person is talking.

    python3 merge.py <glob>            report only
    python3 merge.py <glob> --write    write additions.json
"""
from __future__ import annotations

import json
import re
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import broll as b            # noqa: E402
import qmclip as q           # noqa: E402

HERE = Path(os.environ.get("WLAM_VOCAB") or os.environ.get("QM_VOCAB") or Path(__file__).resolve().parent)

WORD_OK = re.compile(r"^[a-z0-9][a-z0-9'\- .]{1,40}$")  # a caliber ('155mm') or an account ('403b') legitimately starts with a digit
TERM_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]{3,70}$")
MIN_TERM_WORDS, MAX_TERM_WORDS = 2, 6

EXISTING = {
    "expand": set(b.EXPAND),
    "people": set(b.PEOPLE),
    "abstract": set(b.ABSTRACT),
    "not_a_picture": set(b.NOT_A_PICTURE),
}
ALL_KNOWN = set().union(*EXISTING.values()) | set(q.STOP)
PICTURES = set(b.EXPAND.values())

# A person's SURNAME must never appear inside a search term - the library would
# then assert that a stock photo IS that person. Built from the LAST token of
# each PEOPLE key only, not every token: a key like "bill ackman", "chair
# powell" or "speaker johnson" has its identifying surname LAST, and pulling
# every token flagged "medical bill paperwork calculator" and "oncology
# chemotherapy treatment chair" as containing a person's name when "bill" and
# "chair" were doing ordinary work (an invoice, a piece of furniture) - the
# false positives were the first-name/title half of a compound key, never the
# risky half.
NAME_TOKENS = set()
for k in b.PEOPLE:
    parts = k.split()
    t = re.sub(r"[^a-z]", "", parts[-1].lower())
    if len(t) > 3:
        NAME_TOKENS.add(t)
# words that are ordinary English as well as surnames - not a violation
NAME_TOKENS -= {"green", "brown", "white", "black", "gray", "grey", "hunt",
                "banks", "bell", "cook", "fields", "ford", "price", "rice",
                "wood", "young", "cash", "long", "short", "moore", "power",
                "powers", "bush", "carson", "gates", "graham", "hall", "king",
                "lynch", "may", "mason", "may", "reed", "rose", "sharp",
                "stone", "wells", "west", "wolf", "york"}


# CONTEXT BEATS A DOMAIN BRIEF. Two waves produced this vocabulary: one read a
# REAL SENTENCE this show actually used the word in (out_*.json), the other
# worked from a topic brief with no evidence the word is even said that way
# (dom_*.json). Checked against the transcripts by hand for every identity
# collision, the context-grounded call was right or safely cautious every
# single time and the domain guess was wrong every time they disagreed:
#
#   cramer   -> the corpus says SENATOR Kevin Cramer, never Jim Cramer.
#               dom guessed the CNBC host; out correctly abstained.
#   newton   -> "newton METER chip" (an Apple keynote unit of force).
#               dom guessed Isaac Newton; out correctly abstained.
#   newsom   -> the corpus says "Jeremy Newsom", a different person.
#               dom guessed Gavin Newsom; out correctly abstained.
#   zell     -> the corpus lists it beside other fintech APP NAMES - this
#               is "Zelle" the payment app mistranscribed, not Sam Zell.
#               dom guessed the real-estate billionaire; out abstained.
#
# So when a word has an out_*.json classification, IT WINS outright.
RESOLVE = {
    # 'diamond' is ASR mangling "Dimon" in ALL-CAPS hearing transcripts
    # ("MR. DIAMOND", "IF JAMIE DIAMOND") - real, but too risky to ship: the
    # bare word is also an ordinary English noun (a gem, a baseball field),
    # and asserting Jamie Dimon's identity every time somebody says "diamond
    # ring" is a worse defect than missing the hearing reference.
    "diamond": ("expand", "rough diamonds gemstones closeup"),
    # 'ford' is both the carmaker and, confirmed in the corpus, Ontario
    # Premier Doug Ford ("Ontario's Premier Doug Ford just said"). The
    # BARE surname keeps the common/company sense; the person is preserved
    # under his full name below instead of colliding with it.
    "ford": ("expand", "car factory assembly line robots"),
    # No out_*.json classification existed for these four - both proposals
    # were context-free domain guesses, so decided on likelihood and risk:
    "bismarck": ("expand", "state capitol dome exterior"),        # ND capital
                                                                    # roundups
                                                                    # are far more
                                                                    # likely than
                                                                    # the 19th-c.
                                                                    # chancellor
    "bullock": ("people", ["Michele Bullock", "sydney opera house australia"]),
                                                                    # RBA Governor,
                                                                    # active
                                                                    # newsmaker;
                                                                    # "a bullock"
                                                                    # (an ox) is
                                                                    # archaic in
                                                                    # modern speech
    "galileo": ("people", ["Galileo Galilei", "observatory dome telescope night"]),
                                                                    # unambiguous,
                                                                    # low collision
    "pollock": ("expand", "fishmonger fresh fish market ice"),    # a commodity/
                                                                    # seafood angle
                                                                    # fits a
                                                                    # markets show;
                                                                    # Jackson
                                                                    # Pollock is
                                                                    # the narrower
                                                                    # topic
}
EXTRA_PEOPLE = {
    # The person is real and worth having; the bare surname just cannot be
    # the key because it collides with something more common. Filed under
    # the full name instead, which is how a title card would read anyway.
    "doug ford": ["Doug Ford", "toronto ontario cn tower skyline"],
}


def load(paths: list[Path]) -> tuple[dict, list[str]]:
    """Every agent file. Context (out_*) beats a domain guess (dom_*)."""
    out = {"expand": {}, "people": {}, "abstract": set(), "not_a_picture": set()}
    owner: dict[str, tuple[str, int]] = {}     # word -> (category, priority)
    bad: list[str] = []

    def priority(p: Path) -> int:
        return 2 if p.name.startswith("out_") else 1    # higher wins a conflict

    def place(w: str, key: str, val, pr: int, source: str) -> None:
        cur = owner.get(w)
        if cur is None:
            owner[w] = (key, pr)
            if key in ("expand", "people"):
                out[key][w] = val
            else:
                out[key].add(w)
            return
        cur_key, cur_pr = cur
        if cur_key == key:
            # SAME DESTINATION, POSSIBLY A DIFFERENT VALUE. Two agents can
            # both say "expand" and still propose different search terms -
            # this missed that case entirely and kept whichever file sorted
            # first alphabetically, which is how 'schwab' kept a stale
            # dom_003 term after a higher-priority out_017 term should have
            # won. Only actually overwrite when the value differs and the
            # new source outranks the one already recorded.
            if pr > cur_pr and out[key].get(w) != val:
                owner[w] = (key, pr)
                out[key][w] = val
            return
        if pr > cur_pr:
            # a higher-priority source overrides what a lower one wrote
            for k in ("expand", "people"):
                out[k].pop(w, None)
            for k in ("abstract", "not_a_picture"):
                out[k].discard(w)
            owner[w] = (key, pr)
            if key in ("expand", "people"):
                out[key][w] = val
            else:
                out[key].add(w)
        elif pr == cur_pr:
            bad.append(f"{w!r}: claimed by both {cur_key} and {key} at equal "
                      f"priority ({source})")

    for p in sorted(paths):
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError) as e:
            bad.append(f"{p.name}: unreadable ({e})")
            continue
        pr = priority(p)
        for key in ("expand", "people"):
            for w, v in (d.get(key) or {}).items():
                place(str(w).strip().lower(), key, v, pr, p.name)
        for key in ("abstract", "not_a_picture"):
            for w in (d.get(key) or []):
                place(str(w).strip().lower(), key, None, pr, p.name)

    # HAND OVERRIDES WIN OVER EVERYTHING, including out_*.json - they exist
    # because the general rule was checked against real evidence and found
    # wanting for these specific words. See the comment above RESOLVE.
    for w, (key, val) in RESOLVE.items():
        for k in ("expand", "people"):
            out[k].pop(w, None)
        for k in ("abstract", "not_a_picture"):
            out[k].discard(w)
        if key in ("expand", "people"):
            out[key][w] = val
        else:
            out[key].add(w)
    for w, v in EXTRA_PEOPLE.items():
        out["people"].setdefault(w, v)

    return out, bad


def check_term(term: str) -> str | None:
    """Why this search term is unusable, or None."""
    t = str(term).strip()
    if not TERM_OK.match(t):
        return "not a plain search string"
    n = len(t.split())
    if not (MIN_TERM_WORDS <= n <= MAX_TERM_WORDS):
        return f"{n} words (house style is {MIN_TERM_WORDS}-{MAX_TERM_WORDS})"
    low = t.lower()
    hit = next((tok for tok in re.findall(r"[a-z]+", low) if tok in NAME_TOKENS), None)
    if hit:
        return f"contains a person's name ({hit!r})"
    return None


def sacred_violation(word: str, term: str) -> bool:
    """
    Religious picture answering a secular word. See broll._sacred.

    An EXACT REUSE of a picture already shipped is not a new pairing to
    scrutinise - it is the pairing this codebase already ships. "Brazil" and
    "Brazilian" already point at the Christ Redeemer photo as Brazil's own
    visual identity; a new word like "reais" or "Brazilian real" reusing that
    SAME string is the same established call, not a fresh one. The rule this
    guards against is a NEW religious picture invented for an unrelated
    secular word ("mystery" -> a cemetery angel), which only exact reuse of an
    EXISTING term cannot be.
    """
    if term in PICTURES:
        return False
    try:
        return bool(b._sacred(term, word))
    except Exception:                                            # noqa: BLE001
        return False


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pats = args if args else ["out_*.json", "dom_*.json"]
    paths = sorted({p for pat in pats for p in HERE.glob(pat)})
    if not paths:
        raise SystemExit(f"no files matching {pats}")
    print(f"{len(paths)} agent file(s)\n")

    got, conflicts = load(paths)
    rejected: list[str] = []
    add = {"expand": {}, "people": {}, "abstract": [], "not_a_picture": []}

    # ---- expand
    for w, term in got["expand"].items():
        if not WORD_OK.match(w):
            rejected.append(f"expand {w!r}: not a usable key")
            continue
        if w in ALL_KNOWN:
            continue                                  # already classified
        why = check_term(term)
        if why:
            rejected.append(f"expand {w!r} -> {term!r}: {why}")
            continue
        if sacred_violation(w, term):
            rejected.append(f"expand {w!r} -> {term!r}: RELIGIOUS picture for a "
                            f"secular word")
            continue
        add["expand"][w] = str(term).strip()

    # ---- people
    for w, v in got["people"].items():
        if w in EXISTING["people"]:
            continue
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            rejected.append(f"people {w!r}: needs [Display Name, fallback]")
            continue
        name, fb = str(v[0]).strip(), str(v[1]).strip()
        if not name or len(name) > 60:
            rejected.append(f"people {w!r}: bad display name")
            continue
        why = check_term(fb)
        # a fallback MAY name the person's own institution, so the name rule is
        # relaxed here - it is the one place a surname is legitimate.
        if why and "person's name" not in why:
            rejected.append(f"people {w!r} fallback {fb!r}: {why}")
            continue
        if sacred_violation(w, fb):
            rejected.append(f"people {w!r}: religious fallback")
            continue
        add["people"][w] = [name, fb]

    # ---- word lists
    for key in ("abstract", "not_a_picture"):
        for w in sorted(got[key]):
            if w in ALL_KNOWN or not WORD_OK.match(w):
                continue
            add[key].append(w)

    newpics = sorted({t for t in add["expand"].values() if t not in PICTURES})
    reused = len(add["expand"]) - sum(1 for t in add["expand"].values()
                                      if t not in PICTURES)

    print(f"  expand         {len(add['expand']):6,}   "
          f"({reused:,} reuse an existing picture, "
          f"{len(newpics):,} new pictures)")
    print(f"  people         {len(add['people']):6,}")
    print(f"  abstract       {len(add['abstract']):6,}")
    print(f"  not_a_picture  {len(add['not_a_picture']):6,}")
    print(f"\n  rejected       {len(rejected):6,}")
    print(f"  conflicts      {len(conflicts):6,}")
    for r in rejected[:25]:
        print(f"     x {r}")
    if len(rejected) > 25:
        print(f"     ... {len(rejected) - 25} more")
    for c in conflicts[:10]:
        print(f"     ! {c}")

    dupe = Counter(add["expand"].values())
    print(f"\n  most reused new picture: "
          f"{dupe.most_common(1)[0] if dupe else 'n/a'}")

    if "--write" in sys.argv:
        Path(HERE / "additions.json").write_text(json.dumps(add, indent=1,
                                                            sort_keys=True))
        Path(HERE / "rejected.txt").write_text("\n".join(rejected))
        print(f"\nwrote additions.json and rejected.txt")


if __name__ == "__main__":
    main()
