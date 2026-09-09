#!/usr/bin/env python3
"""
CANDIDATE SPANS, already legal, so judgement is spent on the IDEA.

    python3 pick.py                     # sweep the master, ranked candidates
    python3 pick.py --mode conversation # only where the floor actually moves
    python3 pick.py --top 25 --full     # print the whole opening and closing

WHY THIS EXISTS. Picking was the weakest half of this pipeline and it was weak
for a structural reason, not a lack of care: everything that makes a span
ILLEGAL is cheap to compute and was being discovered by hand, one preflight run
at a time. A span was read out of the transcript, authored into a slate, and
only then told that it crosses a layout change, opens mid-clause, delivers 51
seconds, or has a price in it. Each of those is a minute of reading and a
re-author, and the effect is that fewer candidates get considered - which is
exactly the thing SKILL.md says makes a boring set.

So the constraints are swept first and the human reads a shortlist that already
passes them. The same shape as `broll.py propose`: the machine shortlists, the
person decides.

WHAT IT WILL NOT DO IS RANK THE IDEA. There is no lexical statistic on this
material that separates a clip that lands from one that trails off - SKILL.md
records the measurements and the reason a gate like that gets ignored. So it
prints the opening sentence, the closing sentence and the subjects, and the
ranking is over things that are actually measurable: does it fill the band, is
it clean, does it have pictures, does the floor move. THE LAST STEP IS READING.

THE COMPLIANCE SCAN IS THE HIGHEST-VALUE PART and the one worth trusting least.
It flags prices, positions and advice by pattern, which catches the shapes this
desk actually says ("39.30 on Nike", "I'm long here", "you can buy the fund") -
and it cannot read tone, cannot see the screen, and does not know that a wage in
dollars is not a share price. A flag means READ THE SPAN. A clean scan does NOT
mean the span is clean; SKILL.md's rule that compliance applies to what is ON
SCREEN is unchanged and no text scan can see a chart.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
WORK = Path(os.environ.get("WLAM_WORK") or os.environ.get("QM_WORK") or HERE)

import qmclip as q                                             # noqa: E402

# ---------------------------------------------------------------- compliance --
# The shapes this footage actually produces. Each is a REASON TO READ, never a
# verdict - see the module docstring.
MONEY = r"\$\s?\d[\d,]*(?:\.\d+)?"
# A SHARE PRICE IS ATTACHED TO AN INSTRUMENT; A WAGE IS ATTACHED TO A PERSON.
# That is the only principle available without a company-name list, and it
# covers the shape this footage produces - "the $20 accountant", "a $10 robot",
# "$20 an hour" - which are labour costs in a jobs argument and not a security
# anybody could act on. Anything attached to a barrel, a ticker or a company
# still flags.
WAGE_AFTER = (r"(?:\s+(?:an?\s+)?(?:hour|hourly|year|month|week|day)\b"
              r"|\s+(?:an?\s+)?(?:accountant|worker|employee|robot|kid|"
              r"teacher|nurse|driver|clerk|analyst|engineer|coder|programmer|"
              r"assistant|labou?rer|job|salary|wage)s?\b)")
COMPLIANCE = [
    ("price",    re.compile(rf"{MONEY}\b(?!{WAGE_AFTER}|\s*(?:per\s+hour|"
                            rf"billion|trillion|million))", re.I)),
    ("level",    re.compile(r"\b\d{2,3}\.\d{1,2}\b(?!\s*%)")),
    # "And of course, my Nike thesis, I have purchased Nike" walked past the
    # first version of this, which only matched a bare past tense. A position is
    # disclosed in more tenses than one and usually with a possessive.
    ("position", re.compile(r"\b(i'?m|i am|we'?re|we are)\s+(long|short|in)\b|"
                            r"\bi('ve| have)?\s*(just\s+)?"
                            r"(bought|purchased|sold|own|hold|added|averaged|"
                            # "I hold that view" is not a position. Holding an
                            # OPINION reads identically to holding stock here,
                            # and a false flag costs a good candidate 3.0 of
                            # score via `clean`, so the abstract objects are
                            # excluded rather than left to a human to clear.
                            r"accumulated|picked up)\b"
                            r"(?!\s+(that|the|a|an|this|those|these)\s+"
                            r"(view|views|opinion|opinions|belief|beliefs|"
                            r"thought|thoughts|line|position\s+that))|"
                            r"\bmy (position|stake|shares|thesis|entry|average|stock|"
                            r"holding|portfolio|book)\b|"
                            # "I got a bump in my stock, BE" - a position
                            # disclosed by its RESULT rather than by the verb.
                            # It walked past the pattern until the picker was
                            # run at a finer in-point spacing and offered it as
                            # an opening line.
                            r"\b(a|my) bump in (my|that|it)\b|"
                            r"\b(averaging|accumulating) (in|at|more)\b|"
                            # FORWARD-LOOKING INTENT, which the past-tense list
                            # above cannot see and which is the most sensitive
                            # phrasing on a live markets show: "For those of you
                            # who are buying SpaceX stock with me, I'm still
                            # going to be buying even more today" scored ZERO
                            # flags and was the picker's top-ranked span.
                            r"\b(i'?m|i am|we'?re|we are)\s+(still\s+)?"
                            r"(going to\s+|gonna\s+|about to\s+)?(be\s+)?"
                            r"(buying|selling|shorting|adding|accumulating)\b|"
                            r"\bi'?ll\s+(be\s+)?(buying|selling|adding|shorting)\b|"
                            # inviting the audience into the same trade
                            r"\b(buying|selling|shorting)\b[^.]{0,30}\bwith me\b", re.I)),
    ("advice",   re.compile(r"\byou (should|can|could|need to|have to|ought to)\s+"
                            r"(buy|sell|short|hold|own|get in|get out)\b|"
                            r"\b(buy|sell|short) (the|this|that|it)\b|"
                            r"\bstrike price\b|\bcall option\b|\bput option\b", re.I)),
    # THE RECOMMENDATION SHAPE, which none of the patterns above could see.
    # Measured: "I think Nike is a strong buy here, I would be accumulating",
    # "We rate it outperform with a price target of 120", "You should be buying
    # this dip" and "I am upgrading my rating on the stock to overweight" ALL
    # scored zero flags. On a show whose whole subject is what to do with money,
    # a rating, a target and an upgrade are the most compliance-sensitive
    # sentences there are - more than the price patterns that were covered.
    ("rating",   re.compile(r"\b(strong|screaming)\s+(buy|sell)\b|"
                            r"\b(a|an)\s+(buy|sell)\s+(here|now|at)\b|"
                            r"\bprice\s+target\b|\bfair\s+value\s+of\b|"
                            r"\b(over|under)weight\b|"
                            r"\b(out|under)perform(s|ing|ed)?\b|"
                            r"\b(up|down)grad(e|es|ed|ing)\b|"
                            r"\b(raising|lowering|cutting)\s+(my|our|the)\s+"
                            r"(target|rating|estimate)|"
                            r"\b(my|our)\s+rating\b|\brate(d)?\s+it\b|"
                            r"\byou\s+(should|need\s+to|have\s+to|ought\s+to)\s+"
                            r"(be\s+)?(buy|sell|short|hold|own)(ing)?\b|"
                            r"\b(i|we)\s+would\s+be\s+"
                            r"(buy|sell|add|accumulat)(ing)\b", re.I)),
    ("return",   re.compile(r"\b(returns?|gains?|profits?|up|down)\s+(of\s+)?\d+\s?%|"
                            r"\b\d+\s?%\s+(return|gain|profit|yield)\b", re.I)),
]


def compliance_flags(text: str) -> list[str]:
    """
    (kind, and enough CONTEXT to clear it at a glance).

    The context is the point. Measured over one master, 34 of 94 candidates
    carry a flag - plausible on a show that discusses prices for a living, and
    unworkable if each one costs a minute of re-reading. "$20" is a coin flip;
    "the $20 accountant" is resolved the instant you see it, and it is a WAGE
    rather than a share price. Widening the patterns to know that is a losing
    game against English; showing the words is not.
    """
    out = []
    flat = " ".join(text.split())
    for name, rx in COMPLIANCE:
        m = rx.search(flat)
        if not m:
            continue
        a, b = max(0, m.start() - 34), min(len(flat), m.end() + 34)
        ctx = ("..." if a else "") + flat[a:b] + ("..." if b < len(flat) else "")
        out.append(f"{name}: {ctx}")
    return out


# ------------------------------------------------------------------ the data --
def cues() -> list[tuple[float, float, str]]:
    p = WORK / "cues.json"
    if not p.exists():
        raise SystemExit("no cues.json - run analyze.py first")
    return [(float(a), float(b), str(t)) for a, b, t in json.loads(p.read_text())]


def layout_runs() -> list[dict]:
    p = WORK / "sections.json"
    return json.loads(p.read_text()) if p.exists() else []


SENT = re.compile(r"(?<=[.!?])\s+")

# AN OPENING SENTENCE HAS TO CARRY AN IDEA. The first version took any sentence
# start and offered "Wow.", "They just do." and "Oh, it's called, sorry." as
# in-points - each is a legal boundary and none of them opens a clip. The
# non-negotiable is that a clip is ONE COMPLETE IDEA, and it cannot be if the
# first thing said is a reaction to something the viewer did not hear.
OPENER_MIN_WORDS = 7
OPENER_JUNK = re.compile(
    r"^(wow|yeah|yes|no|right|okay|ok|sure|exactly|correct|absolutely|"
    r"oh|ah|hmm|well|so|and|but|anyway|sorry|thank you|thanks|good|great)\b",
    re.I)


# AND A CLOSING SENTENCE HAS TO FINISH ONE. Symmetric to the opener, and it was
# missing: the first span this tool was asked for in anger came back ending on
# "Mm-hmm." - a legal finished sentence by every test in the pipeline, and the
# non-negotiable is that a clip ENDS ANSWERING the idea it started. A clip that
# stops on an acknowledgement has not finished, it has run out.
CLOSER_MIN_WORDS = 5
CLOSER_JUNK = re.compile(
    r"^(mm+[\s-]?h*m+|uh[\s-]?huh|yeah|yes|no|right|okay|ok|sure|exactly|"
    r"correct|absolutely|true|good|great|nice|wow|thanks?|thank you|"
    r"i (agree|know|see)|that'?s (it|right|true|good)|for sure|of course)"
    r"[\s.,!?]*$", re.I)


def closes_an_idea(s: str) -> bool:
    """Does this sentence FINISH the thought, or just acknowledge one?"""
    t = s.strip()
    if CLOSER_JUNK.match(t):
        return False
    words = re.findall(r"[A-Za-z']+", t)
    if len(words) < CLOSER_MIN_WORDS:
        return False
    # A closer that is only a pronoun and a verb resolves nothing - the same
    # objection TRAIL_OFF records for "go.", "that.", "this.".
    return any(w.lower() not in q.STOP for w in words)


def opens_an_idea(s: str) -> bool:
    """Does this sentence stand up as the first thing a viewer hears?"""
    words = re.findall(r"[A-Za-z']+", s)
    if len(words) < OPENER_MIN_WORDS:
        return False
    # A LOWERCASE FIRST LETTER MEANS MID-SENTENCE. sentences() splits on
    # [.!?], and whisper does not always put one where a thought ends - so a
    # cue can begin part-way through a clause and still arrive here looking
    # like a sentence. Whisper DOES capitalise what it believes is a sentence
    # start, which makes the case of the first letter the cheapest honest
    # signal available. Measured after the score was rescaled, the top-ranked
    # candidate in the field opened "you know, and I can see where he may be
    # angling" - seven words, no junk marker, and plainly mid-thought.
    first = next((ch for ch in s.strip() if ch.isalpha()), "")
    if first and first.islower():
        return False
    # A discourse marker is only fatal when the sentence LEANS on it - "So the
    # Fed should meet six times a year" is a fine opener and "So they just do"
    # is not, and the difference is whether anything substantial follows.
    if OPENER_JUNK.match(s.strip()) and len(words) < OPENER_MIN_WORDS + 4:
        return False
    return True


def sentences() -> list[tuple[float, float, str]]:
    """
    (start, end, text) per sentence, times interpolated inside a cue.

    Word-level timing is not in cues.json, so a cue's sentences are spread by
    CHARACTER COUNT across its span. That is exact enough for choosing an
    in-point - the silence pass and plan_ending both re-derive the real edges
    from the audio at render time, and this only has to land inside the right
    second.
    """
    out = []
    for a, b, txt in cues():
        parts = [s for s in SENT.split(txt.strip()) if s.strip()]
        if not parts:
            continue
        total = sum(len(s) for s in parts) or 1
        t = a
        for s in parts:
            d = (b - a) * len(s) / total
            out.append((t, t + d, s.strip()))
            t += d
    return out


def run_at(t: float, runs: list[dict]) -> dict | None:
    return next((r for r in runs if r["start"] <= t < r["end"]), None)


MODES_FOR = {"head": ["head"], "two_up": ["conversation", "head"],
             "share": ["conversation_share", "share"], "gallery": ["head"]}


# ------------------------------------------------------------------ scoring --
def silence_in(a: float, b: float) -> float:
    """Seconds the silence pass will remove from this span."""
    try:
        env = q.envelope(a, b - a)
        rem = q.collapse_silence(env, b - a)
        return sum(e - s for s, e in rem)
    except Exception:                                            # noqa: BLE001
        return 0.0


def subjects(text: str) -> list[str]:
    """Concrete nouns the b-roll vocabulary can actually picture."""
    try:
        import broll
    except Exception:                                            # noqa: BLE001
        return []
    # ONLY WHAT WOULD ACTUALLY BE CUT TO. Counting every EXPAND hit inflated
    # this with "think", "relevant", "tough" and "allowed" - all mapped, none of
    # them a subject anybody would cut to, and each one adding to the score.
    # broll's own ABSTRACT set and NOT_A_PICTURE are the filters it uses itself.
    abstract = getattr(broll, "ABSTRACT", set())
    junk = set(getattr(broll, "NOT_A_PICTURE", set())) | set(q.STOP)
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", text):
        lo = w.lower()
        if lo in seen or len(lo) < 4 or lo in junk or lo in abstract:
            continue
        seen.add(lo)
        if lo in getattr(broll, "PEOPLE", {}):
            out.insert(0, w)                      # a named person leads
        elif lo in broll.EXPAND:
            out.append(w)
    return out


def score(c: dict) -> float:
    """
    Rank on what is MEASURABLE. Deliberately not on the idea - see the docstring.

    The band centre is the target rather than "longer is better": a 90s clip is
    not twice the clip a 75s one is, and the owner's band has a middle.
    """
    lo, hi = q.CLIP_BAND
    mid = (lo + hi) / 2
    fit = 1.0 - min(1.0, abs(c["delivered"] - mid) / (hi - lo))
    # DIVIDED BY 8 UNTIL 2026-08-30, WHICH THE VOCABULARY EXPANSION KILLED.
    # EXPAND went 11,901 -> 31,129, so almost every span now has more than
    # eight picturable subjects: measured over 156 real candidates the count
    # runs 6..29 with a median of 14, and 151 of 156 saturated at 1.0. A term
    # that is 1.0 for 97% of the field ranks nothing. Scaled to the observed
    # top of the distribution it discriminates again.
    pics = min(1.0, len(c["subjects"]) / 24.0)
    clean = 0.0 if c["flags"] else 1.0
    moves = 1.0 if c["mode_hint"].startswith("conversation") else 0.6
    # CROSSTALK ONLY COUNTS AGAINST A SPAN THAT HAS TO FOLLOW THE SPEAKER. On a
    # head clip there is nobody to cut to, so rapid back-and-forth is just pace.
    calm = 1.0
    if c["mode_hint"].startswith("conversation"):
        calm = max(0.0, 1.0 - c.get("banter", 0.0) / BANTER_MAX)
    return 3.0 * clean + 2.0 * fit + 1.5 * pics + 0.5 * moves + 2.0 * calm


SHORT_CUE = 2.5          # a cue this brief is a handover, not a thought
BANTER_WARN = 8.8        # p75 of the 08.26 show
BANTER_MAX = 12.0        # p90 - above this the turn detector is guessing


def banter_rate(a: float, b: float) -> float:
    """
    Short cues per minute - how much RAPID CROSSTALK the span contains.

    Free, because cues.json is already loaded, and it predicts the one failure
    the owner calls non-negotiable. On 08.26 the span that put the wrong man on
    screen measured 8.7/min, the 73rd percentile of the whole show: the turn
    detector was being asked to follow four handovers inside eleven seconds
    ("Well, that's good." / "Good." / "Yeah." / "I'll say hi to them."), and its
    confidence fell to 0.15 saying so.

    A stretch where one person holds the floor is BOTH easier to follow on the
    picture and better to watch. So this is a picking criterion first and a gate
    second - the fix for crosstalk is to pick a different moment, not to cut it
    more cleverly.
    """
    win = [c for c in cues() if c[1] > a and c[0] < b]
    if not win or b - a < 1.0:
        return 0.0
    short = sum(1 for c in win if c[1] - c[0] < SHORT_CUE)
    return short / ((b - a) / 60.0)


def candidates(min_gap: float = 20.0) -> list[dict]:
    """
    Every span that STARTS and ENDS on a sentence and delivers inside the band.

    It walks sentence starts as in-points and, for each, extends sentence by
    sentence until the delivered length enters the band - then takes the first
    ending that lands. One candidate per in-point, and in-points are spaced
    `min_gap` apart so the list is a set of distinct moments rather than a
    hundred shifted copies of one.
    """
    sents = sentences()
    runs = layout_runs()
    lo, hi = q.CLIP_BAND
    card = q.CARD_SECONDS if q.CFG.get("endcard", True) else 0.0
    out: list[dict] = []
    last_start = -1e9
    for i, (a, _e, s0) in enumerate(sents):
        if a - last_start < min_gap:
            continue
        if not opens_an_idea(s0):
            continue
        run = run_at(a, runs)
        if not run:
            continue
        text = s0
        for j in range(i + 1, min(i + 90, len(sents))):
            b = sents[j][1]
            text += " " + sents[j][2]
            if b > run["end"]:
                break                       # never cross a layout change
            span = b - a
            if span < lo:
                continue
            body = span - silence_in(a, b)
            # THE TEMPO SHORTENS THE CLIP, and leaving it out made this tool
            # disagree with preflight by six seconds on the first span it was
            # asked for in anger: it reported 62.6s where preflight measured
            # 56.4s and refused the clip. tempo_for speeds a slow clip up toward
            # the WPM band, and a faster clip is a SHORTER one - the floor is
            # measured on the delivered duration, after it.
            #
            # WPM is estimated from the words in the span over the post-silence
            # body, which is what measure_wpm does with real word timings. Close
            # enough to keep the two tools agreeing about which spans are legal;
            # render still measures it properly.
            words = len(re.findall(r"[A-Za-z0-9']+", text))
            tempo = 1.0
            if body > 1.0 and q.CFG.get("adaptive_speed", True):
                wpm = words / (body / 60.0)
                tlo, thi = q.SPEED_BAND
                if wpm < tlo:
                    tempo = min(tlo / wpm, q.SPEED_MAX)
                elif wpm > thi:
                    tempo = max(thi / wpm, q.SPEED_MIN)
                if abs(tempo - 1.0) < q.SPEED_DEAD:
                    tempo = 1.0
            delivered = body / tempo + card
            if delivered < lo:
                continue
            if delivered > hi:
                break                       # this in-point cannot land in the band
            if not q.finished_sentence(sents[j][2]) or not closes_an_idea(sents[j][2]):
                continue
            out.append({
                "start": round(a, 2), "end": round(b, 2), "span": round(span, 1),
                "delivered": round(delivered, 1), "layout": run["mode"],
                "mode_hint": MODES_FOR.get(run["mode"], ["head"])[0],
                "opens": s0, "closes": sents[j][2],
                "flags": compliance_flags(text), "subjects": subjects(text),
                "banter": round(banter_rate(a, b), 1),
            })
            last_start = a
            break
    for c in out:
        c["score"] = round(score(c), 2)
    return sorted(out, key=lambda c: -c["score"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--mode", help="only candidates whose layout offers this mode")
    ap.add_argument("--gap", type=float, default=20.0,
                    help="seconds between in-points, so the list is distinct moments")
    ap.add_argument("--dirty", action="store_true",
                    help="include candidates with compliance flags")
    ap.add_argument("--full", action="store_true", help="print sentences in full")
    a = ap.parse_args()

    cands = candidates(a.gap)
    if a.mode:
        cands = [c for c in cands
                 if a.mode in MODES_FOR.get(c["layout"], [])]
    dirty = [c for c in cands if c["flags"]]
    if not a.dirty:
        cands = [c for c in cands if not c["flags"]]

    lo, hi = q.CLIP_BAND
    print(f"\n{q.SRC.name}\n"
          f"{len(cands)} candidate(s) that start and end on a sentence, stay "
          f"inside one layout run,\nand deliver {lo:.0f}-{hi:.0f}s"
          + (f" - plus {len(dirty)} held back by the compliance scan"
             if dirty and not a.dirty else "") + "\n")
    cut = lambda s, n: s if a.full else (s[:n] + ("..." if len(s) > n else ""))
    for c in cands[:a.top]:
        print(f"  {c['start']:8.1f} -> {c['end']:8.1f}   {c['delivered']:5.1f}s "
              f"delivered   {c['layout']:7s} -> {c['mode_hint']}   score {c['score']}")
        print(f"      opens   \"{cut(c['opens'], 96)}\"")
        print(f"      closes  \"{cut(c['closes'], 96)}\"")
        if c["subjects"]:
            print(f"      pictures {len(c['subjects'])}: "
                  f"{', '.join(c['subjects'][:10])}")
        if c["flags"]:
            print(f"      FLAGGED  {'; '.join(c['flags'])}")
        print()

    if dirty and not a.dirty:
        print(f"  {len(dirty)} candidate(s) carry a compliance flag and are hidden. "
              f"--dirty to see them.\n")
    print("  The machine has checked the EDGES, the LENGTH, the LAYOUT and the\n"
          "  vocabulary. It has NOT judged the idea - read `opens` and `closes`\n"
          "  and ask whether one thought starts and finishes between them.\n"
          "  A compliance flag is a reason to READ THE SPAN, not a verdict, and a\n"
          "  clean scan cannot see what is on the shared SCREEN.\n")


if __name__ == "__main__":
    main()
