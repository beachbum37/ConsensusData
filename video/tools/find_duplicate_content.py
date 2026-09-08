#!/usr/bin/env python3
"""Find segments that re-record material already present in another segment.

Run this during inventory, before assembling anything. Durations, silence
ratios and speaker turns all look perfectly healthy on a segment that repeats
an earlier one word for word — nothing in the cut pipeline notices, and the
duplication only surfaces when a viewer says "haven't I seen this already?".

    python3 find_duplicate_content.py edit/transcripts/*.json

Compares every pair by sliding a window of N normalised words and asking
whether that exact run appears anywhere in the other transcript. Reports the
overlapping spans in both, so you can decide which take to keep and what is
uniquely worth rescuing from the one you drop.
"""
import argparse, json, re, sys
from pathlib import Path


def load(p):
    ws = json.loads(Path(p).read_text())["words"]
    return [(re.sub(r"[^a-z0-9]", "", w["text"].lower()), w["start"], w["end"])
            for w in ws if w["text"].strip()]


def spans(flags, words, min_len):
    out, cur = [], None
    for i, f in enumerate(flags):
        if f and cur is None:
            cur = i
        elif not f and cur is not None:
            out.append((cur, i - 1)); cur = None
    if cur is not None:
        out.append((cur, len(flags) - 1))
    return [(words[s][1], words[e][2]) for s, e in out if words[e][2] - words[s][1] >= min_len]


def covered(a_words, b_text, w):
    """Which words of A appear inside B as part of an exact w-word run."""
    flags = [False] * len(a_words)
    for i in range(len(a_words) - w + 1):
        if " ".join(x[0] for x in a_words[i:i + w]) in b_text:
            for k in range(i, i + w):
                flags[k] = True
    return flags


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcripts", nargs="+")
    ap.add_argument("--window", type=int, default=8,
                    help="consecutive words that must match exactly (default 8)")
    ap.add_argument("--min-span", type=float, default=2.0,
                    help="ignore overlaps shorter than this many seconds")
    ap.add_argument("--threshold", type=float, default=25.0,
                    help="flag a pair when this %% of a segment is duplicated")
    args = ap.parse_args()

    segs = {Path(p).stem: load(p) for p in args.transcripts}
    joined = {n: " ".join(x[0] for x in w) for n, w in segs.items()}
    names = list(segs)
    worst = 0.0

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            fa = covered(segs[a], joined[b], args.window)
            fb = covered(segs[b], joined[a], args.window)
            pa = 100 * sum(fa) / max(1, len(fa))
            pb = 100 * sum(fb) / max(1, len(fb))
            if max(pa, pb) < args.threshold:
                continue
            worst = max(worst, pa, pb)
            print(f"\n{'='*66}\n{a}   vs  {b}")
            print(f"  {pa:5.1f}% of {a} also appears in {b}")
            print(f"  {pb:5.1f}% of {b} also appears in {a}")
            for name, flags, ws in ((a, fa, segs[a]), (b, fb, segs[b])):
                sp = spans(flags, ws, args.min_span)
                if sp:
                    dur = sum(e - s for s, e in sp)
                    print(f"\n  duplicated inside {name} ({dur:.1f}s):")
                    for s, e in sp:
                        print(f"    {s:7.2f} - {e:7.2f}  ({e-s:5.2f}s)")
                uniq = spans([not f for f in flags], ws, args.min_span)
                if uniq and sum(flags) / max(1, len(flags)) > 0.5:
                    print(f"  unique to {name} — rescue before dropping it:")
                    for s, e in uniq:
                        txt = " ".join(x[0] for x in ws if s <= x[1] <= e)[:90]
                        print(f"    {s:7.2f} - {e:7.2f}  ({e-s:5.2f}s)  {txt}")

    if worst == 0:
        print(f"No pair exceeds {args.threshold:.0f}% overlap — no duplicated content.")
    else:
        print(f"\n{'='*66}\nWorst overlap: {worst:.1f}%. Decide which take to keep "
              f"before assembling.")
        sys.exit(1)


if __name__ == "__main__":
    main()
