#!/usr/bin/env python3
"""
Which camera tile is actually talking over a span.

A transcript has no speaker labels, so on a multi-guest show you infer who is
speaking from context - and when you get it wrong, the clip crops to one person's
tile while a different person's voice plays over it. That is not a subtle defect;
it is the single most obvious way a clip can be broken, and nothing else in the
pipeline catches it.

So measure it instead of guessing. A talking face moves and a listening face does
not, so per-tile frame-to-frame motion in the mouth region separates them cleanly.
Motion is scored against each tile's OWN baseline, because the tiles differ in
lighting, size and how much the person fidgets - comparing raw pixel deltas across
tiles just finds whoever is lit best.

    python3 whospeaks.py 1200 1240
    python3 whospeaks.py 1200 1240 --every 0.4

Reads the tile boxes from project.json ("tiles": {name: [w,h,x,y]}).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
# Per-show state follows QM_WORK; HERE stays the CODE directory.
# One owner for this lives in qmclip.WORK - repeated here because these
# scripts must run without importing it (analyze.py in particular, which
# would delete the transcripts it is writing).
WORK = Path(os.environ.get("WLAM_WORK") or os.environ.get("QM_WORK") or HERE)
CFG = json.loads((WORK / "project.json").read_text())
SRC = Path(CFG["source"])


def frames(start: float, dur: float, every: float, box: tuple[int, int, int, int],
           w: int = 96) -> np.ndarray:
    """Greyscale frames of one tile, sampled every `every` seconds."""
    cw, ch, cx, cy = box
    h = max(8, int(round(w * ch / cw)))
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(SRC),
         "-vf", f"crop={cw}:{ch}:{cx}:{cy},fps={1/every:.4f},scale={w}:{h},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(a) // (w * h)
    if n < 2:
        return np.zeros((0, h, w))
    return a[:n * w * h].reshape(n, h, w).astype(float)


def motion(seq: np.ndarray) -> np.ndarray:
    """
    Per-frame motion in the mouth region.

    The mouth is the bottom-middle of a head-and-shoulders tile. Restricting to it
    matters: whole-tile motion also picks up a listener nodding, leaning back, or a
    hand moving, and those read as loudly as speech.
    """
    if len(seq) < 2:
        return np.zeros(0)
    n, h, w = seq.shape
    roi = seq[:, int(h * 0.45):int(h * 0.92), int(w * 0.22):int(w * 0.78)]
    return np.abs(np.diff(roi, axis=0)).mean(axis=(1, 2))


def audio_energy(start: float, dur: float, every: float) -> np.ndarray:
    """Speech energy on the SAME grid as the frame samples, so the two can be
    correlated directly."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(SRC), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True)
    a = np.frombuffer(p.stdout, dtype="<i2").astype(float) / 32768
    n = max(1, int(every * 16000))
    if len(a) < n:
        return np.zeros(0)
    fr = a[:len(a) // n * n].reshape(-1, n)
    return np.sqrt((fr ** 2).mean(1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("--every", type=float, default=0.25)
    # The rail RE-FLOWS as people join and leave: one guest on air puts a single
    # tile mid-rail, three guests stack from the top. So the tile map is per-span,
    # not per-project, and project.json's copy is only a default.
    ap.add_argument("--tiles", help='JSON {"name":[w,h,x,y]} for THIS span')
    a = ap.parse_args()

    tiles = json.loads(a.tiles) if a.tiles else CFG.get("tiles")
    if not tiles:
        raise SystemExit('project.json has no "tiles" map. Add {name: [w,h,x,y]}.')

    dur = a.end - a.start
    # A baseline sampled from the SAME span: whoever is quietest here is the floor
    # for their own tile. Cross-tile raw comparison finds the best-lit face, not
    # the talking one.
    out = {}
    for name, box in tiles.items():
        m = motion(frames(a.start, dur, a.every, tuple(box)))
        if m.size == 0:
            continue
        out[name] = m

    if not out:
        raise SystemExit("no frames decoded - check the span and the source path")

    # CORRELATE MOUTH MOTION AGAINST THE AUDIO, do not just measure motion.
    # Raw motion barely separates them: a listener nods, shifts, reacts, and on one
    # real span the top two tiles came out 1.37x apart, which is not a decision.
    # Only the person actually talking has a mouth that moves IN TIME with the
    # sound, so correlation is the discriminator and it is not close.
    env = audio_energy(a.start, dur, a.every)
    n = min([len(m) for m in out.values()] + [len(env) - 1])
    if n < 8:
        raise SystemExit("span too short to judge - give it at least a few seconds")
    env = env[1:n + 1]          # motion is a diff, so it lags the energy by one frame

    # SPEECH-GATED RATIO, not a plain correlation. Correlating mouth motion against
    # the amplitude envelope ranks correctly but scores near zero (about 0.02 on a
    # known span), because the relationship is not linear and video noise swamps it
    # - which makes every verdict look ambiguous. Comparing a tile's motion while
    # someone is TALKING against its motion while the room is QUIET is the same
    # question asked in a way that actually separates: the speaker's mouth is busy
    # in the loud frames and still in the quiet ones, a listener's is neither.
    loud = env >= np.percentile(env, 65)
    quiet = env <= np.percentile(env, 30)

    print(f"\n{SRC.name}   {a.start:.1f}s -> {a.end:.1f}s   "
          f"({n} samples @ {a.every}s, {loud.sum()} loud / {quiet.sum()} quiet)\n")

    scores = {}
    for name, m in out.items():
        m = m[:n]
        hi = float(m[loud].mean()) if loud.any() else 0.0
        lo = float(m[quiet].mean()) if quiet.any() else 0.0
        scores[name] = hi / lo if lo > 1e-6 else 0.0

    rank = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    for name, r in rank:
        bar = "#" * max(0, int(round((r - 1.0) * 30)))
        print(f"  {name:<10} talk/quiet {r:5.2f}x  {bar}")

    best = rank[0]
    second = rank[1] if len(rank) > 1 else (None, 1.0)
    margin = best[1] / second[1] if second[1] > 1e-6 else 99.0
    verdict = ("CLEAR" if best[1] >= 1.25 and margin >= 1.15 else
               "WEAK" if best[1] >= 1.10 else "AMBIGUOUS")
    print(f"\n  -> {best[0]} is speaking ({verdict}: {best[1]:.2f}x its own quiet "
          f"baseline, {margin:.2f}x ahead of {second[0]})")
    if verdict != "CLEAR":
        print("     Not decisive. Try a longer span, or look at a frame yourself "
              "before trusting it.")
    print()


if __name__ == "__main__":
    main()
