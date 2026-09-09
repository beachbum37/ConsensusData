#!/usr/bin/env python3
"""
Prove a follow clip cut to the right face - by looking, in one picture.

    python3 verify_turns.py <slug>              # from the slate
    python3 verify_turns.py --start S --end E   # any span
    python3 verify_turns.py <slug> --samples 4  # denser

WHY THIS EXISTS. The turn detector reports a confidence, and on the 08.26 master
that number turned out to carry NO information about whether it was right:

    boundary set        confidence      agreement with the transcript
    tdrz marks only         69%                     43%
    + cue edges             59%                     39%
    + 5s spacing            68%                     34%
    + 8s spacing            74%                     36%

Four variants, all at or below chance for a two-person problem, and the most
confident of them was the second worst. A schedule that says 74% and is 36%
right is worse than one that admits it does not know, because the gate above it
passes. So the check cannot be a number - it has to be the frames.

AND IT HAS TO SAMPLE THE MIDDLE. Twice, edges were checked and looked right
while the turn was wrong: a handover lands near a boundary, so both mouths are
moving there, and whichever face you pull agrees with you. The error lives in
the middle of a long held turn - which is why this samples strictly inside each
turn and never within EDGE_GUARD of its ends.

Read the sheet one row at a time: the framed face is who the schedule put on
screen. If the OTHER mouth is the open one, the schedule is wrong there.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import qmclip as q
import turns as _turns

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("WLAM_WORK") or HERE)

CELL_W = 260                # each face crop, px wide
EDGE_GUARD = 1.0            # never sample this close to a turn boundary
PAD = 10
LABEL_H = 26
PICKED = (86, 214, 138)     # the tile the schedule says is talking
OTHER = (70, 74, 84)


def _font(size: int):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def sample_times(t: dict, n: int) -> list[float]:
    """Evenly spaced points strictly INSIDE the turn. See the module docstring."""
    a, b = t["start"], t["end"]
    lo, hi = a + EDGE_GUARD, b - EDGE_GUARD
    if hi <= lo:                       # a turn too short to guard - take its centre
        return [(a + b) / 2]
    return [lo + (hi - lo) * (i + 0.5) / n for i in range(n)]


def crop_face(src: Path, t: float, box: tuple[int, int, int, int],
              face, out: Path) -> bool:
    """One tile's FACE at time t. Falls back to the whole tile with no face."""
    cw, ch, cx, cy = box
    if face:
        # _face_of returns FRACTIONS OF THE TILE, not pixels - the same units
        # _mouth_roi works in. Treating them as pixels gives a zero-sized crop
        # and every cell on the sheet reads "no crop".
        fx, fy, fw, fh = face
        px, py = cx + fx * cw, cy + fy * ch
        pw, ph = fw * cw, fh * ch
        # widen a little: a mouth reads better with some chin and cheek around it
        cx, cy = int(px - pw * 0.15), int(py - ph * 0.10)
        cw, ch = int(pw * 1.30), int(ph * 1.40)
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"crop={cw}:{ch}:{max(0, cx)}:{max(0, cy)},scale={CELL_W}:-2",
         "-y", str(out)], capture_output=True)
    return r.returncode == 0 and out.exists()


def build(start: float, end: float, tiles: dict, sched: list[dict],
          out_png: Path, samples: int = 3, title: str = "") -> Path:
    src = _turns._src()
    names = list(tiles)
    faces = {n: _turns._face_of(src, start, min(end - start, 20.0), tuple(b))
             for n, b in tiles.items()}
    tmp = out_png.parent / "_vt_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    rows = []
    for ti, t in enumerate(sched):
        for si, at in enumerate(sample_times(t, samples)):
            cells = []
            for n in names:
                f = tmp / f"{ti}_{si}_{n}.png"
                cells.append(f if crop_face(src, at, tuple(tiles[n]), faces[n], f)
                             else None)
            rows.append({"at": at, "who": t["who"], "conf": t.get("confidence", 0.0),
                         "cells": cells, "turn": ti})

    if not rows:
        raise SystemExit("verify_turns: nothing to sample")

    ims = [[Image.open(c).convert("RGB") if c else None for c in r["cells"]]
           for r in rows]
    cell_h = max((im.height for row in ims for im in row if im), default=140)
    fnt, fnt_s = _font(15), _font(12)
    head = 34
    W = PAD + len(names) * (CELL_W + PAD) + 120
    H = head + len(rows) * (cell_h + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (W, H), (18, 20, 25))
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 9), title or f"{start:.1f}-{end:.1f}s   framed = who the "
                              f"schedule put on screen", font=fnt, fill=(235, 235, 235))

    y = head
    for r, row in zip(rows, ims):
        x = PAD
        for n, im in zip(names, row):
            picked = (n == r["who"])
            col = PICKED if picked else OTHER
            if im:
                sheet.paste(im, (x, y))
            else:
                d.rectangle([x, y, x + CELL_W, y + cell_h], fill=(40, 40, 46))
                d.text((x + 8, y + cell_h // 2), "no crop", font=fnt_s, fill=(150, 150, 150))
            d.rectangle([x - 2, y - 2, x + CELL_W + 2, y + cell_h + 2],
                        outline=col, width=4 if picked else 1)
            d.text((x + 2, y + cell_h + 6),
                   f"{n}{'   <= ON SCREEN' if picked else ''}", font=fnt_s,
                   fill=col if picked else (150, 150, 150))
            x += CELL_W + PAD
        d.text((x + 4, y + 6), f"t={r['at']:.1f}s", font=fnt, fill=(220, 220, 220))
        d.text((x + 4, y + 26), f"turn {r['turn'] + 1}", font=fnt_s, fill=(150, 150, 150))
        d.text((x + 4, y + 44), f"conf {r['conf']:.2f}", font=fnt_s,
               fill=(150, 150, 150))
        y += cell_h + LABEL_H + PAD

    sheet.save(out_png)
    for f in tmp.glob("*.png"):
        f.unlink()
    tmp.rmdir()
    return out_png


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args()

    start, end, title = a.start, a.end, ""
    if a.slug:
        slate = json.loads((WORK / "slate.json").read_text())
        clips = slate["clips"] if isinstance(slate, dict) else slate
        c = next((x for x in clips if x.get("slug") == a.slug), None)
        if not c:
            raise SystemExit(f"no clip {a.slug!r} in slate.json")
        start, end, title = c["start"], c["end"], a.slug
    if start is None or end is None:
        raise SystemExit("give a slug, or --start and --end")

    tiles = q.CFG.get("follow_tiles") or q.CFG.get("tiles")
    if not tiles:
        raise SystemExit("project.json has no follow_tiles - nothing to compare")

    sched = _turns.plan(start, end, tiles)
    if not sched:
        raise SystemExit("no turn schedule could be measured over this span")

    out = Path(a.out) if a.out else WORK / f"turns-{title or 'span'}.png"
    build(start, end, tiles, sched, out, a.samples,
          f"{title or ''} {start:.1f}-{end:.1f}s   framed = who the schedule "
          f"put on screen".strip())
    tot = sum(t["end"] - t["start"] for t in sched)
    conf = sum(t["confidence"] * (t["end"] - t["start"]) for t in sched) / max(1e-6, tot)
    sys.stderr.write(
        f"{len(sched)} turns, {conf * 100:.0f}% 'measured' - a number that did NOT "
        f"predict correctness on 08.26.\nRead the sheet, not the percentage: "
        f"{out}\n")
    print(out)


if __name__ == "__main__":
    main()
