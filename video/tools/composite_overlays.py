#!/usr/bin/env python3
"""Composite alpha overlays onto a rendered cut, with optional frosted glass.

video-use's render.py can lay overlays on, but it cannot blur the footage
*behind* one. A glass pane needs that: `backdrop-filter` is a no-op inside an
alpha overlay because nothing sits behind it to sample, so the frost has to be
produced here, by blurring the base inside the pane's rect before the card goes
over it.

    python3 composite_overlays.py base.mp4 overlays.json -o final.mp4

overlays.json is a list of:
    {"file": "...mov", "start": 12.5, "duration": 4.0,
     "glass": {"x": 40, "y": 262, "w": 1840, "h": 556, "blur": 18}}

`glass` is optional. Its rect must match the pane geometry in the composition's
CSS — they are the same rectangle expressed twice and nothing checks that.

Each overlay is PTS-shifted so its frame 0 lands at `start`, and gated with
`enable` so it only draws inside its own window. Audio is copied untouched.
"""
import argparse, json, subprocess, sys
from pathlib import Path


def build_filter(overlays):
    parts, cur = [], "[0:v]"
    for i, ov in enumerate(overlays, start=1):
        t, dur = float(ov["start"]), float(ov["duration"])
        end = t + dur
        g = ov.get("glass")
        if g:
            # Frost the base inside the pane rect, gated to this overlay's window.
            b = f"bl{i}"
            parts.append(f"[0:v]crop={g['w']}:{g['h']}:{g['x']}:{g['y']},"
                         f"boxblur={g.get('blur', 18)}:2[{b}]")
            nxt = f"[g{i}]"
            parts.append(f"{cur}[{b}]overlay={g['x']}:{g['y']}:"
                         f"enable='between(t,{t:.3f},{end:.3f})'{nxt}")
            cur = nxt
        # Shift the card so its own frame 0 lands at t, then gate it.
        parts.append(f"[{i}:v]setpts=PTS-STARTPTS+{t:.3f}/TB[a{i}]")
        nxt = f"[v{i}]"
        parts.append(f"{cur}[a{i}]overlay=0:0:"
                     f"enable='between(t,{t:.3f},{end:.3f})'{nxt}")
        cur = nxt
    parts.append(f"{cur}null[outv]")
    return ";".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("overlays")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--crf", type=int, default=18, help="18 is visually lossless at 1080p")
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()

    overlays = json.loads(Path(args.overlays).read_text())
    for ov in overlays:
        if not Path(ov["file"]).exists():
            sys.exit(f"missing overlay: {ov['file']}")

    cmd = ["ffmpeg", "-y", "-i", args.base]
    for ov in overlays:
        cmd += ["-i", ov["file"]]
    cmd += ["-filter_complex", build_filter(overlays),
            "-map", "[outv]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
            args.output]

    print(f"compositing {len(overlays)} overlay(s) onto {Path(args.base).name}")
    for ov in overlays:
        g = " + glass" if ov.get("glass") else ""
        print(f"  {ov['start']:8.2f}s +{ov['duration']:.1f}s  {Path(ov['file']).name}{g}")
    r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr[-2500:])
    print(f"\ndone: {args.output}")


if __name__ == "__main__":
    main()
