#!/usr/bin/env python3
"""Map a source timestamp to its position in the rendered output.

A cut EDL discards material, so a moment at 21.8s in a source file lands
somewhere else entirely in the finished video — and that output position is
what an overlay's `start_in_output` needs.

    python3 map_time.py edit/edl-v2.json A-true-intro 21.8

Renders run slightly longer than the EDL predicts because each segment is
padded out to a whole frame, and that error accumulates over many segments.
Pass --actual-duration with the real output length and the mapping is scaled
to absorb it; without it, expect drift of roughly a frame per segment.

Returns nothing if the timestamp fell inside material the cut removed.
"""
import argparse, json, sys
from pathlib import Path


def map_time(edl, source, t, scale=1.0):
    off = 0.0
    for r in edl["ranges"]:
        length = r["end"] - r["start"]
        if r["source"] == source and r["start"] <= t < r["end"]:
            return (off + (t - r["start"])) * scale
        off += length
    return None


def source_span(edl, source, scale=1.0):
    """(first, last) output times covered by this source."""
    off = 0.0; first = last = None
    for r in edl["ranges"]:
        length = r["end"] - r["start"]
        if r["source"] == source:
            if first is None:
                first = off
            last = off + length
        off += length
    return (None, None) if first is None else (first*scale, last*scale)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl")
    ap.add_argument("source")
    ap.add_argument("time", nargs="?", type=float)
    ap.add_argument("--actual-duration", type=float,
                    help="measured duration of the rendered output, to correct drift")
    ap.add_argument("--span", action="store_true",
                    help="print the output span this source occupies instead")
    args = ap.parse_args()

    edl = json.loads(Path(args.edl).read_text())
    predicted = sum(r["end"] - r["start"] for r in edl["ranges"])
    scale = (args.actual_duration / predicted) if args.actual_duration else 1.0

    if args.span:
        a, b = source_span(edl, args.source, scale)
        if a is None:
            sys.exit(f"source not in EDL: {args.source}")
        print(f"{a:.3f} {b:.3f}")
        return

    if args.time is None:
        sys.exit("give a time, or use --span")
    out = map_time(edl, args.source, args.time, scale)
    if out is None:
        sys.exit(f"{args.source} @ {args.time}s was cut — no output position")
    print(f"{out:.3f}")


if __name__ == "__main__":
    main()
