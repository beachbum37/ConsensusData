#!/usr/bin/env python3
"""Two clips of one set may not carry the same SPEECH.

`check_broll`'s SET line already refuses the same PICTURE reused by two clips of
one set. Nothing looked at the words. On a webinar or an AMA a host restates a
point twice - routine, and the two tellings are minutes apart - so `pick.py` can
hand back two spans that are healthy on every measure it has: both open and close
on an idea, both pass LENGTH, LAYOUT and the compliance scan, and neither is
inside the other. They only read as a duplicate to a viewer meeting them back to
back in a feed, which is after they shipped.

This is the SET gate's missing half, and it is deliberately the same shape: it
scores across the whole slate, not inside one clip, and `"dupe_ok": true` on a
clip is the escape - the same key the picture check spells `"repeat_ok"`.

The comparison is lifted from the video studio's find_duplicate_content.py, which
was written for the same failure at segment scale and caught a take that was
93.9% a re-recording of another AFTER the assembly and overlay work were done.
Slide a window of N normalised words out of A and ask whether that exact run
appears anywhere in B. It is deliberately dumb: no embeddings, no paraphrase
detection. A paraphrase is a different telling and usually worth keeping; a
verbatim run is the speaker saying the same sentence twice.

    python3 checkdupes.py                # the whole slate
    python3 checkdupes.py --window 6     # stricter: shorter runs count as shared
    python3 checkdupes.py --threshold 15 # refuse at a lower overlap

Exits non-zero past the threshold so it can gate a build the way preflight does.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Per-show state follows WLAM_WORK; HERE stays the CODE directory.
WORK = Path(os.environ.get("WLAM_WORK") or HERE)

OK, WARN, BAD = "ok  ", "warn", "FAIL"


def _norm(t: str) -> list[str]:
    """Words stripped to letters and digits. Punctuation and case carry no signal
    here - whisper's comma placement differs between two decodes of the same
    sentence, and a run that matches except for a comma is still the same run."""
    return [w for w in (re.sub(r"[^a-z0-9]", "", x.lower()) for x in t.split()) if w]


def _cues() -> list[tuple[float, float, str]]:
    p = WORK / "cues.json"
    if not p.exists():
        raise SystemExit("no cues.json - run analyze.py first")
    return [(float(a), float(b), str(t)) for a, b, t in json.loads(p.read_text())]


def _clip_words(clip: dict, cues) -> list[str]:
    """Every word the clip actually carries.

    A cue is counted when it STARTS inside the span. Overlap-based inclusion
    double-counts the cue straddling a boundary into both of two adjacent clips,
    which reads as a shared run that neither clip really has - the exact false
    positive that would make an operator stop trusting this check.
    """
    a, b = float(clip["start"]), float(clip["end"])
    out: list[str] = []
    for s, _e, t in cues:
        if a <= s < b:
            out.extend(_norm(t))
    return out


def _covered(a_words: list[str], b_words: list[str], w: int) -> tuple[float, list[str]]:
    """Share of A's words inside some w-word run that also appears in B.

    Returns the fraction and the longest shared runs, because "38% overlap" is
    not actionable on its own - the operator needs to read the sentence and
    decide which telling to keep.
    """
    if len(a_words) < w or len(b_words) < w:
        return 0.0, []
    btext = " " + " ".join(b_words) + " "
    hit = [False] * len(a_words)
    runs: list[tuple[int, int]] = []
    for i in range(len(a_words) - w + 1):
        if f" {' '.join(a_words[i:i + w])} " in btext:
            for j in range(i, i + w):
                hit[j] = True
            if runs and runs[-1][1] >= i:
                runs[-1] = (runs[-1][0], i + w)
            else:
                runs.append((i, i + w))
    frac = sum(hit) / len(a_words) * 100.0
    longest = sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:3]
    return frac, [" ".join(a_words[s:e]) for s, e in longest]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", type=int, default=8,
                    help="words that must match consecutively (default 8)")
    ap.add_argument("--threshold", type=float, default=25.0,
                    help="percent overlap that FAILs a pair (default 25)")
    a = ap.parse_args()

    slate_p = WORK / "slate.json"
    if not slate_p.exists():
        raise SystemExit(f"no slate.json in {WORK} - nothing to check")
    clips = sorted(json.loads(slate_p.read_text())["clips"], key=lambda c: c["rank"])
    if len(clips) < 2:
        print("one clip in the slate - nothing to compare")
        return

    cues = _cues()
    words = {c["slug"]: _clip_words(c, cues) for c in clips}
    empty = [s for s, w in words.items() if len(w) < a.window]
    for s in empty:
        print(f"  {WARN}  {s}: under {a.window} words in span - not compared. "
              f"Check the span against cues.json.")

    worst = 0.0          # highest overlap seen, excused or not
    worst_live = 0.0     # highest that is NOT excused by "dupe_ok"
    excused = 0
    failed = False
    print(f"\nSET CONTENT  window={a.window} words, FAIL at {a.threshold:.0f}%\n")
    for i, ca in enumerate(clips):
        for cb in clips[i + 1:]:
            wa, wb = words[ca["slug"]], words[cb["slug"]]
            if len(wa) < a.window or len(wb) < a.window:
                continue
            # Score BOTH directions and report the higher. A 40-second clip whose
            # every word reappears inside a 90-second one is fully duplicated even
            # though the long clip is only 40% shared - taking the lower number
            # would let exactly that pair through.
            fa, runs_a = _covered(wa, wb, a.window)
            fb, runs_b = _covered(wb, wa, a.window)
            frac, runs, src = (fa, runs_a, ca) if fa >= fb else (fb, runs_b, cb)
            worst = max(worst, frac)
            if frac < a.threshold / 2:
                continue
            ok = bool(ca.get("dupe_ok") or cb.get("dupe_ok"))
            if ok:
                excused += 1
            else:
                worst_live = max(worst_live, frac)
            tag = OK if ok else (BAD if frac >= a.threshold else WARN)
            if tag == BAD:
                failed = True
            print(f"  {tag}  {ca['slug']}  <->  {cb['slug']}")
            print(f"         {frac:.0f}% of {src['slug']} also appears in the other"
                  + ("   (\"dupe_ok\")" if ok else ""))
            for r in runs:
                print(f"         shared: \"{r[:96]}\"")
            print()

    if not failed and worst < a.threshold / 2:
        print(f"  {OK}  no pair shares a {a.window}-word run worth reporting "
              f"(worst {worst:.0f}%)\n")
        return
    if failed:
        print("REFUSED. Two clips in this set tell the same thing. Drop one, move a\n"
              "span so they stop overlapping, or set \"dupe_ok\": true on a clip if\n"
              "you have read the shared runs above and want both anyway.\n")
        sys.exit(1)
    # SAY WHICH NUMBER THIS IS. Reporting the raw worst here printed "worst pair
    # 46%, under the 25% line" whenever a pair was excused - a sentence that is
    # simply false, and the kind that teaches an operator to stop reading output.
    if excused:
        print(f"  {excused} pair(s) excused by \"dupe_ok\". Highest overlap still "
              f"live: {worst_live:.0f}%, against the {a.threshold:.0f}% line.\n")
    else:
        print(f"  worst pair {worst_live:.0f}%, under the {a.threshold:.0f}% line. "
              f"Read the shared runs before shipping.\n")


if __name__ == "__main__":
    main()
