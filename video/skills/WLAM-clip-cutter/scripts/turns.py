#!/usr/bin/env python3
"""
WHO IS TALKING, SECOND BY SECOND, so a single-face clip can follow the floor.

    python3 turns.py 1852 2036                    # print the turn schedule
    python3 turns.py 1852 2036 --tiles '{"steve":[960,1080,0,0],"flan":[960,1080,960,0]}'

THE ASK. The owner, 2026-08-28: "if we're doing a duo clip and it's single face,
if, for example, Steve is talking, and then Steve Flanagan talks after, it will
switch different talkers."

WHY THIS IS NOT whospeaks.py. That answers one question about a WHOLE span - who
holds the floor over these 50 seconds - and returns a single name. It is the
right tool for authoring `head_crop` on a span where one person talks throughout,
and it is the wrong tool for a span where the floor moves, because the answer to
"who is speaking" over a genuine exchange is "both, in turn". This walks the same
measurement over a sliding window and returns the SCHEDULE.

THE MEASUREMENT IS whospeaks' AND DELIBERATELY SO. A talking face moves and a
listening face does not, but raw motion finds whoever fidgets - so each tile's
mouth motion is scored against ITS OWN quiet baseline, and the ratio is compared
across tiles. That discriminator was arrived at on real footage after a plain
correlation scored 0.02 on a span whose answer was obvious, and re-deriving it
here would be a second definition of one quantity. What is new is only the
windowing and what happens afterwards.

WHAT HAPPENS AFTERWARDS IS MOST OF THE WORK, because a raw per-window verdict is
unusable as an edit:

    the strobe        windows are 1s and people interrupt, so the raw verdict
                      flips 20+ times a minute. Cutting on every flip is not
                      following the speaker, it is a strobe. MIN_TURN holds a
                      framing for a floor before it may be given up.
    the shrug         a listener laughs, nods or says "right" and takes one
                      window. Those are not turns, and a turn shorter than
                      MIN_TURN is absorbed into its neighbour rather than cut.
    the tie           over silence, or a crosstalk window, neither tile wins by
                      enough to act on. MARGIN is the confidence floor and an
                      undecided window HOLDS the current framing rather than
                      guessing - staying on the wrong face is a smaller error
                      than cutting to the wrong face.
    the seam          a cut lands better on a word boundary than mid-syllable,
                      so a turn edge is nudged onto the nearest gap in the
                      audio envelope when one is close.

A turn schedule the caller cannot trust is worse than no schedule, so `plan()`
reports its own confidence per turn and the renderer refuses a follow clip whose
schedule is mostly undecided.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
# Per-show state follows QM_WORK; HERE stays the CODE directory. One owner for
# this lives in qmclip.WORK - repeated for the reason whospeaks.py repeats it.
WORK = Path(os.environ.get("WLAM_WORK") or os.environ.get("QM_WORK") or HERE)

# THE WINDOW IS 1.0s AND THE HOP IS 0.5s. Shorter windows carry too few frames
# for the loud/quiet split to mean anything (the ratio needs both populations
# inside the window); longer ones smear a real handover across the boundary. The
# hop is half the window so a handover is never more than 0.5s late.
WIN = 1.0
HOP = 0.5
EVERY = 0.10                # frame sample inside a window

# A FRAMING HOLDS FOR AT LEAST THIS LONG. Measured against the reference reel's
# own cutaway holds (1.60-2.40s, mean 1.91) and this rig's b-roll floor of 3.0s:
# a face cut is a smaller event than a cutaway, so it may run faster, but under
# about two seconds a two-up starts to read as a tennis match. 2.2s is the
# shortest hold that still looked deliberate on the 08.26 master.
MIN_TURN = 2.2

# HOW FAR AHEAD THE WINNER MUST BE. whospeaks calls 1.15x "CLEAR" over a whole
# span; a 1-second window is noisier, so this is deliberately higher. Below it
# the window is UNDECIDED and the current framing holds.
MARGIN = 1.35
LOUD_PCT, QUIET_PCT = 65, 30


def _cfg() -> dict:
    return json.loads((WORK / "project.json").read_text())


def _src() -> Path:
    return Path(_cfg()["source"])


# ---------------------------------------------------- boundaries from AUDIO ----
# WHERE THE TURNS ARE comes from the SOUND, not from the picture. The picture
# says WHO; the audio says WHEN. Splitting the question that way is the whole
# fix, and it was arrived at from a defect the owner caught by watching:
#
#   "In the first video, Stephen Flanagan is on the screen but BigBeat is
#    talking for the first three seconds... whoever is speaking, that's who you
#    need to cut to. Never the opposite."
#
# The per-window pass got that opening wrong across TWENTY-NINE seconds, and
# both obvious repairs failed to fix it - sweeping the window 1.0-3.0s and the
# tile sampling 96-320px moved the measured share a few points and the answer
# not at all. Two things were actually wrong:
#
#   THE DECISION WAS TOO SHORT. A 1.0s window holds ten samples, and a
#   loud/quiet percentile split over ten samples is noise. Scored over a whole
#   TURN the same measurement is decisive - 6 of 8 segments CLEAR on the clip
#   that was wrong, including the disputed opening at 1.65x for the right man.
#
#   THE ROI WAS A FIXED FRACTION OF THE TILE. rows 45-92%, cols 22-78% - which
#   assumes the face is centred, and on this rig it is not: measured, one
#   speaker's face sits at x0.04-0.67 of his half and the other's at x0.48-0.89.
#   So a fixed box put the SECOND speaker's animated video wall inside his
#   "mouth" region, and a moving background scores as a moving mouth. The mouth
#   is now taken from the face the cascade actually finds.
#
# tinydiarize (whisper.cpp -tdrz) marks speaker CHANGES in the audio. It is
# deliberately conservative - 5 marks on a 109s span where the old pass invented
# 14 - and conservative is what this needs: few, long segments, each decided
# well, beats many short ones each decided badly.
TDRZ_MODEL_ENV = "QM_TDRZ_MODEL"
TDRZ_DEFAULTS = (
    Path.home() / "tableflip-app" / "data" / "models" / "ggml-small.en-tdrz.bin",
    HERE.parent / "models" / "ggml-small.en-tdrz.bin",
)
SEG_MIN = 2.0            # a diarize segment shorter than this is merged
MARGIN_CLEAR = 1.25      # whospeaks' own bar for "this tile is the one talking"
# AND A LOWER BAR TO ACT ON, because HOLDING IS ALSO A DECISION and it is the
# one that shipped the defect. Measured on the clip the owner rejected: three
# consecutive segments scored flanagan at 1.16x, 1.13x and 1.12x - each under
# the CLEAR bar, so all three were discarded and inherited the PREVIOUS
# speaker, putting the wrong man on screen for 47 seconds. Three weak readings
# that agree are evidence; throwing them away is not caution, it is a different
# guess with no measurement behind it at all.
#
# So: above CLEAR the winner is taken and becomes the running answer; between
# DECIDE and CLEAR it is taken but reported as lower confidence; below DECIDE
# it is a coin flip and the previous answer holds.
MARGIN_DECIDE = 1.08
# WHEN TO STOP BELIEVING A LONG WEAK SEGMENT AND CUT IT IN HALF. 12s is about
# two sentences on this material - long enough that a handover inside it is
# likely, short enough that a real single-speaker stretch usually scores CLEAR
# before it is reached. The depth cap bounds the extra decodes: 3 levels turns
# one weak 25s segment into at most eight scores, which is seconds of work.
# THE SPEECH-GATED RATIO IS BLIND TO A SPEAKER WHO NEVER PAUSES, and that is
# how a turn came back CONFIDENTLY WRONG. The ratio asks "does this mouth move
# more on loud frames than on quiet ones", which needs the tile to be quiet at
# some point INSIDE the segment. Measured on 08.26, over a stretch where one man
# talked straight through:
#
#     steve     loud 0.846   quiet 2.316   ratio 0.37
#     flanagan  loud 9.546   quiet 9.723   ratio 0.98
#
# Flanagan has ELEVEN TIMES the mouth motion and is plainly the one talking -
# frames confirm it - but he has no quiet baseline in the window, so his ratio
# sits at 1.0 while the still man's small fluctuations score higher. The ratio
# named the wrong man at confidence 1.00.
#
# So the primary score is now LIFT: this segment's mouth motion against the same
# tile's own median over the WHOLE span. Dividing by the tile's own baseline is
# what makes the comparison fair across two tiles lit differently and framed
# differently, which is the thing raw pixel deltas get wrong.
#
# The ratio is kept, because it guards the case lift cannot see: a listener who
# nods or laughs hard lifts above his baseline without saying a word. But it may
# only VETO - drag a reading down into "uncertain", where the schedule holds the
# previous face - never flip the answer. A veto needs the ratio to disagree
# CLEARLY (VETO_MARGIN), because a marginal ratio is exactly the reading that
# was wrong above.
LIFT_MIN_BASE = 0.15     # a tile this still has no usable baseline
VETO_MARGIN = 1.40       # the ratio must disagree this hard to force uncertainty

SPLIT_IF_LONGER = 12.0
SPLIT_MAX_DEPTH = 3


def _tdrz_model() -> Path | None:
    p = os.environ.get(TDRZ_MODEL_ENV)
    if p and Path(p).exists():
        return Path(p)
    return next((q for q in TDRZ_DEFAULTS if q.exists()), None)


def audio_turns(start: float, end: float) -> list[float] | None:
    """
    Speaker-change times inside the span, in span-relative seconds.

    None when tinydiarize is not available at all, which is a different answer
    from "it found none" - the caller falls back to the sentence-pause split
    rather than treating the span as one turn.
    """
    model = _tdrz_model()
    if not model:
        return None
    src = _src()
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "span.wav"
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
             "-i", str(src), "-ac", "1", "-ar", "16000", "-y", str(wav)],
            capture_output=True)
        if r.returncode or not wav.exists():
            return None
        out = Path(td) / "out"
        r = subprocess.run(
            ["whisper-cli", "-m", str(model), "-tdrz", "-f", str(wav),
             "-oj", "-of", str(out), "--no-prints"],
            capture_output=True)
        js = out.with_suffix(".json")
        if r.returncode or not js.exists():
            return None
        try:
            segs = json.loads(js.read_text()).get("transcription", [])
        except (OSError, ValueError):
            return None
    # EVERY UTTERANCE BOUNDARY IS A CANDIDATE, not only the marked changes. The
    # marks alone are too sparse to cut on: on the 109s clip that started this,
    # tinydiarize marked five, leaving a 47.7-second stretch that contains BOTH
    # speakers and therefore scores 1.01x - undecidable, and held wrong.
    # Splitting at every segment end gives each decision an utterance to work
    # with, and the merge below collapses the runs straight back down, so the
    # cost of a boundary that was not a real change is nothing.
    cuts = []
    for sg in segs:
        t = sg.get("offsets", {}).get("to")
        if t is not None:
            cuts.append(t / 1000.0)
    return sorted(set(c for c in cuts if 0.0 < c < end - start))


def _face_of(src: Path, start: float, dur: float,
             box: tuple[int, int, int, int], w: int = 240):
    """(x, y, w, h) of the face inside the tile, as fractions. None if not found."""
    try:
        import cv2
    except ImportError:
        return None
    cw, ch, cx, cy = box
    h = max(8, int(round(w * ch / cw)))
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{min(dur, 8.0):.3f}",
         "-i", str(src), "-vf",
         f"crop={cw}:{ch}:{cx}:{cy},fps=2,scale={w}:{h},format=gray",
         "-f", "rawvideo", "-"], capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(a) // (w * h)
    if n < 1:
        return None
    seq = a[:n * w * h].reshape(n, h, w)
    det = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    hits = [b for i in range(n)
            for b in det.detectMultiScale(cv2.equalizeHist(seq[i]), 1.1, 5,
                                          minSize=(int(w * 0.12),) * 2)]
    if not hits:
        return None
    x, y, bw, bh = np.median(np.array(hits, float), axis=0)
    return x / w, y / h, bw / w, bh / h


def _mouth_roi(face) -> tuple[float, float, float, float]:
    """The mouth region of a face box, as tile fractions."""
    if face is None:
        # The old fixed box, for a tile the cascade cannot read. It assumes a
        # centred face and is why this function exists.
        return 0.22, 0.45, 0.78, 0.92
    fx, fy, fw, fh = face
    return (fx + fw * 0.20, fy + fh * 0.55,
            fx + fw * 0.80, min(1.0, fy + fh * 1.05))


def _motion_in(src: Path, start: float, dur: float,
               box: tuple[int, int, int, int],
               roi: tuple[float, float, float, float], w: int = 96) -> np.ndarray:
    cw, ch, cx, cy = box
    h = max(8, int(round(w * ch / cw)))
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(src), "-vf",
         f"crop={cw}:{ch}:{cx}:{cy},fps={1 / EVERY:.4f},scale={w}:{h},format=gray",
         "-f", "rawvideo", "-"], capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(a) // (w * h)
    if n < 3:
        return np.zeros(0)
    seq = a[:n * w * h].reshape(n, h, w).astype(float)
    x0, y0, x1, y1 = roi
    r0, r1 = int(h * y0), max(int(h * y0) + 2, int(h * y1))
    c0, c1 = int(w * x0), max(int(w * x0) + 2, int(w * x1))
    return np.abs(np.diff(seq[:, r0:r1, c0:c1], axis=0)).mean(axis=(1, 2))


def baselines(start: float, dur: float, tiles: dict[str, list[int]],
              faces: dict) -> dict[str, float]:
    """
    Each tile's OWN median mouth motion over the whole span - the yardstick a
    segment is measured against. One decode per tile, not one per segment.
    """
    src = _src()
    out = {}
    for name, box in tiles.items():
        m = _motion_in(src, start, dur, tuple(box), _mouth_roi(faces.get(name)))
        out[name] = float(np.median(m)) if m.size >= 4 else 0.0
    return out


def score_segment(start: float, dur: float, tiles: dict[str, list[int]],
                  faces: dict, base: dict[str, float] | None = None
                  ) -> tuple[str | None, float]:
    """(winner, margin) over a WHOLE segment - the reliable unit.

    LIFT decides, the RATIO may only veto. See the note at VETO_MARGIN for the
    measurement that made this the shape.
    """
    src = _src()
    env = _energy(src, start, dur)
    if env.size < 4:
        return None, 1.0
    lift, ratio = {}, {}
    for name, box in tiles.items():
        m = _motion_in(src, start, dur, tuple(box), _mouth_roi(faces.get(name)))
        if m.size < 4:
            continue
        n = min(len(m), len(env) - 1)
        mm, e = m[:n], env[1:n + 1]
        loud, quiet = e >= np.percentile(e, LOUD_PCT), e <= np.percentile(e, QUIET_PCT)
        lo = float(mm[quiet].mean()) if quiet.any() else 0.0
        ratio[name] = (float(mm[loud].mean()) / lo) if lo > 1e-9 else 0.0
        b = (base or {}).get(name, 0.0)
        if b >= LIFT_MIN_BASE:
            lift[name] = float(np.median(mm)) / b
    # With no baselines to work from (an old caller, or two tiles too still to
    # measure) this degrades to the ratio alone rather than refusing to score.
    sc = lift if len(lift) >= 2 else ratio
    if len(sc) < 2:
        return None, 1.0
    rank = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)
    margin = rank[0][1] / rank[1][1] if rank[1][1] > 1e-9 else 99.0
    if sc is lift and len(ratio) >= 2:
        rr = sorted(ratio.items(), key=lambda kv: kv[1], reverse=True)
        vm = rr[0][1] / rr[1][1] if rr[1][1] > 1e-9 else 99.0
        if rr[0][0] != rank[0][0] and vm >= VETO_MARGIN:
            margin = 1.0          # uncertain: the schedule holds the last face
    return rank[0][0], margin


def _tile_motion(src: Path, start: float, dur: float,
                 box: tuple[int, int, int, int], w: int = 96) -> np.ndarray:
    """Mouth-region motion for one tile, on the EVERY grid."""
    cw, ch, cx, cy = box
    h = max(8, int(round(w * ch / cw)))
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(src), "-vf",
         f"crop={cw}:{ch}:{cx}:{cy},fps={1 / EVERY:.4f},scale={w}:{h},format=gray",
         "-f", "rawvideo", "-"], capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(a) // (w * h)
    if n < 2:
        return np.zeros(0)
    seq = a[:n * w * h].reshape(n, h, w).astype(float)
    # The mouth is the bottom-middle of a head-and-shoulders tile. Whole-tile
    # motion also picks up a listener nodding or leaning back, and those read as
    # loudly as speech - whospeaks.motion records the same finding.
    roi = seq[:, int(h * 0.45):int(h * 0.92), int(w * 0.22):int(w * 0.78)]
    return np.abs(np.diff(roi, axis=0)).mean(axis=(1, 2))


def _energy(src: Path, start: float, dur: float) -> np.ndarray:
    """Speech energy on the SAME grid, so the two can be compared directly."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(src), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True)
    a = np.frombuffer(p.stdout, dtype="<i2").astype(float) / 32768
    n = max(1, int(EVERY * 16000))
    if len(a) < n:
        return np.zeros(0)
    fr = a[:len(a) // n * n].reshape(-1, n)
    return np.sqrt((fr ** 2).mean(1))


def verdicts(start: float, end: float, tiles: dict[str, list[int]]
             ) -> list[tuple[float, str | None, float]]:
    """
    (window start, winner or None, margin) every HOP seconds.

    ONE DECODE PER TILE FOR THE WHOLE SPAN, not one per window. The obvious
    shape - loop the windows, decode each - runs ffmpeg 100+ times on a 50s
    span and takes minutes; decoding once and slicing the arrays is the same
    arithmetic in about four seconds.
    """
    src = _src()
    dur = end - start
    mo = {n: _tile_motion(src, start, dur, tuple(b)) for n, b in tiles.items()}
    mo = {n: m for n, m in mo.items() if m.size}
    if len(mo) < 2:
        return []
    env = _energy(src, start, dur)
    if env.size < 2:
        return []
    n = min(min(len(m) for m in mo.values()), len(env) - 1)
    env = env[1:n + 1]                   # motion is a diff, so it lags by one
    mo = {k: v[:n] for k, v in mo.items()}

    out = []
    step, wlen = int(round(HOP / EVERY)), int(round(WIN / EVERY))
    for i in range(0, max(1, n - wlen + 1), step):
        e = env[i:i + wlen]
        if e.size < 4:
            break
        loud, quiet = e >= np.percentile(e, LOUD_PCT), e <= np.percentile(e, QUIET_PCT)
        sc = {}
        for name, m in mo.items():
            w = m[i:i + wlen]
            hi = float(w[loud].mean()) if loud.any() else 0.0
            lo = float(w[quiet].mean()) if quiet.any() else 0.0
            sc[name] = hi / lo if lo > 1e-6 else 0.0
        rank = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)
        best, second = rank[0], rank[1]
        margin = best[1] / second[1] if second[1] > 1e-6 else 99.0
        # A WINDOW WITH NO SPEECH IN IT DECIDES NOTHING. Over a pause both tiles
        # score their own noise floor and the ratio is meaningless - it was
        # naming a winner on silence before this guard, which put a cut in the
        # middle of the one moment nobody is talking.
        speech = float(np.percentile(env, 90)) > 3 * float(np.percentile(env, 10)) + 1e-4
        ok = speech and margin >= MARGIN and best[1] >= 1.10
        out.append((start + i * EVERY, best[0] if ok else None, margin))
    return out


def configured_tracks() -> dict[str, Path]:
    """project.json's "speaker_tracks": {name: path}, resolved against WORK."""
    try:
        cfg = json.loads((WORK / "project.json").read_text())
    except (OSError, ValueError):
        return {}
    raw = cfg.get("speaker_tracks") or {}
    out = {}
    for name, p in raw.items():
        q = Path(p)
        out[name] = q if q.is_absolute() else (WORK / q)
    return out


# ---------------------------------------------------------- per-speaker audio --
# THE ONLY ROUTE THAT IS EXACT. Everything else on this page infers who is
# talking from a mixed track and a picture, and the measured ceiling for that on
# real QM footage was 43% - at or below chance for two people. Given one audio
# file PER PERSON, the same question is answered by comparing two numbers, with
# no model and nothing to tune.
#
# Every live rig can produce these; it is a recording setting, not a purchase:
#   Zoom      Settings > Recording > "Record a separate audio file for each
#             participant"
#   OBS       Settings > Output > Recording > Audio Track, tick 1..6, then
#             assign one source per track in the Advanced Audio Properties
#   Ecamm     Recording > Multi-track audio
#   Riverside / StreamYard / Restream - per-participant tracks are standard on
#             the download page; take the WAVs, not the mixed mp4
#
# The tracks MUST share the master's timeline (same recording, same start). A
# separately-started file is offset and will be confidently wrong, so
# check_tracks() cross-correlates each one against the master and refuses a
# misalignment rather than trusting it.
TRACK_HOP = 0.10          # decision grid, seconds
TRACK_MARGIN = 2.0        # 6 dB - louder than mic bleed, quieter than a turn
TRACK_FLOOR = 0.004       # below this nobody is talking
TRACK_SMOOTH = 5          # median window (0.5s) so one frame cannot flip a turn


def _track_rms(path: Path, start: float, dur: float) -> np.ndarray:
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True)
    a = np.frombuffer(p.stdout, dtype="<i2").astype(float) / 32768
    n = max(1, int(TRACK_HOP * 16000))
    if len(a) < n:
        return np.zeros(0)
    fr = a[:len(a) // n * n].reshape(-1, n)
    return np.sqrt((fr ** 2).mean(1))


def check_tracks(tracks: dict[str, Path], probe: float = 120.0
                 ) -> tuple[bool, str]:
    """Do these tracks belong to this master, on this timeline?"""
    src = _src()
    mix = _track_rms(src, 0.0, probe)
    if not mix.size:
        return False, "could not read the master's audio"
    bad = []
    for name, path in tracks.items():
        if not Path(path).exists():
            return False, f"{name}: no such file: {path}"
        t = _track_rms(Path(path), 0.0, probe)
        if not t.size:
            return False, f"{name}: no audio in {Path(path).name}"
        n = min(len(mix), len(t))
        if n < 50:
            return False, f"{name}: too short to check alignment"
        # Envelope correlation at zero lag against the best lag nearby. A track
        # from the same recording peaks AT zero; one started separately peaks
        # somewhere else, and that is the failure this exists to catch.
        a, b = mix[:n] - mix[:n].mean(), t[:n] - t[:n].mean()
        if a.std() < 1e-9 or b.std() < 1e-9:
            return False, f"{name}: flat envelope, cannot align"
        c = np.correlate(a, b, "full") / (a.std() * b.std() * n)
        lag = int(np.argmax(c)) - (n - 1)
        if abs(lag) > 3:                       # 0.3s
            bad.append(f"{name} is offset by {lag * TRACK_HOP:+.1f}s")
    if bad:
        return False, "; ".join(bad) + " - re-export from the same recording"
    return True, "aligned with the master"


def track_turns(start: float, end: float, tracks: dict[str, Path],
                min_turn: float = MIN_TURN) -> list[dict]:
    """
    The turn schedule from per-speaker audio. Exact, and no picture involved.

    Mic bleed is why this compares a RATIO rather than picking the loudest: each
    mic hears the other person faintly, typically 15-25 dB down, so the direct
    voice wins by far more than TRACK_MARGIN. A frame under that margin is left
    UNDECIDED and inherits the previous answer, exactly as the visual path does.
    """
    dur = end - start
    rms = {n: _track_rms(Path(p), start, dur) for n, p in tracks.items()}
    rms = {n: v for n, v in rms.items() if v.size}
    if len(rms) < 2:
        return []
    n = min(len(v) for v in rms.values())
    names = list(rms)
    M = np.vstack([rms[k][:n] for k in names])

    order = np.argsort(-M, axis=0)
    best, second = order[0], order[1]
    bv = M[best, np.arange(n)]
    sv = M[second, np.arange(n)]
    decided = (bv >= TRACK_FLOOR) & (bv >= TRACK_MARGIN * np.maximum(sv, 1e-9))
    lab = np.where(decided, best, -1)

    # median smooth over decided frames only
    sm = lab.copy()
    for i in range(n):
        w = [x for x in lab[max(0, i - TRACK_SMOOTH // 2):i + TRACK_SMOOTH // 2 + 1]
             if x >= 0]
        if w:
            sm[i] = int(np.bincount(np.array(w)).argmax())

    last = next((int(x) for x in sm if x >= 0), None)
    if last is None:
        return []
    runs: list[dict] = []
    for i in range(n):
        who = int(sm[i]) if sm[i] >= 0 else last
        if sm[i] >= 0:
            last = int(sm[i])
        t0 = start + i * TRACK_HOP
        if runs and runs[-1]["who"] == names[who]:
            runs[-1]["end"] = t0 + TRACK_HOP
            runs[-1]["dec"] += TRACK_HOP if sm[i] >= 0 else 0.0
        else:
            runs.append({"who": names[who], "start": t0, "end": t0 + TRACK_HOP,
                         "dec": TRACK_HOP if sm[i] >= 0 else 0.0})

    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, r in enumerate(runs):
            if r["end"] - r["start"] >= min_turn:
                continue
            left = runs[i - 1] if i else None
            right = runs[i + 1] if i + 1 < len(runs) else None
            keep = (left if right is None else right if left is None else
                    left if (left["end"] - left["start"]) >= (right["end"] - right["start"])
                    else right)
            keep["start"] = min(keep["start"], r["start"])
            keep["end"] = max(keep["end"], r["end"])
            keep["dec"] += r["dec"]
            runs.pop(i)
            changed = True
            break
        i = 0
        while i + 1 < len(runs):
            if runs[i]["who"] == runs[i + 1]["who"]:
                runs[i]["end"] = runs[i + 1]["end"]
                runs[i]["dec"] += runs[i + 1]["dec"]
                runs.pop(i + 1)
                changed = True
            else:
                i += 1
    runs[0]["start"], runs[-1]["end"] = start, end
    return [{"who": r["who"], "start": round(r["start"], 2),
             "end": round(r["end"], 2), "source": "tracks", "degraded": False,
             "confidence": round(min(1.0, r["dec"] / max(1e-6, r["end"] - r["start"])), 2)}
            for r in runs]


TRANSCRIPT_MIN_COV = 0.55   # below this the transcript is not covering the span


def _cfg_transcript():
    """Whether a speaker_transcript is configured at all."""
    try:
        import speakers as _s
        return _s._configured()
    except Exception:                                            # noqa: BLE001
        return None


def _merge_short(sched: list[dict], min_turn: float) -> list[dict]:
    """Absorb any turn under min_turn into its longer neighbour."""
    out = [dict(t) for t in sched]
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i, t in enumerate(out):
            if t["end"] - t["start"] >= min_turn:
                continue
            left = out[i - 1] if i else None
            right = out[i + 1] if i + 1 < len(out) else None
            keep = (left if right is None else right if left is None else
                    left if (left["end"] - left["start"]) >= (right["end"] - right["start"])
                    else right)
            keep["start"] = min(keep["start"], t["start"])
            keep["end"] = max(keep["end"], t["end"])
            keep["aligned"] = round(keep.get("aligned", 0.0) + t.get("aligned", 0.0), 3)
            out.pop(i)
            changed = True
            break
        i = 0
        while i + 1 < len(out):
            if out[i]["who"] == out[i + 1]["who"]:
                out[i]["end"] = out[i + 1]["end"]
                out[i]["aligned"] = round(out[i].get("aligned", 0.0)
                                          + out[i + 1].get("aligned", 0.0), 3)
                out.pop(i + 1)
                changed = True
            else:
                i += 1
    for t in out:
        span = t["end"] - t["start"]
        t["confidence"] = (round(min(1.0, t.get("aligned", 0.0) / span), 2)
                           if span > 1e-6 else 0.0)
    return out


def plan(start: float, end: float, tiles: dict[str, list[int]],
         min_turn: float = MIN_TURN) -> list[dict]:
    """
    The turn schedule: [{who, start, end, confidence}], covering the whole span.

    BOUNDARIES FROM THE AUDIO, IDENTITY FROM THE PICTURE. The sound says WHEN
    the speaker changes (tinydiarize); the tiles say WHO. Each segment is then
    scored as a WHOLE - see score_segment - which is the difference between a
    decision made on ten samples and one made on three hundred.

    Falls back to the old per-window pass only when tinydiarize is unavailable,
    and says so, because that pass is the one that put the wrong man on screen
    for twenty-nine seconds.
    """
    dur = end - start

    # PER-SPEAKER AUDIO WINS OUTRIGHT when it is there. It is not a better
    # guess, it is a different question - two levels compared instead of a
    # mouth inferred from pixels - so it short-circuits everything below.
    tracks = configured_tracks()
    if tracks:
        if len(tracks) < 2:
            raise SystemExit(
                f"\nspeaker_tracks names only {len(tracks)} track - it needs one "
                f"per person.\n")
        ok, why = check_tracks(tracks)
        if not ok:
            raise SystemExit(
                f"\nspeaker_tracks will not be used: {why}.\n\n"
                f"They must come from the SAME recording as the master, on the "
                f"same timeline.\nRe-export them together, or remove "
                f'"speaker_tracks" from project.json to fall back\n'
                f"to the (much weaker) picture-based pass.\n")
        sys.stderr.write(f"turns: using per-speaker audio ({', '.join(tracks)}) "
                         f"- {why}\n")
        return track_turns(start, end, tracks, min_turn)

    # THE STREAM'S OWN TRANSCRIPT, if the platform gave one with names in it.
    # Second only to per-speaker audio, and for the same reason: the platform
    # had each person on their own feed, so this is a record of who spoke, not
    # an inference from a mixed track. Its own timestamps are discarded and the
    # words are aligned onto cues.json - see speakers.py.
    try:
        import speakers as _sp
        tl = _sp.timeline(start, end, list(tiles))
    except Exception as e:                                       # noqa: BLE001
        sys.stderr.write(f"turns: speaker transcript unusable ({e}) - "
                         f"falling back to the picture.\n")
        tl = []
    if tl:
        # MIN_TURN APPLIES HERE TOO. This returned the transcript schedule
        # unfiltered, so a 1.3s interjection became a cut to that person and
        # straight back - the flicker MIN_TURN exists to prevent, skipped
        # purely because the schedule arrived by a different road.
        tl = _merge_short(tl, min_turn)
        cov = _sp.coverage(start, end, tl)
        sys.stderr.write(f"turns: using the stream transcript's speaker labels "
                         f"({len(tl)} turn(s), {cov * 100:.0f}% of the span "
                         f"actually matched)\n")
        if cov < TRANSCRIPT_MIN_COV:
            sys.stderr.write(
                f"turns: only {cov * 100:.0f}% of this span matched the "
                f"transcript (floor {TRANSCRIPT_MIN_COV * 100:.0f}%) - the rest "
                f"would be guesswork carried from the previous speaker.\n"
                f"       Check the transcript covers this part of the show.\n")
        return tl

    # A CONFIGURED TRANSCRIPT THAT PRODUCED NOTHING IS A PROBLEM, NOT A SHRUG.
    # Falling through to the picture route - which measured 43% against ground
    # truth - without saying so means the operator believes they are on the
    # exact road when they are on the worst one.
    if _cfg_transcript() and not tl:
        sys.stderr.write(
            "turns: a speaker_transcript IS configured but produced no usable "
            "schedule, so this is falling back to the PICTURE route, which "
            "measured 43% correct on real footage.\n"
            "       Run: python3 speakers.py <transcript>   to see why.\n")

    cuts = audio_turns(start, end)
    if cuts is None:
        sys.stderr.write(
            "turns: tinydiarize unavailable (model missing, or whisper-cli "
            "failed) - falling back to the per-window pass, which is materially "
            "worse. Put ggml-small.en-tdrz.bin in data/models/ or set "
            "QM_TDRZ_MODEL, and check whisper-cli runs.\n")
        return plan_windowed(start, end, tiles, min_turn)

    # Segment the span, dropping boundaries that would make a segment too short
    # to score. A diarize mark inside a couple of seconds of another is one
    # handover heard twice.
    # CUE BOUNDARIES WERE TRIED HERE AND MEASURED WORSE. Splitting on sentence
    # edges as well as tdrz marks is right in principle - a handover lands on a
    # full stop - but it fragments the span into segments too short to score, and
    # lift needs length. Against transcript ground truth on the 08.26 two-up:
    # tdrz alone 43%, plus cue edges 39%, at 5s spacing 34%, at 8s 36%. It was
    # removed rather than kept as an option, because none of those is usable.
    edges = [0.0]
    for c in cuts:
        if c - edges[-1] >= SEG_MIN and dur - c >= SEG_MIN:
            edges.append(c)
    edges.append(dur)

    src = _src()
    faces = {n: _face_of(src, start, min(dur, 20.0), tuple(b)) for n, b in tiles.items()}
    missing = [n for n, f in faces.items() if f is None]
    if missing:
        sys.stderr.write(
            f"turns: no face found in {', '.join(missing)} - those tiles fall back "
            f"to a centred mouth box, which is what put a moving background inside "
            f"one speaker's ROI. Check the tile rectangles.\n")
    # A CENTRED-BOX FALLBACK MUST NOT REPORT CONFIDENCE. Measured on 08.26, a
    # span where the cascade found NEITHER face still came back at 0.95 across
    # twelve turns - a number computed entirely from background pixels, and
    # indistinguishable from a good reading by anything downstream. Whatever the
    # motion says here, the schedule does not know whose mouth it watched, so it
    # is marked degraded and preflight refuses to cut a conversation on it.
    degraded = bool(missing)

    # A WEAK SCORE ON A LONG SEGMENT MEANS IT CONTAINS A CHANGE THE DIARIZER
    # MISSED, and averaging over both speakers is what makes it weak. This cost
    # a delivered clip: tinydiarize left a 25.1-second hole between two marks,
    # both people talked inside it, the segment scored 1.12x for whoever moved
    # slightly more, and the schedule put the WRONG MAN on screen for the whole
    # stretch. Frames at the edges caught him mid-word and looked right; frames
    # from the MIDDLE showed his mouth shut while the other man talked.
    #
    # So a long weak segment is split and re-scored rather than believed. It
    # recurses while both halves stay above SEG_MIN, and it stops as soon as a
    # half comes back CLEAR - a confident reading needs no further cutting.
    base = baselines(start, dur, tiles, faces)

    def _score_recursive(a: float, b: float, depth: int = 0) -> list[dict]:
        who, margin = score_segment(start + a, b - a, tiles, faces, base)
        if (margin >= MARGIN_CLEAR or b - a < SPLIT_IF_LONGER
                or (b - a) / 2 < SEG_MIN or depth >= SPLIT_MAX_DEPTH):
            return [{"start": a, "end": b, "who": who, "margin": margin}]
        mid = (a + b) / 2
        return _score_recursive(a, mid, depth + 1) + _score_recursive(mid, b, depth + 1)

    scored = []
    for a, b in zip(edges, edges[1:]):
        scored.extend(_score_recursive(a, b))

    # An UNDECIDED segment holds the previous decision rather than guessing -
    # staying on the wrong face is a smaller error than cutting to it.
    last = next((x["who"] for x in scored if x["who"] and x["margin"] >= MARGIN_CLEAR),
                next((x["who"] for x in scored if x["who"]), None))
    if last is None:
        return []
    for x in scored:
        if x["who"] is None or x["margin"] < MARGIN_DECIDE:
            x["held"] = True
            x["who"] = last
        else:
            # Taken either way; only a CLEAR reading resets the running answer,
            # so a run of weak agreement cannot drag the schedule off a
            # confident one.
            x["held"] = x["margin"] < MARGIN_CLEAR
            if x["margin"] >= MARGIN_CLEAR:
                last = x["who"]

    # Merge neighbours that ended up the same person, then absorb anything still
    # under min_turn into its longer neighbour.
    runs: list[dict] = []
    for x in scored:
        if runs and runs[-1]["who"] == x["who"]:
            runs[-1]["end"] = x["end"]
            runs[-1]["dec"] += 0.0 if x["held"] else (x["end"] - x["start"])
        else:
            runs.append({"who": x["who"], "start": x["start"], "end": x["end"],
                         "dec": 0.0 if x["held"] else (x["end"] - x["start"])})
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, r in enumerate(runs):
            if r["end"] - r["start"] >= min_turn:
                continue
            left = runs[i - 1] if i else None
            right = runs[i + 1] if i + 1 < len(runs) else None
            keep = (left if right is None else right if left is None else
                    left if (left["end"] - left["start"]) >= (right["end"] - right["start"])
                    else right)
            keep["start"] = min(keep["start"], r["start"])
            keep["end"] = max(keep["end"], r["end"])
            keep["dec"] += r["dec"]
            runs.pop(i)
            changed = True
            break
        i = 0
        while i + 1 < len(runs):
            if runs[i]["who"] == runs[i + 1]["who"]:
                runs[i]["end"] = runs[i + 1]["end"]
                runs[i]["dec"] += runs[i + 1]["dec"]
                runs.pop(i + 1)
                changed = True
            else:
                i += 1
    runs[0]["start"], runs[-1]["end"] = 0.0, dur
    return [{"who": r["who"], "start": round(start + r["start"], 2),
             "end": round(start + r["end"], 2),
             "degraded": degraded,
             "confidence": 0.0 if degraded else
             round(min(1.0, r["dec"] / max(1e-6, r["end"] - r["start"])), 2)}
            for r in runs]


def plan_windowed(start: float, end: float, tiles: dict[str, list[int]],
                  min_turn: float = MIN_TURN) -> list[dict]:
    """
    The turn schedule: [{who, start, end, confidence}], covering the whole span.

    Undecided windows HOLD rather than guess, short turns are absorbed, and the
    result is contiguous by construction - the renderer switches on it, so a gap
    would be a frame with no crop at all.
    """
    v = verdicts(start, end, tiles)
    if not v:
        return []
    # 1. Carry the last decided verdict forward through undecided windows.
    held, cur = [], None
    for t, who, margin in v:
        if who is not None:
            cur = who
        held.append((t, cur, who is not None, margin))
    # A span can open undecided; back-fill from the first real verdict rather
    # than dropping the head of the clip.
    first = next((w for _t, w, d, _m in held if d and w), None)
    if first is None:
        return []
    held = [(t, w or first, d, m) for t, w, d, m in held]

    # 2. Runs.
    runs = []
    for t, who, decided, margin in held:
        if runs and runs[-1]["who"] == who:
            runs[-1]["end"] = t + HOP
            runs[-1]["n"] += 1
            runs[-1]["decided"] += int(decided)
        else:
            runs.append({"who": who, "start": t, "end": t + HOP,
                         "n": 1, "decided": int(decided)})
    runs[0]["start"] = start
    runs[-1]["end"] = end

    # 3. Absorb anything under min_turn into its neighbour. Repeat, because
    #    absorbing one short run can leave its neighbours adjacent and equal.
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, r in enumerate(runs):
            if r["end"] - r["start"] >= min_turn:
                continue
            # Give it to the longer neighbour: a two-second aside belongs to
            # whoever actually holds the floor around it.
            left = runs[i - 1] if i else None
            right = runs[i + 1] if i + 1 < len(runs) else None
            keep = (left if right is None else
                    right if left is None else
                    left if (left["end"] - left["start"]) >= (right["end"] - right["start"])
                    else right)
            keep["start"] = min(keep["start"], r["start"])
            keep["end"] = max(keep["end"], r["end"])
            keep["n"] += r["n"]
            keep["decided"] += r["decided"]
            runs.pop(i)
            changed = True
            break
        # merge neighbours that are now the same person
        i = 0
        while i + 1 < len(runs):
            if runs[i]["who"] == runs[i + 1]["who"]:
                runs[i]["end"] = runs[i + 1]["end"]
                runs[i]["n"] += runs[i + 1]["n"]
                runs[i]["decided"] += runs[i + 1]["decided"]
                runs.pop(i + 1)
                changed = True
            else:
                i += 1
    return [{"who": r["who"], "start": round(r["start"], 2), "end": round(r["end"], 2),
             "confidence": round(r["decided"] / max(1, r["n"]), 2)} for r in runs]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("--tiles", help='JSON {"name":[w,h,x,y]} for THIS span')
    ap.add_argument("--min-turn", type=float, default=MIN_TURN)
    a = ap.parse_args()
    cfg = _cfg()
    tiles = json.loads(a.tiles) if a.tiles else cfg.get("follow_tiles") or cfg.get("tiles")
    if not tiles or len(tiles) < 2:
        raise SystemExit('need two tiles: --tiles \'{"a":[w,h,x,y],"b":[w,h,x,y]}\' '
                         'or "tiles"/"follow_tiles" in project.json')
    sched = plan(a.start, a.end, tiles, a.min_turn)
    if not sched:
        raise SystemExit("could not decide - check the span, the tiles and the source")
    print(f"\n{_src().name}   {a.start:.1f}s -> {a.end:.1f}s   "
          f"{len(sched)} turn(s), min hold {a.min_turn}s\n")
    for t in sched:
        bar = "#" * int(round((t["end"] - t["start"]) * 2))
        flag = "" if t["confidence"] >= 0.5 else "   <- mostly held, not measured"
        print(f"  {t['start']:8.2f} -> {t['end']:8.2f}  {t['who']:<12} "
              f"conf {t['confidence']:.2f}  {bar}{flag}")
    dec = sum(t["confidence"] * (t["end"] - t["start"]) for t in sched)
    print(f"\n  {dec / (a.end - a.start) * 100:.0f}% of the span was actually "
          f"measured rather than held\n")


if __name__ == "__main__":
    main()
