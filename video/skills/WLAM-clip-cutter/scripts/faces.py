#!/usr/bin/env python3
"""
Where the face is, so crops stop being hand-tuned.

    python3 faces.py video.mp4 [x0 x1] [at]

Uses OpenCV's bundled frontal-face cascade over a handful of sampled frames and
keeps the median box. Two heuristics were tried first and both are recorded here
because they look reasonable and are not:

    motion alone      a talking head moves and a wall does not - but a TV, a
                      ticker board or a live scoreboard behind the speaker moves
                      more, and the box lands on that.
    motion x skin     cancels the scoreboard, but a neck, a hand resting on a
                      chin and a lit collar are all moving skin. On a real clip
                      the peak landed on the speaker's collar, not his face.

A cascade is not clever but it is looking for a face rather than for a proxy, and
that is the difference. It is pinned to opencv-python-headless<5 because 5.0
dropped CascadeClassifier and ships no cascade data.

Sampling several frames and taking the median matters: any single frame can catch
a blink, a turn away, or a hand across the mouth, and one bad frame would place
the crop for the whole clip.
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np

try:
    import cv2
except ImportError:                                    # pragma: no cover
    cv2 = None

# Set once, so the warning below is printed a single time per run rather than
# once per crop hint.
CV2_MISSING_WARNED = False

SAMPLES = 14
GRID = 480          # detect at this width; cascades want a modest resolution


def _sample(src: str, x0: int, x1: int, at: float, dur: float,
            h: int) -> tuple[np.ndarray, float]:
    w = x1 - x0
    gh = int(round(GRID * h / w))
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-t", f"{dur:.2f}",
         "-i", src, "-vf",
         f"fps={SAMPLES / max(dur, 1):.3f},crop={w}:{h}:{x0}:0,"
         f"scale={GRID}:{gh},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    n = len(p.stdout) // (GRID * gh)
    if not n:
        return np.zeros((0, gh, GRID), dtype=np.uint8), w / GRID
    return (np.frombuffer(p.stdout[:n * GRID * gh], dtype=np.uint8)
              .reshape(n, gh, GRID)), w / GRID


def face_box(src: str, x0: int, x1: int, at: float = 0.0, dur: float = 20.0,
             h: int = 1080) -> tuple[int, int, int, int] | None:
    """
    (left, top, right, bottom) of the FACE inside [x0, x1), in source pixels -
    brow to chin, ear to ear - or None when no face is convincingly there.
    """
    if cv2 is None:
        global CV2_MISSING_WARNED
        if not CV2_MISSING_WARNED:
            CV2_MISSING_WARNED = True
            sys.stderr.write(
                "WARNING: opencv is not installed for this interpreter, so the crop "
                "hints below are a GEOMETRIC GUESS, not a face detection.\n"
                "         Check every crop against a real frame before rendering, or "
                f"install it:  {sys.executable} -m pip install 'opencv-python-headless<5'\n")
        return None
    frames, scale = _sample(src, x0, x1, at, dur, h)
    if not len(frames):
        return None
    det = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if det.empty():
        return None

    hits = []
    for f in frames:
        found = det.detectMultiScale(cv2.equalizeHist(f), scaleFactor=1.12,
                                     minNeighbors=6,
                                     minSize=(int(GRID * 0.10),) * 2)
        if len(found):
            # the largest face in the column is the speaker; anything smaller is
            # a picture on the wall or someone on a screen behind them
            bx, by, bw, bh = max(found, key=lambda r: r[2] * r[3])
            hits.append([bx, by, bw, bh])
    if len(hits) < 3:
        return None

    bx, by, bw, bh = np.median(np.array(hits, float), axis=0)
    # The RAW face rect, unpadded and unclamped: brow to chin, ear to ear. Callers
    # need it raw. Padding it to a head here and clamping to the frame destroyed
    # the only thing worth knowing on a close-up - a box clamped to 0..1080 has a
    # meaningless centre and a meaningless chin, and crops placed off it sat 200px
    # low on every close-up speaker.
    return (int(x0 + bx * scale), int(by * scale),
            int(x0 + (bx + bw) * scale), int((by + bh) * scale))


def crop_for(src: str, x0: int, x1: int, aspect: float, at: float = 0.0,
             dur: float = 20.0, h: int = 1080,
             headroom: float = 0.08) -> list[int] | None:
    """
    A [w, h, x, y] box of the given aspect, framed on the face in this column.

    Takes the largest box of that aspect the column allows, centres it on the face
    horizontally, and places it so the head keeps a little headroom - which is
    where a portrait wants a head, and what every hand-tuned crop in this skill
    converged on anyway. Clamped so it never runs outside the column.
    """
    box = face_box(src, x0, x1, at, dur, h)
    if not box:
        return None
    fl, ft, fr, fb = box
    avail = x1 - x0

    ch = min(h, int(round(avail / aspect)))
    cw = int(round(ch * aspect))
    if cw > avail:
        cw = avail
        ch = int(round(cw / aspect))

    cx = int((fl + fr) / 2 - cw / 2)
    cx = max(x0, min(cx, x1 - cw))
    # Put the face centre a little above the crop's middle. Anchoring on an edge
    # (top for headroom, bottom for the chin) breaks the moment the head is bigger
    # than the crop, which is most close-ups; a centre cannot break that way.
    cy = int((ft + fb) / 2 - ch * (0.5 - headroom))
    cy = max(0, min(cy, h - ch))
    return [cw, ch, cx, cy]


if __name__ == "__main__":
    v = sys.argv[1]
    a = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    b = int(sys.argv[3]) if len(sys.argv) > 3 else 1920
    t = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    print("face box:", face_box(v, a, b, t))
    print("9:16 crop:", crop_for(v, a, b, 1080 / 1920, t))
