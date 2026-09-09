#!/usr/bin/env python3
"""
Step 1 of the clip pipeline: look at a long-form video and write everything the
rest of the pipeline needs.

    python3 analyze.py /path/to/webinar.mp4 [--out ~/Desktop/"My Clips"]

Produces, next to this script:
    project.json    source path, frame rate, crops, output dir
    audio16k.wav    16kHz mono, what whisper wants
    transcript.srt  segment-level, properly punctuated
    transcript_compact.txt   [MM:SS] per line - this is what you read to pick clips
    cues.json       the punctuation reference restore_case() aligns against
    sections.json   which stretches are two_up / screen share / single camera

Nothing here is specific to one video. Two things are worth eyeballing after it
runs:

  - sections.json. A `two_up` run means two speakers side by side and is found
    from the dark divider at frame centre, which is reliable. A `share` run is
    found from a bright strip along the top, which is true of Zoom/Meet/Teams
    screen shares and ALSO true of a guest sitting in front of a sunlit window -
    so check those against a real frame.
  - the crop hints, if this is a two-up. They are starting points, not
    answers: head_crop_left / head_crop_right keep each half whole (tighten for
    a bigger face), and duo_crops stacks both for mode "duo".
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

import faces

HERE = Path(__file__).resolve().parent
# Per-show state follows WLAM_WORK; HERE stays the CODE directory.
# One owner for this lives in qmclip.WORK - repeated here because these
# scripts must run without importing it (analyze.py in particular, which
# would delete the transcripts it is writing).
WORK = Path(os.environ.get("WLAM_WORK") or HERE)
DEFAULT_MODEL = Path.home() / "tableflip-app/data/models/ggml-large-v3-turbo.bin"

# The panel's aspect, which every crop this script suggests has to match. It is
# the WHOLE FRAME now (qmclip.PANEL_W / PANEL_H = 1080/1920), not the 1080x1560
# box it was when captions lived in a band underneath the picture.
#
# Written out rather than imported. Importing qmclip has a side effect: when the
# master's audio hash does not match, it deletes cues.json, sections.json and the
# transcripts - which are exactly the files this script is in the middle of
# producing. If you change PANEL_H in qmclip.py, change this line with it.
PANEL_AR = 1080 / 1920


def _face_crop_x(src: str, info: dict) -> int | None:
    """x for the default head window that CENTRES the speaker. None if unsure."""
    try:
        import faces
        w, h = int(info["w"]), int(info["h"])
        cw = min(w, round(h * PANEL_AR))
        fb = faces.face_box(str(src), 0, w, at=max(0.0, info.get("dur", 60) * 0.1),
                            dur=20.0, h=h)
        if not fb:
            return None
        return max(0, min(int(round((fb[0] + fb[2]) / 2 - cw / 2)), w - cw))
    except Exception:                                            # noqa: BLE001
        return None


def vad_args(model: Path) -> list[str]:
    """
    whisper.cpp's Silero VAD flags, or nothing if the weights are not installed.

    Duplicated from qmclip.vad_args rather than imported, for the same reason
    PANEL_AR above is: importing qmclip deletes the transcripts this script is in
    the middle of writing. Keep the two in step.
    """
    vm = model.parent / "ggml-silero-v5.1.2.bin"
    return ["--vad", "-vm", str(vm)] if vm.exists() else []


def run(cmd: list[str], **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        sys.stderr.write(f"\nFAILED: {' '.join(map(str, cmd))}\n{p.stderr[-2500:]}\n")
        raise SystemExit(1)
    return p


def probe(src: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate",
               "-show_entries", "format=duration",
               "-of", "json", str(src)]).stdout
    d = json.loads(out)
    # SAY WHAT IS WRONG WITH THE FILE, rather than dying on a raw IndexError six
    # frames into the traceback. An audio-only master (a podcast .m4a, an
    # exported voice track) makes ffprobe return `{"streams": []}`, and a still
    # image has no duration - both are things somebody will hand this pipeline,
    # and neither is a bug in the pipeline.
    if not d.get("streams"):
        raise SystemExit(
            f"\n{src.name} has no video stream. This rig cuts PICTURE - an "
            f"audio-only master cannot be clipped.\n")
    st = d["streams"][0]
    if "duration" not in d.get("format", {}):
        raise SystemExit(
            f"\n{src.name} has no duration. A still image or a stream capture "
            f"without a container duration cannot be cut into clips.\n")
    try:
        num, den = str(st.get("r_frame_rate", "")).split("/")
        fps = round(float(num) / float(den))
    except (ValueError, ZeroDivisionError):
        raise SystemExit(
            f"\n{src.name} reports an unusable frame rate "
            f"({st.get('r_frame_rate')!r}). Re-encode it to a constant rate "
            f"first: ffmpeg -i in -r 30 -c:v libx264 -crf 18 out.mp4\n")
    return {"w": st["width"], "h": st["height"], "fps": fps,
            "dur": float(d["format"]["duration"])}


def _runs(marks: list[str], dur: float, min_len: int = 20) -> list[dict]:
    """Collapse per-second marks into runs, dropping flashes shorter than 20s."""
    runs, cur, start = [], None, 0
    for i, m in enumerate(marks):
        if m != cur:
            if cur is not None:
                runs.append({"mode": cur, "start": start, "end": i})
            cur, start = m, i
    if cur is not None:
        runs.append({"mode": cur, "start": start, "end": len(marks)})
    return [r for r in runs if r["end"] - r["start"] >= min_len] or \
           [{"mode": "head", "start": 0, "end": int(dur)}]


def column_profiles(src: Path, w: int) -> np.ndarray:
    """One full-width column luma profile per second, over a mid-height band."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-vf",
         f"fps=1,crop={w}:600:0:200,scale={w}:60,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    size = w * 60
    n = len(p.stdout) // size
    if not n:
        return np.zeros((0, w))
    return np.frombuffer(p.stdout[:n * size], dtype=np.uint8) \
             .reshape(n, 60, w).astype(float).mean(axis=1)


def thumbs(src: Path) -> np.ndarray:
    """One 192x108 greyscale thumbnail per second."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-vf",
         "fps=1,scale=192:108,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    n = len(p.stdout) // (192 * 108)
    if not n:
        return np.zeros((0, 108, 192))
    return np.frombuffer(p.stdout[:n * 192 * 108], dtype=np.uint8) \
             .reshape(n, 108, 192).astype(float)


def find_seam(prof: np.ndarray, w: int) -> int | None:
    """
    The compositor's vertical divider, as a sharp LOCAL MINIMUM near centre.

    Measured as a minimum rather than a contiguous dark run: a run walks outward
    into whatever else is dark at the inner edge of a speaker's half - dark hair,
    a shoulder, a framed picture - and on this master reported a 167px divider
    where the real one is about 10px, which would have cropped away a sixth of
    the left speaker.
    """
    mid = w // 2
    lo, hi = mid - int(w * 0.06), mid + int(w * 0.06)
    x = lo + int(np.argmin(prof[lo:hi]))
    ref = float(np.concatenate([prof[x - 40:x - 10], prof[x + 11:x + 41]]).mean())
    if prof[x] >= ref - 25:
        return None
    return x


def app_signature(src: Path, w: int, h: int) -> list[tuple[float, float]]:
    """
    Per second: (mean luma, longest straight UI line) over the middle of frame.

    This is what actually separates a shared application from a camera, and it is
    a property of software rather than of lighting: an app draws long unbroken
    straight edges - window chrome, table rules, chart gridlines, axes - that run
    most of the way across the frame. A room does not, whatever its brightness.

    Brightness was tried first and cannot do it. A dark terminal and an unlit room
    look identical to it; so do browser chrome and a white wall. Both misfired on
    real masters, in both directions.

    Streamed a frame at a time: an hour of 560x360 greyscale would be half a
    gigabyte held at once, and all that is needed per second is two numbers.
    """
    cw, ch = 560, 360
    x0, y0 = int(w * 0.25), int(h * 0.08)
    crop_w, crop_h = int(w * 0.72), int(h * 0.84)
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(src), "-vf",
         f"fps=1,crop={crop_w}:{crop_h}:{x0}:{y0},scale={cw}:{ch},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    out: list[tuple[float, float]] = []
    size = cw * ch
    assert p.stdout is not None
    while True:
        buf = p.stdout.read(size)
        if not buf or len(buf) < size:
            break
        f = np.frombuffer(buf, dtype=np.uint8).reshape(ch, cw).astype(float)
        gx = np.abs(np.diff(f, axis=1))
        gy = np.abs(np.diff(f, axis=0))
        line = max(float((gx > 18).mean(axis=0).max()),
                   float((gy > 18).mean(axis=1).max()))
        out.append((float(f.mean()), line))
    p.stdout.close()
    p.wait()
    return out


def step_at(prof: np.ndarray, x: int, pad: int = 3) -> float:
    """
    Size of the vertical brightness STEP at column x.

    An absolute step, not a dark dip. `rail_gutter` looks for darkness, which is
    the right test for a gutter but blind to a boundary between two lit tiles -
    and a gallery view is exactly that. This measure catches both.
    """
    if x - pad - 1 < 0 or x + pad + 1 >= len(prof):
        return 0.0
    return float(abs(prof[x + 1:x + pad].mean() - prof[x - pad:x - 1].mean()))


def layout_edges(prof: np.ndarray, w: int) -> tuple[float, float]:
    """
    (rail edge, gallery edge) for one frame.

    A SCREEN SHARE has one hard vertical boundary between the camera rail and the
    app, somewhere in the outer fifth of the frame. A GALLERY has boundaries at
    the thirds instead and nothing at the rail. Comparing the two is what
    separates them, and the ratio is decisive on real footage: a share reads
    about 30 versus 3, a gallery about 7 versus 125.

    The old test asked "is there a shared app" from brightness and line length
    alone, and it labelled a 76 second three-across gallery as a screen share -
    which would have cropped the camera rail out of frames that have no rail.
    """
    rail = 0.0
    for lo, hi in ((int(w * 0.08), int(w * 0.27)),
                   (int(w * 0.73), int(w * 0.92))):
        for x in range(lo, hi):
            rail = max(rail, step_at(prof, x))
    span = max(2, int(w * 0.015))
    gal = 0.0
    for c in (w // 3, 2 * w // 3):
        for x in range(c - span, c + span):
            gal = max(gal, step_at(prof, x))
    return rail, gal


def rail_gutter(prof: np.ndarray, w: int) -> tuple[float, int]:
    """
    Strength of the hard vertical gutter between a PIP rail and a shared app.

    The dark-bulk test alone is not enough to call a screen share: a speaker in a
    dark room, or one sitting in front of an unlit TV, also makes the frame dark
    with a brighter strip down one side. What a real composited rail has and a room
    does not is a HARD edge at a fixed x. Measured over the whole rail-edge zone
    rather than at an assumed position, because the rail's width varies per show.

    Separates cleanly on real footage: a dark room scores 11 to 21, a genuine
    share 23 to 119.
    """
    lo, hi = int(w * 0.08), int(w * 0.27)
    best, at = 0.0, lo
    for x in range(lo, hi):
        near = np.concatenate([prof[max(0, x - 30):x - 6], prof[x + 7:x + 31]])
        drop = float(near.mean() - prof[x - 3:x + 4].min())
        if drop > best:
            best, at = drop, x
    # mirror, for a rail on the right-hand side
    lo2, hi2 = int(w * 0.73), int(w * 0.92)
    for x in range(lo2, hi2):
        near = np.concatenate([prof[x - 30:x - 6], prof[x + 7:min(w, x + 31)]])
        drop = float(near.mean() - prof[x - 3:x + 4].min())
        if drop > best:
            best, at = drop, x
    return best, at


def tile_rows(col: np.ndarray) -> list[tuple[int, int]]:
    """Lit row-runs inside a PIP column, i.e. the individual camera tiles."""
    lit = col > 30
    runs, cur, st = [], False, 0
    for y in range(len(lit)):
        if lit[y] != cur:
            if cur:
                runs.append((st, y))
            cur, st = lit[y], y
    if cur:
        runs.append((st, len(lit)))
    return [(a, b) for a, b in runs if b - a >= 80]


def half_crop(w: int, h: int, x0: int, x1: int) -> list[int]:
    """
    Biggest panel-aspect box inside one half of a two-up.

    PANEL_AR is 9:16 now, not the 9:10 this was written for. That makes the box
    noticeably narrower - 608px out of a 1080-tall master rather than 972 - which
    is a BIGGER face, and is the point. It also means a wide lower-third name
    badge is more likely to be trimmed, so check the badge text against the crop
    rather than assuming it survived.

    Bottom-aligned on purpose: a two-up almost always burns that badge into the
    bottom of each half, and keeping it means the speaker is attributed on screen
    for free. Tighten it later for a bigger face - keep the bottom at frame
    height, shrink the height, recompute width as PANEL_AR x height, and centre x
    on the face, checking the badge TEXT still fits.
    """
    avail = x1 - x0
    ch = min(h, int(round(avail / PANEL_AR)))
    cw = int(round(ch * PANEL_AR))
    return [cw, ch, x0 + (avail - cw) // 2, h - ch]


def face_row(src: Path, x0: int, x1: int, at: float, h: int) -> int:
    """
    Where the face sits vertically in one half, from motion energy.

    Measured rather than assumed. A fixed "faces sit in the upper third" offset was
    tried first and cropped both speakers' mouths off on the very next master - how
    high someone sits in frame is a property of their webcam, not a constant. The
    search is limited to the top 72% so a name badge, a ticker crawl or a desk does
    not pull the estimate down.
    """
    w = x1 - x0
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-t", "24", "-i", str(src),
         "-vf", f"fps=2,crop={w}:{h}:{x0}:0,scale=120:135,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    n = len(p.stdout) // (120 * 135)
    if n < 3:
        return int(h * 0.42)
    F = np.frombuffer(p.stdout[:n * 120 * 135], dtype=np.uint8) \
          .reshape(n, 135, 120).astype(float)
    mot = np.abs(np.diff(F, axis=0)).mean(axis=0)
    rows = mot[:int(135 * 0.72), :].mean(axis=1)
    if rows.max() <= 0:
        return int(h * 0.42)
    weight = np.clip(rows - np.percentile(rows, 60), 0, None)
    if weight.sum() <= 0:
        return int(h * 0.42)
    centre = float((np.arange(len(weight)) * weight).sum() / weight.sum())
    return int(centre / 135 * h)


def band_crop(x0: int, x1: int, h: int, aspect: float,
              face_y: int | None = None) -> list[int]:
    """
    Widest band of the given aspect inside one half of a two-up, for mode "duo".

    Positioned so the measured face centre sits a little above the band's middle,
    which is where a head wants to be in a letterbox.
    """
    cw = x1 - x0
    ch = int(round(cw / aspect))
    if ch > h:
        ch = h
        cw = int(round(ch * aspect))
    fy = face_y if face_y is not None else int(h * 0.42)
    # Face a little above the band's middle, but not much: at 0.46 the chin
    # of a speaker who sits low in frame lands on the bottom edge.
    y = int(fy - ch * 0.36)
    return [cw, ch, x0 + (x1 - x0 - cw) // 2, max(0, min(y, h - ch))]


def _guess_show(src) -> str:
    """A readable programme name from the master's filename, to be corrected."""
    import re as _re
    stem = _re.sub(r"[_\s]+", " ", Path(src).stem)
    stem = _re.sub(r"\(\d+\)\s*$", "", stem)              # "(3)" from a re-download
    stem = _re.sub(r"\b\d{1,2}[._/]\d{1,2}[._/]\d{2,4}\b", "", stem)   # the date
    return _re.sub(r"\s{2,}", " ", stem).strip(" -_!.")[:60]


def _guess_date(src) -> str:
    """The date in the master's filename, as written, or empty."""
    import re as _re
    m = _re.search(r"\b(\d{1,2})[._/](\d{1,2})[._/](\d{2,4})\b", Path(src).stem)
    return f"{m[1]}.{m[2]}.{m[3]}" if m else ""


def detect_sections(src: Path, dur: float, w: int,
                    h: int = 1080) -> tuple[list[dict], dict]:
    """
    Classify each second as two_up, screen share, or single camera.

    Three tests, and the ORDER matters:

      1. two_up  - a sharp dark divider near frame centre. Structural, so it is
                   the most reliable signal available; it wins outright.
      2. share   - a shared application. Detected two ways, because one is not
                   enough: a LIGHT app (a browser) puts a bright low-variance
                   strip along the top, while a DARK app (a trading terminal, a
                   dark dashboard) does the opposite and makes the bulk of the
                   frame dark with the camera tiles the only lit thing in it.
      3. head    - anything else: one camera, full frame.

    Both share tests were needed on real footage. The bright-top-strip test alone
    labelled a guest backlit by a window as a screen share (false positive) and
    missed 25 minutes of a dark trading platform (false negative).
    """
    prof = column_profiles(src, w)
    sig = app_signature(src, w, h)
    n = min(len(prof), len(sig))

    marks: list[str] = []
    seams: list[int] = []
    for i in range(n):
        seam = find_seam(prof[i], w)
        centred = seam is not None and abs(seam - w // 2) < w * 0.06
        lum, line = sig[i]
        rail, gal = layout_edges(prof[i], w)
        # A centred dark seam no longer wins outright. A SLIDE inset in a dark
        # frame has a hard vertical border too, and on one master it sat at x1059
        # and turned six minutes of PowerPoint into a "two_up" - which would have
        # cropped two speaker halves out of a deck. A real two-up is two camera
        # feeds: its rail-zone edge is modest (about 27 measured), while the slide
        # frame's is enormous (196). So an overwhelming rail edge overrides the
        # seam; a normal one does not.
        if centred and not (rail > 60 and rail > gal * 2.5):
            marks.append("two_up")
            seams.append(seam)
            continue
        looks_shared = line >= 0.90 or (lum < 45 and line >= 0.55)
        if gal > rail * 1.3 and gal >= 20:
            # thirds dominate: a gallery of faces, NOT a share, whatever the
            # brightness test thinks
            marks.append("gallery")
        elif looks_shared or rail > gal * 1.3:
            marks.append("share")
        else:
            marks.append("head")

    runs = _runs(marks, dur)
    hints: dict = {}
    # Gate the hints on a surviving RUN, not on raw per-second marks: a handful of
    # scattered seconds that _runs() discards as noise would otherwise announce a
    # two-up that the section map does not contain.
    if seams and any(r["mode"] == "two_up" for r in runs):
        seam = int(np.median(seams))
        hints["two_up_seam"] = seam
        hints["head_crop_left"] = half_crop(w, h, 0, seam - 5)
        hints["head_crop_right"] = half_crop(w, h, seam + 6, w)
        # And the pair for mode "duo", both speakers stacked. With the panel at
        # full 9:16 each band is nearly square, so these crops match the BAND's
        # aspect (1080/953 = 1.133), not the panel's 0.5625 - filling a
        # full-height half into a 1.13 band would squash the face.
        sample = next((i for i, m in enumerate(marks) if m == "two_up"), 0)
        at = float(sample) + 2.0
        # Crops come from an actual face detection now, not from a motion proxy.
        # PANEL is the whole 1080x1920 frame, so a duo band is (1920-14)/2 = 953.
        # These MUST track qmclip.PANEL_H / SPLIT_GAP. They are written out rather
        # than imported because importing qmclip clears the transcript artefacts
        # this script is in the middle of producing.
        panel_ar, band_ar = 1080 / 1920, 1080 / 953
        auto_l = faces.crop_for(str(src), 0, seam - 5, band_ar, at, 18.0, h)
        auto_r = faces.crop_for(str(src), seam + 6, w, band_ar, at, 18.0, h)
        if auto_l and auto_r:
            hints["duo_crops"] = [auto_l, auto_r]
        else:
            hints["duo_crops"] = [band_crop(0, seam - 5, h, band_ar),
                                  band_crop(seam + 6, w, h, band_ar)]
        hl = faces.crop_for(str(src), 0, seam - 5, panel_ar, at, 18.0, h)
        hr = faces.crop_for(str(src), seam + 6, w, panel_ar, at, 18.0, h)
        if hl:
            hints["head_crop_left"] = hl
        if hr:
            hints["head_crop_right"] = hr

    share_idx = ([i for i, m in enumerate(marks) if m == "share"]
                 if any(r["mode"] == "share" for r in runs) else [])
    if share_idx:
        # Which side the camera rail sits on, from the averaged column profile of
        # the share seconds: the rail is camera, so it is brighter than the app.
        avg = prof[np.array(share_idx)].mean(axis=0)
        mid = avg[int(w * 0.35):int(w * 0.65)].mean()
        left = avg[int(w * 0.01):int(w * 0.16)].mean() - mid
        right = avg[int(w * 0.84):int(w * 0.99)].mean() - mid
        side = "left" if left >= right else "right"
        hints["pip_side"] = side
        # Measure the rail's real width and its tiles at full resolution.
        i0 = share_idx[len(share_idx) // 2]
        rail_prof = prof[i0]
        if side == "left":
            edge = next((x for x in range(int(w * 0.10), int(w * 0.35))
                         if rail_prof[x] < 30), int(w * 0.19))
            rail_box = (8, edge - 4)
        else:
            edge = next((x for x in range(int(w * 0.90), int(w * 0.65), -1)
                         if rail_prof[x] < 30), int(w * 0.81))
            rail_box = (edge + 4, w - 8)
        hints["pip_rail_x"] = list(rail_box)
        hints["share_crop_hint"] = ("crop the shared app to its CONTENT from "
                                    "outside the rail - the face band absorbs "
                                    "whatever height is left, so the app is never "
                                    "trimmed to an aspect; check a real frame")
    return runs, hints


# Seconds of audio per reference decode.
#
# Back to 90 from 45. The lowercase collapse is what drove it down, and shorter
# windows were never a reliable fix - one stretch came back flat at 45s, at 32s AND
# at 18s. The CASING PROMPT in _decode_healthy is the actual remedy, and it runs
# before any splitting. At 45s a 65-minute master needed 87 whisper passes with 42
# re-decodes on top; at 90s it is 44, which halves the slowest step in the pipeline
# for no loss of quality.
REF_CHUNK = 90.0


def _rms(wav: Path, hop: float = 0.01) -> np.ndarray:
    """Short-time RMS of the whole file, for picking quiet split points."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-ac", "1",
                        "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
    a = np.frombuffer(p.stdout, dtype="<i2").astype(float) / 32768
    n = int(hop * 16000)
    if len(a) < n:
        return np.zeros(1)
    fr = a[:len(a) // n * n].reshape(-1, n)
    return np.sqrt((fr ** 2).mean(1))


def _split_points(wav: Path, dur: float, chunk: float = REF_CHUNK) -> list[float]:
    """
    Chunk boundaries at the quietest moment near each target, so a split never
    lands mid-word.
    """
    env = _rms(wav)
    hop = 0.01
    bounds, t = [0.0], 0.0
    while dur - t > chunk * 1.4:
        target = t + chunk
        lo = max(1, int((target - 6.0) / hop))
        hi = min(len(env) - 1, int((target + 6.0) / hop))
        t = (lo + int(np.argmin(env[lo:hi]))) * hop if hi > lo else target
        bounds.append(t)
    bounds.append(dur)
    return bounds


def _stamp(s: float) -> str:
    # Round ONCE, in milliseconds, then decompose. Truncating the seconds with
    # int() while rounding the milliseconds separately lets a fraction >= .9995
    # emit a FOUR-DIGIT millisecond field - 21.9997 came out "00:00:21,1000" -
    # which is not a legal SubRip stamp. Five delivered .srt files carry one.
    # It also fixes the seconds: 59.9997 belongs at 00:01:00,000, not 00:00:59.
    # The trigger is any non-integer-millisecond time, which the adaptive tempo
    # produces on every cue it touches.
    ms = int(round(max(0.0, s) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _healthy(segs: list[tuple[float, float, str]], window: float = 30.0) -> bool:
    """
    Did this chunk come back as real prose, or did whisper collapse?

    The failure is text returning lowercase with no sentence ends. It is
    INTERMITTENT - the identical audio re-decodes correctly - so it is worth
    simply asking again.

    Judged in SUB-WINDOWS, not over the chunk as a whole. A chunk that starts
    clean and collapses halfway through averages out to a passing score and slips
    past: on one master a chunk read fine until "because when I was on the trading
    floor" and was flat lowercase from there to the end, which is exactly the part
    a clip was cut from. Every window has to stand on its own.
    """
    if not segs:
        return True
    t0 = segs[0][0]
    buckets: dict[int, list[str]] = {}
    for a, _b, text in segs:
        buckets.setdefault(int((a - t0) // window), []).append(text)
    for parts in buckets.values():
        text = " ".join(parts)
        words = text.split()
        if len(words) < 20:
            continue                     # too little to judge; do not loop on it
        caps = sum(1 for w in words if re.search(r"[A-Z]", w)) / len(words)
        if caps < 0.03 or not re.search(r"[.!?]", text):
            return False
    return True


CASING_PROMPT = ("The following is a clean transcript with correct capitalization "
                 "and punctuation, including question marks.")


def _decode(wav: Path, model: Path, a: float, b: float, stem: Path,
            tag: str, prompt: str | None = None) -> list[tuple[float, float, str]]:
    """One whisper pass over [a, b), returned in SOURCE time."""
    piece = stem.with_name(stem.name + "_p.wav")
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
         "-i", str(wav), "-c", "copy", str(piece)])
    cmd = ["whisper-cli", "-m", str(model), "-f", str(piece), "-l", "en",
           *vad_args(model), "-oj", "-of", str(stem), "--no-prints"]
    if prompt:
        cmd += ["--prompt", prompt]
    run(cmd)
    out: list[tuple[float, float, str]] = []
    jf = stem.with_suffix(".json")
    if jf.exists():
        for seg in json.loads(jf.read_text()).get("transcription", []):
            t = seg["text"].strip()
            if t:
                out.append((a + seg["offsets"]["from"] / 1000.0,
                            a + seg["offsets"]["to"] / 1000.0, t))
        jf.unlink(missing_ok=True)
    piece.unlink(missing_ok=True)
    return out


def _decode_healthy(wav: Path, model: Path, a: float, b: float, stem: Path,
                    depth: int = 0) -> list[tuple[float, float, str]]:
    """
    Decode, and if the text collapsed, HALVE the window and try again.

    Splitting rather than re-asking, because the failure is driven by window
    length: the same audio that returns flat lowercase over 90 seconds returns
    clean prose over 45. One retry at the same size is kept for genuine flakiness,
    then it splits, recursively, until the piece is healthy or too short to be
    worth cutting further.
    """
    segs = _decode(wav, model, a, b, stem, "first")
    if _healthy(segs):
        return segs
    # RETRY WITH A CASING PROMPT. This is the fix that actually works. Shortening
    # the window does not always help - one stretch of rapid self-dialogue came
    # back flat lowercase at 45s, at 32s AND at 18s - but the same audio with a
    # prompt establishing capitalisation and punctuation returned
    # "Really? Yeah. They don't. Okay. Well, then what do they do?" perfectly.
    # Whisper is copying the register of its context, so give it one.
    primed = _decode(wav, model, a, b, stem, "primed", CASING_PROMPT)
    if _healthy(primed):
        return primed
    if depth == 0:
        segs = _decode(wav, model, a, b, stem, "retry")
        if _healthy(segs):
            return segs
    if b - a <= 20.0 or depth >= 3:
        return segs                      # as good as it gets; do not loop
    mid = (a + b) / 2
    return (_decode_healthy(wav, model, a, mid, stem, depth + 1) +
            _decode_healthy(wav, model, mid, b, stem, depth + 1))


def transcribe(src: Path, model: Path, dur: float) -> None:
    """
    The reference transcript, decoded in CHUNKS rather than in one pass.

    This is the single highest-leverage thing in the file. Whisper degrades over a
    long input: on a 13.8 minute master the whole-file decode came back 0%
    capitalised with zero sentence ends, so `restore_case` rejected it and the
    pipeline fell back to the word-level pass - which is a materially worse
    transcriber. Every caption error I have had to hand-correct came from that
    fallback ("the artwork" for "the R word", "training stations" for
    TradeStation, a guest's name wrong, a dropped "do at"). Decoding the SAME
    audio in a short window returns all of it correct, punctuated and cased,
    with no glossary and no corrections.

    So: split at quiet points, decode each piece, and stitch with offsets.
    """
    wav = WORK / "audio16k.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])

    bounds = _split_points(wav, dur)
    tmp = WORK / "tmp"
    tmp.mkdir(exist_ok=True)
    segs: list[tuple[float, float, str]] = []
    redone = 0
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        stem = tmp / f"_ref{i:03d}"
        got = _decode(wav, model, a, b, stem, "first")
        if not _healthy(got):
            got = _decode_healthy(wav, model, a, b, stem)
            redone += 1
        segs += got
        print(f"    reference {i + 1}/{len(bounds) - 1}", end="\r", flush=True)

    segs.sort(key=lambda x: x[0])
    (WORK / "transcript.srt").write_text("\n".join(
        f"{i}\n{_stamp(a)} --> {_stamp(b)}\n{t}\n"
        for i, (a, b, t) in enumerate(segs, 1)))
    (WORK / "transcript.txt").write_text("\n".join(t for _a, _b, t in segs))
    note = f", {redone} re-decoded" if redone else ""
    print(f"    reference decoded in {len(bounds) - 1} chunks{note}          ")


def write_cues() -> int:
    """Flatten the segment transcript into [start, end, text] and [MM:SS] form."""
    srt = WORK / "transcript.srt"
    if not srt.exists():
        raise SystemExit(
            f"no transcript at {srt}\n"
            "Drop --skip-transcribe, or put an existing transcript.srt there.")
    txt = srt.read_text()
    cues = []
    for block in re.split(r"\n\n+", txt.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)",
                     lines[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        cues.append([g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                     g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000,
                     " ".join(lines[2:]).strip()])
    (WORK / "cues.json").write_text(json.dumps(cues))
    with (WORK / "transcript_compact.txt").open("w") as f:
        for s, _e, t in cues:
            f.write(f"[{int(s)//60:02d}:{int(s)%60:02d}] {t}\n")
    return len(cues)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default=None, help="where the clips land")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--cta", default="invest.quasarmarkets.com")
    ap.add_argument("--skip-transcribe", action="store_true")
    a = ap.parse_args()

    src = Path(a.video).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"no such file: {src}")

    info = probe(src)
    print(f"{src.name}\n  {info['w']}x{info['h']}  {info['fps']}fps  "
          f"{info['dur']/60:.1f} min")

    if not a.skip_transcribe:
        print("  transcribing (roughly 15x realtime on an M-series Mac)...")
        transcribe(src, Path(a.model), info['dur'])
    n = write_cues()
    print(f"  {n} transcript cues -> transcript_compact.txt")

    # The segment pass is the reference restore_case() takes casing and
    # punctuation from. Sometimes whisper returns the whole master lowercase and
    # unpunctuated; say so here rather than letting it surface later as captions
    # in the wrong case and clips with no retention cuts.
    words = (WORK / "transcript.txt").read_text().split()
    if words:
        caps = sum(1 for w in words if re.search(r"[A-Z]", w)) / len(words)
        stops = sum(1 for w in words if w.rstrip().endswith((".", "!", "?")))
        if caps < 0.02 or stops < max(3, len(words) // 400):
            print(f"  WARNING: this transcript has no usable casing or "
                  f"punctuation ({caps:.1%} capitalised, {stops} sentence ends).")
            print("  qmclip will detect that and ignore cues.json, keeping the "
                  "word-level pass as decoded - which is usually clean even when "
                  "this one is not. Read the captions of the first clip anyway.")

    sections, hints = detect_sections(src, info["dur"], info["w"], info["h"])
    (WORK / "sections.json").write_text(json.dumps(sections, indent=1))
    for s in sections:
        print(f"  {s['mode']:6s} {s['start']//60:02d}:{s['start']%60:02d}"
              f" -> {s['end']//60:02d}:{s['end']%60:02d}")

    out = Path(a.out).expanduser() if a.out else src.parent / f"{src.stem} clips"
    cfg = {
        "source": str(src),
        "out_dir": str(out),
        # Which generation of the LAYOUT this project was authored against. 2 is
        # the full 9:16 panel with captions on the picture; 1 was the 1560-tall
        # panel with a caption band under it. An archived _project/ is supposed to
        # be a recipe that reproduces a delivered clip, and across this boundary
        # it does not - so the renderer says so rather than quietly shipping a
        # visibly different cut of something already posted.
        # THE SHEET'S HEADLINE READS FROM THESE. Without them the largest type
        # on the posting sheet is the raw download filename - a census of 62
        # delivered sheets found "One clip from master" four times and "One clip
        # from Bubba says ___  Tune in to find out____" once, at 72px. `show` is
        # the name of the programme, `date` is when it aired; both are editable
        # by hand and both are cheap to guess wrong, so they are seeded from the
        # file and expected to be corrected.
        "show": _guess_show(src),
        "date": _guess_date(src),
        "layout_version": 2,
        "src_fps": info["fps"],
        "model": a.model,
        "cta": a.cta,
        # "cut_frames" IS DELIBERATELY NOT WRITTEN HERE. Pinning it made every
        # generated project specify the retention cut as a FRAME COUNT, and a
        # frame count is a different beat on every master: the 6 that was meant
        # as "a quarter second" is 0.24s at 25fps, 0.20s at 30, 0.10s at 60.
        # qmclip's CUT_SECONDS default is the quarter second at whatever rate the
        # master runs, and leaving the key out is what lets it apply. Add
        # "cut_frames" by hand only if you actually mean frames.
        "resume_window": 1.60,
        "cap_size": 86,
        # WHERE THE FACE IS, which is what this key has always been named for
        # and never held. It used to be the geometric centre of the frame,
        # written without ever looking for a face - and because a configured
        # value beats a measured one, that number was the reason speakers came
        # out off centre. Measured on the 08.28 head clip, the head sat +116px
        # right of the panel centre, 10.7% of the frame width.
        #
        # None when no face is convincingly there: head_box measures per clip
        # span at render time, which is better than one number for a whole show
        # anyway, and a key that is absent lets it.
        "face_crop_x": _face_crop_x(src, info),
        "head_crop": None,
        "share_crop": [1600, 972, 8, 104],
        "pip_crop": [280, 132, 1634, 464],
        # No face_h. It never reached pack_share (which only reads a PER-CLIP
        # value from the slate) and a single number cannot be right for both a
        # portrait chart and a 16:9 deck. pack_share derives the split from what
        # the app actually wants; set face_h on a clip only to override that.
    }
    cfg.update(hints)
    (WORK / "project.json").write_text(json.dumps(cfg, indent=1))
    print(f"\nproject.json written. Clips will go to {out}")

    if "two_up_seam" in hints:
        print(f"\nTWO-UP stretches present: divider at x{hints['two_up_seam']}.")
        print("  The centred default crop would land half on each face. Put the")
        print("  speaking half on each clip in slate.json as \"head_crop\":")
        print(f"    left  speaker: {hints['head_crop_left']}")
        print(f"    right speaker: {hints['head_crop_right']}")
        print("  Those keep as much of the half as a 9:16 panel can take. For a")
        print(f"  bigger face shrink the height, set width to {PANEL_AR:.3f}x height,")
        print("  keep the bottom at the frame edge, and centre x on the face -")
        print("  then confirm the badge text still fits inside the crop.")
        # `duo` IS RETIRED - canonical_mode refuses it - so step 1 of every job
        # was telling the operator to author a mode the pipeline will not
        # render, and seeding its config alongside. The template for a stretch
        # where the floor moves is `conversation`, which shows ONE face at a
        # time and cuts to whoever is talking.
        print("  For a stretch where they TALK TO EACH OTHER, use mode "
              "\"conversation\" and")
        print(f"    \"follow_crops\": {hints['duo_crops']}")
        print("  which shows ONE speaker at a time and cuts to whoever holds the")
        print("  floor. It needs \"follow_tiles\" too - two named [w,h,x,y] boxes,")
        print("  one per speaker, in the same order. The vertical offset is "
              "measured from")
        print("  where each face actually sits. Each band is 953px tall now that")
        print("  the panel is the full frame, so a speaker who would not fit the")
        print("  old 773px band very likely fits this one.")
    if "pip_side" in hints:
        x0, x1 = hints["pip_rail_x"]
        print(f"\nSCREEN-SHARE stretches present: camera rail on the "
              f"{hints['pip_side']} at x{x0}-{x1}.")
        print("  Set pip_crop to the SPEAKING tile in that rail (a show with two")
        print("  people stacks two tiles - they need different crops), and")
        print("  share_crop to the part of the app worth showing. Both are")
        print("  per-clip in slate.json. Keep pip_crop's aspect equal to")
        print("  1080/face_h. share_crop keeps its own aspect - the face band")
        print("  takes the remaining height - so crop it to the app's content.")
        print("  MEASURE BOTH ON A REAL FRAME - crop inside the tile, above its")
        print("  name badge, and below the app's own chrome and tab bar.")


if __name__ == "__main__":
    main()
