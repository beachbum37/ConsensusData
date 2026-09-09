#!/usr/bin/env python3
"""
Does the camera rail hold still across this span?

A screen-share clip crops a fixed rectangle out of the camera rail. That is only
valid while the rail stays put - and it does not. The compositor RE-FLOWS: when
one person stops talking their tile is dropped and the remaining tile moves and
resizes. On one master the rail was two tiles spanning y278-801 for most of a
minute, then for twenty seconds in the middle it became a single tile at y410-669,
then it switched back.

Cropping a fixed box through that renders the speaker for part of the clip and a
BLACK GAP for the rest. It is not subtle and nothing else in the pipeline catches
it, because the layout is still "share" the whole way through - only the furniture
inside it moved.

    python3 railcheck.py 1194 1255          # is this span safe?
    python3 railcheck.py 473 1357 --windows # list stable windows in a run
    python3 railcheck.py 55 1324 --map      # what does the rail DO across a run?

Run it on any share or duo_share span before authoring a pip_crop.

--map exists because --windows can be right and useless at the same time. On the
08.21.26 McGlone master "railcheck.py 55 1324 --windows" printed "NONE. Every
stretch re-flows inside a clip's length." and stopped. That is a true answer to
the question --windows asks, and the operator still has nowhere to cut. What that
rail actually does is alternate between two STATES, both camera tiles up or one
tile re-centred, and each state holds for a long time: mapping the same range
found stable runs of 271s, 160s, 128s, 103s, 101s and 81s, every one of them long
enough to author a clip inside. --map classifies each sampled frame by the SET of
tile bands it finds, collapses consecutive identical classifications into runs,
and prints the long ones longest first with the state they sit in.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
# Per-show state follows WLAM_WORK; HERE stays the CODE directory.
# One owner for this lives in qmclip.WORK - repeated here because these
# scripts must run without importing it (analyze.py in particular, which
# would delete the transcripts it is writing).
WORK = Path(os.environ.get("WLAM_WORK") or HERE)
CFG = json.loads((WORK / "project.json").read_text())
SRC = Path(CFG["source"])

RAIL_W = 400          # how much of the frame edge the rail can occupy
GRID = 8              # quantise tile edges, so a 1px jitter is not a "change"


def rail_frames(start: float, dur: float, every: float = 1.0) -> np.ndarray:
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(SRC), "-vf",
         f"fps={1/every:.5f},crop={RAIL_W}:1080:0:0,scale={RAIL_W}:1080,format=gray",
         "-f", "rawvideo", "-"], capture_output=True)
    n = len(p.stdout) // (RAIL_W * 1080)
    if not n:
        return np.zeros((0, 1080, RAIL_W))
    return np.frombuffer(p.stdout[:n * RAIL_W * 1080],
                         dtype=np.uint8).reshape(n, 1080, RAIL_W).astype(float)


def _row_runs(frame: np.ndarray) -> list[tuple[int, int]]:
    """The lit row-runs in the rail, BEFORE neighbouring bands are merged.

    Split out of tiles() so --map can report how often the merge below fired
    without running a second tile finder over the same frames. tiles() still
    returns exactly what it always did.
    """
    occ = (frame[:, 20:RAIL_W - 60] > 26).mean(1)
    runs, st = [], None
    for y, v in enumerate(occ):
        if v > 0.55:
            if st is None:
                st = y
        else:
            if st is not None and y - st > 40:
                runs.append((st, y - 1))
            st = None
    if st is not None and len(occ) - st > 40:
        runs.append((st, len(occ) - 1))
    return runs


def _merge_runs(runs: list[tuple[int, int]]) -> tuple:
    """Collapse row-runs that belong to ONE tile, and quantise to the grid."""
    # Merge bands split by a dark stripe INSIDE one tile - a monitor edge behind
    # someone, dark headphones, a shoulder line, or a guest sitting against a DARK
    # STEP-AND-REPEAT BACKDROP, which is the case that forced this gap open. A
    # Bloomberg Intelligence backdrop is almost black except for the logos, so a
    # 259px tile came back as two fragments ~56px apart and the crop's own midpoint
    # landed in the fake gap between them - reported as "the tile left the rail" on
    # a rail that never moved.
    #
    # 90 is safe because it cannot merge two REAL tiles that this rule was not
    # already merging: stacked tiles in this rig sit ~7px apart and were always
    # collapsed into one band. What the guard actually asks is whether the band
    # holding the crop MOVES, and a genuine re-flow (two tiles at 272-800 becoming
    # one at 408-664) still shifts both edges far past the +/-16px tolerance.
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] < 90:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return tuple((a // GRID * GRID, b // GRID * GRID) for a, b in merged)


def tiles(frame: np.ndarray) -> tuple:
    """The lit row-runs in the rail, i.e. where the camera tiles actually are."""
    return _merge_runs(_row_runs(frame))


def tiles_merged(frame: np.ndarray) -> tuple[tuple, int]:
    """tiles(), plus how many bands the merge swallowed in this frame."""
    runs = _row_runs(frame)
    key = _merge_runs(runs)
    return key, len(runs) - len(key)


# How far a band edge may drift before --map calls it a DIFFERENT state.
#
# Measured on the 08.21.26 McGlone master, and the two numbers are far enough
# apart that the threshold is not a judgement call. Inside ONE state the band's
# top edge wandered 40px (416, 448, 456 on consecutive samples) because the
# speaker's backdrop is a dark Bloomberg wall and its upper rows drift in and
# out of the brightness threshold. A GENUINE re-flow - the compositor dropping
# the second tile and re-centring the first - moved the same edge 130px.
#
# Without a tolerance every one of those 40px wobbles started a new state, and
# --map answered "the longest the rail holds one state is 41s" on a run that
# actually holds still for 271s. That is the same right-and-useless answer
# --windows gives, which is the whole reason --map was added, so the tolerance
# is not a nicety here - the flag does not work without it.
MAP_TOL = 64


def _same_state(a: tuple, b: tuple, tol: int = MAP_TOL) -> bool:
    """True when two frames' band sets are the same rail, within MAP_TOL."""
    if len(a) != len(b):
        return False
    return all(abs(x0 - y0) <= tol and abs(x1 - y1) <= tol
               for (x0, x1), (y0, y1) in zip(a, b))


def _state_names(runs: list) -> dict:
    """Name each distinct rail state in the order the run first shows it."""
    names: dict = {}
    for _, _, k, _ in runs:
        if k not in names:
            i = len(names)
            names[k] = chr(ord("A") + i) if i < 26 else f"S{i}"
    return names


def show_map(runs: list, start: float, end: float, every: float, floor: float,
             merged_frames: int, samples: int) -> None:
    """Print what the rail DOES across the run: its states, and where each holds.

    Written on 08.21.26 after --windows answered "NONE. Every stretch re-flows
    inside a clip's length." on a range that in fact contained 271s, 160s, 128s,
    103s, 101s and 81s of held-still rail. --windows asks "is any single stretch
    long enough", and when the rail alternates between two states the answer is
    no while the material is fine. This asks the other question: which state is
    the rail in, and for how long at a time.
    """
    names = _state_names(runs)
    print(f"\nRAIL STATE MAP   {SRC.name}   {start:.0f}-{end:.0f}, "
          f"sampled every {every:.1f}s\n")

    print("   STATES (a state is the SET of tile bands found in a frame):")
    for k, name in names.items():
        held = [r for r in runs if r[2] == k]
        bands = ", ".join(f"y{a}-{b}" for a, b in k) or "none lit"
        print(f"     {name}  {len(k)} band(s)  {bands:<34} "
              f"held {sum(r[3] for r in held):5.0f}s over {len(held)} stretch(es)")

    keep = sorted((r for r in runs if r[3] >= floor), key=lambda r: -r[3])
    print(f"\n   STRETCHES >= {floor:.0f}s, LONGEST FIRST:")
    for s, e, k, d in keep:
        print(f"     {s:7.0f} - {e:7.0f}  ({d:5.0f}s)  {names[k]}  "
              f"tiles={list(k)}")
    if not keep:
        # Still say what the best of a bad run was. Handing back nothing is the
        # thing this mode was written to stop doing.
        s, e, k, d = max(runs, key=lambda r: r[3])
        print(f"     none. The longest the rail holds one state is {d:.0f}s, "
              f"{s:.0f}-{e:.0f} in state {names[k]}.")

    if merged_frames:
        # The same caveat check_rail prints. Stacked tiles in this rig sit ~7px
        # apart, and a guest against a dark step-and-repeat backdrop splits ONE
        # tile into fragments, so both cases arrive here as a merge.
        print(f"\n   note: the tile finder merged neighbours in {merged_frames} of "
              f"{samples} sampled frames, so a band above can be more than one "
              f"tile. What matters here is that the band HOLDS STILL, not how "
              f"many people are inside it.")
    print(f"\n   Author a span inside one stretch, then let PREFLIGHT rule on it:\n"
          f"     python3 preflight.py\n"
          f"   Preflight is the authority and it is FINER than anything this file\n"
          f"   prints on its own, because it is the only one that knows the\n"
          f"   authored pip_crop. When the discovered band is more than 1.6x the\n"
          f"   height of that crop, check_rail measures the CROP's own edges\n"
          f"   instead of the merged band's. Measured on the 08.21.26 McGlone\n"
          f"   master: the span 523.6-617.11 shipped, and preflight passed it as\n"
          f"   \"cropped tile holds still\", while a bare\n"
          f"   \"railcheck.py 523.6 617.11\" on the same span reports it\n"
          f"   re-flowing 28 times. Both are honest about what they measure. Use\n"
          f"   this map to find WHERE to look, never to rule a span out.\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--windows", action="store_true",
                    help="list stable sub-windows instead of judging the span")
    ap.add_argument("--map", action="store_true",
                    help="map the rail's states and where each one holds, "
                         "longest first - use when --windows finds nothing")
    ap.add_argument("--min", type=float, default=46.0,
                    help="shortest window worth reporting")
    a = ap.parse_args()

    seq = rail_frames(a.start, a.end - a.start, a.every)
    if len(seq) < 2:
        raise SystemExit("could not decode the rail - check the span")
    detail = [tiles_merged(f) for f in seq]
    keys = [d[0] for d in detail]

    # --map compares each frame against the ANCHOR of the run it is in, within
    # MAP_TOL, so brightness wobble does not shred a stable stretch. Every other
    # mode keeps the exact-equality test it has always used: --windows and the
    # default report is what feeds check_rail, and loosening those would let a
    # real re-flow through.
    same = (lambda x, y: _same_state(x, y)) if a.map else (lambda x, y: x == y)
    runs, st = [], 0
    for i in range(1, len(keys) + 1):
        if i == len(keys) or not same(keys[i], keys[st]):
            runs.append((a.start + st * a.every, a.start + i * a.every,
                         keys[st], (i - st) * a.every))
            st = i

    if a.map:
        show_map(runs, a.start, a.end, a.every, a.min,
                 sum(1 for _, m in detail if m), len(detail))
        return

    if a.windows:
        print(f"\nSTABLE-RAIL WINDOWS >= {a.min:.0f}s in {a.start:.0f}-{a.end:.0f}:\n")
        keep = [r for r in runs if r[3] >= a.min]
        for s, e, k, d in keep:
            print(f"   {s:7.0f} - {e:7.0f}  ({d:5.0f}s)  tiles={list(k)}")
        if not keep:
            print("   NONE. Every stretch re-flows inside a clip's length.")
        print()
        return

    print(f"\n{SRC.name}   rail across {a.start:.1f}-{a.end:.1f}\n")
    for s, e, k, d in runs:
        print(f"   {s:7.1f} - {e:7.1f}  ({d:4.0f}s)  tiles={list(k)}")
    if len(runs) == 1:
        print("\n  -> STABLE. A fixed pip_crop is safe here.\n")
    else:
        print(f"\n  -> RE-FLOWS {len(runs) - 1} time(s). A fixed pip_crop will show the "
              f"speaker for part of this span and a BLACK GAP for the rest.\n"
              f"     Pick a span inside one of the stretches above, or run with "
              f"--windows over the whole run to find one.\n")


if __name__ == "__main__":
    main()
