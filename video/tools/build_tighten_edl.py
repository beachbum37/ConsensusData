#!/usr/bin/env python3
"""Build an EDL that removes dead air, keeping a natural amount of breath.

For each source, ffmpeg `silencedetect` gives the real silences. Any silence
longer than --max-pause is trimmed back to --keep-pause; shorter ones are left
completely alone. Cutting every pause reads as breathless, so the default keeps
0.35s of air at each seam.

    python3 build_tighten_edl.py 02-intro-ish 03-step1 ... -o edit/edl.json

Edges are padded by --pad on both sides so a trim never clips the start of a
word (Hard Rule 7 — ASR/detector timestamps drift 50-100ms).
"""
import argparse, json, re, subprocess
from pathlib import Path


def probe_duration(p):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
        capture_output=True, text=True).stdout.strip())


def silences(media, thr, mind):
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", media, "-af",
         f"silencedetect=noise={thr}dB:d={mind}", "-f", "null", "-"],
        capture_output=True, text=True)
    out, start = [], None
    for m in re.finditer(r"silence_(start|end): (-?[0-9.]+)", proc.stderr):
        k, v = m.group(1), float(m.group(2))
        if k == "start":
            start = max(0.0, v)
        elif start is not None:
            out.append((start, v)); start = None
    return out


def build(name, args):
    media = f"{name}.mp4"
    dur = probe_duration(media)
    sils = silences(media, args.noise_db, args.max_pause)

    # Each over-long silence becomes a cut of its excess, centered so both
    # sides keep half the retained pause.
    cuts = []
    for s, e in sils:
        if e - s <= args.max_pause:
            continue
        half = args.keep_pause / 2
        cs, ce = s + half, e - half
        if ce - cs > 0.08:                      # not worth a seam
            cuts.append((cs, ce))

    keeps, prev = [], 0.0
    for cs, ce in cuts:
        a, b = prev, min(cs + args.pad, dur)
        if b - a >= args.min_seg:
            keeps.append((a, b))
        prev = max(0.0, ce - args.pad)
    if dur - prev >= args.min_seg:
        keeps.append((prev, dur))
    return dur, keeps, sum(b - a for a, b in keeps)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--max-pause", type=float, default=0.85,
                    help="silences longer than this get trimmed (default 0.85)")
    ap.add_argument("--keep-pause", type=float, default=0.35,
                    help="how much air to leave at a trimmed seam (default 0.35)")
    ap.add_argument("--pad", type=float, default=0.06,
                    help="edge padding, seconds (default 0.06)")
    ap.add_argument("--min-seg", type=float, default=0.30)
    ap.add_argument("--noise-db", type=int, default=-40)
    ap.add_argument("--grade", default=None)
    args = ap.parse_args()

    ranges, sources = [], {}
    print(f"{'source':<26} {'orig':>8} {'tight':>8} {'saved':>8}  segs")
    t_o = t_t = 0
    for n in args.sources:
        dur, keeps, kept = build(n, args)
        sources[n] = str(Path(f"{n}.mp4").resolve())
        for a, b in keeps:
            ranges.append({"source": n, "start": round(a, 3), "end": round(b, 3)})
        print(f"{n:<26} {dur:7.1f}s {kept:7.1f}s {dur-kept:7.1f}s  {len(keeps):4d}")
        t_o += dur; t_t += kept

    edl = {"sources": sources, "ranges": ranges}
    if args.grade:
        edl["grade"] = args.grade
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(edl, indent=2))
    print(f"{'TOTAL':<26} {t_o:7.1f}s {t_t:7.1f}s {t_o-t_t:7.1f}s  {len(ranges):4d}")
    print(f"\n{t_o/60:.1f} min → {t_t/60:.1f} min  ({100*(t_o-t_t)/t_o:.0f}% removed) → {args.output}")


if __name__ == "__main__":
    main()
