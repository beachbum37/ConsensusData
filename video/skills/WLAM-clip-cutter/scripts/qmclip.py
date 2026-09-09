#!/usr/bin/env python3
"""
QM viral clip renderer.

Cuts a span out of the webinar master, reframes it to 1080x1920, renders the
Quasar Markets brand chrome, and burns in word-by-word captions.

The look is taken from the landing page (Quasar Landing NEW VERSION/index.html),
read off its computed styles rather than guessed:

    type      Inter ONLY. Display is weight 400 with -0.02em tracking and a
              1.02 line height, not a bold display face. No Space Grotesk.
    colour    bone white #fffdf9 on slate veil #0e1319, never pure white on navy
    accent    muted slate blue #6f9fb2, lifted to #9cc4d4 for the live word
    voice     small uppercase tracked labels, thin outlined capsules, left aligned

Every clip carries invest.quasarmarkets.com.

Layout (1080x1920)
    y    0..1920    video panel - THE WHOLE FRAME, and the same box in every mode
    y  140..1090    hook: a centred bone card ON the picture, first 3.0s only,
                    placed per clip off where the face is (HOOK_PREF 300..660)
    y 1020..1084    closing address, last 2.6s only, off when the end card is on
    y 1130..1430    captions (86px), ON the picture, keywords in a colour chosen
                    from what is actually behind them in that clip
    y 1430..1920    NOTHING. Platform chrome: TikTok draws over the bottom ~480.
    x  920..1080    NOTHING from y900 down. The right-hand action rail.

There is no band above the picture and no band below it. Nothing sits above the
hook either: feeds that letterbox a 9:16 in the timeline - X on mobile above all -
eat the top strip of the frame, and a small tracked label up there is the first
thing to go.
"""
from __future__ import annotations

import colorsys
import functools
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------- project ----
# Everything about a specific video lives in project.json next to this script;
# nothing about a particular source is baked in. Run `python3 analyze.py <video>`
# first - it writes the config, the transcript, the cue reference and the
# section map.
#
# The build directory must contain NO SPACES: ffmpeg's filter-graph parser
# splits option values on unescaped whitespace and ':'. Only the final mp4 path
# (a plain argv entry) may contain spaces.
# WHERE THIS SHOW'S STATE LIVES, which is not the same place as the CODE.
#
# project.json, slate.json, cues.json, the transcripts, audio16k.wav and tmp/ all
# belong to ONE video. They defaulted into the scripts directory, so the skill
# carried the last job's state into the next one - and the rule at the top of
# SKILL.md is that a new video is a NEW JOB and delivered clips are never
# touched. That rule was being enforced by discipline against a working directory
# that disagreed with it, which is also why eight slate.json backups accumulated
# next to the live one: each is somebody protecting themselves from exactly this.
#
# QM_WORK moves the whole set into the show's own folder. Unset, everything
# behaves as it always did, so this cannot break an existing job - it is opt-in
# per show, and `newjob.py` is the other half (archive what is here, then clear
# it) for anyone who keeps the default.
WORK = Path(os.environ.get("WLAM_WORK") or os.environ.get("QM_WORK") or Path(__file__).resolve().parent)
# The CODE directory, which is NOT the same thing and must never follow QM_WORK.
# Anything shipped WITH the skill - the brand fonts, the deep-filter binary, the
# assets - lives here. Both of those were written as `WORK.parent` back when the
# two were always the same directory, and the first job run with QM_WORK set died
# on `OSError: cannot open resource` looking for QMInter400.ttf next to the job.
# A render is the only thing that catches this: every check passed first.
HERE = Path(__file__).resolve().parent
_cfg = WORK / "project.json"
CFG = json.loads(_cfg.read_text()) if _cfg.exists() else {}


# A KEY PRESENT WITH A NULL VALUE MEANS "NOT SET", everywhere in this file.
#
# `CFG.get(k, default)` does NOT do that - it returns None, because the key
# exists - and every numeric setting below was read that way. `"punch": null`
# appears in 21 of the 69 project.json files on this machine, and it crashed
# qmclip at IMPORT with "float() argument must be ... not 'NoneType'". That takes
# down every command in the pipeline for that job, not just the render: the `fit`
# job could not be preflighted, listed or rendered. Found by running one clip of
# every mode the archive uses.
def _cfg_val(key: str, default):
    """
    CFG.get with a NULL-SAFE default.

    `CFG.get(k, d)` returns None when the key is PRESENT and null - which is an
    ordinary JSON authoring slip ("src_fps": null) - and the eight call sites
    that used it went straight into int(round(...)), tuple(...) and Path(...).
    Those raise at IMPORT time, before any code can say which key or which
    project.json, so the operator gets a traceback out of a module-level line.
    _num already guarded this for numbers; this is the same guard for the rest.
    """
    v = CFG.get(key)
    return default if v is None else v


def _num(key: str, default: float) -> float:
    v = CFG.get(key)
    return default if v is None else float(v)


def _int(key: str, default: int) -> int:
    v = CFG.get(key)
    return default if v is None else int(v)

# A MISSING `source` USED TO RESOLVE TO Path(""), WHICH IS Path("."), WHOSE
# .exists() IS TRUE. So a project.json without the key sailed past every
# existence guard in the file and died much later inside ffprobe with a
# CalledProcessError naming a DIRECTORY - a message that sends you looking at
# ffmpeg rather than at the one missing line. Name it here, where it reads.
#
# Only when a project.json is actually present: importing qmclip with no job at
# all is legitimate (selftest and the tools do it) and must stay quiet.
if _cfg.exists() and not str(CFG.get("source", "")).strip():
    raise SystemExit(
        f"\n{_cfg} has no \"source\". Point it at the master video file -\n"
        f"`python3 analyze.py <video>` writes it for you.\n")
SRC = Path(CFG["source"]) if CFG.get("source") else Path("/nonexistent")
AUDIO = WORK / "audio16k.wav"

# HOW A CUTAWAY ARRIVES AND LEAVES: "cut" (a hard cut, the default - see the
# long note at BROLL_IN for the reference measurements that settled it) or
# "slide" (the cover that rises and swipes, kept because the owner asked for it
# once). It is read here, at the top, because THREE separate places derive from
# it and two of them are defined long before the b-roll block: CTA_BROLL_PAD
# (the invitation's inset inside a cutaway, which only needed to be large
# enough to clear the cover's travel) and BROLL_IN / BROLL_OUT themselves,
# which in turn own the punch flip, preflight's settled-time test and broll.py's
# MIN_HOLD and PAN_DONE.
BROLL_STYLE = str(CFG.get("broll_style", "dissolve")).lower()
if BROLL_STYLE not in ("cut", "slide", "dissolve"):
    raise ValueError(
        f"broll_style must be 'dissolve', 'cut' or 'slide', not {BROLL_STYLE!r}")


def ensure_audio() -> None:
    """
    Guarantee audio16k.wav belongs to the video project.json points at.

    This exists because it silently shipped the wrong show. audio16k.wav is a
    per-project cache written by analyze.py, and NOTHING tied it to `source` -
    so swapping project.json to a different video left the previous video's
    audio in place. The render then took its PICTURE from the new source and
    every WORD from the old one, at the same timestamps. It does not error, it
    does not look wrong in the build log, and the clip comes out with confident,
    fluent captions belonging to a completely different conversation.

    Duration is the cheap tell: two different masters practically never match to
    the second. Mismatch or missing -> re-extract.
    """
    if not SRC.exists():
        return
    want = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(SRC)],
        capture_output=True, text=True, check=True).stdout.strip())
    mismatch = False
    if AUDIO.exists():
        with wave.open(str(AUDIO)) as w:
            have = w.getnframes() / w.getframerate()
        if abs(have - want) <= 1.0:
            return
        mismatch = True
        sys.stderr.write(
            f"note: audio16k.wav is {have:.0f}s but {SRC.name} is {want:.0f}s - "
            f"it belongs to a different video. Re-extracting.\n")
    else:
        sys.stderr.write(f"note: no audio16k.wav for {SRC.name}. Extracting.\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SRC), "-vn",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                    str(AUDIO)], check=True)
    # audio16k.wav is not the only per-project cache. cues.json is the transcript
    # restore_case pulls its words from, and sections.json is the layout map
    # check_layout trusts - both belong to the OLD master and both are silent when
    # wrong: stale cues rewrite the captions with another show's sentences, a stale
    # map approves a span that crosses a cut. If the audio did not match, none of
    # them do.
    #
    # ONLY ON A MISMATCH. A MISSING wav is not evidence of a swapped master - it
    # is what a fresh checkout, an archived _project/, or a cleaned cache looks
    # like - and clearing on it destroyed a hand-written sections.json that
    # SKILL.md explicitly invites. With no wav there is nothing to compare
    # against, so say the side files are UNVERIFIED and leave them alone.
    sides = ("cues.json", "sections.json", "transcript.srt",
             "transcript.txt", "transcript_compact.txt")
    present = [n for n in sides if (WORK / n).exists()]
    if mismatch:
        for stale in present:
            (WORK / stale).unlink()
        if present:
            sys.stderr.write(
                f"note: cleared {' / '.join(present)} - they belonged to the "
                f"previous master. Re-run analyze.py before building.\n")
    elif present:
        sys.stderr.write(
            f"note: {' / '.join(present)} could not be checked against "
            f"{SRC.name} (there was no audio16k.wav to compare). If they came "
            f"from a different master, re-run analyze.py.\n")
FONTS = Path(CFG.get("fonts") or HERE.parent / "assets" / "fonts")
MODEL = Path(CFG.get("model") or
             Path.home() / "tableflip-app/data/models/ggml-large-v3-turbo.bin")
# Silero VAD, run by whisper.cpp itself (--vad). Set "vad": false in project.json
# to turn it off; it stays off silently if the weights are not installed.
VAD_MODEL = Path(CFG.get("vad_model") or MODEL.parent / "ggml-silero-v5.1.2.bin")


_SRC_SIZE: tuple[int, int] | None = None


def src_size() -> tuple[int, int] | None:
    """The master's (width, height), probed once; None when it cannot be read."""
    global _SRC_SIZE
    if _SRC_SIZE is None and SRC.exists():
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(SRC)],
            capture_output=True, text=True).stdout.strip().split(",")
        if len(out) >= 2 and out[0].isdigit() and out[1].isdigit():
            _SRC_SIZE = (int(out[0]), int(out[1]))
    return _SRC_SIZE


def check_box(slug: str, key: str, box) -> tuple[int, int, int, int]:
    """
    An authored crop as four usable integers, or a clear refusal.

    Nothing validated these. ffmpeg's crop filter CLAMPS x and y to the frame,
    so a pip_crop whose bottom edge ran 52px past the source rendered a
    different rectangle than the one authored, silently; a crop wider than the
    frame failed deep inside ffmpeg with a message naming neither the clip nor
    the key; a zero-sized one was a ZeroDivisionError traceback; a three-number
    one was a ValueError. All four now name the clip, the key and the value.
    """
    try:
        w, h, x, y = (int(v) for v in box)
    except (TypeError, ValueError):
        raise SystemExit(
            f"\n{slug}: {key} must be [w, h, x, y], got {box!r}.\n")
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        raise SystemExit(
            f"\n{slug}: {key} {[w, h, x, y]} has a zero or negative side - "
            f"re-author it off a real frame.\n")
    size = src_size()
    if size and (x + w > size[0] or y + h > size[1]):
        raise SystemExit(
            f"\n{slug}: {key} {[w, h, x, y]} runs past the {size[0]}x{size[1]} "
            f"source (to x{x + w}, y{y + h}). ffmpeg would clamp it and render a "
            f"different rectangle than the one authored. Re-author it.\n")
    return w, h, x, y


def vad_args() -> list[str]:
    """
    whisper.cpp's VAD flags, or nothing.

    WHAT THIS ACTUALLY FIXES, because it is not the obvious thing. The failure it
    was installed for looked like hallucination over dead air - a clause appearing
    across 1.9s of -80 dB silence - but the words were REAL, spoken fast on the far
    side of the pause. What was wrong was their TIMESTAMPS: the word-level pass
    (-ml 1 -sow) spread them backwards across the hole, and `drop_unspoken` then
    deleted them for having no energy underneath, which is how a caption came out
    reading "...don't time the market. that."
    Measured on that span, 15s of the 08.12.26 master: 8 words landed inside the
    silence without VAD, 2 with it. It does not fix the drift completely, so
    drop_unspoken stays.
    """
    if not CFG.get("vad", True) or not VAD_MODEL.exists():
        return []
    return ["--vad", "-vm", str(VAD_MODEL)]
DELIVER = Path(_cfg_val("out_dir", WORK / "out"))
OUT = DELIVER / "clips"
CAPDIR = WORK / "captions"

F_DISPLAY = FONTS / "QMInter400.ttf"   # hook headline
F_UI = FONTS / "QMInter500.ttf"        # eyebrow, capsule
F_CAP = FONTS / "QMInter600.ttf"       # captions

# ------------------------------------------------- landing-page palette ----
SLATE = (14, 19, 25)          # --color-slate-veil  page background
BONE = (255, 253, 249)        # --color-bone-white  all type
ACCENT = (111, 159, 178)      # --cyan
ACCENT_HOT = (156, 196, 212)  # --cyan-hot          rules and marks
CAP_KEY = (104, 214, 255)     # keyword caption words - deliberately more vivid
                              # than the page accent; captions are the one place
                              # the look is allowed to shout

# ------------------------------------------------- adaptive caption colour ----
# Captions sit ON the picture now, so their colour cannot be a constant. The old
# fixed cyan was safe only because it always landed on a gradient scrim we drew
# ourselves. Over live video it can sink: a speaker in a blue shirt gives cyan
# keywords almost no separation, and the keyword highlight - the whole device that
# lets someone take the point off a muted frame - stops working.
#
# So the accent is CHOSEN PER CLIP from what is actually behind the caption zone.
# Three rules shape the palette:
#
#   1. Saturated red and saturated green are BANNED. This is finance footage and
#      those two carry direction. A keyword in red over a market clip reads as a
#      call, and the skill's whole compliance stance is that what is on screen is
#      subject to the same rules as what is said.
#   2. The house cyan carries a prior, so a clip only leaves it when it genuinely
#      cannot be read. Most clips keep it and the set stays uniform.
#   3. The light and dark sets are never mixed. A dark accent next to bone base
#      type reads as recessive rather than emphatic, so the base colour picks the
#      set and the accent is chosen inside it.
CAP_SETS = {
    # base text, its stroke, then the accents allowed alongside them
    "light": {
        "base": (255, 253, 249),      # bone white
        "stroke": (7, 10, 14),        # near-black, this is what carries legibility
        "keys": [("cyan",  (104, 214, 255), 0.35),
                 ("amber", (255, 194,  71), 0.12),
                 ("lilac", (198, 168, 255), 0.00)],
    },
    # only for a genuinely bright background - a white chart, a sunlit window -
    # where bone type is weak even behind a stroke
    "dark": {
        "base": (13, 20, 28),         # ink
        "stroke": (255, 253, 249),
        "keys": [("ink-blue", (18,  86, 184), 0.20),
                 ("burnt",    (163,  80,   8), 0.08),
                 ("plum",     (109,  46, 148), 0.00)],
    },
}
CAP_KEY_BY_NAME = {n: rgb for s in CAP_SETS.values() for n, rgb, _ in s["keys"]}
# Above this median background luminance the base type flips to ink. Set high on
# purpose: white-on-video with a black stroke is what short-form captions actually
# use, and flipping too eagerly is what would make two clips in a set disagree.
CAP_FLIP_L = 0.62


def _srgb_to_lin(c: "np.ndarray") -> "np.ndarray":
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rel_lum(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance of an 8-bit sRGB triple."""
    c = _srgb_to_lin(np.array(rgb, dtype=float) / 255.0)
    return float(c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722)


def contrast(l1: float, l2: float) -> float:
    """WCAG contrast ratio between two relative luminances, 1.0 to 21.0."""
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _hue_of(rgb: tuple[int, int, int]) -> float:
    r, g, b = (v / 255.0 for v in rgb)
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360.0


def _hue_gap(a: float, b: float) -> float:
    """Shortest distance between two hues, in degrees, 0 to 180."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def choose_caption_colours(bg: dict) -> dict:
    """
    Pick the base, stroke and keyword colours for one clip from its background.

    `bg` is what sample_caption_bg() measured: median relative luminance, the
    saturation-weighted dominant hue, and how much the samples disagree.

    Scored on two axes because a colour can fail in two different ways. CONTRAST
    is whether it separates from the background at all; HUE DISTANCE is whether it
    separates as a COLOUR, which is the blue-shirt case - cyan on navy clears the
    contrast bar on paper and still disappears, because the eye reads the hue
    before it reads the luminance. Neither test alone would have caught it.
    """
    lum, hue = bg["lum"], bg["hue"]
    setname = "dark" if lum > CAP_FLIP_L else "light"
    # A clip that swings across the flip point (a cut from a dark room to a white
    # chart) must not take the dark set: ink type over the dark half is unreadable,
    # while bone with a heavy stroke survives both. Bias to the safe one.
    if setname == "dark" and bg["split"]:
        setname = "light"
    pal = CAP_SETS[setname]

    stroke_l = rel_lum(pal["stroke"])
    best, usable = None, []
    for name, rgb, prior in pal["keys"]:
        # The floor is measured against the STROKE, not against the video. That is
        # the whole reason the stroke exists: a 5px near-black outline is what
        # separates the glyph from whatever is behind it, so a word is legible even
        # at 1.4:1 against the background. What the accent still has to clear is its
        # own outline - a dark accent inside a dark stroke closes up into a blob.
        if contrast(rel_lum(rgb), stroke_l) < 3.0:
            continue
        # Luminance against the background is still worth something (a bright word
        # on a bright shirt is harder work even outlined), but it is the SECOND
        # test now and it saturates early.
        c_term = min(contrast(rel_lum(rgb), lum), 4.5) / 4.5
        # Hue is the first test, because hue is how the failure actually presents.
        # Cyan on a navy shirt clears every luminance check on paper and still
        # vanishes: the eye reads the colour before it reads the brightness, and
        # that specific case is why any of this exists.
        #
        # A background with no colour in it - a dark room, a black terminal - has
        # no hue to clash with, so every candidate scores the same here and the
        # prior is left to keep the house cyan.
        h_term = (0.65 if bg.get("grey")
                  else min(_hue_gap(_hue_of(rgb), hue), 90.0) / 90.0)
        score = 0.75 * c_term + 1.10 * h_term + prior
        usable.append((score, name, rgb))
        if best is None or score > best[0]:
            best = (score, name, rgb)

    # Cannot happen with the palette as written - every accent in a set clears its
    # own stroke by a wide margin - but if someone retargets the palette to another
    # brand and picks badly, say so rather than rendering an unreadable keyword. An
    # unhighlighted keyword is a lost emphasis; an illegible one is a lost word.
    if best is None:
        return {"base": pal["base"], "stroke": pal["stroke"],
                "key": pal["base"], "key_name": "none", "set": setname,
                "note": "no accent in this set clears 3:1 against its own stroke; "
                        "keywords render in the base colour"}

    return {"base": pal["base"], "stroke": pal["stroke"], "key": best[2],
            "key_name": best[1], "set": setname, "note": ""}


def parse_colour(v) -> tuple[int, int, int] | None:
    """Accept '#68d6ff', 'cyan' (a palette name) or [r, g, b] from the slate."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return tuple(int(x) for x in v)
    s = str(v).strip()
    if s in CAP_KEY_BY_NAME:
        return CAP_KEY_BY_NAME[s]
    s = s.lstrip("#")
    if len(s) == 6:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    raise SystemExit(
        f"\nBAD CAPTION COLOUR {v!r}. Use a hex string like '#68d6ff', an "
        f"[r,g,b] list, or one of {sorted(CAP_KEY_BY_NAME)}.\n")

W, H = 1080, 1920
# THE PANEL IS THE WHOLE FRAME, AND IT IS THE SAME RECTANGLE IN EVERY MODE. head,
# duo, share and duo_share all fill exactly this box - a mode is a way of packing
# it, never a different size. Share used to derive its height from a fixed screen
# band plus a face band, which came out 21px short of a head clip and top-aligned,
# so every screen-share clip sat visibly high with a gap under it. Nothing here may
# be recomputed per mode.
#
# The panel grew 1120 -> 1410 -> 1560 -> 1920 as the hook moved onto the picture,
# then the inset came off, and finally the caption band came off the bottom. It is
# now the full 9:16: there is no letterbox under the picture and nothing beside it.
# That last 360px is the single largest gain the layout has made - it is 23% more
# picture on every clip, and on a duo it takes each band from 773px to 953px.
#
# The captions moved ONTO the picture to pay for it (see CAP_BAND_Y below). That
# is a real trade and it is written up in references/look.md; do not undo half of
# it. Shrinking PANEL_H without moving the captions back leaves a dead band.
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 0, 0, 1080, 1920
PANEL_R = 0        # full bleed: no inset, no rounding, no backdrop at the sides
# The panel now covers every pixel of the frame. Two things existed only to fill
# the area OUTSIDE it and are gone: the blurred slate backdrop derived from the
# shot, and the rounded-corner alpha mask. Both were pure cost once PANEL_R hit 0
# and the panel hit the frame edges - the blur alone was a gblur of a 1080x1920
# frame on every single frame of every clip.
assert (PANEL_X, PANEL_Y, PANEL_W, PANEL_H) == (0, 0, W, H), (
    "The renderer no longer builds a backdrop or a mask, because the panel is the "
    "frame. If you shrink the panel you must put both back, or every clip renders "
    "with a black margin.")

# ------------------------------------------------------------ caption zone ----
# Captions sit ON the picture, in the lower third, which is where short-form
# captions sit everywhere else. They used to live in a 360px band BELOW the panel
# on a gradient scrim; that band is picture now.
#
# The y range is not a taste call, it is the intersection of two constraints:
#
#   1. every app draws its own chrome over the bottom of a vertical video - roughly
#      the bottom 480px on TikTok, 420 on Reels, 300 on Shorts - so nothing that
#      must be read may sit below y1440.
#   2. feeds that letterbox a 9:16 in the timeline crop the TOP strip, and the
#      lower third is where a reader's eye already is.
#
# So the block is centred on y1280 (exactly two thirds down) inside a 300px band
# that ends at 1430, ten pixels clear of TikTok's chrome. One and two line captions
# both centre on the same y, which is what makes ten clips read as one set.
# The BOTTOM edge is the constant that matters, because it is the one that
# collides with platform chrome. TikTok is the worst of the four targets at about
# the bottom 480px of a 1080x1920, so 1920 - 483 = 1437, floored to 1430. Derive
# the top from it, so that anyone who later widens the band for a two-line case
# walks it UP rather than down into the chrome.
CAP_SAFE_BOTTOM = 1430
# THE BAND IS TALLER THAN THE CAPTIONS NEED, so a raised caption can go a long
# way up. It used to be exactly 300px at y1130 and "raised" only meant
# top-aligned inside it, which bought 98px - not enough for the invitation to be
# a real button underneath.
#
# Under a b-roll cutaway there is NO FACE (the one written exception), so nothing
# is competing for the upper frame and the captions can ride right up. The band
# is 480px now and the legacy pair below reproduces today's centring EXACTLY for
# every ordinary frame - a normal caption does not move by a pixel.
CAP_BAND_H = 480
CAP_BAND_Y = CAP_SAFE_BOTTOM - CAP_BAND_H            # 950
# What the band used to be. Non-raised captions are centred against THESE so the
# look is unchanged; only the raised ones use the extra height.
CAP_BAND_Y_REST = 1130
CAP_BAND_H_REST = 300
# ffmpeg's crop CLAMPS rather than failing, so a band that runs past the frame
# silently samples the wrong rows and the colour is chosen from pixels the words
# never touch. Found by moving the band to 1780 in a test and getting the answer
# for 1620 three times in a row.
assert CAP_BAND_Y + CAP_BAND_H <= min(H, 1437), \
    "the caption band crosses the platform chrome line"

# The measure is narrower than the old below-the-panel one (was W - 220 = 860).
# Every app also draws a right-hand action rail - like, comment, share - over
# roughly the same vertical range the captions now occupy, the widest of them
# about 160px. And the measure is a GROUPING budget, not the ink: the stroke
# pushes CAP_STROKE past each end and every inter-word gap carries one more, so a
# three-word row grouped at M inks about M + 4 x CAP_STROKE wide.
#
# Measured against the 541 caption cards this skill has actually rendered: 3.7%
# of them exceed 780 and 8.1% exceed 740, and the widest single word inks at
# 667px, so nothing becomes unbreakable at either. 740 costs about 8% more chunk
# breaks, which is invisible; 780 puts ink at x935, under the rail.
CAP_MEASURE = W - 340                                # 740

# The widest INK the band may carry, as opposed to the widest chunk the grouper
# will build. It is a hair wider than CAP_MEASURE so a chunk group_words already
# decided fits one line is never re-broken by the stroke's extra width - but it
# is a HARD ceiling, because past it the ink goes under the platform action rail
# and the last letters of the line are behind an icon.
CAP_INK_MAX = CAP_MEASURE + 40                       # 780
# How far the type may be condensed to hold a row inside CAP_INK_MAX. A single
# word wider than the measure has nowhere to break, so the only lever left is
# size - the same move the hook card already makes when it cannot find a clear
# band (it drops to 84px before it will overlap a face).
#
# TWO numbers, because "stop shrinking" and "this is worth mentioning" are
# different questions. Past CAP_SHRINK_WARN the caption has stopped matching the
# rest of the set and that is worth a line in the log; but the alternative to
# shrinking further is ink under the platform action rail, which is worse than
# small type, so the hard floor sits lower. At CAP_SHRINK_MIN the caption is
# still 47px, which is legible - and nothing in 6,702 archive tokens comes near
# needing it.
CAP_SHRINK_WARN = 0.72
CAP_SHRINK_MIN = 0.55

# How heavily the type is outlined. Captions used to sit on a scrim we drew, so a
# 2px offset shadow was enough. On live video it is not: the stroke is now the
# thing that makes them readable at all, and the adaptive colour only decides
# WHICH colour is readable, not whether anything is. Measured at the 86px caption
# size - 5px reads as a clean outline, 7px starts to close up the counters of 'e'
# and 'a' after a platform re-encode.
CAP_STROKE = 5
CAP_SHADOW_BLUR = 7
CAP_SHADOW_DY = 6

# What the colour probe looks at is where the INK lands, not the whole band. One
# row of 86px type is 103px inside a 300px band, so sampling the band reads 200px
# of background no word ever touches - on a duo that is the difference between
# sampling the lower speaker's face and sampling his face plus both shoulders.
CAP_INK_W = CAP_MEASURE + 2 * CAP_STROKE                        # 750
CAP_PROBE_H = 180
CAP_PROBE_Y = CAP_BAND_Y + (CAP_BAND_H - CAP_PROBE_H) // 2      # 1190

# Screen-share split: the speaker's camera above the shared screen, both at panel
# width. The crop sits inside the meeting tile: past the active-speaker border and
# above the name badge.
#
# There is no global face-band height. It is DERIVED per clip by pack_share() from
# what the app naturally wants, and an authored per-clip `face_h` in the slate
# overrides it. A project-level `face_h` key never reached pack_share and is inert
# - do not reintroduce one, because a single number cannot be right for both a
# portrait chart and a 16:9 deck.
SPLIT_GAP = 14
# Output at the master's own rate. Converting 25 to 30 duplicates roughly every
# fifth frame, and that pulldown judder is indistinguishable from - and masks -
# a two-frame retention tick. All three platforms accept 25.
SRC_FPS = int(round(_cfg_val("src_fps", 25)))
FPS = SRC_FPS

# Screen-share source region (w, h, x, y) in the 1920x1080 master: below the
# browser chrome and left of the picture-in-picture gutter.
SHARE_CROP = tuple(_cfg_val("share_crop", (1600, 972, 8, 104)))

# Camera-shot source region (w, h, x, y), overriding the default centred 9:10
# crop of the full frame. A single-camera master needs no override. A two-up
# master does: its centre is the seam between the two speakers, so the default
# crop lands half on each face. Set this to the speaking half instead.
HEAD_CROP = tuple(CFG["head_crop"]) if CFG.get("head_crop") else None

# Steve's camera during the screen-share stretch, inside the Zoom tile: past
# the blue active-speaker border and above the name badge. 268x166 native is
# the hard ceiling on how large he can be in those clips.
PIP_CROP = tuple(_cfg_val("pip_crop", (280, 132, 1634, 464)))

INVEST = CFG.get("cta", "invest.quasarmarkets.com")

# Caption size. Read from config so write_srt and the burn-in agree on the
# chunking - they must use the same font metrics or the .srt groups words
# differently than the video shows them.
CAP_SIZE = _int("cap_size", 86)

# The hook is on the picture, not above it, and it leaves. A headline that sits
# there for a whole minute is paying rent on real estate the video wants, and by
# the fifth second nobody is reading it any more - it has already done its job of
# stopping the scroll.
HOOK_HOLD = _num("hook_hold", 3.0)
# The card ARRIVES and LEAVES; it does not switch on and off. Arrival is a pop:
# scale 0.92 -> 1.018 -> 1.0 with the overshoot peaking just past half way,
# alpha 0.85 -> 1. Not from zero - frame 0 is the cover a feed shows before
# anyone presses play, so the card must already read on it. The exit mirrors
# the entrance at a slightly longer length: fade, settle to 0.97, drift up 14px.
# Numbers from the 2026 survey in references/look.md ("fade 150-250ms, pop
# 150-250ms, entrance under 400ms; typewriter and bounce read as template").
# 2026-08-22 (second pass, the motion system): the card SWIPES. It arrives from
# the right - 60px of travel on an ease-out quart over HOOK_IN, alpha 0.85 -> 1
# on a smoothstep - and leaves LEFT, off the frame, on an ease-in cubic over
# HOOK_OUT with a 133ms alpha fade under the last third. No scale on type:
# scale belongs to the punch-ins and the live caption word. The compass is one
# rule for every element: picture arrives from BELOW, type arrives from the
# RIGHT, everything leaves LEFT. All three durations are DELIVERED seconds;
# render() scales them by the tempo, because the overlay runs pre-setpts.
HOOK_IN = 0.30
HOOK_OUT = 0.233
HOOK_ALPHA0 = 0.85
HOOK_SLIDE_IN = 60
HOOK_FADE_AT = 0.100          # into HOOK_OUT, the alpha fade starts
HOOK_FADE_D = 0.133
# WHERE the card goes is decided per clip, not pinned. It used to sit at y96,
# which is inside the top strip every app covers (TikTok's chrome to ~140, Shorts
# to ~288, and the 4:5 in-feed crop on Reels and LinkedIn takes 285 off the top),
# and in `share` it landed straight across the speaker's eyes because the camera
# tile is at the top of the panel. So: it WANTS the band below, centred on y480;
# it may rise to HOOK_MIN_TOP or drop to HOOK_MAX_BOTTOM to stay off a face; and
# a face is measured, not assumed - see panel_faces() and place_hook().
HOOK_PREF = (300, 660)
HOOK_MIN_TOP = 140
HOOK_MAX_BOTTOM = CAP_BAND_Y - 40          # 1090, clear of the captions
HOOK_FACE_PAD = 24
HOOK_RAIL_Y = 900                          # below this the action rail bites
HOOK_MAX_BLOCK = 390                       # the card never taller than this
HOOK_MIN_SIZE = 84                         # the card shrinks to this to clear a face, no further
HOOK_PAD = 60                              # canvas margin: shadow blur + drift + overshoot

# The retention cut REMOVES footage; it does not add a hold. Measured off the
# reference reel: three cuts in 13.6s, roughly every 3.6s, with speech running
# continuously straight through each one and no silent trough. That is a jump
# cut taking out the breath at the end of a sentence, which both tightens the
# pace and gives the picture a visible snap.
#
# Only real silence is removed, found in the waveform - whisper's word timings
# are contiguous by construction (a word's end IS the next word's start), so
# the "gap" between words is an artefact and cutting on it would clip speech.
# THE BEAT IS A DURATION, NOT A FRAME COUNT, and it was written as a frame count
# divided by the master's rate - so what the comment called "0.24s, a quarter
# second" was only 0.24s on a 25fps master. The same 6 frames is 0.20s at 30
# (this desk), 0.10s at 60, and 0.05s at 120: the retention cut this rig is
# named for quietly halves and then vanishes as masters get faster, with nothing
# in the build log changing. That is the hardcoded-frame-count bug this file has
# shipped twice before, in a constant that sets the pace of every clip.
#
# `cut_frames` stays honoured as FRAMES when it is authored, because somebody who
# wrote it meant frames. The DEFAULT is now the quarter second it always claimed
# to be, at whatever rate the master runs.
CUT_SECONDS = 0.24       # the beat a retention cut takes out, in time
CUT = (_num("cut_frames", 0) / SRC_FPS) if CFG.get("cut_frames") is not None else CUT_SECONDS
MIN_AIR = 0.10           # skip the cut unless there is at least this much air
MIN_SPACING = 1.10       # and do not cut twice inside this window
# How far past a sentence end to look for speech resuming. A pause longer than
# this is not shortened at all - the search gives up and the cut is skipped,
# which is the opposite of what you want on the longest pause in a clip. An
# interview leaves bigger holes than a solo talk, so it is configurable.
RESUME_WINDOW = _num("resume_window", 1.60)


def snap(t: float) -> float:
    """Round a time onto a source frame boundary."""
    return round(t * SRC_FPS) / SRC_FPS


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        sys.stderr.write(f"\nFAILED: {' '.join(str(c) for c in cmd)}\n{p.stderr[-3000:]}\n")
        raise SystemExit(1)
    return p


# ------------------------------------------------------------- captions ----
# Whisper has no idea what these proper nouns are, and a misspelt partner name
# burned into a clip is not fixable after the fact.
# Matched case-insensitively, replaced with the correct casing. Word-level
# decoding keeps sentence case and already gets WebMob and KiwiTech right; what
# it cannot know is that Edgar is EDGAR and that the name is Steven.
TERMS = {
    "stephen": "Steven", "edgar": "EDGAR", "fred": "FRED", "jetro": "JETRO",
    "lat-am": "LatAm", "sadr": "Sadr", "webmob": "WebMob",
    "kiwitech": "KiwiTech", "tradier": "Tradier", "seasonax": "Seasonax",
    "benzinga": "Benzinga", "tv": "TV",
    # Markets vocabulary whisper lower-cases. "fed" is the central bank in this
    # footage every time; it is never the verb.
    "fed": "Fed",
    # House style does not burn profanity into a caption. The audio is muted
    # separately via a clip's "mute" windows; this keeps the text clean too.
    "shit": "s---", "shitty": "s---ty", "fuck": "f---", "fucking": "f---ing",
    "bullshit": "bulls---", "ass": "a--",
    "warsh": "Warsh",
    # whisper has no idea what a rug pull is and writes it as one nonsense word.
    # Not English in any spelling, so replacing it can never corrupt real text.
    "ruggpool": "rug pull", "ruggpool's": "rug pull's", "ruggpull": "rug pull",
    "bessett": "Bessent", "bessent": "Bessent", "bessette": "Bessent",
    # "dollar-yen" spoken fast. The word pass offers the Chinese port "Dalian"
    # and the reference the Turkish resort "Dalyan"; neither is ever said on a
    # markets tape, so replacing them cannot corrupt real text.
    "dalyan": "dollar-yen", "dalian": "dollar-yen",
    # QM Live 08.28.26: "the Claude and the Anthropic" came out as "the clawed
    # and adanthropic". Both are wrong in a way that reads as OUR error rather
    # than his speech, and neither spelling is a word - "adanthropic" is not
    # English at all and "clawed" is, but never on a markets tape next to a
    # model name. This desk names these two constantly now.
    "clawed": "Claude", "adanthropic": "Anthropic", "anthropic": "Anthropic",
    "claude": "Claude", "chatgpt": "ChatGPT", "openai": "OpenAI",
    "tuttle": "Tuttle", "nasdaq": "Nasdaq", "capex": "CapEx", "etf": "ETF",
    "aws": "AWS", "qqq": "QQQ", "spx": "SPX", "dtes": "DTEs",
    # clock times whisper writes as bare digits
    "830": "8:30", "930": "9:30", "430": "4:30",
    # AI Matters / Dr. Patrick Bell (08.19.26). whisper has no "neuromorphic"
    # in its vocabulary and offers these instead; none is a real word here, so
    # replacing them cannot corrupt real text.
    "neomorphic": "neuromorphic", "neomorphics": "neuromorphics",
    "mirror-morphic": "neuromorphic", "neuro-morphic": "neuromorphic",
    # the Greek historian, and a drone
    "ucidides": "Thucydides", "drave": "drone",
    "preposarious": "preposterous",
    # the word pass produces its own spellings, which the reference-pass scan
    # never sees: "noomorphic" only ever appeared in a delivered caption.
    "noomorphic": "neuromorphic", "nueromorphic": "neuromorphic",
    "neuromophic": "neuromorphic", "numorphic": "neuromorphic",
}
# Phrase fixes; the replacement may be a different length than the source.
#   "what the buyers sell" is whisper mishearing "what to buy or sell", the
#   compliance line the whole talk turns on.
MERGES = [
    # QM Live 08.27.26, Dave Conley segment. whisper split one continuous
    # sentence in two and left the second half lowercase, so the caption read
    # "to a whole bunch." on one card and "in Europe," on the next - a full stop
    # followed by a lowercase start, which reads as our error rather than his
    # speech. Re-transcribing 789-797 of the master gives one sentence, "I
    # talked to a whole bunch in Europe." The replacement is character-identical
    # to the phrase apart from the stop it removes, so where the phrase occurs
    # correctly punctuated elsewhere this is a no-op.
    (("whole", "bunch", "in"), "whole bunch in"),
    # Same show, BigBeat solo. "...the nonsense, right? because it is what's
    # happening" - the word pass left "because" lowercase directly after a
    # question mark, and the caption chunker then opened a card on it. Scoped to
    # the three-word phrase because a bare ("right","because") would rewrite the
    # very common "right, because" into "right? Because" wherever it appears.
    # It is FOUR tokens, not three, because the existing ("because","it") entry
    # below exists to kill a cue-boundary capital ("because It can operate") and
    # the merge loop breaks on the first match - a three-token rule here consumes
    # "because" first, that entry never fires, and the caption ships "Because It".
    (("nonsense", "right", "because", "it"), "nonsense, right? Because it"),
    # QM Live 08.25.26, Dave Conley segment. Three corrections, each verified by
    # re-transcribing the master audio at the timestamp rather than by reading.
    #
    # "I do not want to put brakes on CURING cancer, though" is the host's answer
    # to "it's going to take your job, oh and it might cure cancer" - the whole
    # point is that you do not slow down a cancer cure. The word pass wrote "fear
    # and cancer", which is semantically backwards and lands in the clip's turn.
    # Scoped to the five-word phrase so an ordinary "fear and cancer" survives.
    (("brakes", "on", "fear", "and", "cancer"), "brakes on curing cancer"),
    # Same breath. The audio is a cut-off false start, "I did-", before the guest
    # comes back with "no, no, I get it". The word pass completed it into a whole
    # invented sentence. Scoped to eight words including the preceding "though"
    # so a genuine "I did not want to do that" is never touched.
    (("though", "i", "did", "not", "want", "to", "do", "that"), "though. I did"),
    # Mortgage rates. The reference pass and a re-transcribe both give "they're in
    # 4% and 5%"; the word pass dropped the first percent sign and spelled the
    # number out, so the caption read "four and 5%". split_token gives "5" a core
    # and "%." a tail, hence the bare 5 in the sequence.
    (("they're", "in", "four", "and", "5"), "They're in 4% and 5"),
    (("the", "buyers", "sell"), "to buy or sell"),
    # QM Live 08.26.26, Xiao-Li Meng. He is describing how we invented the GYM
    # once machines took the physical labour, and the word pass hears "gems".
    # It is the load-bearing word of that whole answer. Scoped to the three-word
    # phrase so an ordinary "create the gems" is never touched.
    (("create", "the", "gems"), "create the gyms"),
    # McGlone 08.21.26. "it's the SOCK puppet of the stock market" - his own
    # phrase for an asset that only moves when the S&P moves; he uses it twice
    # in the same interview and the reference pass got it right the first time.
    # "stock puppet" is not a phrase in English, so replacing it is safe.
    (("stock", "puppet"), "sock puppet"),
    # Same show. "I was in the trading pit" comes back as "the trading pitch
    # set" - nonsense, and it lands in his credibility line. Scoped to the
    # three-word phrase, which occurs nowhere else in English.
    (("trading", "pitch", "set"), "trading pit"),
    # Litt 08.20.26. "$3 on a 27 DOLLAR base" (he paid $26.97) comes back as
    # "27-cent base", which turns an 11% rise into an eleven-hundred-percent one
    # in the same breath as he says "that's 11%". "27-cent" is not a phrase that
    # occurs on its own, so the pairing is safe to replace anywhere.
    (("27-cent", "base"), "27 dollar base"),
    # same clip: "when I came back this morning" -> "when it came back". Scoped
    # to the whole six-word phrase so an ordinary "when it came back" survives.
    (("when", "it", "came", "back", "this", "morning"),
     "When I came back this morning"),
    # "an institution like J.P. Morgan or Goldman Sachs" comes back as "JV
    # Morgan". Not a firm, not a phrase - safe to replace anywhere.
    (("jv", "morgan"), "J.P. Morgan"),
    # McGlone 08.22.26. "stock market CAP to GDP" - the standard ratio - comes
    # back as "capped to GDP", which reads as a rate cap rather than a
    # valuation measure, and it lands in the clip's evidence line. Scoped to
    # the three-word phrase so an ordinary "capped to" survives anywhere else.
    (("capped", "to", "gdp"), "cap to GDP"),
    # "it's clear as a bell" comes back as "it clears the bell". "clears the
    # bell" is not a phrase in English - the idiom is the only thing it can be -
    # so the four-word pairing is safe to replace anywhere.
    (("it", "clears", "the", "bell"), "It's clear as a bell"),
    (("jp", "morgan"), "J.P. Morgan"),
    # "grade A type AI" loses the capital and reads as an article in the caption.
    (("grade", "a", "type"), "grade A type"),
    # "they buy a stock as a tree" is "as a trade" - and the investment-versus-
    # trade distinction is the entire point of the clip it appears in.
    (("as", "a", "tree"), "as a trade"),
    # on a metals show "take a look at the end" is the yen every time
    (("at", "the", "end", "where's"), "at the yen. Where's"),
    # "hold on, what- define AI for me" comes back as "what did you define"
    (("what", "did", "you", "define"), "Define"),
    # "a SCIF, S-C-I-F" (secure compartmented information facility) comes back
    # as the image format. Scoped to the phrase - a bare gif -> SCIF rule would
    # corrupt any future show that talks about an actual GIF.
    (("within", "this", "gif"), "within this SCIF"),
    (("this", "gif"), "this SCIF"),
    (("mirror", "morphic"), "neuromorphic"),
    # AI Matters 08.19.26. "all these things that we, these wearables" - he
    # restarts the sentence. The word pass invents "eat" in the gap, which
    # burns in as people EATING their wearables. Scoped to the full stumble.
    (("we", "eat", "these", "wearables"), "we, these wearables"),
    # "it's not silly that they will be immune" - decodes disagree between
    # "silly" and "so", and neither is English here; the sense is plainly
    # "it's not that they will be immune, but it is much harder to jam them".
    # Dropping the disputed filler is the smallest honest edit. "not silly
    # that" is not a phrase in English, so this can never corrupt real text.
    (("not", "silly", "that"), "not that"),
    # a cue boundary left a capital mid-sentence: "because It can operate".
    # After "because", "it" is always lower case.
    (("because", "it"), "because it"),
    # "a couple of milliseconds is literally a couple of KILOMETRES of travel" -
    # the word pass repeats "milliseconds" and the sentence stops meaning
    # anything. This 4-token run is never legitimate English.
    (("couple", "of", "milliseconds", "kilometers"), "couple of kilometers"),
    # NOTE: MERGES run BEFORE TERMS in fix_terms(), so at this point the word
    # pass still has the raw mis-spelling - matching on the corrected spelling
    # never fires. Match the raw token.
    (("since", "the", "ucidides"), "since Thucydides"),
    (("since", "the", "thucydides"), "since Thucydides"),
    # The same host tic again, on the Patrick Bell master: "Define failing" loses
    # its first syllable and comes back "If I find failing" / "Find failing". Two
    # independent decodes of the isolated 9s both heard "find failing", so this is
    # the model mishearing rather than the audio being unclear.
    (("if", "i", "find", "failing"), "Define failing"),
    # AI Matters 08.26.26, Dr. Patrick Bell on the unavoidable-accident case:
    # "it would choose to harm itself before it would harm its PASSENGER". Both
    # full-length passes wrote "passage"; the isolated 4s re-decode of the same
    # audio gives "passenger", and "harm its passage" is not a phrase in English,
    # so this can never corrupt real text. It is the clip's closing word.
    (("harm", "its", "passage"), "harm its passenger"),
    # Same clip. A reference cue boundary falls between "...can be done" and
    # "With this particular action", so the word pass carries a capital into the
    # middle of the sentence - the same fault as the "because It" entry above.
    # Scoped to the whole five-word phrase rather than a bare ("done","with"):
    # _respan keeps only the LAST token's tail, so a two-token rule would eat the
    # full stop in a genuine "...I am done. With that said". This phrase cannot
    # legitimately straddle a sentence end, and on already-correct text it is a
    # no-op.
    (("done", "with", "this", "particular", "action"),
     "done with this particular action"),
    (("find", "failing"), "Define failing"),
    # "...is what you're saying? In a lot of ways" gains a stray "for"
    (("saying", "for", "in"), "saying? In"),
    # "you want to be shorter" is "be short it", the other half of the maxim.
    (("to", "be", "shorter"), "to be short it"),
    # whisper inserts a stray "is" into "take profits too fast".
    (("profits", "is", "too", "fast"), "profits too fast"),
    (("people", "understand", "is"), "people to understand is"),
    (("season", "x"), "Seasonax"),
    # ("big","beat") -> "BigBeat" was REMOVED. It fired on the bare token pair with
    # no context test, so on a markets show it rewrote "a big beat on earnings" into
    # "a BigBeat on earnings". A merge that corrupts correct English is worse than
    # one that never runs: the host's name is on his lower third anyway, and the
    # post caption names him. Keep this table for things that are not words.
    (("trade", "station"), "TradeStation"),
    (("trey", "station"), "TradeStation"),
    # the 19th-century retailer, not the Roblox currency
    (("sears", "robux"), "Sears Roebuck"),
    (("sears", "roebucks"), "Sears Roebuck"),
    # The bare ("big","beat") pair is deliberately NOT merged (see the note above -
    # it rewrote "a big beat on earnings"). This is the host being ADDRESSED by name,
    # which needs the vocative comma in front of it, so the context makes it safe.
    (("today", "big", "beat"), "today, BigBeat"),
    (("pit", "big", "beat"), "pit, BigBeat"),
    # guests address the host by his handle and whisper hears an initial
    (("big", "v", "will", "tell"), "BigBeat will tell"),
    # The Fed chair is Warsh. whisper also hears the surname "Walsh", which IS a real
    # name, so this is merged in context rather than added to TERMS.
    (("did", "walsh", "make"), "Did Warsh make"),
    (("walsh", "has", "said"), "Warsh has said"),
    (("what", "walsh", "has"), "what Warsh has"),
    # QM Live 08.28.26: the same surname comes back as the verb "wash" on this
    # master ("the Fed prior to WASH", "what WASH is bringing"). Matched in
    # context - neither phrase is English about laundry - so this cannot corrupt
    # real text the way a bare "wash" -> "Warsh" in TERMS would.
    (("prior", "to", "wash"), "prior to Warsh"),
    (("what", "wash", "is", "bringing"), "what Warsh is bringing"),
    (("what", "wash", "is", "saying"), "what Warsh is saying"),
    (("prior", "to", "walsh"), "prior to Warsh"),
    (("what", "walsh", "is", "bringing"), "what Warsh is bringing"),
    (("what", "walsh", "is", "saying"), "what Warsh is saying"),
    (("trade", "pulse"), "TradePulse"),
    (("money", "net"), "Money.net"),
    # "a 30 or 60 seat swing" - whisper hears "sweet"
    (("sweet", "swing"), "seat swing"),
    # a nuisance poll text: "report spam and put it down". The audio is genuinely
    # unclear and whisper offers "report slam" / "reports to him", neither of
    # which is English - ship the plain meaning rather than gibberish.
    (("report", "slam"), "report spam"),
    # the reference doubles a clause here: "looking at these houses, looking at
    # these races". A clean decode of the same audio has only "these races".
    (("these", "houses", "looking", "at", "these", "races"), "these races"),
    (("calci",), "Kalshi"),
    # "avoid our shares dropping" - whisper drops the plural
    (("avoid", "our", "share", "dropping"), "avoid our shares dropping"),
    (("option", "change"), "option chain"),
    # "the R word" (recession) comes back as "the artwork" every time
    (("heard", "the", "artwork"), "heard the R word"),
    # the Fed chair, not the noun - only merged in context so ordinary "power" is safe
    (("from", "power", "over"), "from Powell over"),
    (("that", "power", "said"), "that Powell said"),
    # The word-level pass (-ml 1 -sow) silently DROPS words where the segment
    # pass hears them fine - here it left a 0.77s hole and produced the broken
    # "what are you going to the grocery store?". A merge can restore them,
    # because _respan redistributes a longer replacement over the matched span.
    (("going", "to", "the", "grocery"), "going to do at the grocery"),
    # "by the time we get to midterms" comes back as "by the meantime"
    (("by", "the", "meantime", "we"), "by the time we"),
    # restore_case treats a reference cue boundary as a sentence start, so a
    # clause split across two cues comes back capitalised mid-sentence:
    # "And for me, it's Adding robotics and biotech together."
    (("it's", "adding"), "it's adding"),
    # "still an Illinois boy" - the reference hears "still in Illinois, boy",
    # which relocates the speaker (he is shopping at a Publix in Florida) and
    # reads as an address rather than as where he grew up. The word pass had
    # "an Illinois boy" and only fluffed the first word, so the sense is not in
    # doubt. Merged on the four-token run so ordinary "in Illinois" is safe.
    (("still", "in", "illinois", "boy"), "Still an Illinois boy"),
    # The trader Victor Niederhoffer, whom whisper splits into two English words.
    # Merged on the full three-token name so the common noun "victor" is safe.
    (("victor", "nita", "hoffer"), "Victor Niederhoffer"),
    (("victor", "niita", "hoffer"), "Victor Niederhoffer"),
    # "how you think as a sports bettor" comes back as the comparative "better",
    # which turns the noun into an adjective and loses the meaning entirely.
    # Merged on the ordered pair: a genuine "better sports ..." puts the words the
    # other way round, so this cannot corrupt correct English.
    (("sports", "better"), "sports bettor"),
    (("sports", "betters"), "sports bettors"),
]

# Split a token into its word and any trailing punctuation. Matching the raw
# token fails on "SELL." while succeeding on "SELL," - and the sentence-final
# case is exactly the one that matters.
_SPLIT = re.compile(r"^(.*[A-Za-z0-9])([^A-Za-z0-9]*)$")

# How many consecutive words the reference may delete before the deletion is read
# as the REFERENCE being wrong rather than the word pass inventing. Every recorded
# invention this pipeline has caught is a single token; the deletion that shipped a
# broken caption was seven. Three is inside the first population and well clear of
# the second.
CASE_DROP_MAX = 3

# Words whose trailing period is not a full stop.
# "no" was in this set for the ordinal "No. 3" and came out: across one whole
# show plus 93 delivered .srt files there are ZERO real "No. <digit>" ordinals
# and seven emphatic "No." - so it was only ever making the pipeline refuse to
# end a clip on the word "No.", which on this material is a perfectly good place
# to stop.
ABBREV = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "inc", "ltd",
          "co", "corp", "vs", "etc", "approx", "fig", "est", "dept", "gov",
          "sen", "rep", "gen", "col", "capt", "lt", "sgt", "jan", "feb", "mar",
          "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"}

def finished_sentence(t: str) -> bool:
    """
    Does this token actually END a sentence?

    A trailing period is not enough, and every false positive here shipped a
    clip. An **ellipsis** ends with '.' - that shipped "now that's a
    different...". So does an **abbreviation** - the fix for that then shipped
    "Now, how Mr." Initials ("E.") are the same trap.

    And the stop can be WRAPPED. whisper writes a closing quote or bracket
    outside the period ('market."'), and a bare endswith(".") scores that as
    unfinished - so the out-point rule would either run past a perfectly good
    ending or pull back and delete it. Trailing wrappers come off first.

    Lifted out of render() on 2026-08-24 so preflight can ask the same question
    the renderer will. It had its own weaker copy - a bare
    endswith((".","!","?")) - which passed all three false positives above, so
    EDGES printed OK on spans the renderer then had to rescue.
    """
    t = t.rstrip().rstrip('"\'”’)]}»')
    if t.endswith("\u2026") or t.endswith(".."):
        return False
    if not t.endswith((".", "!", "?")):
        return False
    if t.endswith(("!", "?")):
        return True
    core = t[:-1]
    if core.lower() in ABBREV:
        return False
    # A SENTENCE-FINAL NUMBER IS A SENTENCE END. The dotted-token rule below
    # exists for U.S. and initials, and it was swallowing every decimal, price
    # and percentage that closes a sentence: "Down 2.3%." "104.76." "$79.5."
    # Measured across one show, 28 real sentence ends were invisible (~2.8% of
    # 995) - 10 of them made the clip DELETE its closing sentence and 18 made it
    # run on to the cap. One Ford clip lost "Down 2.3%.", the number it existed
    # for. Test the trailing character rather than a regex, so a leading "$" or
    # a thousands comma cannot break it.
    if core[-1:].isdigit() or core.endswith("%"):
        return True
    # an initial, or anything with internal periods like U.S.
    return not (len(core) == 1 or "." in core)


def plan_ending(words, dur, layout_ok=None, hard_out=None, start=0.0):
    """
    Where the out-point has to move so the clip ends on a finished sentence.

    Returns (kind, index, cost):

      "landed"   the clip already ends on a full stop. Nothing to do.
      "back"     trim back to words[index] - `cost` seconds of speech deleted.
      "forward"  run on to words[index] - `cost` seconds added.
      "flat"     no sentence end anywhere in the decode, so the ending cannot be
                 checked at all. Usually an unpunctuated whisper pass.
      "stuck"    there ARE sentence ends and none is reachable. index names the
                 nearest one so the message can point at it.

    ONE owner, because there were two: render() did this and preflight guessed at
    it with a bare endswith((".","!","?")), which passes an ellipsis, an
    abbreviation and an initial - the three false positives render() had already
    been tightened against. So EDGES printed OK on spans the renderer then had to
    rescue, and printed nothing at all about whether the rescue would work.

    `words` must include the lookahead past `dur` (END_LOOKAHEAD), or the forward
    direction cannot be seen. `layout_ok(t)` should raise if extending the clip to
    source time `t` would cross a layout change; pass None to skip that test.
    """
    # `w.end <= dur`, not `w.start < dur`. A word that starts inside the span and
    # finishes PAST the out-point is cut mid-utterance, and scoring it as the
    # last word inside made the clip report a clean landing while the closing
    # word was chopped: measured on a real span, 'stagnating.' runs [75.730,
    # 76.240] against an out-point of 75.970, so the stop closure is cut and full
    # speech continues to 76.37 - and render's own note claimed the out-fade had
    # been "held back so it starts after the last word".
    #
    # Treating the straddler as OUTSIDE turns it into a forward move, which
    # already carries the run-on cap, the hard_out veto and layout_ok. The cause
    # is structural: spans are authored off cues.json segment times while this
    # judges on the word pass, so they disagree by fractions of a word.
    inside = [w for w in words if w.end <= dur]
    if not inside:
        return "flat", None, None
    if finished_sentence(inside[-1].text):
        return "landed", None, None

    ends = [i for i, w in enumerate(words) if finished_sentence(w.text)]
    if not ends:
        return "flat", None, None
    back = [i for i in ends if words[i].end <= dur]
    fwd = [i for i in ends if words[i].end > dur]

    # The cap on running on scales with the clip: a flat 4s was that judgement
    # made for a 45s clip and then applied unchanged to a 95s one.
    runon_max = max(4.0, min(6.0, dur * 0.08))
    fwd_cost = words[fwd[0]].end - dur if fwd else None
    if fwd_cost is not None and fwd_cost > runon_max:
        fwd_cost = None
    if fwd_cost is not None and hard_out is not None:
        if start + words[fwd[0]].end > hard_out:
            fwd_cost = None
    if fwd_cost is not None and layout_ok is not None:
        try:
            layout_ok(start + words[fwd[0]].end + END_PAD)
        except SystemExit:
            fwd_cost = None             # extending would cross a layout change

    back_i = back[-1] if back else None
    back_cost = (min(words[-1].end, dur) - words[back_i].end
                 if back_i is not None else None)
    if back_cost is not None and back_cost > dur * 0.34:
        back_cost = None                # deleting a third of the clip is worse

    # Direction. The two are NOT symmetrical when the speaker is mid-sentence at
    # the out-point: running on lets them finish the sentence, pulling back
    # deletes it. Only a trivially small pull-back wins outright - there the
    # out-point is already on the sentence and a stray word of the next one hangs
    # off it, so nothing is lost.
    cheap_back = back_cost is not None and back_cost <= END_BACK_FREE
    if fwd_cost is not None and not cheap_back:
        return "forward", fwd[0], fwd_cost
    if back_cost is not None:
        return "back", back_i, back_cost
    near = min((abs(words[i].end - dur), i) for i in ends)[1]
    return "stuck", near, words[near].end - dur


# A sentence can be finished and still not LAND. These are the words that end a
# grammatical sentence while carrying none of the meaning - the thought they
# close belongs to something already said, so the clip stops on a pronoun and the
# payoff is a sentence away in one direction or the other. Read off the delivered
# archive, where clips end on "go.", "that.", "this.", "about.", "good.", "way."
# and "through.". Advisory only, and only in preflight: it is an editorial call
# about whether the moment was picked right, which is not a thing to decide from
# a word list at render time.
TRAIL_OFF = {"that", "this", "it", "them", "there", "here", "those", "these",
             "go", "good", "way", "about", "through", "too", "well", "so",
             "then", "much", "one", "right", "yeah", "okay", "sure", "stuff",
             "thing", "things", "something", "anything", "everything"}

# The other edge. A clip that opens on a discourse marker AND a bare pronoun has
# dropped the viewer into the middle of a conversation - "but how does it get
# around" needs the sentence before it, while "so the fed has no ability" is just
# how people talk. BOTH conditions are required and that is the whole design:
# measured over 90 delivered clips, the pair fires on 8 and is right about six,
# where the marker alone fires on 25 at about 36% precision, which is alert
# fatigue rather than a check.
#
# DO NOT import broll.py's OPENERS for this. It holds the / a / what / why / how
# / i / we / you and flags 60 of 90 delivered clips - it is solving a different
# problem (is this term searchable) with the same word.
OPEN_MARKER = {"so", "and", "but", "well", "now", "okay", "yeah", "anyway",
               "because", "right", "look", "see", "actually", "basically"}
OPEN_PRONOUN = {"it", "its", "they", "them", "their", "he", "him", "his",
                "she", "her", "those", "these", "that", "this"}

# Verbal filler. Worth stripping because the segment transcript is faithful to the
# audio, so reconciling against it restores every "uh" the word pass had quietly
# dropped - one clip came back reading "33% inflation on, uh, uh, since 2019".
# Nobody wants that burned into a caption. Speech is unchanged; only the text is.
FILLER = {"uh", "um", "erm", "uhh", "umm", "mm", "mhm", "hmm", "ah"}


def strip_filler(words: list[Word]) -> list[Word]:
    """Drop standalone filler tokens, carrying any real punctuation forward."""
    out: list[Word] = []
    carry = ""
    for w in words:
        core, tail = split_token(w.text)
        # An ALL-CAPS token is never a hesitation. "erm" is a real filler word
        # and it is also the Exchange Rate Mechanism, which is what it means on
        # a markets tape - and MERGES/TERMS run BEFORE this, so an acronym
        # arrives here already upper-cased while whisper writes the hesitation
        # lower-case. Without this test strip_filler silently ate "the ERM" and
        # carried its full stop back onto "the", leaving "out of the." in the
        # caption. Found on QM Live 08.21.26.
        if core.lower() in FILLER and not core.isupper():
            # keep a sentence end the filler happened to carry
            if tail and any(c in tail for c in ".!?"):
                carry = tail if not carry else carry
            continue
        if carry and out:
            prev = out[-1]
            pcore, ptail = split_token(prev.text)
            if not any(c in ptail for c in ".!?"):
                out[-1] = Word(prev.start, prev.end, pcore + carry)
            carry = ""
        out.append(w)
    return out or words


def split_token(text: str) -> tuple[str, str]:
    """Word plus trailing punctuation. Matching the raw token fails on "sell."
    while succeeding on "sell," - the sentence-final case is the one that
    matters."""
    m = _SPLIT.match(text)
    return (m.group(1), m.group(2)) if m else (text, "")


FIX_STEPHEN = bool(CFG.get("fix_stephen", False))


def _real_stephens() -> list[str]:
    """Surnames of anybody on THIS show whose name is genuinely Stephen."""
    out = []
    people = [CFG.get("host")] + list((CFG.get("speakers") or {}).values())
    for v in people:
        name = v.get("name") if isinstance(v, dict) else v
        m = re.match(r"\s*Stephen\s+(\S+)", str(name or ""), re.I)
        if m:
            out.append(m.group(1).strip(".,"))
    return out


def fix_spelling(t: str) -> str:
    """
    Whisper hears "Stephen"; the host is Steven E. Orr.

    BUT THIS SHOW HAS A REAL STEPHEN, AND THIS RULE WAS RENAMING HIM. It was
    written when Steven E. Orr was the only person who appeared, and it rewrote
    every "Stephen" in every caption, case-insensitively. The co-host is
    **Stephen Flanagan** - this file's own notes record the master's burned-in
    lower third reading "Stephen Flanagan / Forex Educator" - so the correction
    for one man's name was burning the WRONG NAME onto the other man's face:

        "Stephen Flanagan makes a good point" -> "Steven Flanagan ..."

    Text alone cannot tell the two apart, and a wrong name under a real
    person is a worse defect than a first name spelt the other way. So the
    correction now stands down entirely whenever the show's own config names
    somebody who really is a Stephen. The NAMEPLATE is unaffected either way -
    it is set from config, never from the transcript, so it has always been
    right.
    """
    # OPT-IN, BECAUSE THE SAFE DEFAULT IS TO LEAVE A NAME ALONE. This used to
    # run whenever _real_stephens() came back empty - and _real_stephens reads
    # CFG["speakers"], which is a PER-CLIP slate key that never appears in
    # project.json, so it was ALWAYS empty and the guard NEVER FIRED. Measured:
    # fix_spelling("Stephen Flanagan makes a point") still returned "Steven
    # Flanagan" after the guard was added.
    #
    # Rather than thread clip state into a text helper, the default is now to do
    # nothing. Misspelling the host's first name is cosmetic; burning the wrong
    # name onto a real person's face is not, and this show has both a Steven and
    # a Stephen. Set "fix_stephen": true in project.json only on a show where
    # nobody is really called Stephen.
    if not FIX_STEPHEN or _real_stephens():
        return t
    return re.sub(r"\bStephen\b", "Steven", t, flags=re.I)


@dataclass
class Word:
    start: float
    end: float
    text: str


def _respan(start: float, end: float, repl: str, tail: str) -> list[Word]:
    """Spread one replacement phrase across the span it replaces."""
    parts = repl.split()
    total = sum(len(p) for p in parts)
    out, t = [], start
    for i, p in enumerate(parts):
        e = end if i == len(parts) - 1 else t + (end - start) * len(p) / total
        out.append(Word(t, e, p + (tail if i == len(parts) - 1 else "")))
        t = e
    return out


def fix_terms(words: list[Word]) -> list[Word]:
    """Correct proper nouns and mis-heard phrases in the caption stream."""
    out: list[Word] = []
    i = 0
    while i < len(words):
        matched = False
        for seq, repl in MERGES:
            n = len(seq)
            if i + n <= len(words):
                got = [split_token(w.text)[0].lower() for w in words[i:i + n]]
                if got == list(seq):
                    last = words[i + n - 1]
                    out.extend(_respan(words[i].start, last.end, repl,
                                       split_token(last.text)[1]))
                    i += n
                    matched = True
                    break
        if matched:
            continue
        w = words[i]
        core, tail = split_token(w.text)
        key = core.lower()
        out.append(Word(w.start, w.end, TERMS[key] + tail) if key in TERMS else w)
        i += 1
    return out


_REF_USABLE: bool | None = None


def reference_usable() -> bool:
    """
    Is cues.json worth aligning against at all?

    `restore_case()` exists to take casing and punctuation FROM the segment pass,
    on the assumption that pass is the better-punctuated of the two. When it is
    not - whisper returned the whole master lowercase and unpunctuated, which it
    does - aligning against it *downgrades* good word-level text, and strips the
    sentence ends `find_removals()` needs, so the clip silently renders with no
    retention cuts as well.

    So this is checked rather than assumed. Judged over the whole file, not the
    span: a short span legitimately might carry no capital and no full stop.
    """
    global _REF_USABLE
    if _REF_USABLE is not None:
        return _REF_USABLE
    path = WORK / "cues.json"
    if not path.exists():
        _REF_USABLE = False
        return False
    words: list[str] = []
    for _s, _e, text in json.loads(path.read_text()):
        words.extend(text.split())
    if not words:
        _REF_USABLE = False
        return False
    caps = sum(1 for w in words if re.search(r"[A-Z]", w)) / len(words)
    stops = sum(1 for w in words if w.rstrip().endswith((".", "!", "?")))
    _REF_USABLE = caps >= 0.02 and stops >= max(3, len(words) // 400)
    if not _REF_USABLE:
        sys.stderr.write(
            f"note: {path.name} has no usable casing or punctuation "
            f"({caps:.1%} capitalised, {stops} sentence ends) - ignoring it and "
            "keeping the word-level pass as decoded.\n")
    return _REF_USABLE


def _prose_score(tokens: list[str]) -> float:
    """How much sentence structure is in this text: capitals plus full stops."""
    if not tokens:
        return 0.0
    caps = sum(1 for t in tokens if re.search(r"[A-Z]", t)) / len(tokens)
    stops = sum(1 for t in tokens
                if t.rstrip().endswith((".", "!", "?"))) / len(tokens)
    return caps + stops


def reference_words(start: float, dur: float) -> list[str]:
    """
    The same span from the full-webinar pass, which is decoded at segment
    granularity.

    Word-level decoding (-ml 1) is reliable for timing but NOT for punctuation:
    on some spans it returns the whole thing lowercase with no full stops at
    all, which both breaks the caption casing and leaves no sentence ends to
    tick on. The segment pass punctuates those same spans correctly.
    """
    path = WORK / "cues.json"
    if not path.exists() or not reference_usable():
        return []
    out: list[str] = []
    for s, e, text in json.loads(path.read_text()):
        if e > start and s < start + dur:
            out.extend(text.split())
    return out


_NORM = re.compile(r"[^a-z0-9]")


def _respan_tokens(start: float, end: float, tokens: list[str]) -> list[Word]:
    """Lay a run of tokens across a time span, weighted by their length."""
    if not tokens:
        return []
    total = sum(len(t) for t in tokens) or 1
    out, t = [], start
    for i, tok in enumerate(tokens):
        e = end if i == len(tokens) - 1 else t + (end - start) * len(tok) / total
        out.append(Word(t, max(e, t + 0.06), tok))
        t = e
    return out


def restore_case(words: list[Word], ref: list[str]) -> list[Word]:
    """
    Reconcile the two whisper passes: the segment pass decides WHAT was said,
    the word pass decides WHEN.

    It is not enough to copy casing onto matched words. The word pass also drops
    small connectives and sometimes emits a phrase twice - it wrote "I don't care
    I don't care who you are" and turned "So the rate decision" into "right? the
    rate decision" - and a matched-blocks-only merge leaves all of that burned in.
    Aligning properly means taking the reference's tokens and giving them the word
    pass's timings, so duplicates disappear and dropped words come back.

    The reference is gathered by whole cues, so it overruns the clip at both ends.
    Leading and trailing insertions are therefore ignored - otherwise the captions
    would open with words spoken before the clip starts.
    """
    if not ref:
        return words
    import difflib
    a = [_NORM.sub("", w.text.lower()) for w in words]
    b = [_NORM.sub("", t.lower()) for t in ref]
    ops = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    equals = [k for k, (tag, *_) in enumerate(ops) if tag == "equal"]
    if not equals:
        return words
    first, last = equals[0], equals[-1]

    out: list[Word] = []
    for k, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            for m in range(i2 - i1):
                w = words[i1 + m]
                out.append(Word(w.start, w.end, ref[j1 + m]))
        elif tag == "delete":
            # The word pass has something the reference does not. USUALLY that is
            # an invention - a word heard in a gap, or a repeat - and dropping it
            # is right. The examples recorded above this function are all ONE
            # token: "eat" invented in a gap, "milliseconds" repeated.
            #
            # BUT A LONG RUN IS NOT AN INVENTION, IT IS THE REFERENCE MISSING
            # SPEECH, and dropping it burns a broken sentence into a delivered
            # clip. Confirmed on a shipped clip: the audio plainly says "You've
            # got to be very wake up and look at what the Treasury is doing
            # because" and the caption reads "You've at what the treasury's doing
            # because" - 1.97s of clear speech deleted, ungrammatical text on
            # screen, and nothing anywhere reported it.
            #
            # Note where this sits: drop_unspoken has ALREADY run, so every word
            # reaching here has real audio energy underneath it. A run that long
            # with energy under it is speech, whatever the reference thinks.
            if i2 - i1 > CASE_DROP_MAX:
                out.extend(words[i1:i2])
                sys.stderr.write(
                    f"note: keeping {i2 - i1} word(s) the reference transcript "
                    f"does not have ({' '.join(w.text for w in words[i1:i2])[:60]!r}"
                    f") - too long to be an invention.\n")
                continue
            continue                      # word pass invented it; drop it
        elif tag == "replace":
            if k < first or k > last:
                # OUTSIDE the clip's own span, same as an insert there. The guard
                # covered `insert` only, so a leading or trailing REPLACE wrote
                # reference words from before the in-point or after the out-point
                # over this clip's first or last caption - text the viewer never
                # hears. Keep what the word pass actually decoded instead.
                out.extend(words[i1:i2])
                continue
            out.extend(_respan_tokens(words[i1].start, words[i2 - 1].end,
                                      ref[j1:j2]))
        elif tag == "insert":
            if k < first or k > last:
                continue                  # outside the clip's own span
            t0 = out[-1].end if out else words[0].start
            t1 = words[i1].start if i1 < len(words) else t0 + 0.25 * (j2 - j1)
            if t1 <= t0:
                t1 = t0 + 0.20 * (j2 - j1)
            out.extend(_respan_tokens(t0, t1, ref[j1:j2]))

    # Safety net: if alignment produced something wildly different in size, the
    # match was bad and the untouched word pass is the safer output.
    if not out or not 0.5 <= len(out) / max(1, len(words)) <= 2.0:
        return words
    for i in range(1, len(out)):            # keep times monotonic
        if out[i].start < out[i - 1].end:
            out[i] = Word(out[i - 1].end, max(out[i].end, out[i - 1].end + 0.06),
                          out[i].text)
    return out


def _decode_words(start: float, dur: float, slug: str) -> list[Word]:
    """One whisper word-level pass over a span, returned in span-relative time."""
    tmp = WORK / "tmp"
    tmp.mkdir(exist_ok=True)
    wav = tmp / f"{slug}.wav"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(AUDIO), "-c", "copy", str(wav)])
    stem = tmp / slug
    run(["whisper-cli", "-m", str(MODEL), "-f", str(wav), "-l", "en",
         "-ml", "1", "-sow", *vad_args(), "-oj", "-of", str(stem), "--no-prints"])
    data = json.loads((tmp / f"{slug}.json").read_text())
    out: list[Word] = []
    for seg in data["transcription"]:
        t = seg["text"].strip()
        if not t:
            continue
        a = seg["offsets"]["from"] / 1000.0
        b = seg["offsets"]["to"] / 1000.0
        out.append(Word(a, max(b, a + 0.12), fix_spelling(t)))
    return out


def _punctuated(words: list[Word], window: float = 25.0) -> bool:
    """
    Did this pass come back with sentence structure, or flat?

    Judged in SUB-WINDOWS. Whisper's collapse to flat lowercase is driven by how
    much audio it is given, so a long span often reads correctly at the start and
    goes flat partway through. Measured across the whole span that averages out to
    a pass, and the chunked re-decode that would have fixed it never runs - which
    is how a clip shipped reading "...for an absolute stone fact. because when i
    was on the trading floor all the big banks had two brokers now our pit was so
    big". Every window has to stand on its own.
    """
    if not words:
        return True

    def ok(ws: list[Word]) -> bool:
        if len(ws) < 20:
            return True                  # too little to judge
        caps = sum(1 for w in ws if re.search(r"[A-Z]", w.text)) / len(ws)
        stops = sum(1 for w in ws if w.text.rstrip().endswith((".", "!", "?")))
        return caps >= 0.03 and stops >= 1

    t0 = words[0].start
    buckets: dict[int, list[Word]] = {}
    for w in words:
        buckets.setdefault(int((w.start - t0) // window), []).append(w)
    return all(ok(b) for b in buckets.values())


def _quiet_split(start: float, dur: float, target: float) -> float:
    """The quietest moment near `target`, so a chunk boundary never cuts a word."""
    env = envelope(start, dur)
    if env.size < 4:
        return target
    lo = max(1, int((target - 1.6) / HOP))
    hi = min(len(env) - 1, int((target + 1.6) / HOP))
    if hi <= lo:
        return target
    return (lo + int(np.argmin(env[lo:hi]))) * HOP


CHUNK = 14.0


def word_times(start: float, dur: float, slug: str) -> list[Word]:
    """
    Re-transcribe this span at word granularity.

    Whisper decodes a long span flat. On a 43s clip it returned 2.4% capitalised
    and zero sentence ends, while 12s windows of the same audio came back properly
    punctuated - and flat text costs both the caption casing and every retention
    cut, since the cuts are placed on sentence ends. So a flat result is re-decoded
    in chunks and stitched.

    Boundaries are put at the quietest point near each target rather than at a
    fixed stride, so a chunk edge never lands mid-word.
    """
    words = _decode_words(start, dur, slug)
    if not _punctuated(words) and dur > CHUNK * 1.4:
        bounds, t = [0.0], 0.0
        while dur - t > CHUNK * 1.4:
            t = _quiet_split(start, dur, t + CHUNK)
            bounds.append(t)
        bounds.append(dur)
        stitched: list[Word] = []
        for i in range(len(bounds) - 1):
            a, b = bounds[i], bounds[i + 1]
            part = _decode_words(start + a, b - a, f"{slug}_c{i}")
            stitched += [Word(w.start + a, w.end + a, w.text) for w in part]
        if stitched and _punctuated(stitched):
            words = stitched

    # restore_case takes casing and punctuation FROM the reference, on the
    # assumption the reference is the better-punctuated of the two. Check that per
    # SPAN rather than assuming it. `reference_usable()` is a whole-file gate and a
    # file can be healthy overall while one twenty-second stretch inside it is flat
    # - and aligning against a flat stretch DOWNGRADES a word pass that had the
    # text right. That is exactly how a clip shipped reading "...for an absolute
    # stone fact. because when i was on the trading floor" while the word pass had
    # it correctly cased and punctuated all along.
    kept = [w for w in words if re.search(r"[A-Za-z0-9]", w.text)]
    ref = reference_words(start, dur)
    if ref and _prose_score(ref) + 0.02 < _prose_score([w.text for w in kept]):
        sys.stderr.write(
            f"note: {slug} reference is flatter than the word pass over this span; "
            f"keeping the word pass.\n")
        ref = []
    words = restore_case(kept, ref)
    # Filter again AFTER aligning: the tokens now come from the segment reference,
    # which carries its own punctuation-only tokens (a stray "-" between clauses).
    words = [w for w in words if re.search(r"[A-Za-z0-9]", w.text)]
    words = strip_filler(fix_terms(words))
    # A clip almost always starts mid-sentence, so its first token can come back
    # lowercase. Capitalise it - a caption opening on a lowercase word reads as a
    # rendering fault rather than as a sentence joined in progress.
    if words and words[0].text[:1].islower():
        w = words[0]
        words[0] = Word(w.start, w.end, w.text[0].upper() + w.text[1:])
    return words


# ------------------------------------------------------- retention cuts ----
HOP = 0.01   # envelope resolution, 10ms


def envelope(start: float, dur: float) -> np.ndarray:
    """Short-time RMS of the clip's audio, in dB."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(AUDIO), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True)
    a = np.frombuffer(p.stdout, dtype="<i2").astype(float) / 32768
    n = int(HOP * 16000)
    if len(a) < n:
        return np.zeros(1)
    fr = a[:len(a) // n * n].reshape(-1, n)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1) + 1e-12))


# A clip must never sit in silence. Two different faults produce it and they need
# different fixes, so both live here.
# EVERY delivered clip is at least this long, end card included. Set by the user
# as a hard floor, not a target: a clip shorter than this does not hold a feed.
# Raised 35 -> 45 on 2026-08-04. Individual clips can be asked to run longer still
# (a slate entry may carry its own floor); this is the number nothing goes under.
# Enforced twice in render() - once on the requested span, so a doomed cut is
# rejected before it costs a render, and once after the silence pass, because
# collapsing dead air SHORTENS a clip and a 36s span can land under the floor.
# RAISED 45 -> 60 ON 2026-08-28, by the owner: "every clip has to be minimum a
# minute to a minute thirty." That is a floor AND a target band, and the two
# numbers are not the same kind of thing - MIN_CLIP refuses, CLIP_BAND reports.
# A clip under the floor is not shipped; a clip inside 60-90 is the house length
# and preflight says so when one lands outside it.
#
# WHAT THIS COSTS, measured over the 96 delivered clips: 71 of them are under
# 60s and would be refused today. That is not a reason to soften it - they are
# posted and finished and are never re-run - but it does mean a re-cut of any
# show before this date will stop on LENGTH, and the fix is to widen the span
# rather than to lower the number.
MIN_CLIP = _num("min_clip", 60.0)
# The house band. A clip shorter than CLIP_BAND[0] is refused by MIN_CLIP above;
# one longer than CLIP_BAND[1] is a WARN, because a long clip is sometimes right
# (the 08.21 McGlone clip the owner called "literal perfect" ran 1:35) and a
# refusal there would be this file's own recurring mistake - a gate that stops
# good work gets switched off.
CLIP_BAND = (60.0, 90.0)
# AND A CEILING. There was a floor and nothing above it, so a mis-typed `end` -
# a digit, a swapped pair - renders however long it says and the first anybody
# knows is a 6-minute file in the posting folder. This is not an editorial limit:
# the house clips run 45-90s and this sits far above them, at the point where the
# only explanation is a mistake. Every platform this ships to takes 3 minutes.
MAX_CLIP = _num("max_clip", 180.0)
CARD_SECONDS = 4.0   # what endcard.append adds; kept in step with endcard.py

MAX_GAP = 0.34       # the longest pause allowed to survive in a finished clip
MIN_SPEECH_RUN = 0.12  # shorter than this above the floor is not someone talking
KEEP_AIR = 0.24      # what a collapsed pause is left with, so speech does not slur

# HOW A CLIP ENDS. The speaker finishes the sentence, the sentence lands, there is
# a beat of air, and THEN the card takes the frame. All three parts, in that order.
#
# The words were already guarded (see finished_sentence and the out-point rule in
# render). The AIR was not, and that is what shipped as "the sentence gets cut
# off" while every text check passed. Measured on 2026-08-24 across the 83
# delivered clips under COMPLETED QM PROJS: 55 of them carried under 0.25s of air
# between the last speech and the end of the body, against a 0.25s out-fade - so
# on two thirds of the archive the fade was already running while the last word
# was still sounding. Fifteen finished AT OR ABOVE the clip's own median speech
# level (worst +6.7 dB), which is a butt cut at full voice straight into the
# swipe. The tail floor was 0.06s.
END_PAD = 0.42       # the tail taken when there is a natural pause to take it from
END_PAD_MIN = 0.30   # and the floor when the speaker runs straight on. Was 0.06.
# AND IN PRACTICE THE FLOOR IS ALWAYS WHAT APPLIES. Measured over a real 80s
# decode: 219 word transitions, only 11 carry any gap at all, the median gap
# after a SENTENCE END is 0.010s and the largest anywhere is 0.26s. Not one
# sentence end in that decode has END_PAD_MIN of transcript gap after it. So
# `min(END_PAD, gap)` never binds and every clip is padded by exactly
# END_PAD_MIN - which is the intended behaviour, but do not read the clamp as
# something that adapts. It does not; whisper butts words together.
#
# The consequence is worth knowing before anyone "fixes" the tail again. The
# acoustic release of the closing word rings about 0.15s past the timestamp the
# word pass gives it, so a 0.30s pad is roughly 0.15s of real air, and the
# out-fade rides the last of the word. On a speaker who genuinely pauses that is
# invisible; on one who runs straight into the next sentence there is no silence
# to end on at all, and the honest options are to fade over the release (what
# happens), to run on into the next sentence, or to pull back and lose the
# payoff. Fading is the right one. Raising END_PAD_MIN past about 0.30 does not
# buy air, it buys the next word.
END_FADE = 0.25      # the audio out-fade. It may never BEGIN before the last word
                     # has finished sounding - render() places it off the word,
                     # not off the end of the file.
# How far back a full stop may be and still be taken by trimming rather than by
# running on. Inside this, the out-point is essentially already on the sentence
# and a word or two of the next one hangs off it; past it, trimming DELETES a
# sentence the speaker was in the middle of, which is the defect, not the fix.
END_BACK_FREE = 0.60
# How far past the requested out-point to decode when looking for the next full
# stop. preflight used 3.0 and render 5.0, so preflight could report a span as
# stuck that render then finished cleanly - and with the run-on cap now reaching
# 6s on a long clip the disagreement got wider. One number, both files.
END_LOOKAHEAD = 5.0


DENOISE_BIN = HERE.parent / "tools" / "deep-filter"
# HOW HARD TO DENOISE, IN dB. The default is 100, which means "no limit" - take
# the noise all the way out - and that is what leaves every pause at digital
# zero. Real recorded audio never does that, and a pause that reads -240 dB
# between phrases is one of the things that makes an edit sound machine-made.
#
# MEASURED BOTH WAYS, because the answer is not the same on every master:
#
#   On a NOISY source (the Nathan Dean master with pink noise mixed in to stand
#   for a room or a Zoom), the quiet floor runs -58.5 dB raw; at the default it
#   goes to -81.5, and at 24 it goes to about -70. That difference is the room
#   still being there, and it is the whole point.
#
#   On a CLEAN source (that master untouched) it changes NOTHING - the output is
#   digital zero at every setting. Its pauses already sit at -90.8 dB, which is
#   about one bit at 16-bit, so there is no room tone left to preserve and
#   nothing to mix back. The -240 in a delivered Bloomberg clip is the SOURCE
#   being silent, not the denoiser removing anything.
#
# So this is a no-op on the clean feeds this desk mostly cuts, and a real
# improvement on the guest recorded in a room - which is exactly the material the
# rig meets when it is not cutting a studio. 24 rather than 18 because the job
# here is still to remove HVAC and hiss; the limit exists to stop it also
# removing the fact that a room exists.
DENOISE_ATTEN = _num("denoise_atten", 24)


def denoise(clip: Path) -> None:
    """
    DeepFilterNet over the finished BODY, before the end card goes on.

    Why here and not in the filter graph: deep-filter is a binary, not an ffmpeg
    filter, so it cannot be a link in the chain. Doing it on the body also keeps
    it off the card, whose swipe is a produced sound and does not want a speech
    denoiser anywhere near it.

    Measured on 30s of the 08.12.26 master: the room-tone floor went from -81.8 dB
    to digital zero and the speech peak moved -0.3 dB. It removes the Zoom hiss
    and HVAC and leaves the voice alone.

    ONE CONSEQUENCE WORTH KNOWING. Every pause in a denoised clip now reads as
    -240 dB, which is the same signature as a real hole. Any check that looks for
    dead air by absolute level has to run on the ORIGINAL audio, not on the
    delivered file, or it will flag every natural breath. The silence pass is
    safe: it works off audio16k.wav, upstream of this.

    IT USED TO DOWNMIX TO MONO ON THE WAY IN (`-ac 1`), and the body was then
    re-normalised and re-muxed as a ONE-CHANNEL file - confirmed by running the
    exact command, 2026-08-24. The end card concat upmixes it back to stereo
    against the card's own stereo audio, and that conversion is power-preserving,
    so the loudness survives the round trip and every delivered clip measures 2
    channels with L and R identical to 0.00 dB. So this was NOT costing 3 LU, and
    an earlier version of this note claiming it did was wrong.

    It is still worth not doing. A downmix averages the two channels, so a Zoom or
    StreamYard recording with one dead or noisy channel has the good channel
    halved and the bad one folded in, and nothing downstream can tell. Denoising
    the stereo the render produced costs nothing and cannot do that.

    WHAT THE REAL DEFECT IS: clips in one set do not play at the same level.
    Measured over a random 16 of the 91 delivered clips, integrated loudness runs
    -15.93 to -14.01 LUFS, sd 0.48 LU - about 2 LU end to end, which is audible
    when two clips play back to back in a feed. The cause is NOT settled, so this
    function does not try to correct it; it MEASURES and prints, so the number is
    on the record before a set ships instead of after. Read the LOUDNESS line in
    the build log across a set: if two clips differ by more than about a dB, that
    is the thing to chase, and now you can see it without decoding anything.

    Off with "denoise": false in project.json, and silently off if the binary is
    not installed.
    """
    if not CFG.get("denoise", True) or not DENOISE_BIN.exists():
        return
    tmp = WORK / "tmp"
    tmp.mkdir(exist_ok=True)
    # SCOPED TO THE CLIP, because two renders in one job folder shared these two
    # directories and raced. The loser did not fail gracefully either: it
    # rmtree'd the other render's scratch AFTER that render had written its wav
    # into it, so one clip died with FileExistsError and the other silently
    # denoised nothing. A job folder is a per-show thing and two clips of the
    # same show are exactly what somebody renders in parallel.
    din, dout = tmp / f"{clip.stem}_df_in", tmp / f"{clip.stem}_df_out"
    for d in (din, dout):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    wav = din / f"{clip.stem}.wav"
    # No `-ac 1`: keep whatever the render produced. See the note above.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(clip),
         "-vn", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)])
    p = subprocess.run([str(DENOISE_BIN), "--atten-lim-db", str(DENOISE_ATTEN),
                        "-o", str(dout), str(wav)],
                       capture_output=True, text=True)
    cleaned = dout / wav.name
    if p.returncode != 0 or not cleaned.exists():
        sys.stderr.write(f"note: denoise skipped for {clip.stem} "
                         f"({p.stderr.strip()[-160:] or 'no output'}).\n")
        return
    # Re-normalise on the CLEANED audio. The first loudnorm measured a signal that
    # still had a noise floor in it; with the floor gone the same target lands
    # slightly differently, and the set has to match across clips.
    merged = tmp / f"{clip.stem}_dn.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-i", str(cleaned),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
         # -ar EXPLICITLY. Without it this re-encode inherits whatever sample
         # rate the denoiser emitted, so the delivered body could differ from
         # every other clip in the set - and from the end card it is concatenated
         # with, which is the one seam a rate mismatch is audible at.
         "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart",
         str(merged)])
    shutil.move(str(merged), str(clip))
    sys.stderr.write(f"denoise: {clip.stem} cleaned (DeepFilterNet)\n")


def report_loudness(clip: Path) -> None:
    """
    Print what this body actually measures, so a mismatched set is visible.

    The chain targets I=-14 / TP=-1.5 twice - once in the render filter graph and
    again after the denoise - and nothing has ever checked that the file agrees.
    It mostly does not: sd 0.48 LU across a 16-clip sample, 2 LU end to end.

    A number in the build log is the whole feature. Do NOT turn this into a
    correction loop: `loudnorm` is single-pass by design here, chasing
    |I - target| < 0.1 would ship unnormalised audio on the three denoise skip
    paths, and references/pipeline.md already sets the defensible bar at "within
    about a dB across the set". This makes that bar checkable.
    """
    try:
        p = subprocess.run(
            # -vn, because `-f null` otherwise maps and fully decodes the
            # 1080x1920 stream for a measurement that only reads audio: 15.67
            # against 2.81 CPU-seconds on a 49.5s clip, identical I/TP/LRA.
            ["ffmpeg", "-hide_banner", "-nostats", "-vn", "-i", str(clip), "-af",
             "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True)
    except OSError:
        return
    # The LAST json block, not the first: ffmpeg can print more than one, and the
    # measurement summary is the one at the end.
    ms = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', p.stderr, re.S)
    if not ms:
        return
    m = ms[-1]
    try:
        j = json.loads(m)
        I, TP, LRA = float(j["input_i"]), float(j["input_tp"]), float(j["input_lra"])
    except (ValueError, KeyError, TypeError):
        return
    if not all(abs(v) < 1e4 for v in (I, TP, LRA)):
        # A SILENT CLIP IS A REFUSAL, not a skipped log line. loudnorm prints
        # -inf / -70 on a stream with no signal, and this used to `return` -
        # so the one measurement that can see a dead clip stayed quiet about
        # exactly the case it should shout at. selftest's silencedetect could
        # not catch it either (it was passing `-v error`, which deletes the
        # filter's output), so a clip with no sound had nothing standing
        # between it and the posting folder.
        raise SystemExit(
            f"SILENT CLIP: {clip.stem} measures I={I} LUFS - there is no "
            f"audio in the delivered file. Check the master's audio stream, "
            f"the mute windows, and that the span is not entirely inside one.")
    LOUDNESS[clip.stem] = (I, TP)
    flag = "" if abs(I + 14.0) <= 1.0 else "   <- over a dB off target"
    sys.stderr.write(f"loudness: {clip.stem} I={I:.2f} LUFS  TP={TP:.2f} dBTP  "
                     f"LRA={LRA:.1f}{flag}\n")
    try:
        report_timbre(clip)
    except Exception:                                        # noqa: BLE001
        pass


def report_timbre(clip: Path) -> None:
    """
    How BRIGHT this clip is, so a set cut from two microphones is visible.

    Guests arrive on whatever they own, and a set does not match in timbre even
    when it matches in level. Measured across 89 delivered clips, the 4-6 kHz
    band relative to the 500 Hz - 4 kHz speech core has a between-clip spread of
    sd 4.51 dB, and it correlates only r=0.146 with source bandwidth - so it is
    real microphone difference, not a codec artefact.

    THIS MEASURES AND DOES NOT CORRECT, deliberately. A band EQ was designed and
    costed, and the honest conclusion was that the log line is most of its value:
    a guest whose mic is 8 dB bright is something to fix at the source next week,
    not to paper over every week. It is also sequenced behind a loudness question
    that is still open - the archive's 2 LU spread has no confirmed cause - and
    correcting timbre on top of an unexplained level difference is guessing
    twice. If it is ever built: ONE band, correct only outside a window, move
    only to the window edge, clamp, one pass, and never treat a `duo` as one
    signal (the duo demanding the largest correction has a WITHIN-clip swing of
    14.70 dB, larger than the between-clip spread the stage would exist to fix).

    Only the 4-6 kHz band is worth reporting. 60-120 Hz sits under the deliberate
    highpass=75 and no phone reproduces it; 6-9 kHz correlates r=0.671 with the
    codec band, so it mostly measures the encoder; 500 Hz-4 kHz is already matched
    to under 2 dB across the archive.
    """
    try:
        # 120s cap on the decode. A body never runs longer in practice and the
        # measurement is an average, so more samples buy nothing - but an
        # unbounded rfft on a surprise input is how a report crashes a render.
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(clip), "-t", "120", "-ac", "1",
             "-ar", "16000", "-f", "f32le", "-"], capture_output=True)
        if not p.stdout:
            return
        x = np.frombuffer(p.stdout, dtype=np.float32)
        if x.size < 16000:
            return
        n = 1024
        m = x.size // n * n
        F = np.abs(np.fft.rfft(x[:m].reshape(-1, n) * np.hanning(n), axis=1)) ** 2
        power = F.mean(axis=0)
        freq = np.fft.rfftfreq(n, 1 / 16000)
        core = power[(freq >= 500) & (freq < 4000)].mean()
        hi = power[(freq >= 4000) & (freq < 6000)].mean()
        if core <= 0 or hi <= 0:
            return
        rel = 10 * np.log10(hi / core)
        TIMBRE[clip.stem] = float(rel)
        sys.stderr.write(f"timbre:   {clip.stem} 4-6kHz {rel:+.1f} dB rel. speech "
                         f"core\n")
    except Exception:
        pass


def speech_floor(env: np.ndarray) -> float:
    """
    The dB line below which audio is not someone talking.

    Relative to the clip's own speech level, because show audio is not normalised,
    with an absolute backstop so a very quiet clip cannot drag the line into its
    own dialogue.
    """
    # Measured on four clips off one master: speech sits at about -16 dB (85th
    # pct) and real silence at -60 to -85. A floor 28 dB under speech lands near
    # -44, which separates them cleanly. -35 dB under (the first attempt) put the
    # line at -51 and let room tone count as talking, so a 1.3s dead tail survived
    # the pass and still shipped. Clamped both ways: never so low it ignores a
    # pause, never so high it starts eating quiet consonants.
    return min(max(float(np.percentile(env, 85)) - 28.0, -46.0), -40.0)


def last_speech(env: np.ndarray, upto: float, min_run: float = 0.15) -> float | None:
    """
    When someone last actually SPOKE, in seconds.

    Not "the last frame above the floor" - a single 10ms transient clears that,
    and one -43 dB click nine seconds into dead air was enough to defeat the
    out-point trim. Speech is sustained, so it has to hold above the floor for
    at least `min_run`.
    """
    if env.size < 2:
        return None
    thr = speech_floor(env)
    n = min(len(env), max(1, int(upto / HOP)))
    need = max(1, int(min_run / HOP))
    end = None
    i = 0
    while i < n:
        if env[i] < thr:
            i += 1
            continue
        j = i
        while j < n and env[j] >= thr:
            j += 1
        if j - i >= need:
            end = j * HOP
        i = j
    return end


def decode_window(env: np.ndarray, dur: float, lookahead: float,
                  max_hole: float = 1.0) -> float:
    """
    How much audio to hand the word-level decoder.

    The lookahead exists to find the NEXT sentence end past the out-point, but on
    a live show the next sentence can be ten seconds away with dead air in
    between. Whisper spreads a chunk's words across the whole chunk, so a silent
    hole inside the window drags the words before it late - on one clip the last
    four words landed 1 to 4 seconds after the audio had already stopped, which
    then read as hallucination and got real speech deleted.

    So the window ends at the first silent hole after the clip's own last word.
    Trimming the tail is not enough; the hole is usually in the middle.
    """
    if env.size < 2:
        return dur + lookahead
    thr = speech_floor(env)
    end_s = last_speech(env, dur)
    if end_s is None:
        return dur + lookahead
    last = int(end_s / HOP)
    n = min(len(env), int((dur + lookahead) / HOP))
    i = last + 1
    while i < n:
        if env[i] >= thr:
            i += 1
            continue
        j = i
        while j < n and env[j] < thr:
            j += 1
        if (j - i) * HOP >= max_hole:
            return max(1.0, i * HOP + 0.35)
        i = j
    return dur + lookahead


def drop_unspoken(words: list[Word], env: np.ndarray) -> list[Word]:
    """
    Remove words the audio does not contain.

    whisper does not return "nothing" for dead air - it HALLUCINATES fluent text
    over it, with plausible timings. One clip shipped ending on "That's a lot."
    laid over eight seconds of -85 dB silence: the words were never spoken, and
    they were burned into the captions.

    A word that was really said has energy somewhere inside its own span. One that
    does not is invented, so it goes.
    """
    if env.size < 2 or not words:
        return words
    thr = speech_floor(env)

    def quiet(w: Word) -> bool:
        a = max(0, int(w.start / HOP) - 4)
        b = min(len(env), int(w.end / HOP) + 4)
        return b <= a or float(env[a:b].max()) < thr

    flags = [quiet(w) for w in words]

    # Drop RUNS, not individual words. A single word under the floor is a soft
    # function word - "I'm", "a", the unstressed half of a contraction - and
    # dropping those corrupted real captions ("Something happens at bank"). A
    # hallucination is different in kind: whisper fills LONG dead air, so it
    # arrives as a run of words with no energy anywhere under any of them.
    drop = [False] * len(words)
    i = 0
    while i < len(words):
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < len(words) and flags[j]:
            j += 1
        span = words[j - 1].end - words[i].start
        # a trailing run is the common case and is judged more harshly, because
        # nothing after it can vouch for it
        # 1.5s for an interior run, not 0.9s. A SHORT run over silence is usually
        # real speech whose timings drifted early, not an invention: "Well, it
        # doesn't" got timed into a 1.3s pause a beat before he actually said it,
        # and deleting it left a caption reading "All right. affect me, Big B."
        # Losing real words is worse than a caption highlight arriving a beat off.
        # The hallucinations this guard exists for are much longer - the two that
        # shipped were 4s and 14 words - so they are still caught.
        if span >= 1.50 or (j == len(words) and span >= 0.45):
            for k in range(i, j):
                drop[k] = True
        i = j

    kept = [w for w, d in zip(words, drop) if not d]
    if len(kept) != len(words):
        lost = " ".join(w.text.strip() for w, d in zip(words, drop) if d)
        sys.stderr.write(
            f"note: dropped {len(words) - len(kept)} word(s) whisper invented "
            f"over silence: \"{lost[:80]}\"\n")
    return kept


def collapse_silence(env: np.ndarray, dur: float,
                     max_gap: float = MAX_GAP) -> list[tuple[float, float]]:
    """
    Removal windows that squeeze EVERY silent run down to `KEEP_AIR`.

    `find_removals` only cuts at sentence ends, takes at most `cut_frames`, and
    gives up when speech does not resume inside `resume_window` - so on a live
    show, where the host goes quiet mid-thought to read a chart, the longest holes
    are exactly the ones it skips. One clip came back 31% silence.

    This pass ignores sentences and works straight off the envelope, so nothing
    survives on a technicality.
    """
    if env.size < 2:
        return []
    thr = speech_floor(env)
    quiet = env < thr
    n = min(len(env), int(dur / HOP))

    # SPEECH IS SUSTAINED, so a lone sample poking above the floor does not end a
    # pause. `last_speech` already knows this - it demands a `min_run` because one
    # -43 dB click nine seconds into dead air defeated the out-point trim - but
    # this pass did not, and the same fault shows up differently here: instead of
    # missing a pause it SHREDS one. A 1.45s hole on the 08.18 master carried two
    # room-tone transients at -44.5 and -45.8 against a floor of -46.0. They split
    # it into runs of 0.95s, 0.20s and 0.20s; only the first cleared MAX_GAP, so
    # 0.65s of the pause shipped - as three fragments the residual check then
    # reported as three short pauses rather than one long one.
    #
    # The transients are room tone, and DeepFilterNet deletes room tone, so what
    # measured -45 dB in the source played at -80 dB in the delivered file. The
    # hole was audible in a way nothing upstream had flagged.
    #
    # Bridge them: a stretch above the floor that is both BRIEF and QUIET (never
    # more than 8 dB clear of the line - a real word is 20 dB clear) is treated as
    # part of the pause it interrupts. Both conditions matter. Brief alone would
    # swallow a clipped "yeah."; quiet alone would swallow a mumbled sentence.
    hold = max(1, int(MIN_SPEECH_RUN / HOP))
    i = 0
    while i < n:
        if quiet[i]:
            i += 1
            continue
        j = i
        while j < n and not quiet[j]:
            j += 1
        # `0 < i` used to be here and it excluded index 0 by construction, so a
        # clip whose head sits ON the room-tone line - measured, a delivered clip
        # opened at -44.4 dB against a floor of -44.2 - had no leading pause to
        # find and the clamp below could not reach it. The head is exactly where a
        # brief quiet stretch most wants bridging, because there is no preceding
        # word for it to belong to.
        if (j < n and j - i < hold
                and float(env[i:j].max()) < thr + 8.0):
            quiet[i:j] = True
        i = j

    out: list[tuple[float, float]] = []
    i = 0
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        a, b = i * HOP, j * HOP
        # THE RUN AT THE HEAD OF THE CLIP IS DIFFERENT, and it used to be treated
        # the same. Two things kept dead air at the front: this `> max_gap` gate
        # skipped any leading pause under 0.34s entirely, and KEEP_AIR then left
        # another 0.24s in front of the cut when it did fire. Nothing else pulls
        # the in-point onto the first word - render() trims only the out-point.
        #
        # Measured over 90 delivered clips, time to first speech: median about
        # 0.05-0.12s, p75 0.16-0.27s, worst 0.61s. Eight to fourteen clips open on
        # 0.30s or more, and the worst of them is LITERAL digital silence - the
        # first 60ms of one reads -240/-126/-90/-124/-195/-240 dBFS with no
        # caption word until +0.59s. That is the stay-or-scroll window spent on
        # nothing.
        #
        # CLAMP, DO NOT DELETE. Two measurements say a near-zero lead is wrong.
        # The 80ms `afade=t=in` would then sit on the first phoneme - the exact
        # mirror of the out-fade defect fixed on 2026-08-24. And the opening is
        # STAGED: measured on a delivered clip the hook card plateaus at t=0.233
        # and the caption pops at t=0.267, so the headline lands and then the
        # first word does, two frames apart. KEEP_AIR is what the well-behaved
        # clips already have, so clamping to it preserves that staging exactly
        # while removing the 0.61s beat from the clips that have one.
        head = (i == 0)
        if b - a > (KEEP_AIR + 0.06 if head else max_gap):
            # keep a breath at the FRONT of the pause: the beat after a sentence
            # is what makes a cut feel like an edit rather than a glitch. At the
            # head there is no preceding sentence, so the breath is the lead-in
            # the card arrives over, and KEEP_AIR is the whole of it.
            st = snap(0.0) if head else snap(a + KEEP_AIR)
            en = snap(b - KEEP_AIR if head else b - 0.02)
            # NO REMOVAL MAY EAT THE CLIP'S TAIL. plan_ending has already set
            # `dur` to the last word plus at least END_PAD_MIN, deliberately, so
            # the final word is not butt-cut and the out-fade does not run while
            # it is still sounding. This pass then took the trailing pause down
            # to `b - 0.02` and gave that tail straight back: measured on
            # 02-no-good-answers-on-hormuz, a 0.30s guaranteed tail was delivered
            # as 0.07s. The pause is collapsed from the ACOUSTIC start of the
            # silence, which sits before the transcript's word end, so the window
            # reached past the word it was supposed to be standing off.
            if not head:
                en = min(en, snap(dur - END_PAD_MIN))
            if en - st >= 0.08 and en < dur and (head or st > 0):
                out.append((st, en))
        i = j
    return out


def merge_windows(*groups: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Union of removal windows. apply_removals sums over them, so any overlap
    would be subtracted twice and the timeline would drift."""
    all_w = sorted(w for g in groups for w in g)
    out: list[tuple[float, float]] = []
    for s, e in all_w:
        if out and s <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return [(s, e) for s, e in out if e > s]


def residual_silence(env: np.ndarray, rem: list[tuple[float, float]],
                     dur: float) -> float:
    """Longest pause that will still be in the finished clip. The check that the
    other two functions actually worked."""
    if env.size < 2:
        return 0.0
    thr = speech_floor(env)
    removed = lambda t: any(s <= t < e for s, e in rem)
    worst = cur = 0.0
    for i in range(min(len(env), int(dur / HOP))):
        if removed(i * HOP):
            continue
        if env[i] < thr:
            cur += HOP
            worst = max(worst, cur)
        else:
            cur = 0.0
    return worst


def find_removals(words: list[Word], env: np.ndarray,
                  dur: float) -> list[tuple[float, float]]:
    """
    Windows of real silence to drop, one per sentence end where there is
    enough air. Returns frame-snapped (start, end) pairs in source time.
    """
    if env.size < 2:
        return []
    # ONE definition of silence, shared with collapse_silence and
    # residual_silence. This used to be `speech - 18.0`, which sits 10 dB ABOVE
    # speech_floor - so the two passes disagreed about where a pause began, and
    # this one started its cut inside the previous word's release: it clipped the
    # tail of the speech and left the actual silence sitting after the join.
    speech = float(np.percentile(env, 85))
    thr = speech_floor(env)
    out: list[tuple[float, float]] = []
    last = -MIN_SPACING
    for w in words[:-1]:
        if not w.text.rstrip().endswith((".", "!", "?")):
            continue
        if w.end - last < MIN_SPACING or dur - w.end < 0.60:
            continue
        # Walk forward from the sentence end to where speech actually resumes
        # (energy back above threshold and staying there), then back to where
        # the pause began. A fixed search window is not enough: Steve's pauses
        # run past it, so its far edge is not the real end of the silence and
        # the cut lands mid-pause instead of butted against the next line.
        hold = int(0.04 / HOP)
        i = int(w.end / HOP)
        lim = min(len(env), int((w.end + RESUME_WINDOW) / HOP))
        resume = None
        while i < lim:
            if env[i] >= thr and all(env[j] >= thr for j in
                                     range(i, min(i + hold, len(env)))):
                resume = i
                break
            i += 1
        if resume is None:
            continue
        j = resume
        while j > 0 and env[j - 1] < thr:
            j -= 1
        air = (resume - j) * HOP
        if air < MIN_AIR:
            continue
        take = snap(min(CUT, air - 0.04))
        if take < MIN_AIR:
            continue
        # Butt the removal up against the resuming speech so the next sentence
        # starts right after the join, the way the reference reel does.
        e = snap(resume * HOP - 0.05)
        s = snap(e - take)
        if s < j * HOP:
            s = snap(j * HOP)
            e = snap(s + take)
        if e <= s or e >= dur or s <= 0:
            continue
        out.append((s, e))
        last = w.end
    return out


# ------------------------------------------------------------------ the weld --
# A CLIP MAY BE TWO MOMENTS. Everything above this cuts SILENCE; the weld cuts
# SPEECH, deliberately, and it is the only thing in the pipeline that does.
#
# WHY IT EXISTS. People do not talk in 75-second units. The hook is at 12:04,
# the payoff is at 19:41, and between them is three minutes of a different
# subject. A contiguous span either loses the hook or ships the three minutes,
# and until this existed those were the only two options - so the picker's whole
# job was finding the rare stretch where one idea happens to open and close
# inside the band. Most good moments are not shaped like that.
#
# WHY IT IS NOT TWO RENDERS CONCATENATED. That is the obvious shape and it is
# wrong here. Every overlay in this pipeline - captions, hook card, nameplate,
# cutaways, CTA, out-fade - is authored against ONE timeline derived from
# out_dur. Two renders means two of everything and a seam where the two clocks
# meet, which is exactly the class of bug this file spends most of its length
# recording. But the renderer ALREADY removes arbitrary windows from a span and
# concatenates what survives, picture and sound together, and it has done it on
# every clip for months (see cut_graph). So a weld is not a new mechanic: it is
# an authored removal that happens to contain speech. `start` and `end` stay the
# outer bounds, the middle is dropped, and everything downstream sees one
# ordinary, slightly shorter clip. Nothing else in the graph had to learn about
# it.
#
# THE ONE THING THAT IS GENUINELY NEW is that the words inside the window have
# to GO. apply_removals maps a time inside a removed window onto that window's
# START, which is right for silence - there are no words in it - and
# catastrophic here: the entire dropped passage would pile up on the join at
# 0.06s per word and strobe through the captions. drop_words deletes them before
# the map runs. That asymmetry is the whole reason this is a named function and
# not two lines at the call site.
MIN_DROP = 4.0      # under this it is a trim; move `end` instead
DROP_SNAP = 0.75    # how far an edge may be walked to find real air
DROP_SIDE = 4.0     # body either side, so neither half is a fragment
DROP_HOLD = 0.05    # a silent run this long is silence; one sample is a dip


def _in_air(env: np.ndarray, i: int, n: int) -> bool:
    """
    Silence at sample i, measured as a RUN and not as a sample.

    The same lesson find_removals and last_speech both record: a single 10ms
    frame clears or fails any threshold you like. One -43 dB click nine seconds
    into dead air was once enough to defeat the out-point trim entirely.
    """
    thr = speech_floor(env)
    hold = max(1, int(DROP_HOLD / HOP))
    if i < 0 or i + hold > n:
        return False
    return bool(np.all(env[i:i + hold] < thr))


def air_edges(env: np.ndarray, dur: float, a: float, b: float
              ) -> tuple[float, float, str]:
    """
    Move an authored drop onto real air, keeping the words either side WHOLE.

    Authored edges come off sentence times, and pick.py's sentence times are
    interpolated by character count inside a cue - accurate to the second, not
    to the phoneme. Cutting on one lands mid-word about as often as not, and a
    weld that clips the last syllable of the hook is worse than no weld at all.

    THE DIRECTION OF EACH WALK IS THE ONE THAT KEEPS THE SPEECH. The drop's
    start walks FORWARD out of speech, so the last word before the join
    survives; its end walks BACK out of speech, so the first word after the join
    survives. An edge already sitting in air does not move.

    Beyond DROP_SNAP the authoring is wrong rather than imprecise, and the
    caller is told so - a snap with no ceiling would quietly eat a sentence to
    make a bad weld look legal.
    """
    n = min(len(env), int(dur / HOP))
    if n < 2:
        return a, b, ""
    lim = int(DROP_SNAP / HOP)
    note = []

    i, moved = int(a / HOP), 0
    while moved < lim and not _in_air(env, i, n):
        i += 1
        moved += 1
    if moved:
        note.append(f"in +{moved * HOP:.2f}s")
    a2 = i * HOP if moved <= lim else a
    if moved >= lim:
        note.append("in NOT FOUND")

    j, moved_b = int(b / HOP), 0
    while moved_b < lim and not _in_air(env, j - int(DROP_HOLD / HOP), n):
        j -= 1
        moved_b += 1
    if moved_b:
        note.append(f"out -{moved_b * HOP:.2f}s")
    b2 = j * HOP if moved_b <= lim else b
    if moved_b >= lim:
        note.append("out NOT FOUND")

    return snap(a2), snap(b2), ", ".join(note)


def weld_windows(drop: list[list[float]] | None, start: float, dur: float,
                 env: np.ndarray) -> tuple[list[tuple[float, float]], list[str]]:
    """
    Authored excisions in SOURCE seconds -> validated windows in SPAN time.

    Returns (windows, problems) rather than raising, because the two callers
    need the same verdict in two shapes: render() turns a problem into a
    SystemExit, and preflight prints it beside every other refusal. One owner,
    two presentations - the alternative is two implementations of one rule,
    which is how the two tools came to disagree about length by six seconds.
    """
    if not drop:
        return [], []
    bad: list[str] = []
    out: list[tuple[float, float]] = []
    for k, d in enumerate(drop):
        try:
            a0, b0 = float(d[0]) - start, float(d[1]) - start
        except (TypeError, ValueError, IndexError):
            bad.append(f"drop {k} is not a [from, to] pair of source seconds")
            continue
        if b0 <= a0:
            bad.append(f"drop {k} runs backwards ({d[0]} -> {d[1]})")
            continue
        if a0 < 0 or b0 > dur:
            bad.append(
                f"drop {k} ({d[0]:.1f} -> {d[1]:.1f}) is outside the span "
                f"{start:.1f} -> {start + dur:.1f} - a weld cuts the MIDDLE "
                f"out; to move an edge, author `start` or `end`")
            continue
        a, b, note = air_edges(env, dur, a0, b0)
        if "NOT FOUND" in note:
            bad.append(
                f"drop {k} ({d[0]:.1f} -> {d[1]:.1f}) has no silence within "
                f"{DROP_SNAP:.2f}s of an edge - it is cutting into speech. "
                f"Move it onto a sentence end.")
            continue
        if b - a < MIN_DROP:
            bad.append(
                f"drop {k} removes only {b - a:.1f}s. Under {MIN_DROP:.0f}s "
                f"this is a trim, not a weld - author `end` instead")
            continue
        out.append((a, b))
    out.sort()
    for i in range(len(out) - 1):
        if out[i + 1][0] < out[i][1]:
            bad.append("two drops overlap; merge them into one")
            break
    if out:
        if out[0][0] < DROP_SIDE:
            bad.append(
                f"the first half is only {out[0][0]:.1f}s long - under "
                f"{DROP_SIDE:.0f}s it is a fragment, not a hook")
        if dur - out[-1][1] < DROP_SIDE:
            bad.append(
                f"the last half is only {dur - out[-1][1]:.1f}s long - under "
                f"{DROP_SIDE:.0f}s it is a fragment, not a payoff")
    return out, bad


def drop_words(words: list[Word],
               drops: list[tuple[float, float]]) -> list[Word]:
    """
    Words inside an authored excision are GONE, not collapsed.

    Tested on the MIDPOINT so a word straddling an edge by a few milliseconds
    goes to the side it mostly belongs to, rather than being duplicated on one
    side and half-spoken on the other.
    """
    if not drops:
        return words
    keep = []
    for w in words:
        mid = (w.start + w.end) / 2
        if any(s <= mid < e for s, e in drops):
            continue
        keep.append(w)
    return keep

def remap_time(t: float, rem: list[tuple[float, float]]) -> float:
    """
    A time on the ORIGINAL span -> the same moment on the shortened one.

    THE ONLY forward map in this pipeline, and it is module scope for a reason.
    broll_chain used to carry its own walk-the-windows version of this, and the
    two disagreed: on a time landing INSIDE a removed window the loop assigned
    that window's raw start, forgetting the windows already subtracted before it,
    so an insert placed up to 1.9s late on the real 08.18 removal sets. Two ways
    of computing the same number is exactly how the captions drifted off the
    words the first time this pipeline had a timeline.
    """
    # a time inside a removed window collapses to that window's start
    return t - sum(min(max(t - s, 0.0), e - s) for s, e in rem)


def apply_removals(words: list[Word], dur: float,
                   rem: list[tuple[float, float]]) -> tuple[list[Word], float]:
    """Map word timings onto the shortened timeline."""
    if not rem:
        return words, dur
    total = sum(e - s for s, e in rem)
    remap = lambda t: remap_time(t, rem)

    out = []
    for w in words:
        a, b = remap(w.start), remap(w.end)
        out.append(Word(a, max(b, a + 0.06), w.text))
    return out, dur - total


# ---------------------------------------------------------- typography -----
def tracked_width(d: ImageDraw.ImageDraw, text: str,
                  font: ImageFont.FreeTypeFont, track: float) -> float:
    return d.textlength(text, font=font) + track * max(0, len(text) - 1)


def draw_tracked(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
                 font: ImageFont.FreeTypeFont, fill, track: float,
                 stroke: int = 0, stroke_fill=None) -> float:
    """
    PIL has no letter-spacing, and this look depends on it.

    Drawn in two passes when a stroke is asked for: every glyph's outline first,
    then every glyph's face. One pass would let the next letter's outline sit on
    top of the previous letter's face, which at tracked spacing chews a notch out
    of the right side of each character.
    """
    x, y = xy
    if stroke:
        cx = x
        for ch in text:
            d.text((cx, y), ch, font=font, fill=stroke_fill,
                   stroke_width=stroke, stroke_fill=stroke_fill)
            cx += d.textlength(ch, font=font) + track
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + track
    return x


def wrap_tracked(d: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                 max_w: float, track: float) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if tracked_width(d, trial, font, track) <= max_w or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def wrap_balanced(d: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                  max_w: float, track: float) -> list[str]:
    """
    Wrap into even-length lines rather than filling greedily.

    Greedy filling packs the first line and leaves whatever is left on the last
    one, which strands orphans: "Your data is already / there" reads as text that
    overflowed, not as a headline that was set. Balancing the same words gives
    "Your data is / already there".

    Same line count as greedy - this only moves the breaks - chosen by minimising
    the sum of squared slack against the measure, the classic Knuth objective.
    """
    words = text.split()
    n = len(words)
    greedy = wrap_tracked(d, text, font, max_w, track)
    if n < 2 or len(greedy) < 2:
        return greedy
    target = len(greedy)

    def width(i: int, j: int) -> float:
        return tracked_width(d, " ".join(words[i:j]), font, track)

    INF = float("inf")
    memo: dict[tuple[int, int], tuple[float, list[int]]] = {}

    def solve(i: int, k: int) -> tuple[float, list[int]]:
        if k == 1:
            w = width(i, n)
            return ((max_w - w) ** 2, [n]) if w <= max_w else (INF, [])
        if (i, k) in memo:
            return memo[(i, k)]
        best: tuple[float, list[int]] = (INF, [])
        for j in range(i + 1, n - k + 2):
            w = width(i, j)
            if w > max_w:
                break
            cost, rest = solve(j, k - 1)
            if cost == INF:
                continue
            total = cost + (max_w - w) ** 2
            if total < best[0]:
                best = (total, [j] + rest)
        memo[(i, k)] = best
        return best

    cost, cuts = solve(0, target)
    if cost == INF:
        return greedy
    out, prev = [], 0
    for c in cuts:
        out.append(" ".join(words[prev:c]))
        prev = c
    return out


STOP = set("""a an and are as at be been but by can could did do does for from
get got had has have he her him his how i if in into is it its just like me my
no not of on or our out say says she so than that the their them then there
these they this to too up us was we were what when which who will with would
you your im its dont thats theres youre were weve ive youve about all also am
any because been before being both each even ever every much many more most
some such very only other over same still take than very well why
theyre doesnt wouldnt couldnt shouldnt isnt wasnt arent werent didnt cant wont
hasnt havent hes shes lets whats wheres hows thatll itll theyll youll wed theyd
gonna gotta kinda sorta yeah okay""".split())


def _keyword(text: str) -> bool:
    """
    Is this a word the eye should land on?

    The live-word highlight is a reading aid - it says where you are, not what
    matters. Colouring the nouns, numbers and names instead means a viewer who
    reads nothing else still takes the point off the frame. Anything with a digit
    or a capital mid-sentence qualifies; so does any long word that is not
    furniture.
    """
    core = split_token(text)[0]
    if not core:
        return False
    if any(c.isdigit() for c in core) or "%" in text or "$" in text:
        return True
    # Strip the apostrophe BEFORE the furniture test. It used to be tested raw,
    # so "they're" never matched anything in STOP, fell through to the capital
    # rule, and took the accent colour - measured 2026-08-24, 157 accented words
    # across 4,860 were contractions, and 27 caption lines in 25 delivered clips
    # came out ENTIRELY accent-coloured, including one frame reading just
    # "what's" in accent blue over a chart. STOP already held the stripped forms
    # of I'm / it's / don't / that's / you're; it did not hold they're, which is
    # 29 of the 157 on its own.
    #
    # NOT COSMETIC. _keyword also drives the punch ladder (see punch_windows), so
    # a key rung that was firing on a contraction now fires on the next real noun
    # or number instead - measured, a median 0.60s later. Re-read preflight's
    # PUNCH line after touching this; that is the acceptance test, not the
    # accent count.
    low = core.lower().replace("'", "").replace("\u2019", "")
    if low in STOP:
        return False
    if core[:1].isupper() and len(core) > 2:
        return True
    return len(low) >= 6


# How long the last card of a chunk stays up after its last word, when the next
# chunk is not already due. It was a bare 0.30 literal here and NOTHING in
# write_srt, so the sidecar .srt and the burned-in captions disagreed by up to
# 0.30s on every cue.
#
# 0.40, because MAX_GAP (0.34) is this pipeline's own declaration of the longest
# pause a finished clip may contain, plus two frames of whisper slop. A card can
# therefore never hold past something the cut mechanic already calls not-a-pause.
# Measured over 32 modern clips: the band went empty 70 times for 12.75s total,
# and one of those holes is five consecutive frames sitting OVER a b-roll
# cutaway, where the caption is the only thing carrying the speech. At 0.40 that
# is 34 holes and 7.76s.
#
# DO NOT RAISE IT TO ~0.9 TO CLOSE THE REST. Measured, the LARGEST gaps are the
# LOUDEST: a 1.67s hole peaks at -11.7 dBFS against a -14.5 dBFS speech level,
# i.e. it is live speech whisper failed to timestamp, not a pause. A long linger
# parks a stale card over a different sentence.
CAP_LINGER = 0.40

# Words that must not END a caption card. A card breaking after "the" or "of"
# reads as text that overflowed rather than text that was set - it is the classic
# amateur tell, and it was happening on 21.2% of cards. Deliberately NARROW:
# seeding this from STOP (which holds is / are / was / we / that / this) produces
# 181 one-word cards, a stutter worse than the fault being fixed.
CAP_NO_TAIL = set("""a an the of to in on at by for from with into onto over
under and or but nor so yet than that as if is are was were be been am do does
did has have had will would can could should may might must our your their its
his her my
i we you he she it they""".split())
# The subject pronouns on that last line were added after a render: a card came
# out reading "level they", which opens a clause and leaves it hanging. Measured
# over the archive they take bad tails from 17.9% to 15.6% for four extra cards
# in 2,390 and no extra orphans - so they are free. This is as far as the list
# goes: the audit that produced it measured that seeding from STOP, which also
# holds is / are / was / that / this, produces 181 one-word cards.


# The cost of breaking a card, tuned by sweep against the 43 delivered caption
# files (2,380 cards). Every term is load-bearing and two of them were arrived at
# only after the first attempt failed:
#
#   CAP_BREAK   a flat charge for making a card AT ALL. Without it the program
#               has no reason to pack, and it split gratuitously: +365 cards
#               (+15%) on the first run, which is a churnier band, not a calmer
#               one. At 3.0 the card count comes out +0.4% - unchanged.
#   CAP_ORPHAN  a one-word card. The first attempt charged 5.0 and produced 265
#               of them against 62 delivered - a stutter worse than the fault
#               being fixed. It saturates at 9.0: past that the remaining
#               orphans are FORCED (a word too wide to share a card at
#               CAP_MEASURE - "neuromorphic", "announcements"), not chosen.
#
# Result over the archive: cards 2,380 -> 2,390 (+0.4%), ending on furniture
# 30.3% -> 11.0%, cards too brief to read 224 -> 208, one-word cards 62 -> 84
# (of which 30 are a whole one-word sentence, which is a beat and not an orphan).
CAP_BREAK = 3.00
CAP_ORPHAN = 9.00
# NO CARD MAY FLASH. _tail_cost already charges a chunk that is too brief to
# read, but a cost can be outbid, and on the 08.28 clip it was: 12 of 71 cards
# came in under 0.45s and two ran 0.13s - FOUR FRAMES. Measured on the delivered
# file, "Even though" appeared and vanished between "the last meeting." and "the
# Democrats are". The eye catches the flicker and reads nothing, which is worse
# than the words never being there. Peak rate was 23.6 words per second.
#
# The cause is upstream and not fixable here: "Even though" cannot be spoken in
# four frames, so whisper's word alignment is simply wrong at that point, and a
# grouper that trusts those times will keep producing flickers however the cost
# is tuned. So this is a FLOOR, applied after the program has run - a sub-floor
# card is merged into a neighbour rather than shown.
#
# The merge is allowed to exceed `max_words` because the hard constraint is that
# the card fits ONE LINE; the word count is a style preference, and a 5-word
# card that can be read beats a 2-word card that cannot. It never crosses a
# sentence boundary - best_split runs per sentence and so does this.
CAP_MIN_ON = 0.45
# WHEN A CARD CANNOT BORROW A WORD, IT BORROWS TIME. The word-level rebalance
# above fixes most flickers, but eight of the 08.28 clip's cards stayed under
# the floor because they are WIDTH-BOUND - the line physically cannot hold
# another word. "Even though the" still measured 0.31s, and it cannot be spoken
# in 0.31s: whisper's word alignment is simply wrong at those points, and no
# amount of regrouping repairs a bad timestamp.
#
# So the next card is shown slightly LATE instead, which hands its slack to the
# card that needs it. This is ordinary subtitle practice - a caption need not
# start on the exact frame of its first phoneme - and it is bounded, because a
# caption that drifts far from the voice is its own defect. A card may never
# appear more than CAP_LATE_MAX after its own first word, and never after that
# word has finished being spoken.
CAP_LATE_MAX = 0.20


def _tail_cost(chunk: list["Word"], last: bool = False,
               tempo: float = 1.0) -> float:
    """
    How bad a place to break is the end of this chunk?

    `last` means this is the final chunk of a sentence, so it is not a break at
    all - the sentence ends there whatever we do. It is charged nothing except
    the orphan term, which still applies: a sentence ending on a lone word is a
    lone word on screen either way.
    """
    if not chunk:
        return 0.0
    if last:
        return CAP_ORPHAN if len(chunk) == 1 else 0.0
    txt = chunk[-1].text.rstrip()
    core = split_token(txt)[0].lower()
    c = CAP_BREAK
    if finished_sentence(txt):
        c -= 1.50                       # a full stop is the best break there is
    elif txt.endswith((",", ";", ":")):
        c -= 1.05
    if core in CAP_NO_TAIL:
        c += 4.00                       # ends on furniture - the tell
    if len(chunk) == 1:
        c += CAP_ORPHAN                 # an orphan is worse than a bad break
    # ON THE DELIVERED CLOCK. This is the only time-dependent term in the cost,
    # and the two callers hand in different clocks: build_caption_sequence gets
    # SOURCE times (the overlays composite pre-setpts) and write_srt gets
    # delivered ones. Left unscaled the two grouped differently whenever a tempo
    # was applied - measured, 2 of 75 cues on one clip - so the sidecar .srt and
    # the burned-in captions broke in different places. Readability is a property
    # of what the VIEWER experiences, so the delivered clock is also the right
    # one on the merits.
    dur = (chunk[-1].end - chunk[0].start) / max(tempo, 1e-6)
    if dur < 0.80:
        c += 6.00 * (0.80 - dur)        # too brief to read
    return c


def group_words(words: list[Word], font: ImageFont.FreeTypeFont, max_w: int,
                max_words: int = 4, tempo: float = 1.0) -> list[list[Word]]:
    """
    Group words into caption chunks that fit one line.

    This used to fill greedily - pack until the next word does not fit, break
    there - so where a card ended was decided by pixel width and nothing else.
    Measured across 1,235 delivered cards, 21.2% ended on a preposition or an
    article. `wrap_balanced` forty lines above already made exactly this move for
    the hook headline, for the reason recorded in references/look.md: greedy
    filling strands orphans, and a viewer reads that as an accident.

    So the break is COSTED instead, by a short dynamic program inside each
    sentence. The hard constraints are unchanged and still hard: a chunk must fit
    one line at CAP_MEASURE, must not exceed `max_words`, and a sentence end
    still closes a chunk. Everything else is the cost in _tail_cost.

    `max_words` went 3 -> 4 with this change, and it does NOT make cards longer:
    measured over the archive the mean is 2,390 cards against 2,380 delivered, so
    words per card is unchanged. What the extra slot buys is ROOM FOR THE PROGRAM
    to rebalance a sentence (4 words as 2+2 instead of 3+1) rather than being
    forced into an orphan by arithmetic.

    Both write_srt and build_caption_sequence call this, so the sidecar and the
    burn-in stay in step - but only because `tempo` is threaded through to
    _tail_cost. They hand in different clocks (source times for the burn-in,
    delivered for the .srt), and the readability term is the one part of the cost
    that cares. Pass the tempo with SOURCE times; leave it 1.0 with delivered.
    """
    def fits(seg: list[Word]) -> bool:
        if not seg or len(seg) > max_words:
            return False
        # A SINGLE WORD ALWAYS FITS, even when it is wider than the measure.
        # Without this the program has no legal cut for that word at all, INF
        # propagates back through cost[] to cost[0], and the fallback below
        # discards the WHOLE PLAN for the sentence - turning every word of it
        # into its own card. Measured: `interconnectedness` is 796px against a
        # 740px CAP_MEASURE and is the only one of 6,702 tokens in the archive
        # over the measure, and it shipped 28 consecutive one-word cards across
        # 10.9s of a delivered clip. CAP_ORPHAN already prices the orphan this
        # creates; the point is that it stays ONE orphan.
        if len(seg) == 1:
            return True
        return font.getbbox(" ".join(x.text for x in seg))[2] <= max_w

    def best_split(seg: list[Word]) -> list[list[Word]]:
        """Cheapest way to cut one sentence into legal chunks."""
        n = len(seg)
        INF = float("inf")
        # cost[i] = best cost of chunking seg[i:]; cut[i] = where the first ends
        cost = [INF] * (n + 1)
        cut = [0] * (n + 1)
        cost[n] = 0.0
        for i in range(n - 1, -1, -1):
            for j in range(i + 1, n + 1):
                piece = seg[i:j]
                if not fits(piece):
                    break
                if cost[j] == INF:
                    continue
                # the last chunk of a sentence is not a "break" - it ends where
                # the sentence does, so it is not charged a tail cost
                c = cost[j] + _tail_cost(piece, last=(j == n), tempo=tempo)
                if c < cost[i]:
                    cost[i], cut[i] = c, j
        if cost[0] == INF:              # a single word wider than the measure
            return [[w] for w in seg]
        out, i = [], 0
        while i < n:
            out.append(seg[i:cut[i]])
            i = cut[i]
        return out

    def wfits(seg: list[Word]) -> bool:
        """Width only - the ONE hard constraint. See CAP_MIN_ON."""
        if len(seg) <= 1:
            return True
        return font.getbbox(" ".join(x.text for x in seg))[2] <= max_w

    def on(ch: list[Word]) -> float:
        return (ch[-1].end - ch[0].start) / max(tempo, 1e-6)

    def derush(cs: list[list[Word]]) -> list[list[Word]]:
        """
        Lengthen any card too brief to read, ONE WORD AT A TIME. See CAP_MIN_ON.

        Merging two whole cards was the obvious move and it does not work: the
        combined line is often wider than the measure, so the merge is refused
        and the flicker survives - which is exactly what the first version of
        this did, and what selftest caught. Borrowing a single word from the
        NEXT card extends this one's span to that word's end, which is usually
        all the floor needs, and it leaves both cards inside the measure.

        Forward first, because a brief card at the head of a thought reads as
        the start of what follows rather than the end of what came before. A
        backward borrow is only taken when it does not push the PREVIOUS card
        under the floor in turn - otherwise the flicker just moves.
        """
        guard = 0
        i = 0
        while i < len(cs) and guard < 4 * len(cs) + 16:
            if on(cs[i]) >= CAP_MIN_ON:
                i += 1
                continue
            guard += 1
            nxt = cs[i + 1] if i + 1 < len(cs) else None
            prv = cs[i - 1] if i > 0 else None
            if nxt and len(nxt) > 1 and wfits(cs[i] + nxt[:1]):
                cs[i], cs[i + 1] = cs[i] + nxt[:1], nxt[1:]
            elif nxt and len(nxt) == 1 and wfits(cs[i] + nxt):
                cs[i] = cs[i] + nxt
                cs.pop(i + 1)
            elif (prv and len(prv) > 1 and wfits(prv[-1:] + cs[i])
                  and on(prv[:-1]) >= CAP_MIN_ON):
                cs[i], cs[i - 1] = prv[-1:] + cs[i], prv[:-1]
            elif prv and len(prv) == 1 and wfits(prv + cs[i]):
                cs[i] = prv + cs[i]
                cs.pop(i - 1)
                i -= 1
            else:
                i += 1                  # nothing legal to borrow; leave it
        return cs

    def relax(cs: list[list[Word]]) -> list[list[Word]]:
        """
        Hand slack to any card still under the floor. See CAP_LATE_MAX.

        Applied HERE rather than in either caller, because build_caption_
        sequence and write_srt both group through this function and a display
        time computed in one of them would silently disagree with the other -
        the exact class of divergence CAP_LINGER and the tempo term were both
        added to close.

        The shift lands on the FIRST word of the following card, which is what
        the samplers key their card boundaries off, so the highlight and the
        card arrive together.
        """
        need = CAP_MIN_ON * max(tempo, 1e-6)
        late = CAP_LATE_MAX * max(tempo, 1e-6)
        for i in range(len(cs) - 1):
            gap = cs[i + 1][0].start - cs[i][0].start
            if gap >= need:
                continue
            w0 = cs[i + 1][0]
            # Never later than the bound, and never past the word's own end -
            # a card arriving after its first word has finished is a caption
            # for something already said.
            to = min(cs[i][0].start + need, w0.start + late, w0.end)
            if to > w0.start:
                cs[i + 1] = [Word(start=to, end=max(w0.end, to + 1e-3),
                                  text=w0.text)] + cs[i + 1][1:]
        return cs

    chunks: list[list[Word]] = []
    sent: list[Word] = []
    for w in words:
        sent.append(w)
        if finished_sentence(w.text) and len(sent) >= 2:
            chunks.extend(derush(best_split(sent)))
            sent = []
    if sent:
        chunks.extend(derush(best_split(sent)))
    return relax(chunks)


def write_srt(words: list[Word], path: Path, body: float | None = None) -> None:
    """A plain .srt of the clip, on the same timeline as the rendered video."""
    font = ImageFont.truetype(str(F_CAP), CAP_SIZE)
    chunks = group_words(words, font, max_w=CAP_MEASURE)

    def stamp(s: float) -> str:
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

    path.parent.mkdir(parents=True, exist_ok=True)
    # Cue ends carry CAP_LINGER, the same hold the burned-in card gets, clamped
    # to the next cue. Without it the sidecar disagreed with the picture by up to
    # CAP_LINGER on every single cue, which is exactly the kind of quiet
    # divergence this file keeps finding.
    # THE MINIMUM A CUE MAY LAST. Under this a player either skips it or flashes
    # it, so the word is lost to anybody reading the sidecar - which is every
    # viewer with captions on, and every platform that ingests the .srt for
    # auto-captioning and search.
    CUE_MIN = 0.10

    def cue_end(i: int, c: list[Word]) -> float:
        """
        Where a caption cue ends: its last word plus the linger, pulled back so
        it does not run into the next cue - but NEVER below its own last word.

        THE FLOOR IS THE FIX. This used to be a bare min() against the next
        chunk's start, and the silence pass can collapse the gap between two
        chunks to nothing: when the next chunk starts at or before this cue's
        last word ends, the cue came out ZERO LENGTH. Measured on the delivered
        show, 02-no-good-answers-on-hormuz cue 19 "And when" ran
        00:00:12,433 --> 00:00:12,433 and shipped that way in both the original
        and the recut. The burned-in captions were fine - they are rendered from
        the word list, not from this file - so nothing on screen ever showed it.

        A cue that would still be shorter than CUE_MIN is EXTENDED rather than
        dropped, which can overlap the next cue by a few tens of milliseconds.
        That is the right trade: overlapping cues are well-tolerated and the
        worst case is two lines briefly on screen, where the alternative is a
        word nobody reading the captions ever sees.
        """
        e = c[-1].end + CAP_LINGER
        if i < len(chunks):
            e = max(c[-1].end, min(e, chunks[i][0].start))
        elif body is not None:
            # THE LAST CUE IS CLAMPED TOO. Every other cue is pulled back to the
            # next one; the last had nothing to be pulled back to, so it took the
            # full CAP_LINGER and ran up to 0.40s past the end of the body -
            # which is over the opening of the Quasar end card, where there is no
            # caption on screen to match it. A player showing the sidecar put a
            # line of the interview over the card.
            e = max(c[-1].end, min(e, body))
        return max(e, c[0].start + CUE_MIN)

    path.write_text("\n".join(
        f"{i}\n{stamp(c[0].start)} --> {stamp(cue_end(i, c))}\n"
        f"{' '.join(w.text for w in c)}\n" for i, c in enumerate(chunks, 1)))


def layout_chunk(chunk: list[Word], font: ImageFont.FreeTypeFont,
                 max_w: int) -> list[list[Word]]:
    rows: list[list[Word]] = []
    cur: list[Word] = []
    for w in chunk:
        trial = cur + [w]
        if cur and font.getlength(" ".join(x.text for x in trial)) > max_w:
            rows.append(cur)
            cur = [w]
        else:
            cur = trial
    if cur:
        rows.append(cur)
    return rows


# The live word POPS: 3 frames up to 1.05 (1.06 on a number, $ or %), 3 frames
# settling to 1.02, and it HOLDS 1.02 while it is the live word - a colour shift
# plus a scale under 6%, which the 2026 survey found is the premium version of
# the highlight (bounce and fill are the template ones). Words shorter than
# CAP_POP_MIN_FRAMES get colour only. The word is rendered on its own at the
# bigger size and pasted centred on its 1.0-width slot, so the row never
# reflows - the neighbours do not move.
CAP_POP = (1.03, 1.04, 1.05, 1.04, 1.03)
CAP_POP_NUM = (1.03, 1.05, 1.06, 1.05, 1.03)
CAP_POP_HOLD = 1.02
CAP_POP_MIN_FRAMES = 4

# THE SNAP: a new caption card arrives by expanding HORIZONTALLY into place.
#
# Measured off the reference the owner sent (youtube.com/shorts/gaRRMkRjoHE),
# frame by frame at its native 30fps on a clean caption onset:
#
#     frame   0      1      2      3      4+
#     width   0.717  0.886  0.964  1.000  held
#
# That is an out_cubic from 0.70 to 1.0 over four frames - 1-(1-u)^3 predicts
# 0.881 / 0.965 / 0.995 / 1.0 against the measured 0.886 / 0.964 / 1.0 / 1.0, so
# the curve is not a guess. The HEIGHT does not change: the glyph rows held at
# 42px through the whole expansion. It is a horizontal scale about the centre and
# nothing else - no fade, no vertical move, no per-word entrance.
#
# It is what the owner meant by "a flow of the captions... it's seamless". A card
# that simply appears reads as a cut; a card that expands into place reads as one
# continuous line of speech being laid down. It costs four extra unique PNGs per
# card and nothing at render time.
# THE MEASURED VALUES, not a curve fitted to them. Four numbers is less code than
# the easing that approximates them, it is exact, and it cannot drift the way a
# re-derived exponent can. out_cubic gets within 0.03 of these if the shape is
# ever needed at another frame rate; the deltas are +0.169, +0.078, +0.036, each
# about 0.46x the last.
CAP_SNAP_CURVE = (0.717, 0.886, 0.964, 1.0)
CAP_SNAP_FRAMES = len(CAP_SNAP_CURVE)
# The largest scale any word ever reaches. render_caption_png reserves this much
# headroom when it sizes a row, so a row that fits at rest still fits when its
# widest word goes live.
CAP_POP_MAX = max(max(CAP_POP), max(CAP_POP_NUM), CAP_POP_HOLD)
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    key = (str(path), size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
    return _FONT_CACHE[key]


def _numeric(text: str) -> bool:
    return any(c.isdigit() for c in text) or "%" in text or "$" in text


def _snap_x(img: Image.Image, sx: float) -> Image.Image:
    """Scale `img` horizontally about its own centre. See CAP_SNAP."""
    if sx >= 0.999:
        return img
    cx = img.width / 2.0
    # AFFINE takes the INVERSE map (output -> input), so the x scale is 1/sx and
    # the offset keeps the centre column fixed.
    return img.transform(img.size, Image.AFFINE,
                         (1.0 / sx, 0, cx * (1 - 1.0 / sx), 0, 1, 0),
                         Image.BILINEAR)


def render_caption_png(chunk: list[Word], active: int, font: ImageFont.FreeTypeFont,
                       size: tuple[int, int], path: Path,
                       colours: dict | None = None, pop: float = 1.0,
                       raised: float = 0.0, snap: float = 1.0) -> None:
    """One caption state: the whole chunk, keywords in the clip's chosen accent,
    the live word scaled by `pop` about its own centre."""
    bw, bh = size
    col = colours or {"base": BONE, "stroke": (7, 10, 14), "key": CAP_KEY}
    base, stroke, keyc = col["base"], col["stroke"], col["key"]
    # The drop follows the PALETTE, it is not a fixed near-black. On the dark set
    # the base is ink and the stroke is bone, so a hardcoded dark drop sits under
    # dark type and eats the light halo that is the only thing carrying it -
    # precisely the case the dark set exists for, and invisible while testing on
    # the light one.
    drop = tuple(col["stroke"]) + (150,)

    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    rows = layout_chunk(chunk, font, max_w=CAP_INK_MAX)
    if int(font.size * 1.20) * len(rows) > bh:
        sys.stderr.write(
            f"note: a caption chunk needs {len(rows)} rows in a {bh}px band and "
            f"will clip. Lower cap_size, or raise CAP_BAND_H and walk CAP_BAND_Y "
            f"up with it - CAP_SAFE_BOTTOM must not move.\n")

    # No plate and no scrim. Legibility over live video comes from a stroke plus a
    # soft drop, which is what short-form captions everywhere use: a plate would
    # put the letterbox back in a different costume, and a scrim would dim exactly
    # the third of the picture this change was made to win back.
    #
    # The drop is drawn into its own layer and blurred. A hard offset copy - which
    # is what this did when the captions were on a scrim - reads as a printing
    # fault once there is texture behind it.
    shadow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    d = ImageDraw.Draw(img)

    line_h = int(font.size * 1.20)
    # RAISED: top of the band instead of centred, so the invitation can have the
    # bottom strip. A two-line block then ends at y1336 against the strip's
    # y1338. It is only ever true while the invitation is up.
    # Raised: the top of the (taller) band. Otherwise centred where it has always
    # been - against the REST band, not this one, so nothing moves.
    # A FLOAT, NOT A FLAG, so the band can TRAVEL between the two positions
    # instead of teleporting between them. `raised` is 0 at rest, 1 fully up.
    #
    # It was a bool, and the card jumped the whole 278px in ONE FRAME at every
    # edge of a raise window - measured on the delivered file, six times a clip,
    # in the one element the viewer's eye is locked to. Everything else in this
    # clip moves on a curve; this was the only thing left that teleported.
    _rest = ((CAP_BAND_Y_REST - CAP_BAND_Y)
             + (CAP_BAND_H_REST - line_h * len(rows)) // 2)
    y = int(round(_rest * (1.0 - min(max(raised, 0.0), 1.0))))
    idx = 0
    # The stroke grows each glyph outward by CAP_STROKE on every side, so words set
    # at the plain space width would have their outlines touching. Pay for it in
    # the space rather than in the measure.
    for row in rows:
        # PER-ROW TYPE SIZE, so a row that cannot break stays inside the rail.
        # layout_chunk keeps a single word on its own row whatever its width -
        # it has to, there is nowhere to break a word - so a word wider than
        # CAP_INK_MAX used to be drawn at full size and centred, putting its ink
        # under the platform action rail. `interconnectedness` inks at 796px
        # against a 780px ceiling and is the only one of 6,702 tokens in the
        # archive over it, so this is rare - and when it happens the last letters
        # of the word sit behind the share icon, which reads as a broken render
        # rather than as a long word.
        #
        # Condense that row and only that row. Everything else on the card is
        # untouched, so a set still matches; and because the pop is applied on
        # top of the ROW's font, the live word still grows by the same fraction.
        rfont = font
        rspace = font.getlength(" ") + CAP_STROKE
        # THREE terms, and every one of them was needed to stop the ink reaching
        # the rail:
        #   the advances                what getlength gives
        #   + 2 * CAP_STROKE            the stroke grows the glyphs outward on
        #                               EVERY side, so the ink is wider than the
        #                               advance at both ends. Measuring advances
        #                               alone passed a 796px word through a 780px
        #                               ceiling and then drew 806px.
        #   + the POP headroom          the live word grows to CAP_POP_MAX about
        #                               its own centre, so a row sized to fit at
        #                               rest overflows the moment its widest word
        #                               goes live. Reserve it up front, on the
        #                               widest word, so the shrink is CONSTANT
        #                               across every state of the card - a shrink
        #                               that changed per state would visibly
        #                               resize the caption as each word lit.
        widest = max((font.getlength(w.text) for w in row), default=0.0)
        natural = (sum(font.getlength(w.text) for w in row)
                   + rspace * (len(row) - 1) + 2 * CAP_STROKE
                   + widest * (CAP_POP_MAX - 1.0))
        if natural > CAP_INK_MAX:
            ratio = max(CAP_INK_MAX / natural, CAP_SHRINK_MIN)
            rfont = _font(F_CAP, max(8, int(font.size * ratio)))
            rspace = rfont.getlength(" ") + CAP_STROKE
            if ratio < CAP_SHRINK_WARN:
                sys.stderr.write(
                    f"note: caption row {' '.join(w.text for w in row)!r} inks "
                    f"{natural:.0f}px against a {CAP_INK_MAX}px ceiling, so it is "
                    f"condensed to {ratio:.0%} of "
                    f"the caption size. Check the transcript for a run-together "
                    f"token.\n")
        widths = [rfont.getlength(w.text) for w in row]
        x = (bw - (sum(widths) + rspace * (len(row) - 1))) / 2
        for w, wid in zip(row, widths):
            if _keyword(w.text):
                colour, alpha = keyc, 255
            elif idx == active:
                colour, alpha = base, 255
            else:
                colour, alpha = base, 205
            if idx == active and abs(pop - 1.0) > 1e-3:
                # The live word, bigger, centred on the slot it would have had.
                # Anchored on the BASELINE ("ms"), centred on the 1.0 advance
                # width. "mm" was the em-box middle, which sat a word with a
                # descender or no ascender 8-11px below its neighbours for
                # the whole time it was live.
                big = _font(F_CAP, int(round(rfont.size * pop)))
                asc, _desc = rfont.getmetrics()
                cx, cy = x + wid / 2, y + asc
                ds.text((cx, cy + CAP_SHADOW_DY), w.text, font=big, fill=drop,
                        stroke_width=CAP_STROKE, stroke_fill=drop, anchor="ms")
                d.text((cx, cy), w.text, font=big, fill=colour + (alpha,),
                       stroke_width=CAP_STROKE, stroke_fill=stroke + (alpha,),
                       anchor="ms")
            else:
                ds.text((x, y + CAP_SHADOW_DY), w.text, font=rfont,
                        fill=drop, stroke_width=CAP_STROKE, stroke_fill=drop)
                d.text((x, y), w.text, font=rfont, fill=colour + (alpha,),
                       stroke_width=CAP_STROKE, stroke_fill=stroke + (alpha,))
            x += wid + rspace
            idx += 1
        y += line_h

    out = Image.alpha_composite(shadow.filter(
        ImageFilter.GaussianBlur(CAP_SHADOW_BLUR)), img)
    # The snap is applied to the FINISHED card, drop shadow and all, so the
    # shadow expands with the type instead of sitting still behind it.
    out = _snap_x(out, snap)
    out.save(path)


# HOW LONG THE CAPTIONS TAKE TO RIDE UP AND BACK DOWN. Slower than the elements
# it is making room for - the nameplate fades in over 0.50s and the invitation
# rises over 0.50s - because the captions are the thing being read, and a fast
# move on the thing you are reading is the one move a viewer notices.
CAP_RAISE_T = 0.42


def _raise_at(t: float, wins: list[tuple[float, float]] | None) -> float:
    """
    How far up the caption band is at time t: 0 at rest, 1 fully raised.

    A SMOOTHSTEP EITHER SIDE OF EVERY WINDOW EDGE, rather than a step. The card
    still commits to a single position for its whole life - it is one PNG, and a
    card that moved mid-word would be worse than one that moves between words -
    but consecutive cards now land on intermediate positions through the
    transition, so the band reads as travelling rather than cutting.
    """
    if not wins:
        return 0.0
    best = 0.0
    for a, b in wins:
        if t <= a - CAP_RAISE_T or t >= b + CAP_RAISE_T:
            continue
        if t < a:
            u = (t - (a - CAP_RAISE_T)) / CAP_RAISE_T
        elif t > b:
            u = ((b + CAP_RAISE_T) - t) / CAP_RAISE_T
        else:
            u = 1.0
        u = min(max(u, 0.0), 1.0)
        best = max(best, u * u * (3 - 2 * u))
    return best


def build_caption_sequence(words: list[Word], seqdir: Path, dur: float,
                           tempo: float = 1.0,
                           raise_wins: list[tuple[float, float]] | None = None,
                           cap_size: int = CAP_SIZE,
                           band: tuple[int, int] | None = None,
                           colours: dict | None = None) -> int:
    """
    Render the caption band as a transparent PNG sequence.

    This ffmpeg has neither libass nor drawtext, so every glyph is rasterised
    here with PIL. Only the unique caption states are drawn; the per-frame
    sequence is built from hard links, so a 40s clip costs ~100 renders.
    """
    if seqdir.exists():
        shutil.rmtree(seqdir)
    seqdir.mkdir(parents=True)
    uniq = seqdir / "u"
    uniq.mkdir()
    band = band or (W, CAP_BAND_H)

    font = ImageFont.truetype(str(F_CAP), cap_size)
    states: list[tuple[float, float, Path]] = []
    n = 0
    drawn: dict[tuple[int, int], Path] = {}
    # CAP_MEASURE, not the band width: the grouping and the row layout must use the
    # same measure or the .srt groups words differently than the video shows them.
    chunks = group_words(words, font, max_w=CAP_MEASURE, tempo=tempo)
    for ci, chunk in enumerate(chunks):
        nxt = chunks[ci + 1][0].start if ci + 1 < len(chunks) else None
        _prev_end = -1e9          # see the cascade note below
        for i, w in enumerate(chunk):
            if i + 1 < len(chunk):
                end = chunk[i + 1].start
            else:
                # Linger 0.30s after the chunk, but never past the next chunk's
                # first word. The sampler holds a state until its end and then
                # skips every state already over, so an overlapping tail hid
                # the next word's pop frames - and a short first word entirely:
                # measured on the reference clip, 63 of 117 chunk-first words
                # were never the live word and every chunk appeared ~317ms late.
                end = chunk[-1].end + CAP_LINGER
                if nxt is not None:
                    end = min(end, nxt)
            # THE FLOOR CASCADES, or it just moves the problem to the next
            # word. `max(end, w.start + 0.08)` guarantees THIS word a window,
            # and on crammed speech that window runs past where the NEXT word
            # begins - measured on whisper output for "And the Fed said", the
            # windows came out 0.00-0.08, 0.05-0.13, 0.09-0.17, each starting
            # before its predecessor had finished. The sampler holds a state to
            # its end and skips whatever is already over, so those overlaps eat
            # the following word's first frames: the same failure the comment
            # above records for the chunk tail, one level down. Starting each
            # word no earlier than the previous one ended gives every word its
            # own frames.
            w_start = max(w.start, _prev_end)
            end = max(end, w_start + 0.08)
            _prev_end = end
            nf = int(round((end - w_start) * FPS))
            ladder = CAP_POP_NUM if _numeric(w.text) else CAP_POP
            # THE RAISE IS PART OF THE STATE, not something read off the step's
            # start time afterwards. It used to be sampled once per merged step,
            # and the merge collapses every frame of the HOLD into a single step
            # - so a raise transition that landed inside a hold did not move the
            # band at all, and then the whole remaining travel arrived on the
            # next word in one frame.
            #
            # Measured on a plain 3-words-a-second run with one raise window:
            # the band stepped 30, 28, 28, 27px and then TELEPORTED 98px in a
            # single frame at the window's leading edge, and 95px at the
            # trailing one. That is the opposite of "slow moving and clean".
            #
            # Including the quantised raise in the merge test breaks a step
            # wherever the band actually moves, and merges everywhere it does
            # not - so a still band still costs one state, exactly as before.
            # the pop and the raise, one sub-state per frame, merged where both
            # repeat
            steps: list[tuple[float, float, float, int]] = []
            for k in range(nf):
                pop = (1.0 if nf < CAP_POP_MIN_FRAMES
                       else (ladder[k] if k < len(ladder) else CAP_POP_HOLD))
                t0 = w.start + k / FPS
                t1 = end if k == nf - 1 else w.start + (k + 1) / FPS
                # OVERLAP, not containment. Testing `a <= t0 < b` only raised a
                # card that BEGAN inside the window, so a card that started
                # before the invitation came up stayed low and the two collided -
                # the caption sits at y1228..1331 at rest and the pill at
                # y1230..1380, which is the same rows. A card is raised whenever
                # it is on screen for any part of the window.
                #
                # QUANTISED TO 1/40 OF THE TRAVEL, 7px a step. It was 1/20, and
                # 14px quanta against a travel that peaks near 30px a frame means
                # the curve lands 2 quanta on most frames and 3 on some - which
                # measured as an even ramp interrupted by a 42px lurch at the
                # steepest point of the smoothstep. Halving the quantum takes the
                # worst frame to 28px and makes the ramp monotone.
                #
                # It costs almost nothing now that a step breaks whenever the
                # band moves: the extra states only exist for the ~26 frames a
                # transition is actually travelling, and the holds at 0 and at 1
                # still collapse to one state each.
                hq = int(round(_raise_at(t0, raise_wins) * 40))
                if (steps and abs(steps[-1][2] - pop) < 1e-6
                        and steps[-1][3] == hq):
                    steps[-1] = (steps[-1][0], t1, pop, hq)
                else:
                    steps.append((t0, t1, pop, hq))
            for t0, t1, pop, hq in steps:
                # THE SNAP, on the first CAP_SNAP_FRAMES of the CHUNK - not of
                # each word. It is the card arriving, so it fires once per card
                # and the words inside it just light up as usual.
                k = int(round((t0 - chunk[0].start) * FPS))
                sx = CAP_SNAP_CURVE[k] if 0 <= k < CAP_SNAP_FRAMES else 1.0
                key = (n, int(round(pop * 100)), hq, int(round(sx * 100)))
                p = drawn.get(key)
                if p is None:
                    p = uniq / f"s{n:04d}_{key[1]}_{key[3]}_r{hq:02d}.png"
                    render_caption_png(chunk, i, font, band, p, colours, pop=pop,
                                       raised=hq / 40, snap=sx)
                    drawn[key] = p
                states.append((t0, t1, p))
            n += 1

    blank = uniq / "blank.png"
    Image.new("RGBA", band, (0, 0, 0, 0)).save(blank)

    frames = int(round(dur * FPS))
    si = 0
    for f in range(frames):
        t = f / FPS
        while si < len(states) - 1 and t >= states[si][1]:
            si += 1
        src = states[si][2] if (states and states[si][0] <= t < states[si][1]) else blank
        dst = seqdir / f"{f:05d}.png"
        try:
            # os.link, not Path.hardlink_to: the latter is 3.10+, and which
            # python3 wins on PATH here is not stable (macOS ships 3.9).
            os.link(src, dst)
        except OSError:
            dst.write_bytes(src.read_bytes())
    return frames


# -------------------------------------------------------------- chrome -----
def _ease(x: float) -> float:
    """Smooth in/out, so a ramp has no hard corner at either end."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# There is no static overlay layer any more.
#
# It carried one thing: a gradient scrim from the panel's lower edge to the frame
# bottom, which the captions sat on. That scrim existed to make the type read the
# same from clip to clip - on it, a caption over a white chart and a caption over a
# dark room looked identical, and inconsistency between clips is what stops a set
# looking like a set.
#
# With the panel full 9:16 there is no space below the picture to put it, and
# painting it OVER the picture would dim the third of the frame this change was
# made to win back. The consistency problem it solved is real and did not go away,
# so it is solved a different way now: the stroke in render_caption_png gives every
# caption the same hard edge whatever is behind it, and choose_caption_colours
# picks a colour that separates from that particular background. The scrim made
# every background the same; this makes the type fit every background.


def attr_height(name: str, role: str, rung: int) -> tuple[int, list]:
    """
    (height, [(text, font, track, alpha), ...]) for an attribution rung.

    Heights come from font.getmetrics(), never a literal - the ascent and descent
    of these faces at these sizes is what decides the box, and hardcoding it is
    how a card starts clipping a descender after a font change.
    """
    if not name or rung >= 4:
        return 0, []
    f_n = _font(F_UI, ATTR_NAME_PX)
    an, dn = f_n.getmetrics()
    if rung == 1 and role:                      # stacked
        for px in ATTR_ROLE_PX:
            f_r = _font(F_DISPLAY, px)
            ar, dr = f_r.getmetrics()
            return (an + dn + ATTR_LEAD + ar + dr,
                    [(name, f_n, ATTR_NAME_TRACK, 255),
                     (role, f_r, ATTR_ROLE_TRACK, ATTR_ALPHA)])
    if rung == 2 and role:                      # one line
        for px in (24, 22):
            f_r = _font(F_DISPLAY, px)
            ar, dr = f_r.getmetrics()
            return ar + dr, [(f"{name}  \u00b7  {role}", f_r, ATTR_ROLE_TRACK, 235)]
    return an + dn, [(name, f_n, ATTR_NAME_TRACK, 255)]     # name only


def missing_glyphs(text: str, font_path: Path, size: int = 48) -> list[str]:
    """
    Characters this font has no glyph for, which PIL draws as a black box.

    PIL DOES NOT RAISE ON AN UNCOVERED CHARACTER. It draws .notdef - a filled
    rectangle - so an emoji pasted into a hook, or an invisible U+2060 that came
    along with a copy-paste from a doc, renders as a black brick in the middle of
    the title card and nothing anywhere says why. The hook is the first thing on
    screen; this is the one string that must not fail silently.

    Detected by drawing the character and comparing it against U+FFFF, which is a
    noncharacter no font covers - if they render identically, the font fell back
    to .notdef. That works on any TrueType file without adding a dependency.
    """
    try:
        f = ImageFont.truetype(str(font_path), size)
    except OSError:
        return []
    def _bitmap(ch: str) -> bytes:
        im = Image.new("L", (size * 2, size * 2), 0)
        ImageDraw.Draw(im).text((size // 2, size // 2), ch, font=f, fill=255)
        return im.tobytes()
    tofu = _bitmap("\uffff")
    blank = _bitmap(" ")
    bad: list[str] = []
    for ch in dict.fromkeys(text):
        if ch.isspace():
            continue
        b = _bitmap(ch)
        # a character that draws the tofu box, or draws NOTHING at all (an
        # invisible joiner or word-joiner that survived a paste)
        if b == tofu or b == blank:
            bad.append(ch)
    return bad


def hook_plate(hook: str, max_w: int = W - 200, max_block: int = HOOK_MAX_BLOCK,
               min_size: int = 42, name: str = "", role: str = "",
               rung: int = 1, must_fit: bool = True) -> tuple[Image.Image, int, int]:
    """
    The hook as a white title card, drawn ONCE on its own canvas.

    A solid bone box with slate type, not white type on a scrim. Over live video a
    scrim has to be heavy enough to carry white text against a lit face, and by the
    time it is heavy enough it has dimmed the picture anyway - a filled box is the
    same contrast with none of the murk, and it reads as a deliberate card rather
    than as text dropped on a frame.

    Returns (canvas, card_w, card_h). The canvas is the card plus its soft drop
    shadow inside a HOOK_PAD margin, centred, so build_hook_sequence can scale and
    drift it without anything being clipped. Placement is NOT decided here - see
    place_hook().
    """
    hook = hook.strip()
    if not hook:
        raise SystemExit(
            "\nEMPTY HOOK. Every clip needs one - it is the first thing on screen "
            "and it is what stops the scroll.\n"
            "Set \"hook\" in slate.json to 3 to 8 words in the speaker's voice.\n")
    bad = missing_glyphs(hook, F_DISPLAY)
    if bad:
        shown = ", ".join(f"{c!r} (U+{ord(c):04X})" for c in bad)
        raise SystemExit(
            f"\nHOOK HAS CHARACTERS THE TITLE FONT CANNOT DRAW: {shown}\n"
            f"  hook: {hook!r}\n"
            f"PIL renders these as a filled black box in the middle of the "
            f"card. If it came from a paste, retype it; emoji do not belong in "
            f"a title card.\n")
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    pad_x, pad_y = 44, 30
    fitted = False
    for size in range(120, max(min_size, 42) - 1, -2):
        f_h = ImageFont.truetype(str(F_DISPLAY), size)
        track = -0.02 * size
        lines = wrap_balanced(probe, hook, f_h, max_w - pad_x * 2, track)
        lh = int(size * 1.06)
        if len(lines) <= 3 and lh * len(lines) + pad_y * 2 <= max_block:
            fitted = True
            break
    # THE FLOOR IS REPORTED, NOT JUST DOCUMENTED. HOOK_MIN_SIZE says the card
    # shrinks to 84 "and no further"; this loop's own floor is the min_size
    # parameter, which defaults to 42. A long hook therefore walked straight past
    # the documented floor and set at half of it, silently - 13 words is enough.
    # Nothing on the card looks broken, it just stops being a title.
    # `must_fit=False` IS NOT A LOOPHOLE, it is the difference between the
    # budget and an experiment. hook_card asks for a card that fits the tallest
    # CLEAR BAND when a face is in the way (see the `_plate(4, max_block=tallest)`
    # call) - and that band is routinely tiny: measured on a real duo, 12px, and
    # on a duo_share, 120px. That call is a deliberate best effort whose failure
    # the caller already handles by taking the least-bad overlap and saying so.
    #
    # Refusing there took the whole of duo and duo_share down: 'Is this
    # quantitative easing' - four words - died on "needs more than 12px of card",
    # which is not a sentence anybody could act on. The refusal belongs to the
    # REAL budget only.
    if not fitted and must_fit:
        raise SystemExit(
            f"\nHOOK WILL NOT FIT: {hook!r} is {len(hook.split())} words and "
            f"still needs more than {max_block}px of card at the smallest type "
            f"this rig will set ({max(min_size, 42)}px).\n"
            f"Cut it to 3 to 8 words - it is the first thing on screen.\n")
    if size < HOOK_MIN_SIZE and must_fit:
        sys.stderr.write(
            f"WARNING: hook {hook!r} ({len(hook.split())} words) sets at "
            f"{size}px, under the {HOOK_MIN_SIZE}px floor - the title card "
            f"stops reading as a title at a glance. Cut it to 3 to 8 words.\n")

    widths = [tracked_width(probe, ln, f_h, track) for ln in lines]
    # THE ATTRIBUTION IS ADDED TO THE BOX, NOT TAKEN OUT OF THE HEADLINE. The
    # headline has already fitted against max_block above; this widens and
    # heightens the card around it.
    attr_h, attr_lines = attr_height(name, role, rung)
    attr_w = 0.0
    for txt, fnt, trk, _a in attr_lines:
        attr_w = max(attr_w, tracked_width(probe, txt, fnt, trk))
    box_w = int(min(max(max(widths), attr_w) + pad_x * 2, max_w))
    box_h = int(lh * len(lines) + pad_y * 2 + (ATTR_GAP + attr_h if attr_h else 0))
    cw, ch = box_w + 2 * HOOK_PAD, box_h + 2 * HOOK_PAD
    bx, by = HOOK_PAD, HOOK_PAD

    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    # a soft drop so the card lifts off the picture instead of floating flat on it
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [bx + 6, by + 10, bx + box_w + 6, by + box_h + 10], radius=22,
        fill=(4, 7, 11, 130))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=22,
                        fill=BONE + (255,))
    y = by + pad_y
    for ln, wd in zip(lines, widths):
        draw_tracked(d, (bx + (box_w - wd) / 2, y), ln, f_h, SLATE + (255,), track)
        y += lh
    if attr_lines:
        # Slate on opaque bone, so no stroke and no shadow. Sentence case
        # throughout: UPPERCASE stays reserved for the closing address.
        y += ATTR_GAP - (lh - int(f_h.size * 1.0))
        for txt, fnt, trk, alpha in attr_lines:
            wd = tracked_width(d, txt, fnt, trk)
            draw_tracked(d, (bx + (box_w - wd) / 2, y), txt, fnt,
                         SLATE + (alpha,), trk)
            y += fnt.getmetrics()[0] + fnt.getmetrics()[1] + ATTR_LEAD
    return img, box_w, box_h


def probe_panel(t: float, graph: str, nbytes: int,
                pix_fmt: str = "gray") -> bytes | None:
    """
    ONE frame of the reframed panel at source time t, through `graph`.

    Three frames are decoded and the LAST is returned, and that is the whole
    point of this helper. In `share`, `duo` and `duo_share` the reframing chain
    composites the picture onto a `color=` source, and overlay is main-driven:
    the colour source's first frame is emitted before the first decoded picture
    frame has arrived, so a one-frame probe returns the bare slate stack -
    measured at luma 19 against 32.6 for the frames after it. Both the caption
    colour and the hook's face search were reading that blank frame on every
    share clip, which is how a chart came back as "L=0.01, no colour" and a
    face in plain view as "no face". `head` has no stack and was never affected.
    """
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(SRC),
         "-frames:v", "3", "-filter_complex", graph, "-map", "[o]",
         "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"],
        capture_output=True, cwd=WORK)
    n = len(p.stdout) // nbytes
    if not n:
        return None
    return p.stdout[(n - 1) * nbytes:n * nbytes]


# How many reframed frames the face search looks at. The card is up for
# HOOK_HOLD seconds, so the window is the card's own window plus a little, and
# eight input-seek decodes off the master cost about a second - the same budget
# sample_caption_bg spends, for the same reason.
FACE_SAMPLES = 8


def panel_faces(start: float, fg: str, splits: int, extra: str,
                slug: str = "") -> list[tuple[int, int, int, int]] | None:
    """
    Where the faces are IN THE PANEL while the hook card is up.

    Measured through the clip's own reframing chain, exactly as the caption
    colour is, because the question is where a face sits in the 1080x1920 the
    viewer sees - not in the source. In `share` the face is at the top of the
    panel, in `head` it fills the middle, in `duo` there are two; the source
    frame cannot answer that and the reframed one can.

    Returns (left, top, right, bottom) boxes in panel pixels, largest first, or
    None when the measurement could not be made at all - no OpenCV for this
    interpreter, or nothing decoded. An empty list means it looked and found
    nobody, which is a different answer: the card then takes its preferred band.
    """
    try:
        import cv2
    except ImportError:
        sys.stderr.write(
            "WARNING: opencv is not installed for this interpreter, so the hook card "
            "cannot see where the face is and takes its default band. Install it: "
            f"{sys.executable} -m pip install 'opencv-python-headless<5'\n")
        return None
    det = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if det.empty():
        return None
    gw, gh = 360, 640                                 # panel at one third
    graph = (f"[0:v]split={splits}[fgsrc]{extra};"
             f"[fgsrc]{fg}[fgv];"
             f"[fgv]scale={gw}:{gh}:flags=area,format=gray[o]")
    lo, hi = start + 0.2, start + HOOK_HOLD + HOOK_OUT + 0.4   # the card's window, at tempo 1
    hits: list[tuple[float, float, float, float]] = []
    decoded = 0
    for i in range(FACE_SAMPLES):
        t = lo + (hi - lo) * (i / max(1, FACE_SAMPLES - 1))
        raw = probe_panel(t, graph, gw * gh)
        if raw is None:
            continue
        decoded += 1
        f = np.frombuffer(raw, dtype=np.uint8).reshape(gh, gw)
        found = det.detectMultiScale(cv2.equalizeHist(f), scaleFactor=1.1,
                                     minNeighbors=5,
                                     minSize=(int(gw * 0.10),) * 2)
        for (x, y, w, h) in found:
            hits.append((float(x), float(y), float(w), float(h)))
    if not decoded:
        return None

    # Cluster by centre, because `duo` has two people and `duo_share` has two
    # tiles: a single median over every hit would land between them. Greedy is
    # enough - faces in a frame are far apart next to the jitter of one face.
    clusters: list[list[tuple[float, float, float, float]]] = []
    for hit in hits:
        cx, cy = hit[0] + hit[2] / 2, hit[1] + hit[3] / 2
        for c in clusters:
            mx = float(np.median([b[0] + b[2] / 2 for b in c]))
            my = float(np.median([b[1] + b[3] / 2 for b in c]))
            if abs(cx - mx) < gw * 0.22 and abs(cy - my) < gh * 0.14:
                c.append(hit)
                break
        else:
            clusters.append([hit])
    need = max(3, decoded // 3)
    faces = []
    for c in clusters:
        if len(c) < need:
            continue
        x, y, w, h = np.median(np.array(c, float), axis=0)
        k = W / gw
        # Inflated 3% of W/H each way (32px, 58px): the punch-in's B framing
        # enlarges the face 6% about its centre, and the card must stay clear
        # of the face in BOTH framings.
        ix, iy = int(0.03 * W), int(0.03 * H)
        faces.append((max(0, int(x * k) - ix), max(0, int(y * k) - iy),
                      min(W, int((x + w) * k) + ix), min(H, int((y + h) * k) + iy)))
    faces.sort(key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    if slug:
        where = ", ".join(f"y{t}..{b}" for _l, t, _r, b in faces) or "none"
        sys.stderr.write(
            f"hook: faces in the panel over the card window ({decoded} frames): "
            f"{where}\n")
    return faces


def free_bands(faces: list[tuple[int, int, int, int]]) -> list[tuple[int, int]]:
    """The stretches of HOOK_MIN_TOP..HOOK_MAX_BOTTOM with no face in them."""
    lo, hi = HOOK_MIN_TOP, HOOK_MAX_BOTTOM
    cuts = sorted((min(hi, max(lo, t - HOOK_FACE_PAD)),
                   min(hi, max(lo, b + HOOK_FACE_PAD)))
                  for _l, t, _r, b in faces)
    free: list[tuple[int, int]] = []
    cur = lo
    for a, b in cuts:
        if a > cur:
            free.append((cur, a))
        cur = max(cur, b)
    if cur < hi:
        free.append((cur, hi))
    return free


def place_hook(card_h: int, faces: list[tuple[int, int, int, int]] | None,
               slug: str = "") -> tuple[int, bool]:
    """
    The card's TOP edge in the panel, and whether it is clear of every face.

    The card wants HOOK_PREF, centred on y480 - inside the strip every app leaves
    clear and low enough to survive a 4:5 feed crop. Every face is then cut out
    of the allowed range (HOOK_MIN_TOP..HOOK_MAX_BOTTOM) with HOOK_FACE_PAD
    around it, and the card takes the free band nearest its preferred centre:
    ABOVE a face that sits low (`head`), where it is centred as near y480 as the
    band allows; BELOW a face that sits high (`share`, the camera tile is at the
    top of the panel), where it drops to the bottom of the band - as far from
    the face as it can get, which also keeps it off the name badge most sources
    burn in under the chin; BETWEEN two faces (`duo`), centred in the gap.

    If no band is tall enough the caller shrinks the card and asks again; if it
    still does not fit, the card takes the tallest band and overlaps the face by
    the least it can, and SAYS so - 3 seconds over a forehead is better than a
    card in the chrome or over the captions.
    """
    pref_c = (HOOK_PREF[0] + HOOK_PREF[1]) / 2

    def centred_in(a: float, b: float) -> int:
        c = min(max(pref_c, a + card_h / 2), b - card_h / 2)
        return int(round(c - card_h / 2))

    if not faces:
        top = centred_in(*HOOK_PREF)
        why = ("no face measurement, default band" if faces is None
               else "no face in the panel, default band")
        sys.stderr.write(f"hook: card at y{top}..{top + card_h} ({why})\n")
        return top, True

    f_top = min(t for _l, t, _r, _b in faces)
    f_bot = max(b for _l, _t, _r, b in faces)
    bands = free_bands(faces)

    def relation(a: int, b: int) -> str:
        if b <= f_top + HOOK_FACE_PAD:
            return "above"
        if a >= f_bot - HOOK_FACE_PAD:
            return "below"
        return "between"

    best: tuple[float, int, tuple[int, int], str] | None = None
    for a, b in bands:
        if b - a < card_h:
            continue
        rel = relation(a, b)
        if rel == "above":
            top = centred_in(a, b)
        elif rel == "below":
            top = b - card_h
        else:
            top = int(round((a + b) / 2 - card_h / 2))
        score = abs(top + card_h / 2 - pref_c)
        if best is None or score < best[0]:
            best = (score, top, (a, b), rel)
    if best is not None:
        _s, top, (a, b), rel = best
        sys.stderr.write(
            f"hook: card at y{top}..{top + card_h}, {rel} the face "
            f"(free band y{a}..{b})\n")
        return top, True

    # Nothing fits. Take the tallest band and overlap as little as possible:
    # flush to the band's far edge, so the overlap is hair, not eyes.
    if bands:
        a, b = max(bands, key=lambda ab: ab[1] - ab[0])
        rel = relation(a, b)
        top = a if rel == "above" else b - card_h
        top = min(max(top, HOOK_MIN_TOP), HOOK_MAX_BOTTOM - card_h)
    else:
        top = centred_in(*HOOK_PREF)
    # MEASURE THE OVERLAP INSTEAD OF ASSERTING IT. This branch used to print
    # "OVERLAPS a face" and return False unconditionally, without ever comparing
    # the position it had just chosen against a face rectangle. It often does
    # overlap - but the bands already carry HOOK_FACE_PAD around every face, so
    # flushing the card to a band's far edge can leave it clear of the face and
    # only inside the safety margin. Reporting that as an overlap trains the
    # operator to ignore the line, and the False it returns is what the caller
    # uses to decide the card is compromised.
    lap = max((min(top + card_h, fb) - max(top, ft)
               for _l, ft, _r, fb in faces), default=0)
    if lap <= 0:
        near = min(min(abs(top + card_h - ft), abs(fb - top))
                   for _l, ft, _r, fb in faces)
        sys.stderr.write(
            f"hook: card at y{top}..{top + card_h} is clear of every face "
            f"(nearest {near}px) but no band was {card_h}px tall with the "
            f"{HOOK_FACE_PAD}px pad, so it sits inside the pad\n")
        return top, True
    sys.stderr.write(
        f"WARNING: hook card at y{top}..{top + card_h} OVERLAPS a face "
        f"(y{f_top}..{f_bot}) by {lap}px - no clear band between "
        f"y{HOOK_MIN_TOP} and y{HOOK_MAX_BOTTOM} is {card_h}px tall even at "
        f"{HOOK_MIN_SIZE}px type. The card is only up for {HOOK_HOLD:.1f}s; "
        f"shorten the hook if it matters on this clip.\n")
    return top, False


def fx_unit(t0: float, d: float) -> str:
    """ffmpeg expression: progress 0..1 of a window starting at t0 lasting d."""
    return f"min(1,max(0,(t-{t0:.3f})/{d:.3f}))"


# DO NOT QUANTISE THE CUTAWAY TRAVEL ONTO THE DELIVERED FRAME GRID. It was
# proposed on the reasoning that the overlays composite pre-tempo, so the
# trailing setpts drops frames out of the curve and some delivered frame has to
# travel double. The reasoning is sound and the premise is FALSE, and it was only
# caught by simulating it rather than arguing about it.
#
# Simulated over 300 phases at each tempo, worst per-delivered-frame travel of
# the 1080px swipe:
#
#     tempo    as it ships    quantised with ceil()
#     1.000       246 px          440 px
#     1.040       246 px          440 px
#     1.063       246 px          440 px
#     1.120       244 px          366 px
#
# The curve is a continuous function of source time, so sampling it on the
# delivered grid samples the SAME curve at wider intervals over a proportionally
# longer source window - the travel per delivered frame does not change with the
# tempo, and there is nothing to fix. Quantising forces the progress onto nine
# discrete levels that the delivered frames do not line up with, which stalls
# some frames and makes others jump two levels at once. It is nearly twice as
# bad as doing nothing.
#
# What IS true, and is a separate question nobody has asked the owner: the swipe
# already runs at 246px, 23% of frame WIDTH, against the 1/6 rule fx_ease cites.
# The rise is 284px of 1920, 15% of frame HEIGHT, comfortably inside it. So the
# two halves of the move are not cut to the same rule. BROLL_OUT 0.300 was set
# after the owner watched the first version and called it glitchy, so it is a
# reviewed number - do not change it on the arithmetic alone.


def fx_ease(kind: str, u: str) -> str:
    """
    ffmpeg expression for an easing of the unit progress expression `u`.

    One place for the curves:
      out_quart  1-(1-u)^4   arrivals of SMALL things: fast away, settles softly
      in_cubic   u^3         departures of SMALL things: gathers speed and goes
      in_out     u*u*(3-2u)  smoothstep - fades, and every LARGE travel

    THE CURVE FOLLOWS THE DISTANCE, and getting that backwards is what made the
    first cutaways glitch. Peak velocity is about 4x the average on a quart and
    3x on a cubic, against 1.5x on a smoothstep. Over the hook card's 60px that
    is nothing. Over the picture's full 1920px rise it put 885px - 46% of the
    frame - into ONE frame, and a full-frame jump that big with no motion blur
    strobes: it reads as a flash rather than as a move. So anything travelling
    a large fraction of the frame uses in_out, which keeps the worst frame near
    the 1/6-of-the-frame rule of thumb that broadcast pans are cut to.
    """
    if kind == "out_quart":
        return f"(1-pow(1-({u}),4))"
    if kind == "in_cubic":
        return f"pow(({u}),3)"
    if kind == "in_out":
        return f"(({u})*({u})*(3-2*({u})))"
    raise ValueError(kind)


def _ease_out_cubic(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _ease_in_cubic(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x ** 3


def hook_state(t: float, tempo: float = 1.0) -> float | None:
    """
    The card's ALPHA at source time t, or None when it is not there.

    Only the alpha lives in the PNG sequence now. The travel - 60px in from the
    right, then off the frame to the left - is an overlay x expression in the
    filter graph (see hook_overlay), and the exit fade is a `fade` filter on the
    same stream, so the hold is one hard-linked file from HOOK_IN to the end.
    """
    hin, hhold, hout = HOOK_IN * tempo, HOOK_HOLD * tempo, HOOK_OUT * tempo
    if t < 0 or t >= hhold + hout:
        return None
    if t < hin:
        return HOOK_ALPHA0 + (1 - HOOK_ALPHA0) * _ease(t / hin)
    return 1.0


def hook_overlay(card_w: int, tempo: float = 1.0) -> tuple[str, str]:
    """
    (stream filter, overlay x expression) for the hook layer, in SOURCE time.

    x: +HOOK_SLIDE_IN -> 0 on an ease-out quart over HOOK_IN; then, from
    HOOK_HOLD, 0 -> -(W/2 + card_w/2 + 40) on an ease-in cubic over HOOK_OUT, so
    the card is fully off the left edge when the window ends. Frame 0 shows the
    card at x=+60 and alpha 0.85: a feed that thumbnails frame zero still gets
    the headline. The stream filter fades the alpha over the last HOOK_FADE_D of
    the exit so the card does not clip against the frame edge at full opacity.
    """
    hin, hhold, hout = HOOK_IN * tempo, HOOK_HOLD * tempo, HOOK_OUT * tempo
    travel = W // 2 + card_w // 2 + 40
    # In on a quart over 60px (a small travel: crisp is right). OUT on a
    # smoothstep, because the card leaves across most of the frame - the same
    # distance rule as the picture, and on a cubic the last frames of that
    # travel moved 344px each, half the card's own width per frame.
    x = (f"if(lt(t,{hin:.3f}),{HOOK_SLIDE_IN}*pow(1-{fx_unit(0.0, hin)},4),"
         f"if(gt(t,{hhold:.3f}),"
         f"2*floor(-{travel}*{fx_ease('in_out', fx_unit(hhold, hout))}/2),0))")
    pre = (f"format=rgba,fade=t=out:st={hhold + HOOK_FADE_AT * tempo:.3f}:"
           f"d={HOOK_FADE_D * tempo:.3f}:alpha=1")
    return pre, x


def build_hook_sequence(hook: str, seqdir: Path, dur: float,
                        faces: list[tuple[int, int, int, int]] | None = None,
                        slug: str = "", tempo: float = 1.0,
                        name: str = "", role: str = "") -> tuple[int, int, int]:
    """
    The hook layer's PNG sequence: the card's alpha over time, at a fixed place.

    Returns (frames, overlay_y, card_w). The layer is only as tall as the card's
    canvas and is overlaid at overlay_y; the arrival's alpha ramp is a handful
    of unique files and the hold is one file hard-linked through the exit (the
    exit's travel and fade happen in the filter graph - see hook_overlay).
    """
    if seqdir.exists():
        shutil.rmtree(seqdir)
    seqdir.mkdir(parents=True)
    uniq = seqdir / "u"
    uniq.mkdir()

    # THE RUNG LADDER, and the shrink order is inverted from what it was. The
    # card used to shrink the HEADLINE the moment place_hook could not fit it.
    # It now drops the ATTRIBUTION first - stacked, then one line, then name
    # only, then nothing - re-placing at each rung, and only shrinks the headline
    # once the credential is gone. The headline stops the scroll; the credential
    # is second. A credential that will not fit at 22px falls to name-only rather
    # than condensing: shortening a real person's job title by algorithm risks
    # misstating it.
    #
    # The 3-line hooks are the ones that drop off rung 1. A three-line headline
    # plus a two-line footnote is five lines on one card, which is where a card
    # stops being a card.
    def _plate(rung: int, **kw):
        return hook_plate(hook, name=name, role=role, rung=rung, **kw)  # kw carries must_fit

    # THE CARD DOES NOT CARRY THE CREDENTIAL ANY MORE, and the ladder below is
    # kept behind "attr_on_card": true rather than deleted, because the reasoning
    # in it is still correct and a show may want it back.
    #
    # The owner, 2026-08-25: "The top is the title. And then after the title
    # goes, it will be the person's name in a box." That is an ORDER, and the
    # card cannot deliver it - a credential set into the title card arrives at
    # the same instant as the headline and leaves with it, so there is no "after
    # the title goes" for it to happen in.
    #
    # THIS OVERTURNS "The white card ALWAYS carries the name" (SKILL.md,
    # 2026-08-25, earlier the same day), and it is recorded there as an overturn
    # rather than done quietly. That rule was written when the alternative was
    # tracked type on the picture, gated to head, that vanished on share - i.e.
    # when the choice was "card or nothing". It is not that any more: the
    # nameplate is now a card of its own, on every mode, and the argument that
    # settled the old rule ("the card is ours, is the thing the eye lands on, and
    # is the only attribution that survives a crop") is satisfied by it in full.
    #
    # Keeping BOTH is the one option that is definitely wrong: the name would be
    # on screen twice in the first eight seconds, in two sizes, which is the
    # "two vocabularies in one clip" failure this file records twice already.
    rung = 1 if (name and ATTR_ON_CARD) else 4
    canvas, card_w, card_h = _plate(rung, max_block=HOOK_ATTR_BLOCK)
    top, fits = place_hook(card_h, faces, slug)
    while not fits and faces and rung < 4:
        rung += 1
        canvas, card_w, card_h = _plate(rung, max_block=HOOK_ATTR_BLOCK)
        top, fits = place_hook(card_h, faces, slug)
        if fits:
            sys.stderr.write(f"hook: attribution dropped to rung {rung} "
                             f"({'one line' if rung == 2 else 'name only' if rung == 3 else 'none'})"
                             f" to clear the face\n")
    if not fits and faces:
        # Only now the headline. Re-set to the tallest clear band, down to
        # HOOK_MIN_SIZE type and no further. A smaller card off the eyes beats a
        # bigger one across them; a card under 84px is not a hook.
        tallest = max((b - a for a, b in free_bands(faces)), default=0)
        if 0 < tallest < card_h:
            # best effort against a band that may be far too short - see
            # must_fit in hook_plate
            canvas, card_w, card_h = _plate(4, max_block=tallest,
                                            min_size=HOOK_MIN_SIZE,
                                            must_fit=False)
            rung = 4
            sys.stderr.write(f"hook: card re-set to {card_h}px tall to clear "
                             f"the face\n")
            top, fits = place_hook(card_h, faces, slug)
    # Under the right-hand action rail the card narrows to the caption measure,
    # the same reason the captions do - and it is re-set and re-placed, because
    # a narrower card is usually a taller one.
    if top + card_h > HOOK_RAIL_Y and card_w > CAP_MEASURE:
        canvas, card_w, card_h = _plate(rung, max_w=CAP_MEASURE,
                                        max_block=HOOK_ATTR_BLOCK)
        top, fits = place_hook(card_h, faces, slug)
    if name and rung < 4:
        sys.stderr.write(
            f"hook: names {name!r}" + (f", {role!r}" if role and rung < 3 else "")
            + f" on the card (rung {rung})\n")
    HOOK_TOOK_ATTR[0] = bool(name) and rung < 4
    cw, ch = canvas.size
    layer_y = top - HOOK_PAD
    blank = uniq / "blank.png"
    Image.new("RGBA", (W, ch), (0, 0, 0, 0)).save(blank)

    def draw(alpha: float, path: Path) -> None:
        layer = Image.new("RGBA", (W, ch), (0, 0, 0, 0))
        im = canvas
        if alpha < 0.999:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
        layer.alpha_composite(im, ((W - cw) // 2, 0))
        layer.save(path)

    made: dict[object, Path] = {}
    frames = int(round(dur * FPS))
    for f in range(frames):
        t = f / FPS
        a = hook_state(t, tempo)
        if a is None:
            src = blank
        else:
            key: object = "hold" if a >= 0.999 else round(a, 3)
            src = made.get(key)
            if src is None:
                src = uniq / f"h{len(made):03d}.png"
                draw(a, src)
                made[key] = src
        dst = seqdir / f"{f:05d}.png"
        try:
            # os.link, not Path.hardlink_to: the latter is 3.10+, and which
            # python3 wins on PATH here is not stable (macOS ships 3.9).
            os.link(src, dst)
        except OSError:
            dst.write_bytes(src.read_bytes())
    return frames, layer_y, card_w


# ------------------------------------------------------------ invest CTA ----
# THE BOTTOM OF THE SAFE AREA, not the middle of the frame (owner, 2026-08-24:
# "it should be on the bottom of the video... not in the middle because it kinda
# fucks the video up a little bit"). It sat at y966..1084, which is dead centre
# of a 1920 frame - across the speaker's chest on a head crop and over the chart
# in share.
#
# 92px is what the frame actually has. Below CAP_SAFE_BOTTOM 1430 is platform
# chrome (TikTok's ~480px puts the floor at y1440), and above is the caption
# band. The only way to open a strip at the bottom is to ride the captions UP
# while the invitation is on screen: a TOP-aligned two-line caption ends at
# y1336, so y1338..1430 is clear of both. See CAP_RAISED.
# TALL ENOUGH TO CONTAIN THE RISE, which is the difference between an animation
# and a pop. At 250px the band could not hold a pill that starts 380px below its
# resting place, so the entrance was drawn outside the canvas and CLIPPED - the
# pill simply appeared, which is exactly what the owner meant by "not just pop up,
# it needs to animate in". The band now reaches y1810 so the whole travel is
# inside it. Nothing else lives down there; the invitation is the only tenant
# below the captions.
#
# 630 -> 700 on 2026-08-25. The lockup is one plate now (button + address on a
# single canvas, so they scale as one object) and carries PILL_SHADOW_PAD on
# every side, which makes it 251px tall against the 150px pill the 630 was sized
# around; and the rest position is derived from CAP_SAFE_BOTTOM rather than
# hand-set, which moved it up. 19 + PILL_RISE 380 + 251 = 650 needed. _pill_metrics
# ASSERTS this rather than trusting the two numbers to stay in step - the same
# clipped-entrance defect this comment describes had to be found by watching the
# clip the first time. y1180 + 700 = 1880, still inside the 1920 frame.
CTA_BAND_H = 700
# ...AND THE HEIGHT ITS OTHER TENANTS CENTRE THEMSELVES IN, WHICH IS NOT THE SAME
# NUMBER. The comment above says "the invitation is the only tenant below the
# captions" and that is FALSE - build_capsule_sequence's own docstring says "Two
# tenants again" 800 lines down. THREE renderers besides the pill draw onto a
# W x CTA_BAND_H canvas and centre their content in it:
#
#     render_attr_band_png   the speaker nameplate fallback   (a LIVE path -
#                            it fires whenever the hook card has no clear band)
#     _render_cta_line       the "line" invitation style
#     (the closing address used to be a third tenant here; it could never draw -
#      see the note above build_capsule_sequence)
#
# So when the band grew 630 -> 700 to contain the pill's entrance travel, all
# three moved DOWN 35px - further under the action rail - for a reason that has
# nothing to do with any of them. Nothing reported it: preflight's SAFE check
# scores the captions and the invitation and knows about neither.
#
# The captions had this exact problem and solved it: CAP_BAND_H 480 is the
# CANVAS (tall, so a raised card can ride high) and CAP_BAND_H_REST 300 is what
# the content centres in. Same split here. CTA_BAND_H is the canvas the pill's
# 380px rise has to fit inside; CTA_BAND_H_REST is where everything else sits,
# and it does not move when the pill's geometry changes.
CTA_BAND_H_REST = 630
# A quiet line ABOVE the captions. It sat at 1846 for as long as there was a scrim
# down there to sit on, which put it 74px off the frame bottom - inside TikTok's
# ~480px of chrome, Reels' ~420 and Shorts' ~300, so it was unreadable on all
# three. It survived only because it is off by default whenever the end card is
# on, which is nearly always. 1020..1084 clears the chrome and leaves 46px of air
# above CAP_BAND_Y.
CTA_BAND_Y = 1180                           # the RESTING lockup sits at the top of it
CTA_TAIL = 2.6           # only the closing seconds carry it
# With the closing card on, the address is already the last thing on screen for
# four seconds. Repeating it inside the clip's final beat puts it twice in a row,
# which reads as a mistake rather than as emphasis - so the in-body line switches
# itself off. Turn it back on with "cta_in_body": true (e.g. if endcard is off).
CTA_IN_BODY = bool(CFG.get("cta_in_body", not CFG.get("endcard", True)))

# THE INVITATION, and where it is allowed to be.
#
# The owner asked for "invest into quasar markets, or sign up for free" on the
# clip. The brand problem it answers is real and measured: the mark appears ONLY
# in the closing card, so the ~90% of viewers who scroll before it never see it -
# and during b-roll cutaways the SPEAKER is gone too, which on a 48s clip with
# three inserts is 12.6 seconds, a quarter of the runtime, with nothing on screen
# identifying whose clip this is.
#
# IT IS NOT A BUTTON. look.md records an outlined capsule being tried twice and
# rejected twice: "an enclosed shape sitting against the video is the busiest
# element in the frame, and it competes with the face for exactly the duration you
# want the face winning", and "a button that cannot be tapped is a small broken
# promise on every clip". Plain tracked type reads as a signature. That holds.
#
# WHERE IT GOES IS THE WHOLE IDEA. It rides the CUTAWAYS. That is the one time
# the clip has no face on screen - the single written exception to the
# face-at-all-times rule - so the objection above cannot apply: there is nothing
# for it to compete with. It is also exactly when the clip is anonymous. So the
# gap and the slot are the same seconds, and the line costs the face nothing.
# The closing beat stays governed by CTA_IN_BODY, unchanged.
# THE VERB AND THE HOST ARE ONE AUTHORED PAIR, AND A CROSSED PAIR IS REFUSED.
# The first build put "Sign up free" over INVEST.QUASARMARKETS.COM and that is a
# defect the viewer eats: the line names a free product action and the address is
# the RAISE page. SKILL.md holds what is ON SCREEN to the same standard as what is
# said, and an imperative to invest burned over a strategist discussing markets is
# a solicitation sitting on top of market commentary - the archive already carries
# a clip whose own note reads "Do not overlay any raise, valuation or CTA card on
# this one or it stops reading as a disclaimer."
#
# So the default pair is the product action over the product host. "Invest in
# Quasar Markets" over the invest host stays a legal pair for a set that wants it;
# what is refused is crossing them. This is also the owner's own second phrasing,
# verbatim - "or sign up for free" - and it is aimed at the ~90% who scroll, which
# is the gap this element exists to close. A raise ask aimed at a first-time
# fifty-second viewer is not.
CTA_VERB = CFG.get("cta_verb", "Sign up free")
CTA_STYLE = CFG.get("cta_style", "pill")   # "pill" or "line"
CTA_HOST = CFG.get("cta_signup", "quasarmarkets.com")
if ("sign" in CTA_VERB.lower() or "free" in CTA_VERB.lower()) \
        and CTA_HOST.lower().startswith("invest."):
    raise SystemExit(
        f"\nCROSSED CTA PAIR: {CTA_VERB!r} over {CTA_HOST!r}.\n"
        f"A free-signup line must not land on the raise page. Either set\n"
        f'  "cta_signup": "quasarmarkets.com"      (keep the free-signup line)\n'
        f'  "cta_verb": "Invest in Quasar Markets" (keep the invest host)\n')
CTA_ON_BROLL = bool(CFG.get("cta_on_broll", True))
# INSET INSIDE EACH CUTAWAY. 0.35 was sized against the SLIDE, whose cover
# spent BROLL_IN 0.333s rising and BROLL_OUT 0.300s swiping - the pad existed so
# the invitation was not arriving while the picture behind it was still moving.
# Under BROLL_STYLE "cut" there is no travel to clear: the cover is whole on its
# first drawn frame, so the pad is only a BEAT, and holding it at 0.35 would now
# be taking 0.70s out of a 2.0s cutaway for nothing.
#
# That matters because the pill's own animation is a fixed 14 frames
# (PILL_IN_FRAMES + PILL_OUT_FRAMES = 0.467s). At hold 2.6 and pad 0.35 the
# window is 1.90s and the button SETTLES for 1.43s; at the hold of 2.0 that a
# short clause actually gets, it settles for 0.83s - a call to action that
# arrives, is legible for four fifths of a second, and leaves. Four frames of
# pad puts that back to 1.27s at hold 2.0 and 1.87s at 2.6.
# THE CUTAWAY IS A SEQUENCE OF BEATS, NOT ONE MOMENT. Owner, 2026-08-25:
# "cuz the broll + signup feels very rushed ... the whole sequence of them needs
# to be feel smooth and clean and seemles."
#
# The pad was ONE symmetric number, and at 4 frames it put the button's arrival
# 0.13s after the picture's - so the cut and the button landed together, the
# button left as the picture cut back, and two 2-second events collided into
# one. That reads as rushed no matter how clean each individual move is.
#
# Split, and asymmetric on purpose, so the beat is:
#     the picture lands and holds ALONE           CTA_BROLL_LEAD
#     the button arrives                          PILL_IN_FRAMES
#     it holds, and is read
#     it leaves                                   PILL_OUT_FRAMES
#     the picture holds ALONE again               CTA_BROLL_TAIL
#     cut back to the speaker
#
# The lead is longer than the tail because the picture is the thing the viewer
# has to understand first - the button is a second thought laid over a picture
# they have already read. Landing them together makes the button an interruption
# and the picture an afterthought.
#
# At the 3.0s floor: window 1.95s, of which 1.48s is a settled button. At a 4.0s
# hold: 2.95s window, 2.48s settled. Under the old symmetric 4 frames and a 2.0s
# hold it was 1.12s settled with no air at either end.
CTA_BROLL_LEAD = 0.35 if BROLL_STYLE == "slide" else 0.60
CTA_BROLL_TAIL = 0.35 if BROLL_STYLE == "slide" else 0.45
# Kept as an alias so an external reader of CTA_BROLL_PAD still resolves. NOTE
# that nothing outside this file has ever read it - broll.py and preflight.py
# reference BROLL_PAD, which is the unrelated 0.25s tpad rounding allowance.
CTA_BROLL_PAD = CTA_BROLL_LEAD
CTA_FADE = 0.24          # kept for cta_windows' own arithmetic
# THE VERB HAS TO LEAD, AND WIDTH IS WHAT DECIDES THAT, NOT SIZE. At 46/26 the
# verb was the bigger type and still lost, because "INVEST.QUASARMARKETS.COM" is
# a long string and the address came out WIDER than the invitation sitting on top
# of it - so the eye took the address first and the offer read as a subtitle to a
# URL. 56 over 28 is a clean 2:1, which is enough that the verb leads on size by
# more than the address leads on width.
# Compacted to fit the 92px strip: 38 + 8 + 2 + 8 + 24 = 80, with room for the
# stroke. The verb still leads on size and now leads on width too, because the
# address lost the `invest.` host.
CTA_VERB_SIZE = 38
CTA_ADDR_SIZE = 30
# ... and the address is tracked TIGHTER than the closing card's 3.0. Tracking is
# what makes a short line read as a signature; on a 24-character address it just
# makes it wider, which is the problem above.
CTA_ADDR_TRACK = 4.0     # the closing card's own URL tracking
CTA_LINE_TRACK = 0.6     # ... and its tagline tracking
# The closing card's accent rule, lifted unchanged in width and hue, on a dark
# plate because at the card's own alpha over a stock photograph it disappeared.
CTA_RULE_W, CTA_RULE_H = 148, 2
# IT ARRIVES THE SAME WAY THE CAPTIONS DO, and that is the point.
#
# It first flew 110px in from the right, and the owner watched it and said it
# needed to be "smoother... more professional the way it comes in... we don't want
# it to be clawish". A second motion vocabulary inside one clip is what makes an
# edit feel assembled rather than authored: the captions expand into place on
# CAP_SNAP_CURVE and the invitation was sliding, so the frame carried two
# different ideas of how type arrives.
#
# Now there is one. The invitation expands on the SAME measured curve, over the
# same four frames, with a short fade under it. Nothing travels. That is what he
# meant by "if it's a flow, it's seamless" - the elements are not animating
# individually, the clip has a single way that words appear.
CTA_FADE_IN = CAP_SNAP_FRAMES / FPS     # 0.133s, the caption's own arrival
CTA_FADE_OUT = 0.18

# THE BUTTON. Owner, 2026-08-24, pointing at a MrBeast short: "it's about the
# subscribe, but for our case it would be follow for more, sign up for quasar
# markets... that's kinda the idea where it's a nice animate overlay."
#
# NOTE WHAT THIS OVERRIDES. references/look.md rejected an enclosed shape against
# the video twice, on the grounds that "a button that cannot be tapped is a small
# broken promise on every clip". That objection is still true and the owner has
# overruled it with a specific, extremely successful reference. It is his call and
# it is recorded here so nobody reverts it as a regression.
#
# MEASURED off youtube.com/shorts/hYahU_Cqwp8 at its native 30fps:
#
#   frame   y0     width    what
#   0       1632   419      enters from below, already part-scaled
#   1       1450   471
#   2       1368   482
#   3       1322   513
#   4       1294   533
#   5       1275   542      width OVERSHOOTS
#   6       1263   545      peak width
#   ...     1245   529      settles - width comes back, y keeps easing up
#   then    descends and leaves the same way
#
# So it is a SPRING: it rises from below the frame, overshoots in scale, settles,
# holds about ten frames, and drops back out. Resting geometry 529x153 centred at
# y1245..1398. Total life about 0.75s.
#
# OURS IS SHORTER, AND THE FRAME DECIDES THAT. His captions are 46px at y936 -
# dead centre and tiny - so a 153px pill at y1245 has the whole lower third to
# itself. Ours are 86px in a band ending at y1430. Even with the captions raised
# to the top of their band a two-line block ends at y1336, so the strip is
# y1338..1430 and a 153px pill does not fit. 88px does, and at 88px it still
# reads as a button rather than as a label.
PILL_H = 150
# THE TYPE FILLS THE PILL. Set side by side with the reference at the same crop
# and scale, 40px type in a 150px pill read as a small chip against its button -
# the reference's cap height fills most of its pill and ours had twice the air.
# 62 is about 0.41 of PILL_H, which is where the reference sits, and it takes the
# pill to ~470px wide against the reference's 529.
PILL_PAD_X = 56
PILL_TEXT_PX = 62
# THE TRAVEL IS THE ANIMATION. The reference rises 387px (y1632 -> y1245); this
# was 150 and the difference is entirely why ours read as an appearance rather
# than an entrance. It also stays OPAQUE the whole way - the reference is a solid
# object entering from off-frame, not something fading up, and fading it is what
# makes a rise look like a dissolve.
PILL_RISE = 380.0
# Room for the pill's own drop shadow, on all four sides. GaussianBlur(10)
# reaches 24px before its alpha reaches zero; at 12/11/16/7 it was being cut
# off mid-gradient, worst at alpha 46/255 along the bottom edge. See the long
# note in render_cta_png.
PILL_SHADOW_PAD = 30
PILL_ADDR_GAP = 12         # air between the button and the address beneath it
CTA_ADDR_STROKE = 3
# THE WHOLE LOCKUP HAS TO CLEAR THE PLATFORM CHROME, AND IT DID NOT. Measured
# on the delivered 08.25 clip and reproduced by rendering this function: the
# pill rested at frame y1242..1392 (fine) and the address ran to y1448 with its
# stroke - 18px past CAP_SAFE_BOTTOM (1430) and 8px past the y1440 TikTok floor
# the CTA_BAND_Y note below quotes. Fourteen of the address's twenty-two ink
# rows sat under the action rail.
#
# It survived because the only guard was `ay + f_a.size < CTA_BAND_H`, which
# tests the BAND (630 -> frame y1810) rather than the safe line 380px above it,
# and because preflight's SAFE check scores the pill and reported "the
# invitation to y1422" while the ink actually reached 1448.
#
# So the rest position is DERIVED from the safe line instead of being a
# hand-set 50: the lockup's bottom edge lands PILL_SAFE_MARGIN above
# CAP_SAFE_BOTTOM, whatever the address's height turns out to be. Changing
# CTA_ADDR_SIZE or the host string now moves the lockup instead of quietly
# pushing it further under the rail.
PILL_SAFE_MARGIN = 10
# 7 -> 10 FRAMES EACH WAY, to the same brief as the b-roll dissolve: "a little
# bit slower, a little bit cleaner ... you can have it be smoother and kinda flow
# into it", and "the smooth transition to the sign up for free quasar markets".
# 7 frames is 0.233s, which is the reference button's own speed and reads snappy
# beside a 0.35s cross-dissolve; 10 frames is 0.333s and sits in the same
# register as the picture around it. The reference measured 7; the clip it lives
# in has changed underneath it.
#
# AND 10 -> 15 (2026-08-25), same brief a third time: "it needs to flow in there
# slower and smoother". 15 frames is exactly 0.500s at 30. The worst single-frame
# scale step over the entrance falls from 0.067 to 0.0479 and lands on frame 0
# where the alpha is still ramping; the worst step near the SETTLE, which is the
# part anyone actually watches, falls from 0.0100 to 0.0028. The whole travel
# costs 1.000s out of a 3.15s window at BROLL_HOLD, leaving 2.15s settled - most
# of two breaths at PILL_PULSE_FRAMES.
#
# THE CEILING IS 17, not "as slow as you like". The feasibility gate in
# cta_windows needs PILL_TRAVEL + PILL_SETTLE_MIN inside the inset window, which
# at BROLL_HOLD_MIN 3.0 is 1.95s: N <= 15*(hold - 1.85). 15 clears it with 0.15s
# to spare; 18 would start silently dropping the invitation off the shortest
# cutaways.
#
# AND IT IS DERIVED FROM FPS, NOT WRITTEN DOWN. A hardcoded 15 is 0.500s on this
# show and 0.600s on a 25fps one, and SRC_FPS defaults to 25 - so the number that
# was chosen as "half a second" would have been a fifth longer on most of the
# shows this rig cuts. That is not a nicety: at 25fps a hardcoded 15 pushes
# PILL_TRAVEL to 1.200s, the feasibility gate in cta_windows to 2.000s, and a
# BROLL_HOLD_MIN cutaway's window is 1.95s - so the button would have been
# DROPPED off every minimum-length cutaway on every 25fps show, and (until the
# line added below it) dropped in silence.
PILL_TRAVEL_S = 0.50
PILL_IN_FRAMES = int(round(PILL_TRAVEL_S * FPS))
PILL_OUT_FRAMES = PILL_IN_FRAMES
# What the pill's animation actually costs, so cta_windows can refuse a window
# too short to settle in. It used to test 2.0 * CTA_FADE + 0.4 = 0.88s, and
# CTA_FADE belongs to the "line" style the pill replaced - the pill branch of
# cta_state never reads it. At the old guard's own limit the button would have
# spent 53% of its life travelling and nothing would have said so.
PILL_TRAVEL = (PILL_IN_FRAMES + PILL_OUT_FRAMES) / FPS
PILL_SETTLE_MIN = 0.8    # the shortest hold that reads as a button, not a flash


def cta_insert_min() -> float:
    """
    The shortest cutaway that can CARRY the sign-up, from its own five beats.

    THIS NUMBER IS WHY BROLL_HOLD_MIN IS 2.5, and writing it down is what lets
    every other insert be short. The recorded rejection of fast b-roll was "the
    broll + signup feels very rushed" - the button, not the picture - and the
    note under it already said so: "The reference does not carry an invitation
    button inside its cutaways. Ours does, and that is the whole difference."

    The beats are: the picture arrives, the button leads in, the button settles
    long enough to be read, the button leaves, the picture leaves. So an insert
    that carries the invitation owes all five and an insert that does not owes
    only the picture.

    Measured at 25fps this is 2.81s, against a MIN_HOLD of 3.2 - so today EVERY
    insert pays for a button that exactly one of them carries.
    """
    return round(max(CTA_BROLL_LEAD, BROLL_IN) + PILL_TRAVEL + PILL_SETTLE_MIN
                 + max(CTA_BROLL_TAIL, BROLL_OUT), 3)
# HOW MUCH OF THE TRAVEL THE ALPHA RAMP COVERS. It was 0.34 - a third - which at
# 15 frames is five frames of fade, and the first of those is alpha 0.0 exactly.
# build_capsule_sequence discards any frame under 0.004, so the first frame that
# ever reached the screen was the SECOND one, at 21% opacity: the button
# materialised at a fifth of full strength in a single frame, at both ends of
# every cutaway. Measured, not inferred - cta_state's own alphas are
# 0.00, 0.21, 0.42, 0.63, 0.84, 1.00.
#
# 0.55 over a smoothstep gives 0.00, 0.04, 0.16, 0.32, 0.50, 0.68, 0.84, 0.96,
# 1.00 - the first visible frame is 4%, which is an object arriving rather than
# one being switched on. It still RISES the whole way; only the opacity takes
# longer, so the note below about it being "a solid object arriving, just not
# switched on" still holds - it is simply not switched on quite so abruptly.
PILL_FADE = 0.55
# scale over those 7 frames, from the measured widths (419..545 peak, 529 rest).
#
# THE LAST TWO ENTRIES USED TO BE 1.03 THEN 1.0, AND THAT WAS A ONE-FRAME SNAP.
# `dy` reaches 0 at kin=6 while the scale was still at its 1.03 peak, so the
# lockup arrived, stopped dead, and then jumped 3% - 13.9px of width and 4.6px
# of height between two frames at 30fps - with nothing in between. The exit is
# the entrance reversed, so it fired again at the start of every exit: six
# visible ticks in a three-cutaway clip, on an element whose whole brief is
# "smoother ... more professional the way it comes in".
#
# The overshoot is kept - it is the measured character of the reference button -
# and the RETURN from it is spread over the last three frames instead of being
# spent in one: 1.03 -> 1.02 -> 1.01 -> 1.0. Worst single-frame scale step goes
# from 0.030 to 0.010, and the settle now finishes on the same frame the travel
# does. PILL_SCALE[7] is the resting value the hold reads; entries 0..6 are the
# seven animated frames (kin/kout never index past 6, so the eighth was dead
# under the old tuple and is now the value the two curves converge on).
# RESAMPLED from the measured 7-frame curve onto 10, not re-invented: the shape
# (rise to a 1.03 overshoot, settle back) is what was measured off the reference
# button; only the number of samples it is drawn over has changed. The last
# entry is the resting value the hold reads.
# RESAMPLED AGAIN onto 14 (see PILL_IN_FRAMES). Same rule as the 7 -> 10 pass:
# linear interpolation of the measured shape, not a new shape. The last entry is
# EXACTLY 1.0 and it is the last frame the entrance draws, which is what lets the
# pulse below start from the resting scale with nothing to step over.
# THE MEASURED CURVE, AND IT IS SAMPLED RATHER THAN RE-TYPED. It was a tuple
# indexed directly by the frame counter, which made its LENGTH and the two frame
# counts one quantity in three places with nothing saying so: set PILL_OUT_FRAMES
# to 13 against a 15-entry curve and the exit plays the first thirteen frames and
# finishes at 1.0156 - a permanent 1.6% oversize on the frame it leaves. It also
# meant the curve had to be hand-resampled every time the travel changed (7 -> 10
# -> 15, three times now) and could not follow FPS at all.
#
# So this is the SHAPE, at its measured resolution, and pill_scale() reads it at
# whatever number of frames the travel turns out to be. The values are the ones
# taken off the reference button: a rise to a 1.03 overshoot and a settle back.
PILL_SCALE = (0.79, 0.857, 0.907, 0.94, 0.973, 1.0, 1.02, 1.027, 1.023, 1.01, 1.0)
assert PILL_SCALE[-1] == 1.0, \
    "PILL_SCALE ends on the value the travel lands on and the pulse starts from; "\
    "anything but 1.0 puts a step at both seams"

# ------------------------------------------------------------- the pulse ----
# THE BUTTON BREATHES WHILE IT SITS. The owner, 2026-08-25: "The sign up? It
# needs to pulse. It needs to move as it's sitting there ... it's gonna pulse,
# and it's gonna move." Everything else in the clip is in motion by now - the
# picture dissolves, the captions pop, the framing punches - and the one element
# asking to be acted on was the only thing holding perfectly still. "We don't
# want any staticness" is his sentence about it.
#
# THE SHAPE IS (1 - cos)/2, NOT sin, AND THAT IS THE WHOLE OF WHY IT DOES NOT
# TICK. It starts at exactly 1.0 with ZERO velocity, rises to 1 + AMP at the half
# cycle, and returns to 1.0 with zero velocity - so the seam between the
# entrance's last frame (PILL_SCALE[-1] = 1.0, also zero velocity by
# construction) and the pulse's first frame is continuous in both position and
# speed. A sine would start at 1.0 travelling at its maximum rate, which is a
# visible kick on the frame the travel ends.
#
# 0.024 IS 11px OF WIDTH on the 462px button and 3.6px of height, and the whole
# lockup's bottom edge moves 3.0px. That reads as breathing at arm's length on a
# phone; 0.04 read as a throb and 0.012 could not be seen at all. 1.6s is one
# calm breath - at a settled 2.2s the viewer sees one full cycle and the start of
# a second, which is what makes it a pulse rather than a single grow-and-shrink.
#
# IT IS WEIGHTED OUT ACROSS THE EXIT rather than switched off. The exit begins
# wherever the pulse happens to be, and dropping straight to PILL_SCALE would
# step up to 11px of width in one frame - the exact defect recorded above for the
# old 1.03 -> 1.0 snap, reintroduced from the other side.
#
# IN FRAMES, NOT SECONDS, AND THAT IS NOT A STYLE CHOICE. SRC_FPS is 25 on most
# shows and 30 on this one, so a period written in seconds is a different number
# of frames per show - and the raised cosine is only a PALINDROME, and therefore
# only cheap to dedupe, on an integer number of frames. 36 frames measured best
# across the three hold lengths this rig produces: 1.8 breaths at BROLL_HOLD,
# 1.36 at the live job's authored 3.7s, and one clean swell and release at
# BROLL_HOLD_MIN. 30 frames read as a throb; 48 never finished a breath on a
# short cutaway.
PILL_PULSE_FRAMES = int(round(1.20 * FPS))
PILL_PULSE_AMP = 0.024
PILL_PULSE_TAPER = 8       # frames to close the breath in, before the exit

# ---------------------------------------------------------- who is talking ----
# NOBODY ON SCREEN WAS EVER NAMED, and on a finance clip the speaker's authority
# IS the product - "Senior Commodity Strategist, Bloomberg Intelligence" is the
# reason to believe the sentence. The slate had no speaker field at all.
#
# THE SHOW ALREADY PAYS TO PRODUCE THIS AND THE CROP THROWS IT AWAY. The master
# carries proper burned-in lower thirds - measured on 08.24, a plate at x15..600,
# y850..1058 reading "BigBeat / Founder and CEO of Quasar Markets" and
# "Stephen Flanagan / Forex Educator" - and the default head crop is 608px wide
# and centred, x656..1264, which clears that plate entirely. Every head clip
# discards the attribution.
#
# It is retyped rather than lifted, for two reasons. The plate is only inside the
# frame on a duo (where it is currently being SLICED - see check_graphics), and
# the host's plate says "BigBeat", which is a screen handle. A handle is exactly
# what a finance clip cannot use.
#
# IT SHARES THE ADDRESS'S BAND AND COSTS NOTHING. y1020..1084 is empty for all
# but the last CTA_TAIL seconds of every clip, and it already has an overlay
# input in the filter graph. The name takes the same rectangle earlier, the
# address takes it at the end, and they are never on screen together - so this is
# one more PNG sequence's worth of drawing into a sequence that was already being
# built, no new ffmpeg input, no extra overlay, no measurable render cost.
# THE CREDENTIAL IS SET INTO THE HOOK CARD, not into a band of its own.
#
# It shipped on 2026-08-24 as a two-line plate at y1020..1084 and that placement
# was wrong for two measured reasons, both of which the frame decides rather than
# taste:
#
#   IT SAT ON THE FACE. On a head crop of a 16:9 source the 9:16 crop is a tight
#   close-up, and the band landed across the speaker's NOSTRILS - mean luma 137.6,
#   lit skin. That is the same defect that got the hook card unpinned from y96 on
#   2026-08-22 ("it covered his face to the nose"), and it had already been solved
#   once: place_hook finds a clear band around the face and nothing else in this
#   pipeline does.
#
#   IT SAT ON THE CHART. Measured across 17 delivered share clips, the SPLIT_GAP
#   seam lands anywhere from y400 to y993 depending on how pack_share divides the
#   panel, and APP_MIN_FRAC forces the app band to at least 998px - so the app's
#   top edge is at y969..1038 in every default pack, and a fixed band at y966
#   is ON the shared chart. There is no safe fixed y in share, because the packer
#   moves the seam per clip.
#
# So it goes where the machinery already is. The card is the one element already
# measured off panel_faces, already placed clear of the face, already narrowed
# under the rail. Three more things fall out for free: it reaches 100% of
# impressions instead of the fraction who survive to +3.4s; it needs no curves,
# no PNG states and no inputs of its own; and poster() scores only the first
# HOOK_HOLD seconds, so THE COVER FRAME THE FEED JUDGES THE CLIP ON NOW CARRIES
# THE CREDENTIAL, which nothing in this pipeline did before.
#
# THAT LAST ONE IS NO LONGER TRUE, and it is the price of the 2026-08-25 ordering
# ("the top is the title, and then after the title goes, the person's name in a
# box"). The credential is off the card by default, and the nameplate arrives
# AFTER poster()'s window closes - ATTR_AFTER_HOOK puts it past HOOK_HOLD, and
# poster scores min(HOOK_HOLD, 3.2) - so no cover frame can carry it. It is
# recorded rather than deleted because it is the strongest argument for the card
# and the next person weighing this has to know it was paid, not overlooked.
# The reach argument is unaffected: the nameplate is up by +3.3s, which is still
# inside the first four seconds of every clip.
# OFF BY DEFAULT (owner, 2026-08-24): "we don't really need the name cards
# because the name cards are already on the StreamYard. The names are gonna be
# there." The show's own rig burns a lower third into the source, so a second one
# is a duplicate - and two nameplates on one frame is the mistake read, which is
# the same argument the share-mode badge gate already makes.
#
# The whole mechanism stays behind the flag rather than being deleted, because it
# is the fallback for any source that does NOT carry its own badge - a phone
# recording, a podcast feed, a guest who joins without one. Set "name_card": true
# in project.json, or "speaker" on a clip with "force": true.
#
# WORTH KNOWING IF IT IS EVER SWITCHED BACK ON: a 608-wide centred head crop
# (x656..1264) clears the source badge entirely, measured at x15..600 on the
# 08.24 master - so on a head clip the rig's own lower third is cropped away and
# nobody is named at all. Author the crop to keep it, or turn this on.
# BACK ON, AND THE REASON IS MEASURED. It was switched off on the plan that the
# StreamYard rig already names everybody and the crop would simply keep it. The
# owner then watched a clip and said the name tag was not there, and he is right:
#
#   THE RIG'S BADGE CANNOT SURVIVE A VERTICAL CROP. It sits at the BOTTOM of a
#   1080-tall source, so any crop that keeps it puts it at the bottom of the
#   1920-tall output. Measured on the delivered Morrison clip, it lands at
#   y1673..1919 - 243px BELOW CAP_SAFE_BOTTOM, and behind the UI on all three
#   platforms (TikTok cuts at y1440, Reels y1500, Shorts y1620).
#
# There is no crop that fixes this. Cropping less height moves the badge up
# relative to the source but not relative to the OUTPUT, because it is pinned to
# the bottom of both. So either we draw it, or nobody is named on any vertical
# clip. We draw it.
#
# "name_card": false still turns it off for a source whose badge is somewhere
# other than the bottom edge - measure before assuming.
ATTR_ON = bool(CFG.get("name_card", True))
# Whether the HOOK CARD also carries the credential. Default False since
# 2026-08-25 - the nameplate is its own card now and arrives after the title, so
# putting it on both would name the speaker twice in eight seconds. See the long
# note at the rung ladder in build_hook_sequence.
ATTR_ON_CARD = bool(CFG.get("attr_on_card", False))
# BIGGER AND WITH MORE AIR. At 32px hard under the headline it read as a stray
# line rather than an attribution - the owner asked for "the names of the people
# need to be cleaner". Nothing was ADDED to fix that: no rule, no dash, no box.
# It is spacing and size, which is how this system fixes things.
ATTR_NAME_PX = 42          # QMInter500, sentence case
ATTR_NAME_TRACK = 0.4      # a hair, so it reads as a byline and not as a caption
ATTR_ROLE_PX = (30, 27, 24)  # QMInter400, +1.2 tracking; 24 is a hard floor
ATTR_ROLE_TRACK = 1.2
ATTR_GAP = 36              # air between the headline block and the name. 22 was
                           # cramped: the quote and its attribution have to read
                           # as two things, and the only thing separating them is
                           # this gap.
ATTR_LEAD = 4              # between the two attribution lines
ATTR_ALPHA = 190           # the bone card's mirror of look.md's muted token
# The card's own cap grows to hold the attribution. HOOK_MAX_BLOCK stays 390 for
# the HEADLINE, so the headline never pays for the credential - measured over all
# 41 distinct shipped hooks, the alternative (taking it out of the headline's 390)
# costs a mean 6.5px and a max 24px of type, pushing one hook below HOOK_MIN_SIZE.
HOOK_ATTR_BLOCK = 460

# AND A FALLBACK, BECAUSE ON A HEAD CROP THE CARD CANNOT CARRY IT.
#
# Measured against the real face geometries this pipeline actually produces: on a
# head crop the face spans y369..1125 (Morrison) and y438..1488 (08.24 clip 3),
# so the largest clear band is ~229px and the card needs 314-410px at EVERY rung
# including name-only. `place_hook` refuses all four. Head is 20 of 44 delivered
# clips, so "put it on the card" alone silently drops the credential on the
# commonest mode - which is worse than the placement it replaced.
#
# So each placement is used where it is safe:
#
#   card   share, duo, and any head clip with a clear band. Never on the face,
#          reaches every impression, lands in the poster frame.
#   band   head ONLY, when no rung fits. y966..1084 sits on the lower face, which
#          is the least-bad place on a crop that has no clear band at all - and
#          it is up for four seconds, not the whole clip.
#
# The band is gated to HEAD deliberately. Its other defect was landing on the
# shared chart, and share is exactly where the card DOES fit, so the fallback
# never needs to run there and can never hit that seam.
#
# AND IT IS A CARD NOW, NOT TYPE ON THE PICTURE (2026-08-25). The owner, looking
# at the Nathan Dean clip: "I actually love this look here of the person's name,
# what they have, whoever they are. That is actually perfect ... The only thing
# it needs to be, it needs to be a white box behind it so it's cleaner, you can
# view it better, with black text - but then that should animate in and it
# should animate out ... instead of it, like, go swiping, it should kinda fade
# in." And: "The top is the title. And then after the title goes, it will be the
# person's name in a box." So: title card, then nameplate card, in that order,
# and the nameplate is the SAME object as the hook card - bone plate, slate type
# - arriving a second time rather than a different element in a different
# vocabulary.
#
# THIS IS ALSO WHERE A REAL DEFECT WAS FOUND AND FIXED. The tracked-line version
# was drawn at `y = (CTA_BAND_H_REST - block) / 2` inside a 700px band pinned at
# CTA_BAND_Y 1180, which put its ink at y1460..1548 on the delivered file -
# measured, not inferred. CAP_SAFE_BOTTOM is 1430 and the note above it says
# "nothing that must be read may sit below y1440", because TikTok draws its own
# chrome over roughly the bottom 480px. The credential has therefore been
# rendering INSIDE the platform chrome on every head clip this rig has shipped,
# which is exactly the "you can view it better" the owner was reaching for
# without being able to name it. Like the invitation beside it, the card's rest
# position is now DERIVED from CAP_SAFE_BOTTOM by _attr_metrics() rather than
# fixed, so it cannot drift back down.
#
# AND THE CAPTIONS RIDE UP FOR IT, the same way they already do for the
# invitation. The nameplate and the button are two tenants of ONE strip at the
# bottom of the frame - they are never on screen together (attr_band_state and
# cta_state are mutually exclusive in build_capsule_sequence) - so they take the
# same rows, and a viewer sees one object appear in one place twice rather than
# two elements in two places.
# WHEN IT ARRIVES IS DERIVED FROM THE HOOK'S EXIT, NOT WRITTEN DOWN. 3.25 was
# HOOK_HOLD 3.0 + HOOK_OUT 0.233 plus a rounding, which is right at tempo 1.0 and
# wrong at every other tempo - the card's exit is tempo-scaled (hook_state takes
# it) and a bare constant is not. Stepped frame by frame at 1.04 the title is
# still at full alpha, sliding off left, while the nameplate is fading up at 0.42;
# at SPEED_MAX 1.12 they overlap for a third of a second. Two bone cards on screen
# at once is the exact ordering this whole change exists to deliver, broken by the
# one number that did not follow the clip.
ATTR_AFTER_HOOK = 0.08     # air between the title leaving and the name arriving
ATTR_TEMPO = [1.0]         # set once per clip by render(), like BROLL_WINDOWS
ATTR_BAND_HOLD = 4.2
# THE SECOND SPEAKER'S PLATE. A head clip has one person and one card; a
# conversation clip switches between two, and until 2026-08-28 only ONE of them
# was ever named - the other could hold the screen for forty seconds
# unidentified. The owner's rule is that every clip carries the white box with
# the name on it, and the spirit of that is that people ON SCREEN get named.
#
# Broadcast plates each person the first time you cut to them, and that is what
# this is: [(start, end, name, title)] in composite seconds, filled by render()
# from the turn schedule, empty on every other clip shape. One card each, at
# their first appearance, never again.
ATTR2: list[tuple[float, float, str, str]] = []
ATTR2_SETTLE = 0.35        # let the cut land before the card arrives on it


def attr_window2() -> tuple[float, float] | None:
    """(start, end) of the SECOND speaker's plate, or None."""
    return (ATTR2[0][0], ATTR2[0][1]) if ATTR2 else None


def attr_band_state2(t: float) -> float:
    """Alpha for the second plate - the same cross-fade as the first."""
    win = attr_window2()
    if win is None or t < win[0] or t >= win[1]:
        return 0.0
    a, b = win
    if t < a + ATTR_BAND_IN:
        u = min(max((t - a) / ATTR_BAND_IN, 0.0), 1.0)
        return 1.0 - (1.0 - u) ** 3
    if t > b - ATTR_BAND_OUT:
        u = min(max((b - t) / ATTR_BAND_OUT, 0.0), 1.0)
        return u ** 3
    return 1.0
# SLOWER AND SMOOTHER, AND A PURE CROSS-FADE. 0.28s with 44px of horizontal
# travel was the "swiping" the owner asked to be rid of, and it was also the one
# element in the clip still arriving on the type compass (look.md: "type arrives
# from the RIGHT") while everything around it had gone to dissolves. A card that
# fades has no direction to be inconsistent about. The in is longer than the out
# because arriving is the part that must not be missed.
ATTR_BAND_IN = 0.50
ATTR_BAND_OUT = 0.42
# Air between the nameplate leaving and the first cutaway arriving, so the
# two cross-fades are consecutive beats rather than one muddy one.
ATTR_BAND_GAP = 0.30
# The plate. Padding and radius are the hook card's, scaled to a two-line block
# rather than a headline: 44/30 and r22 around 84-120px type reads as a title
# card, and the same numbers around 54/32px type read as a slab.
ATTR_PLATE_PAD_X = 38
ATTR_PLATE_PAD_Y = 22
ATTR_PLATE_R = 16
ATTR_PLATE_PAD = 44        # canvas margin, so the drop shadow is never clipped
ATTR_PLATE_LEAD = 6        # air between the name and the role
# 14, which puts the plate's bottom edge on y1416 - the SAME ROW the invitation's
# address inks on. The two tenants of this strip end on one line, which is the
# only reason a viewer reads them as one object appearing twice.
ATTR_SAFE_MARGIN = 14
ATTR_NAME_SIZE = 54        # the size the owner approved on the 08.25 clip
ATTR_ROLE_SIZE = 32
def speaker_label(speaker: str | dict | None = None,
                  mode: str = "head") -> tuple[str, str]:
    """
    (name, title) for a clip, or ("", "") when nobody is named.

    A clip's own `speaker` wins; otherwise the show's `host` from project.json,
    because most clips are the host and retyping the same name six times a week
    is how a wrong one eventually ships. Either may be a bare string (the name,
    no title) or {"name": ..., "title": ...}.
    """
    def _split(v) -> tuple[str, str]:
        if isinstance(v, dict):
            # A DICT THAT NAMES NOBODY IS A TYPO, NOT AN ABSENCE. {"nmae": ...}
            # returned ("", "") here, fell through to the host fallback below,
            # and burned the HOST'S NAME onto a guest's face - while preflight
            # reported it as coming "from the clip". Refuse it instead.
            if not (set(v) & {"name", "title"}):
                raise SystemExit(
                    f"\nspeaker: {sorted(v)} names nobody - expected 'name' "
                    f"and optionally 'title'.\n"
                    f"Left alone this falls back to the show's host and puts "
                    f"the wrong name on screen.\n")
            return str(v.get("name", "")).strip(), str(v.get("title", "")).strip()
        if not v:
            return ("", "")
        t = str(v).strip()
        # "Nathan Dean, Sr. Analyst, Bloomberg Intelligence" is how anybody
        # writes this in a bare string, and it used to become a NAME of that
        # whole run - one 32px line across the card instead of the 54px name
        # over the 32px title the two-line plate is built for. Split on the
        # FIRST comma: everything after it is the credential, commas and all.
        if "," in t:
            name, _, title = t.partition(",")
            return name.strip(), title.strip()
        return (t, "")

    name, title = _split(speaker)
    # A TILE TAG IS NOT A NAME, and this field has two meanings in this pipeline.
    # Older share and duo slates in the archive use "speaker" as a lowercase
    # PARTICIPANT TAG - measured across the live jobs: "exchange", "alan",
    # "nathan", "steve", "dave" - because check_speaker uses it to say which TILE
    # is talking, not what to print. Those values were survivable while the
    # credential only ever reached the hook card behind a rung ladder that
    # usually refused it. The nameplate is unconditional, so a bone card reading
    # "exchange" would ship on a two-up.
    #
    # The test is capitalisation, because every presentable credential has some
    # and no tile tag in the archive does. It REFUSES and says so rather than
    # title-casing: "steve" auto-capitalised to "Steve" is a different wrong
    # answer, since the man's card says "Steven E. Orr".
    if name and not any(c.isupper() for c in name):
        sys.stderr.write(
            f"note: {name!r} reads as a tile tag rather than a credential (no "
            f"capitals), so nobody is named on this clip. Set \"speaker\" to "
            f"{{\"name\": ..., \"title\": ...}} to name them.\n")
        name, title = "", ""
    if name:
        return name, title
    # A DUO MAY NOT FALL BACK TO THE HOST. On a two-up the card sits between two
    # faces and names ONE person, which works because it is a QUOTE attribution -
    # it claims authorship of the sentence above it. Defaulting to the host there
    # would put the host's name on a guest's sentence half the time, and this
    # pipeline has no reliable per-band speaker attribution to prevent it
    # (whospeaks margins of 1.13x and 1.12x over 40-56s spans are the reason duo
    # is excluded from the punch). Nothing is inferred: name the speaker by hand
    # or the card carries no credential.
    # head_follow joins them, for the same reason and a sharper version of it:
    # the frame CHANGES person part way through, so a host fallback would put
    # one name over both people in the same clip. An explicit `speaker` is fine
    # and is the right thing to set - at the nameplate's window exactly one
    # person is on screen and the turn schedule says who - but it must be typed,
    # never inferred.
    if mode in ("duo", "duo_share", "conversation", "conversation_share"):
        return "", ""
    return _split(CFG.get("host"))


def _ease_out(x: float) -> float:
    """Fast depart, soft arrival - what makes an entrance read as crisp."""
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


ATTR_BAND_MIN = 2.2        # the shortest life that reads as a credential


def attr_at() -> float:
    """When the nameplate arrives, in composite seconds. See ATTR_AFTER_HOOK."""
    return (HOOK_HOLD + HOOK_OUT) * ATTR_TEMPO[0] + ATTR_AFTER_HOOK


def attr_window(dur: float) -> tuple[float, float] | None:
    """
    (start, end) of the nameplate in CLIP seconds, or None if it does not fit.

    One place that answers it, because four callers need the same answer and
    they must not each derive it: attr_band_state draws it, build_caption_
    sequence raises the captions for it, cta_windows keeps the invitation off
    the same rows, and preflight reports it. The invitation used to be the only
    tenant of this strip and the two were free to be computed separately; they
    are not any more.

    IT IS ALSO CLIPPED OFF THE FIRST CUTAWAY, and that is not tidiness. The
    first render of the card version put its fade-out across the first insert's
    dissolve - measured on the delivered file at +7.35s, the nameplate at 12%
    over a cover at 43% - and two cross-fades running through each other at
    once is exactly the mud the owner means by "we don't want any staticness ...
    everything should just flow". They are consecutive beats, so they get
    consecutive time: title card, nameplate, then the picture.

    BROLL_WINDOWS is a module record filled by broll_chain, which runs before
    every caller here. preflight has no windows and gets the unclipped answer,
    which is the right one for a report that runs before anything is rendered.
    """
    at = attr_at()
    end = min(at + ATTR_BAND_HOLD,
              dur - (CTA_TAIL if CTA_IN_BODY else 0.0) - ATTR_BAND_OUT)
    if BROLL_WINDOWS:
        clipped = min(w[0] for w in BROLL_WINDOWS) - ATTR_BAND_GAP
        # THE CREDENTIAL IS NOT DROPPED TO MAKE ROOM. If the first cutaway lands
        # so early that clipping would leave less than ATTR_BAND_MIN, the card
        # keeps its full life and the two overlap - an unnamed speaker is a
        # worse clip than a busy second, and this pipeline has no other place to
        # put the attribution once it is off the hook card.
        # NOT REPORTED FROM HERE. attr_band_state calls this once per FRAME, so a
        # stderr line in this function wrote 1440 identical notes per clip into
        # the same stream that carries the b-roll placements and the "invite: no
        # room" warnings - drowning the operator-facing signal this change was
        # added to provide. build_capsule_sequence says it once instead.
        if clipped - at >= ATTR_BAND_MIN:
            end = min(end, clipped)
    if end - at < ATTR_BAND_IN + ATTR_BAND_OUT + 0.5:
        return None
    return at, end


def attr_band_state(t: float, dur: float, on: bool) -> float:
    """
    Alpha for the nameplate card at clip time t. See ATTR_AFTER_HOOK.

    A PURE CROSS-FADE. It returns one number now, not (alpha, dx): the 44px of
    horizontal travel that used to come back with it was the "swiping" the owner
    asked to be rid of, and a card that fades has no direction to be inconsistent
    about. The curves are the same pair the cutaway either side of it uses -
    ease-out on the way in, ease-in on the way out - so the whole clip moves in
    one register.
    """
    win = attr_window(dur) if on else None
    if win is None or t < win[0] or t >= win[1]:
        return 0.0
    a, b = win
    if t < a + ATTR_BAND_IN:
        u = min(max((t - a) / ATTR_BAND_IN, 0.0), 1.0)
        return 1 - (1 - u) ** 3
    if t > b - ATTR_BAND_OUT:
        u = min(max((b - t) / ATTR_BAND_OUT, 0.0), 1.0)
        return u ** 2
    return 1.0


@functools.lru_cache(maxsize=8)
def _attr_metrics(name: str, role: str) -> tuple:
    """
    (name_font, role_font, name_w, role_w, plate_w, plate_h, rest_y) for a
    nameplate, measured once.

    A function rather than constants for the same reason _pill_metrics is one:
    two of these numbers depend on the FONTS and on the particular credential
    being set, so a hand-written height goes stale the moment a title is long
    enough to shrink the type - and a stale height is how an element ends up
    drawn into the platform chrome, which is precisely what happened to the
    version this replaces.

    The type shrinks so the PLATE fits CAP_MEASURE, which is not the same as the
    ink fitting it. A caption is bare type, so its ink budget IS its width; the
    nameplate is type on a filled card with ATTR_PLATE_PAD_X either side, so a
    name shrunk to exactly 740px of ink draws a 816px card. Measured before this
    was fixed, "Alexandra Konstantinopoulos / Managing Director, Global Macro
    Strategy Research" rendered a plate at x144..943 against an action rail that
    leaves x151..929 usable - over the chrome at BOTH ends, on the one element
    whose whole job is to be read. The captions beside it were inside, because
    they are measured against the thing they actually draw.

    So the budget is CAP_MEASURE minus the padding. Same 740px limit, same two
    constraints - the right-hand action rail every app draws, and the grouping
    budget the rest of this look is set to - applied to the card rather than to
    the words inside it.
    """
    measure = CAP_MEASURE - 2 * ATTR_PLATE_PAD_X
    d0 = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    f_n = _font(F_CAP, ATTR_NAME_SIZE)
    f_r = _font(F_UI, ATTR_ROLE_SIZE)
    wn = tracked_width(d0, name, f_n, 0.6)
    wr = tracked_width(d0, role, f_r, 1.8) if role else 0.0
    if max(wn, wr) > measure:
        k = max(measure / max(wn, wr), CAP_SHRINK_MIN)
        f_n = _font(F_CAP, max(8, int(ATTR_NAME_SIZE * k)))
        f_r = _font(F_UI, max(8, int(ATTR_ROLE_SIZE * k)))
        wn = tracked_width(d0, name, f_n, 0.6)
        wr = tracked_width(d0, role, f_r, 1.8) if role else 0.0
    # HEIGHTS COME FROM getmetrics(), NEVER A LITERAL - the same rule attr_height
    # already states for the card's own rung. The ascent and descent of these
    # faces at these sizes is what decides the box.
    an, dn = f_n.getmetrics()
    block = an + dn + ((ATTR_PLATE_LEAD + sum(f_r.getmetrics())) if role else 0)
    # EVEN, so the plate's centre lands on the frame's 539.5 rather than half a
    # pixel to the right of it. An odd width cannot be centred on a 1080px frame,
    # and half a pixel of asymmetry on a bone plate over a moving picture is
    # exactly the class of thing SKILL.md records the owner naming on the button.
    pw = int(min(max(wn, wr) + ATTR_PLATE_PAD_X * 2, CAP_INK_MAX)) // 2 * 2
    ph = int(block + ATTR_PLATE_PAD_Y * 2)
    # THE REST POSITION IS DERIVED FROM CAP_SAFE_BOTTOM, not written down. The
    # plate's ink ends ATTR_PLATE_PAD above the canvas's own bottom edge (the
    # margin the shadow lives in), so put that ATTR_SAFE_MARGIN clear of the
    # line platform chrome starts at. This is the whole of the y1460..1548 fix.
    rest_y = (CAP_SAFE_BOTTOM - ATTR_SAFE_MARGIN) - CTA_BAND_Y - ph
    if rest_y < 0:
        raise ValueError(
            f"the nameplate ({ph}px) does not fit above CAP_SAFE_BOTTOM "
            f"{CAP_SAFE_BOTTOM} in a band starting at {CTA_BAND_Y}")
    return f_n, f_r, wn, wr, pw, ph, rest_y


def attr_plate_rows(name: str, role: str) -> tuple[int, int]:
    """
    (top, bottom) of the nameplate's PLATE in frame coordinates.

    build_caption_sequence asks this so the captions can be raised clear of it,
    and preflight asks it so the safe-area check measures what actually ships
    rather than rebuilding the geometry out of constants - which is the failure
    mode SKILL.md records for the invitation ("Two owners of one quantity, and
    the one that could not see the ink was the one doing the checking").
    """
    _f_n, _f_r, _wn, _wr, _pw, ph, rest_y = _attr_metrics(name, role)
    return CTA_BAND_Y + rest_y, CTA_BAND_Y + rest_y + ph


def render_attr_band_png(path: Path, alpha: float, name: str, role: str,
                         colours: dict | None = None) -> None:
    """
    The nameplate: a bone card with slate type, the hook card arriving a second
    time.

    NOT tracked bone type on the picture any more, and not because the old one
    was illegible - it was legible, and the owner said so ("I actually love this
    look ... that is actually perfect"). It is a card because he asked for one
    ("it needs to be a white box behind it so it's cleaner ... with black text")
    and because the alternative reads as two vocabularies: the title arrives as a
    bone card with slate type and the credential arrived as outlined bone type on
    the picture, which is the same failure this file records for the invitation's
    address before it was drawn onto the button's own plate.

    `colours` is accepted and ignored. The adaptive caption palette exists so
    type ON THE PICTURE separates from whatever is behind it; ink on an opaque
    bone plate has no such problem, which is most of the argument for the plate.
    """
    img = Image.new("RGBA", (W, CTA_BAND_H), (0, 0, 0, 0))
    if alpha <= 0.004 or not name:
        img.save(path)
        return
    f_n, f_r, wn, wr, pw, ph, rest_y = _attr_metrics(name, role)

    cw, ch = pw + 2 * ATTR_PLATE_PAD, ph + 2 * ATTR_PLATE_PAD
    plate = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    bx, by = ATTR_PLATE_PAD, ATTR_PLATE_PAD
    # The same soft drop the hook card carries, at the same offset, so the two
    # sit at the same height off the picture. ATTR_PLATE_PAD is larger than
    # GaussianBlur(12)'s own reach, so the gradient ends because it has faded
    # out and not because it ran out of canvas - the rectangular-halo defect
    # SKILL.md records measuring on the invitation, not repeated here.
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [bx + 4, by + 8, bx + pw - 1 + 4, by + ph - 1 + 8],
        radius=ATTR_PLATE_R, fill=(4, 7, 11, 115))
    plate.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))

    d = ImageDraw.Draw(plate)
    # -1 on both far edges: PIL's rounded_rectangle is INCLUSIVE of x1 and y1, so
    # a rect from bx to bx+pw draws pw+1 columns and the plate's centre lands
    # half a pixel right of the frame's. Same defect, same fix, as the pill.
    d.rounded_rectangle([bx, by, bx + pw - 1, by + ph - 1],
                        radius=ATTR_PLATE_R, fill=BONE + (255,))
    # Slate on opaque bone, so no stroke and no shadow on the type - the hook
    # card's rule for its own attribution rung, applied here.
    an, dn = f_n.getmetrics()
    y = by + ATTR_PLATE_PAD_Y
    draw_tracked(d, (bx + (pw - wn) / 2, y), name, f_n, SLATE + (255,), 0.6)
    if role:
        draw_tracked(d, (bx + (pw - wr) / 2, y + an + dn + ATTR_PLATE_LEAD),
                     role, f_r, SLATE + (ATTR_ALPHA,), 1.8)

    if alpha < 0.999:
        plate.putalpha(plate.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(plate, (int(round((W - cw) / 2.0)),
                                int(round(rest_y - ATTR_PLATE_PAD))))
    img.save(path)


CAP_RAISE_BRIDGE = 1.2


def merge_raise(wins: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """
    The caption raise windows, with short gaps between them closed up.

    MOVING THE CAPTIONS IS THE COST; HOLDING THEM HIGH IS FREE. The band is 480px
    for exactly this reason, and a raised card is still in the lower third. So
    when the nameplate leaves and a cutaway's invitation arrives less than
    CAP_RAISE_BRIDGE later, the captions stay up through the gap rather than
    dropping 278px and coming straight back - measured on the first cut of the
    08.25 recut, three consecutive cards at rows 987, 1265, 987 inside 1.3s. Two
    moves for one beat, in the element the viewer's eye is locked to.

    1.2s is the gap at which the two events stop reading as one beat: it covers
    the nameplate-to-first-cutaway hand-off (0.76s measured) and leaves the
    ordinary spacing between two cutaways - 8 to 11 seconds - well alone.
    """
    out: list[tuple[float, float]] = []
    for a, b in sorted(wins):
        if out and a - out[-1][1] <= CAP_RAISE_BRIDGE:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def cta_windows(body: float, attr: str = "") -> list[tuple[float, float]]:
    """
    When the invitation is on screen, in SOURCE seconds of the composite.

    One window per approved cutaway, inset by CTA_BROLL_PAD at both ends so the
    line is not arriving while the cover is still travelling. BROLL_WINDOWS is
    filled by broll_chain, which is why the band is built after it.

    `attr` is the speaker's name when a nameplate is being drawn, and it is here
    because the two share a strip. build_capsule_sequence gives the nameplate
    priority when both want the same frame, so an overlap does not put two cards
    on top of each other - it silently truncates the invitation's ENTRANCE, which
    is worse than not showing it: a button that rises halfway and disappears is a
    glitch, where a button that does not appear on the first cutaway is a choice.
    """
    out: list[tuple[float, float]] = []
    aw = attr_window(body) if attr else None
    # BOTH PLATES, not just the first. The invitation and the nameplate share
    # the same rows, and the second speaker's card is as much a tenant of them
    # as the first - see ATTR2.
    aw2 = attr_window2()
    # THE INSET IS A BEAT, NOT A CLEARANCE, which is why the per-insert moves do
    # not change it. CTA_BROLL_LEAD 0.60 / CTA_BROLL_TAIL 0.45 come from the
    # five-beat argument recorded above them - "the picture lands and holds
    # ALONE" - not from how long the picture spends travelling, and every entry
    # in BROLL_MOVES rides the same BROLL_IN / BROLL_OUT ramp anyway.
    #
    # It is written as a max() so that the day somebody gives a move its own
    # duration, the invitation stops arriving into a still-travelling picture BY
    # CONSTRUCTION rather than by somebody remembering this paragraph.
    lead = max(CTA_BROLL_LEAD, BROLL_IN)
    tail = max(CTA_BROLL_TAIL, BROLL_OUT)
    if CTA_ON_BROLL:
        for a, b in BROLL_WINDOWS:
            a2, b2 = a + lead, b - tail
            for _w in (aw, aw2):
                if _w and a2 < _w[1] and b2 > _w[0]:
                    # Push the invitation past the nameplate if what is left of
                    # the cutaway can still hold it; otherwise this cutaway
                    # carries the picture alone, which is what the beat was for.
                    a2 = max(a2, _w[1] + lead)
                    sys.stderr.write(
                        f"invite: window at +{a:.1f}s starts after the nameplate "
                        f"(+{_w[1]:.1f}s)\n")
            # Enough window for the pill to arrive, be READ, and leave. The old
            # test was 2.0 * CTA_FADE + 0.4, built from a constant belonging to
            # the "line" style; the pill's animation is PILL_TRAVEL and what is
            # left of the window after it is the only part anyone can read.
            if b2 - a2 >= PILL_TRAVEL + PILL_SETTLE_MIN:
                out.append((a2, b2))
            else:
                # SAY SO. This used to drop in silence, and TWO things go with
                # it: the invitation on that cutaway, and the caption RAISE for
                # those frames, because the same list feeds build_caption_
                # sequence's raise_wins. A cutaway quietly missing its button
                # while its captions sit low is a difference between two clips
                # in one set that nothing accounted for.
                sys.stderr.write(
                    f"invite: no room on the cutaway at +{a:.1f}s - "
                    f"{b2 - a2:.2f}s of window against the "
                    f"{PILL_TRAVEL + PILL_SETTLE_MIN:.2f}s the button needs "
                    f"to arrive, be read and leave\n")
    if CTA_IN_BODY:
        out.append((max(0.0, body - CTA_TAIL), body))
    # OVERLAPPING CUTAWAYS MUST NOT MAKE THE BUTTON LEAVE AND COME STRAIGHT BACK.
    # Two inserts that overlap - authored close together, or pushed together by
    # the word re-snap - produce two overlapping invitation windows, and
    # cta_state reads them independently: measured with inserts at 10.0 and 11.0,
    # the pill ran its whole exit to alpha 0.0 at t=13.567 and popped back to 1.0
    # on the very next frame. A hard pop is the one thing this element has been
    # rebuilt three times to avoid.
    #
    # A plain overlap union, NOT merge_raise's bridged one: the captions ride up
    # across a short gap because holding them high is free, but the invitation
    # standing over the speaker between two cutaways is not - it would be up on
    # a frame with a face on it, which is what CTA_ON_BROLL exists to prevent.
    merged: list[tuple[float, float]] = []
    for a, b in sorted(out):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _pill_alpha(u: float) -> float:
    """
    The invitation's opacity at travel progress `u`, on a smoothstep.

    Linear over a fifth of the travel put the first VISIBLE frame at 21% - see
    PILL_FADE. A smoothstep over a longer window starts at 4% and is at full
    strength well before the rise finishes, which is what "arriving" looks like.
    """
    x = min(max(u / PILL_FADE, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def pill_scale(k: int, n: int) -> float:
    """
    PILL_SCALE read at frame `k` of an `n`-frame travel, linearly interpolated.

    k = 0 is the first frame and k = n-1 is the LAST, which returns exactly
    PILL_SCALE[-1] = 1.0 - so the travel always lands on the resting scale
    whatever n is, and the seam with the pulse is free by construction rather
    than by somebody having resampled the tuple correctly by hand.
    """
    if n <= 1:
        return PILL_SCALE[-1]
    u = min(max(k / (n - 1), 0.0), 1.0)
    q = u * (len(PILL_SCALE) - 1)
    i = min(int(q), len(PILL_SCALE) - 2)
    return PILL_SCALE[i] + (PILL_SCALE[i + 1] - PILL_SCALE[i]) * (q - i)


def pill_pulse(k: int, settle: int) -> float:
    """
    The resting button's breath, as a scale multiplier. See PILL_PULSE_AMP.

    `k` is the FRAME index since the entrance landed and `settle` is how many
    frames the hold has in total. Both integers, deliberately: the phase has to
    be identical on every cutaway in a clip or the three buttons breathe out of
    step with each other, and deriving it from float time cannot do that -
    a window's start is a source time carrying an arbitrary sub-frame offset, so
    each cutaway would get its own phase.

    ONE-SIDED, AND IT ONLY EVER GROWS. A button that dips under its own rest
    size reads as pulling back rather than breathing, and 1.0 is the value both
    travel curves converge on, so growing from it is the only way the two seams
    are free. The raised cosine supplies its own easing: zero velocity at the
    trough, maximum at the half swell, zero at the peak.

    IT IS CLOSED BEFORE THE EXIT, over PILL_PULSE_TAPER frames. The first
    version tapered it ACROSS the exit using the exit's own progress as the
    weight, and the exit's scale curve is the entrance reversed - so it climbed
    back through the 1.0264 overshoot while the pulse was still near its peak
    and the two multiplied. Measured, the button reached 1.0435 on the way out,
    20px wider than at rest, having jumped 0.007 of scale on the exit's first
    frame. It read as a pop on the calmest beat in the clip.
    """
    if k <= 0 or settle <= 1:
        return 1.0
    env = max(0.0, min(1.0, (settle - 1 - k) / PILL_PULSE_TAPER))
    return 1.0 + PILL_PULSE_AMP * env * \
        (1 - math.cos(2 * math.pi * k / PILL_PULSE_FRAMES)) / 2


def cta_state(t: float, wins: list[tuple[float, float]]) -> tuple[float, float, float]:
    """
    (alpha, scale, dy) for the invitation at composite time t.

    In "pill" style it SPRINGS: it rises PILL_RISE px from below on the measured
    PILL_SCALE curve, overshoots slightly, settles, holds, and drops back out the
    same way. In "line" style scale is the horizontal snap and dy is 0, which is
    the tracked-type version the pill replaced.
    """
    for a, b in wins:
        if a <= t < b:
            if CTA_STYLE != "pill":
                if t < a + CTA_FADE_IN:
                    k = int((t - a) * FPS)
                    return min(1.0, (k + 1) / CAP_SNAP_FRAMES), \
                        CAP_SNAP_CURVE[min(k, CAP_SNAP_FRAMES - 1)], 0.0
                if t > b - CTA_FADE_OUT:
                    u = min(max((b - t) / CTA_FADE_OUT, 0.0), 1.0)
                    return u ** 3, CAP_SNAP_CURVE[0] + (1 - CAP_SNAP_CURVE[0]) * u ** 3, 0.0
                return 1.0, 1.0, 0.0
            # +EPS BEFORE THE TRUNCATION, AND IT IS A REAL DEFECT NOT A NICETY.
            # t arrives as k/FPS, and (1/30)*30 is 0.9999999999999999 in binary
            # floating point, so a bare int() returned 0 for the SECOND frame as
            # well as the first. Stepped out, the entrance ran
            # 0,0,1,2,3,4,5,5,6,7... - the first frame drawn twice and another
            # pair doubled mid-travel, which is a visible stall at exactly the
            # moment the eye is tracking the move. It has been there since the
            # pill shipped and it is part of what "it's not smooth" was pointing
            # at. Measured after: 0,1,2,3,4,5,6,7,8,9, no repeats.
            kin = int((t - a) * FPS + 1e-6)
            kout = int((b - t) * FPS + 1e-6)
            # IT USED TO BE OPAQUE THROUGHOUT - "a solid object entering from
            # off-frame", and fading a rise was called out as making it read as
            # a dissolve. That was right when everything around it cut hard.
            # Now the picture it lands on cross-dissolves in and out, so an
            # object that snaps to full opacity in one frame is the only hard
            # edge left in the sequence. PILL_FADE covers the FIRST THIRD of the
            # travel only: it is still a solid object arriving, it just is not
            # switched on. The rise is what carries the entrance; this only
            # takes the edge off its first frames.
            if kin < PILL_IN_FRAMES:
                u = kin / max(1, PILL_IN_FRAMES - 1)
                e = 1 - (1 - u) ** 3                     # out_cubic on the rise
                return _pill_alpha(u), \
                    pill_scale(kin, PILL_IN_FRAMES), \
                    PILL_RISE * (1 - e)
            if kout < PILL_OUT_FRAMES:
                u = kout / max(1, PILL_OUT_FRAMES - 1)
                # THE EXIT IS THE ENTRANCE PLAYED BACKWARDS, and it was not.
                # `u` counts DOWN from 1 to 0 across the departure, so `u ** 3`
                # - read as a function of time - is an ease-OUT: measured, the
                # lockup's first departing frame moved 113.1px and its last
                # moved 0.5px. The button leapt off the frame and then crawled,
                # which is the opposite of "it's gonna come out and smooth out".
                # `1 - (1 - u) ** 3` mirrors the arrival exactly: 0.1px on the
                # first frame, accelerating to 75.8px on the last. Together with
                # 10 -> 15 frames the peak per-frame travel falls 113.1 -> 75.8.
                e = 1 - (1 - u) ** 3
                return _pill_alpha(u), \
                    pill_scale(kout, PILL_OUT_FRAMES), \
                    PILL_RISE * (1 - e)
            # THE PULSE'S CLOCK IS AN INTEGER FRAME COUNT FROM THE FRAME THE
            # TRAVEL LANDED ON - see pill_pulse for why it is not float time.
            settle = int(round((b - a) * FPS)) - PILL_IN_FRAMES - PILL_OUT_FRAMES
            return 1.0, pill_pulse(kin - PILL_IN_FRAMES, settle), 0.0
    return 0.0, 1.0, 0.0


@functools.lru_cache(maxsize=1)
def _pill_metrics() -> tuple:
    """
    Everything the invitation's geometry is derived from, measured once.

    Returns (font, addr_font, verb_advance, addr_advance, addr_bbox, pill_w,
    pill_h, lockup_h, rest_y). It is a function rather than a block of module
    constants because two of the numbers depend on the FONTS - the address's
    ink height sets the lockup's height, and the lockup's height sets where it
    has to rest to clear the platform chrome - so a hand-set constant goes
    stale the moment CTA_ADDR_SIZE or CTA_HOST changes, which is exactly how
    the address came to be drawn 18px under CAP_SAFE_BOTTOM.
    """
    f = _font(F_CAP, PILL_TEXT_PX)
    f_a = _font(F_UI, CTA_ADDR_SIZE)
    d0 = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = tracked_width(d0, CTA_VERB, f, 0.4)
    wa = tracked_width(d0, CTA_HOST.upper(), f_a, CTA_ADDR_TRACK)
    abox = f_a.getbbox(CTA_HOST.upper())
    pw, ph = int(tw + PILL_PAD_X * 2), PILL_H
    ah = abox[3] - abox[1] + 2 * CTA_ADDR_STROKE
    lock_h = int(2 * PILL_SHADOW_PAD + ph + PILL_ADDR_GAP + ah)
    # The lockup's INK ends PILL_SHADOW_PAD above its own bottom edge, so the
    # ink's last row lands at rest_y + lock_h - PILL_SHADOW_PAD in band
    # coordinates. Put that PILL_SAFE_MARGIN clear of CAP_SAFE_BOTTOM.
    rest_y = (CAP_SAFE_BOTTOM - PILL_SAFE_MARGIN) - CTA_BAND_Y - lock_h + PILL_SHADOW_PAD
    if rest_y < 0:
        raise ValueError(f"the invitation lockup ({lock_h}px) does not fit above "
                         f"CAP_SAFE_BOTTOM {CAP_SAFE_BOTTOM} in a band starting "
                         f"at {CTA_BAND_Y}")
    # The entrance starts PILL_RISE below the rest position and the band is the
    # canvas it is drawn on, so a band shorter than that CLIPS the travel and
    # the pill appears rather than arrives - the exact defect SKILL.md records
    # being fixed once by taking CTA_BAND_H to 630. Assert it instead of
    # trusting that the constants still agree.
    if rest_y + PILL_RISE + lock_h > CTA_BAND_H:
        raise ValueError(
            f"CTA_BAND_H {CTA_BAND_H} clips the pill's entrance: it needs "
            f"{rest_y:.0f} + PILL_RISE {PILL_RISE:.0f} + lockup {lock_h} = "
            f"{rest_y + PILL_RISE + lock_h:.0f}px")
    return f, f_a, tw, wa, abox, pw, ph, lock_h, rest_y


@functools.lru_cache(maxsize=8)
def pill_ink_bottom(alpha_floor: int = 60, sx: float = 1.0) -> int:
    """
    The last row of the resting invitation that carries readable ink, in BAND
    coordinates. preflight's SAFE check asks this instead of rebuilding the
    lockup out of constants - see the note where it is called.

    `alpha_floor` 60 deliberately ignores the outermost tail of the drop
    shadow, which is a gradient nobody reads and which the safe line is not
    about, while including the address's stroke, which is what the hand-built
    sum used to miss.

    `sx` IS HERE BECAUSE THE BUTTON IS NOT ONE SIZE ANY MORE. It rests at 1.0,
    overshoots to max(PILL_SCALE) on the way in, and BREATHES to
    1 + PILL_PULSE_AMP while it sits - and the plate is centre-anchored, so
    every one of those pushes the bottom row further down. A checker that only
    ever asks about the rest state is exactly the shape of bug SKILL.md records
    for this element already: "Two owners of one quantity, and the one that
    could not see the ink was the one doing the checking."
    """
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cta.png"
        render_cta_png(p, 1.0, sx, 0.0)
        a = np.array(Image.open(p).convert("RGBA"))
    rows = np.where((a[..., 3] > alpha_floor).any(axis=1))[0]
    return int(rows.max()) if len(rows) else 0


@functools.lru_cache(maxsize=8)
def attr_ink_bottom(name: str, role: str, alpha_floor: int = 60) -> int:
    """
    The nameplate's last readable row, in BAND coordinates, by rendering it.

    attr_plate_rows() gives the PLATE; this gives what the alpha actually
    reaches, shadow included down to `alpha_floor`. preflight asks this one for
    the same reason it asks pill_ink_bottom rather than rebuilding a sum out of
    constants - the checker and the renderer must be the same code.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "attr.png"
        render_attr_band_png(p, 1.0, name, role)
        a = np.array(Image.open(p).convert("RGBA"))
    rows = np.where((a[..., 3] > alpha_floor).any(axis=1))[0]
    return int(rows.max()) if len(rows) else 0


def render_cta_png(path: Path, alpha: float, sx: float, dy: float = 0.0,
                   colours: dict | None = None) -> None:
    """
    The invitation. A white pill with slate type, or the tracked line it replaced.

    THE PILL IS BONE, NOT PURE WHITE, and slate type on it - the same pairing the
    hook card uses, so the two read as the same object arriving twice rather than
    as a card and a button from different systems. It is drawn at rest and then
    scaled and lifted, so the corner radius scales with it and the spring does not
    deform the type independently of its box.
    """
    img = Image.new("RGBA", (W, CTA_BAND_H), (0, 0, 0, 0))
    if alpha <= 0.004:
        img.save(path)
        return
    if CTA_STYLE != "pill":
        return _render_cta_line(img, path, alpha, sx, colours)

    # THE BUTTON AND ITS ADDRESS ARE ONE OBJECT, DRAWN ON ONE PLATE. They used
    # to be two: the pill was built on its own canvas, scaled, and composited,
    # and then the address was drawn straight onto the band AFTERWARDS at a
    # fixed size. Four of the five things the owner could see came out of that
    # one decision, and they were found by rendering this function frame by
    # frame through the entrance rather than by reading it:
    #
    #   THE ADDRESS DID NOT SCALE. It measured 22px of glyph on EVERY frame,
    #   including the ones where the pill was at PILL_SCALE[0] = 0.79. On frame
    #   0 the button was 364px wide and the URL under it was 405px - the
    #   subordinate line WIDER than the button, at full weight, for two frames
    #   before it equalised. That is the "two vocabularies in one clip" failure
    #   SKILL.md already recorded for type, happening inside a single element.
    #
    #   THE PILL GREW DOWNWARD ONLY. `x` centred the scaled plate but `y` was
    #   its TOP-LEFT, so the 1.03 scale overshoot landed as +0.4px above and
    #   +4.9px below and the pill's own centre moved 139.6 -> 137.0 between two
    #   frames on which `dy` was 0 both times. Anchoring the centre puts the
    #   overshoot at +-2.3px and halves the settle.
    #
    #   THE SHADOW WAS CLIPPED TO A RECTANGLE AROUND A CAPSULE. GaussianBlur(10)
    #   reaches 24px before its alpha hits zero, and the canvas gave it 12px
    #   left, 11 right, 16 above and 7 below - so it was cut at alpha 9/255 on
    #   top, 17 left, 21 right and 46 BELOW, and 46/255 terminating in one pixel
    #   is a visible edge: measured on the delivered file, +20.5 luma across a
    #   single row at the plate's bottom, +13.9 averaged over the whole 486px
    #   cut. A hard rectangular halo around a round button is exactly the kind
    #   of thing that reads as "not symmetrical" without being nameable.
    #   PILL_SHADOW_PAD is 30 - larger than the blur's own reach - so the
    #   gradient ends because it has faded out, not because it ran out of
    #   canvas, and the margin is EQUAL on all four sides.
    #
    #   THE THREE CENTRES DISAGREED by a pixel: the frame's 539.5, the plate's
    #   540.0 (PIL's rounded_rectangle is inclusive of both endpoints, so a rect
    #   from 12 to 12+pw is pw+1 wide inside a canvas of pw+24) and the
    #   address's 539.0. The lockup is drawn on a full-frame-width canvas now,
    #   so everything on it is centred on one number and the composite cannot
    #   introduce a second.
    f, f_a, tw, wa, abox, pw, ph, lock_h, rest_y = _pill_metrics()
    addr = CTA_HOST.upper()
    plate = Image.new("RGBA", (W, lock_h), (0, 0, 0, 0))
    px0, py0 = (W - pw) / 2.0, float(PILL_SHADOW_PAD)
    sh = Image.new("RGBA", plate.size, (0, 0, 0, 0))
    # -1 ON BOTH FAR EDGES: PIL's rounded_rectangle is INCLUSIVE of x1 and y1, so
    # [px0, py0, px0 + pw, py0 + ph] draws pw+1 x ph+1 pixels. That one extra
    # column is why the plate's centre measured 540.00 against the frame's 539.5
    # for as long as this element has existed.
    ImageDraw.Draw(sh).rounded_rectangle([px0, py0 + 4, px0 + pw - 1, py0 + 4 + ph - 1],
                                         radius=ph / 2, fill=(4, 7, 11, 120))
    plate.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    dp = ImageDraw.Draw(plate)
    dp.rounded_rectangle([px0, py0, px0 + pw - 1, py0 + ph - 1], radius=ph / 2,
                         fill=BONE + (255,))
    # THE LABEL IS CENTRED ON ITS INK, NOT ON THE FONT'S NOMINAL SIZE, and that
    # is the whole of "the pill is not symmetrical" (the owner, 2026-08-25).
    #
    # It used to draw at (ph - f.size)/2 - 2, which centres the POINT SIZE (62)
    # while PIL draws from the ASCENDER line - and the two are different boxes.
    # Measured on the delivered 08.25 clip by rendering this function directly:
    # metrics ascent 61 / descent 15, getbbox("Sign up free") = (0, 15, 346, 74),
    # so the ink ran 58px down from a draw origin of 54.0 and landed at plate
    # y69..128 inside an interior of y12..162. That is 58px of air above the
    # label and 35px below it - a 23px asymmetry in a 150px pill, 15% of its
    # height, and it reads as the type sinking in the button.
    #
    # Four placements were rendered side by side and looked at:
    #     current  (ph - size)/2 - 2      top 58  bottom 35   ASYM +23
    #     INK BOX  centre bbox[1]..[3]    top 46  bottom 47   ASYM  -1   <- ships
    #     cap band captop..baseline       top 53  bottom 40   ASYM +13
    #     optical  cap + a quarter desc   top 43  bottom 50   ASYM  -7
    # The cap-band version is the usual typographic answer and it is WRONG here,
    # because "Sign up free" carries two descenders (g, p) and one of them sits
    # under the optical centre of the word: centring the caps leaves the word
    # looking low anyway, which is the defect being fixed. The ink box is what
    # the eye reads as the object.
    #
    # THE HORIZONTAL WAS ALREADY RIGHT and was not touched: tracked_width uses
    # len(text) - 1 so it carries no trailing tracking, and the plate measures
    # 58px / 59px of air either side of the ink, against 50/52 on the owner's
    # own reference button (youtube.com/shorts/hYahU_Cqwp8, measured 2026-08-25
    # at f850-870: a 546px button, H-ASYM -2px). Both are inside a pixel of
    # centred; do not "fix" it by switching to the ink box, which would put the
    # side bearings of S and e in charge of where the word sits.
    ink = f.getbbox(CTA_VERB)
    draw_tracked(dp, (px0 + (pw - tw) / 2, py0 + (ph - (ink[3] - ink[1])) / 2 - ink[1]),
                 CTA_VERB, f, SLATE + (255,), 0.4)

    # THE ADDRESS UNDER IT. Owner: "it should be sign up for free
    # quasarmarkets.com" - the pill is the invitation and the line beneath is
    # where it goes. Inside the pill it would crowd a 150px button; under it, it
    # reads the way the closing card reads. Drawn onto the SAME plate, so it
    # arrives as one object rather than travelling beside one.
    #
    # Drawn at 255, not 245. It was 4% transparent while the button beside it
    # was opaque, which is a difference nobody chose - the two are one lockup.
    draw_tracked(dp, ((W - wa) / 2, py0 + ph + PILL_ADDR_GAP - abox[1]),
                 addr, f_a, BONE + (255,), CTA_ADDR_TRACK,
                 stroke=CTA_ADDR_STROKE, stroke_fill=(7, 10, 14, 220))

    # 0.0005, NOT 0.002. The pulse's largest per-frame step is 0.00208 and its
    # trough is flat, so at a 0.002 threshold the plate spent about a fifth of
    # every breath NOT resampled - and an un-resampled plate is marginally
    # crisper than a LANCZOS'd one, so the button's sharpness flickered once per
    # cycle. Below 0.0005 the resize is a no-op anyway.
    if abs(sx - 1.0) > 0.0005:
        nw, nh = max(2, int(round(plate.width * sx))), max(2, int(round(plate.height * sx)))
        plate = plate.resize((nw, nh), Image.LANCZOS)
    if alpha < 0.999:
        plate.putalpha(plate.getchannel("A").point(lambda v: int(v * alpha)))
    # ANCHORED ON THE CENTRE IN BOTH AXES. `y` used to be the plate's top edge
    # while `x` was its centre, so the scale overshoot only ever pushed the
    # lockup DOWN. Both are centres now, and both round rather than floor - a
    # floor on a width whose parity flips with the scale made the pill's centre
    # jitter 539.50 / 540.00 / 540.00 / 539.50 ... across the entrance.
    cx, cy = W / 2.0, rest_y + dy + lock_h / 2.0
    img.alpha_composite(plate, (int(round(cx - plate.width / 2)),
                                int(round(cy - plate.height / 2))))
    img.save(path)


def _render_cta_line(img: Image.Image, path: Path, alpha: float, sx: float,
                     colours: dict | None) -> None:
    """The tracked verb-over-address line, kept behind "cta_style": "line"."""
    base, stroke = BONE, (7, 10, 14)
    layer = Image.new("RGBA", (W, CTA_BAND_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f_v, f_a = _font(F_UI, CTA_VERB_SIZE), _font(F_UI, CTA_ADDR_SIZE)
    verb, addr = CTA_VERB, CTA_HOST.upper()
    wv = tracked_width(d, verb, f_v, CTA_LINE_TRACK)
    wa = tracked_width(d, addr, f_a, CTA_ADDR_TRACK)
    gap = 8
    y = (CTA_BAND_H_REST - (f_v.size + gap + CTA_RULE_H + gap + f_a.size)) / 2
    draw_tracked(d, ((W - wv) / 2, y), verb, f_v, base + (255,),
                 CTA_LINE_TRACK, stroke=4, stroke_fill=stroke + (215,))
    ry = y + f_v.size + gap
    d.rectangle([(W - CTA_RULE_W) / 2, ry, (W + CTA_RULE_W) / 2, ry + CTA_RULE_H],
                fill=ACCENT + (235,))
    draw_tracked(d, ((W - wa) / 2, ry + CTA_RULE_H + gap), addr, f_a,
                 base + (245,), CTA_ADDR_TRACK, stroke=3,
                 stroke_fill=stroke + (215,))
    if alpha < 0.999:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(_snap_x(layer, sx), (0, 0))
    img.save(path)


# THE CLOSING ADDRESS IS GONE, AND IT COULD NEVER DRAW.
#
# The band was documented as having three tenants - the nameplate, the
# invitation, and a tracked INVEST.QUASARMARKETS.COM line for the closing beat -
# picked between with `if ba > 0.004 ... elif ia > 0.004 ... else capsule`.
#
# The `else` was unreachable in every shipping configuration. capsule_state
# returns zero unless CTA_IN_BODY, CTA_IN_BODY is `not endcard`, and the end card
# defaults on - so with a card there is no closing beat in the body at all. And
# WITHOUT a card, cta_windows appends its own (body - CTA_TAIL, body) window, so
# the INVITATION takes the closing beat and the `elif` fires first. Either way
# the address never reached a frame.
#
# The pill owns the closing beat: it carries the same address under a button, so
# nothing is lost. Deleted rather than left as a fourth thing to reason about,
# and the docstring below now says two tenants because there are two.

def build_capsule_sequence(seqdir: Path, dur: float,
                           colours: dict | None = None,
                           cta: bool = True,
                           attr: tuple[str, str] | None = None,
                           wins: list[tuple[float, float]] | None = None) -> int:
    """
    The lower band: the NAMEPLATE early, the INVITATION under each cutaway, and
    the ADDRESS at the end.

    One rectangle with three tenants that are never on screen together, which is
    why none of them costs anything - this sequence was already being built and
    already had its overlay input. Same hard-link trick as the captions: only
    distinct states are drawn, so a four-second hold is one PNG hard-linked a
    hundred and twenty times.

    ORDER MATTERS: the invitation's windows come from BROLL_WINDOWS, which
    broll_chain fills, so this is built AFTER it.
    """
    # THREE TENANTS, not two, and they are never on screen together: the
    # NAMEPLATE early, the INVITATION under each cutaway, and the closing
    # ADDRESS. (This note used to say the nameplate was "gone from this band -
    # it is set into the hook card now", and pointed at ATTR_NAME_PX, a symbol
    # that no longer exists. The credential came back off the card on
    # 2026-08-25; see the rung ladder in build_hook_sequence.)
    aname, arole = attr or ("", "")
    if aname:
        w = attr_window(dur)
        sys.stderr.write(
            f"name: {aname!r} on a bone card, +{w[0]:.1f}s to +{w[1]:.1f}s\n"
            if w else
            f"name: NO ROOM for {aname!r} on this clip - nobody is named\n")
        # ONCE PER CLIP, from the one place that runs once per clip.
        if w and BROLL_WINDOWS:
            first = min(x[0] for x in BROLL_WINDOWS)
            if w[1] > first - ATTR_BAND_GAP + 1e-6:
                sys.stderr.write(
                    f"note: the first cutaway at +{first:.1f}s leaves no room to "
                    f"finish the nameplate before it; they overlap for "
                    f"{w[1] - (first - ATTR_BAND_GAP):.2f}s\n")
    # HANDED IN, NOT RECOMPUTED. It was a bare cta_windows(dur) here while
    # render() called cta_windows(dur, attr=...) for the captions - two callers
    # deriving one quantity, which is the failure this file keeps recording. On
    # a clip whose first cutaway lands inside the nameplate's window they
    # disagreed: render() dropped that window, this one kept it, and the
    # nameplate outranks the invitation in the key below - so the button's whole
    # entrance was suppressed and it appeared at full opacity and resting scale
    # on the first frame after the card left. Taking the list as an argument
    # makes the two the same object rather than two answers that ought to agree.
    if wins is None:
        wins = cta_windows(dur, attr=aname) if cta else []
    elif not cta:
        wins = []
    if wins:
        why = []
        if CTA_ON_BROLL and BROLL_WINDOWS:
            why.append(f"{len([w for w in wins if w[1] < dur - 0.01])} cutaway(s)")
        if CTA_IN_BODY:
            why.append("the closing beat")
        sys.stderr.write(f"invite: {CTA_VERB!r} over the address, under "
                         f"{' and '.join(why)}\n")
    if seqdir.exists():
        shutil.rmtree(seqdir)
    seqdir.mkdir(parents=True)
    uniq = seqdir / "u"
    uniq.mkdir()

    made: dict[tuple, Path] = {}
    frames = int(round(dur * FPS))
    for f in range(frames):
        t = f / FPS
        ba = attr_band_state(t, dur, bool(aname))
        ba2 = attr_band_state2(t)
        ia, isx, idy = cta_state(t, wins)
        if ba > 0.004:
            key = ("b", 0, int(round(ba * 60)))
        elif ba2 > 0.004:
            key = ("b", 1, int(round(ba2 * 60)))
        elif ia > 0.004:
            # x1000 ON THE SCALE, NOT x200. At x200 one quantisation step is
            # 0.005 of scale - 2.3px of the button's width - and the pulse's
            # whole amplitude is 0.024, so the breath would have climbed a
            # five-step staircase instead of moving. x1000 gives it 24 steps at
            # 0.46px each, which is under the resampling noise of the LANCZOS
            # resize that draws it. The cost is bounded: distinct states are
            # 14 + 14 travel frames plus the pulse's own cycle, and the pulse
            # REPEATS, so it is tens of PNGs for the whole clip however many
            # cutaways there are.
            key = ("i", int(round(ia * 60)), int(round(isx * 1000)),
                   int(round(idy)))
        else:
            key = ("blank",)
        src = made.get(key)
        if src is None:
            src = uniq / f"c{len(made):04d}.png"
            if key[0] == "b":
                _n, _r = ((aname, arole) if key[1] == 0
                          else (ATTR2[0][2], ATTR2[0][3]))
                render_attr_band_png(src, key[2] / 60, _n, _r, colours)
            elif key[0] == "i":
                render_cta_png(src, key[1] / 60, key[2] / 1000.0,
                               float(key[3]), colours)
            else:
                Image.new("RGBA", (W, CTA_BAND_H), (0, 0, 0, 0)).save(src)
            made[key] = src
        dst = seqdir / f"{f:05d}.png"
        try:
            # os.link, not Path.hardlink_to: the latter is 3.10+, and which
            # python3 wins on PATH here is not stable (macOS ships 3.9).
            os.link(src, dst)
        except OSError:
            dst.write_bytes(src.read_bytes())
    return frames


# build_mask() is gone with the backdrop. It painted a rounded-rectangle alpha
# channel so the inset panel had soft corners over the blurred background. Once
# PANEL_R went to 0 it was a solid white rectangle the size of the panel, and now
# that the panel is the whole frame it is a solid white rectangle the size of the
# frame: an extra PNG, an extra ffmpeg input and an alphamerge per frame, all to
# multiply the picture by one.


# ------------------------------------------------------- retention edit ----
# HOW THE BODY IS CUT. "select" is one pass with no split; "trim" is the older
# N-trims-and-concat. Both are kept because this is the most timing-critical
# function in the pipeline - out_dur is derived from what it produces and every
# overlay in the clip is authored against that - so a rollback has to be one
# key in project.json rather than a code change under pressure.
#
# THEY ARE TWO IMPLEMENTATIONS OF ONE TRANSFORMATION, NOT TWO DEFINITIONS OF ONE
# QUANTITY, which is the trap this file keeps recording. The kept-span list is
# computed once and shared; only the filter that expresses it differs.
CUT_MODE = str(CFG.get("cut_mode") or "select").lower()


def keep_spans(rem: list[tuple[float, float]], dur: float
               ) -> list[tuple[float, float]]:
    """The spans that survive the removals. One owner, both cut modes."""
    keep: list[tuple[float, float]] = []
    t = 0.0
    for s, e in rem:
        if s > t:
            keep.append((t, s))
        t = e
    if t < dur:
        keep.append((t, dur))
    return keep


def cut_graph(rem: list[tuple[float, float]], dur: float,
              mute: list[tuple[float, float]] | None = None
              ) -> tuple[str, str, str]:
    """
    Filter graph that rebuilds the clip with the removal windows dropped.

    The kept spans are concatenated, picture and sound together, so each join is
    a jump cut with speech running straight through it. The rest of the pipeline
    then sees an ordinary, slightly shorter clip.

    ONE `select` REPLACED N TRIMS AND A CONCAT, and it is a memory fix rather
    than a tidy-up. The old shape emitted one `[0:v]trim=A:B` per kept span off a
    SINGLE input - 17 to 40 of them on a real clip - and a filter input consumed
    more than once forces ffmpeg to insert a `split`, which must buffer every
    decoded frame until the LAST branch has taken it. The working set is
    therefore the whole span decoded at source resolution, independent of how
    many cuts there are:

        span x fps x (w x h x 1.5)      58s x 30 x 1920x1080x1.5 = 5.4 GB

    Measured on 2026-08-28, a `duo` clip with a 58.4s body: RSS 19.0 GB, swap
    driven from its 6 GB base to 97.4 GB used with 886 MB free, and 0.21 seconds
    of CPU in 29 seconds of wall clock. It fails as a HANG, not an error. A
    whole-set build stalled on its third clip for the same reason.

    `select` has ONE consumer of the input, so there is no split and nothing to
    buffer: frames stream through and are either passed or dropped.

    `gte(t,s)*lt(t,e)`, NOT `between(t,s,e)`. `between` is inclusive at BOTH
    ends, so it keeps the frame sitting exactly on a span's end - which `trim`
    excludes - and that is a one-frame difference per span, up to 40 frames of
    duplicated content on a real clip. The half-open form is exactly trim's
    semantics and is the same idiom punch_enable already uses.

    `setpts=N/FRAME_RATE/TB` renumbers the surviving frames consecutively, which
    is what closes the gaps; `FRAME_RATE` and `SR` are ffmpeg's own variables, so
    neither rate is hardcoded here.

    THE MUTE GETS SIMPLER AND THE OLD FOOTGUN GOES WITH IT. Mute windows are
    authored in SPAN time, so `volume` has to run BEFORE the select, while `t` is
    still span time - after it, `t` is output time and the windows would land
    somewhere else. With one audio branch there is nothing to asplit, which
    retires this documented trap: a filter OUTPUT label may only be consumed
    once, and feeding one `[amuted]` into every atrim looked right and was
    silently wrong - ffmpeg 8 rebinds the second and later references to the raw
    input, so the mute survived only in the first kept span. Measured on a
    controlled test, a mute inside the first atrim came out at -99 dB and the
    identical filter inside the second came out at -21.1 dB, i.e. untouched. A
    shipped clip escaped only because its one mute happened to land in span zero.
    """
    keep = keep_spans(rem, dur)

    def _mute_chain() -> str:
        if not mute:
            return ""
        spans = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in mute)
        return f"volume=0:enable='{spans}',"

    # PASS THROUGH ONLY WHEN THERE IS GENUINELY NOTHING TO CUT. The test used to
    # be `len(keep) < 2`, which was safe for as long as a removal could never
    # start at 0.0 - find_removals skipped `s <= 0` and collapse_silence required
    # `st > 0`. The leading-silence clamp of 2026-08-24 removed that guarantee,
    # and a head-anchored removal that is the ONLY removal produces exactly one
    # kept span: `keep = [(X, dur)]`. The old test then returned the passthrough
    # graph and the body shipped its FULL length while `out_dur`, the caption,
    # hook and CTA sequences, the .srt and the out-fade were all authored X
    # seconds shorter. Nothing warned; the log said it had cut.
    #
    # preflight structurally cannot catch this - it never calls cut_graph - which
    # is why the assertion in render() exists as well.
    if not rem or not keep:
        if not mute:
            return "", "0:v", "0:a"
        return f"[0:a]{_mute_chain().rstrip(',')}[am0];", "0:v", "am0"

    if CUT_MODE == "trim":
        return _cut_graph_trim(keep, mute)

    sel = "+".join(f"gte(t,{a:.3f})*lt(t,{b:.3f})" for a, b in keep)
    return (f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB[cv];"
            f"[0:a]{_mute_chain()}aselect='{sel}',asetpts=N/SR/TB[ca];"), "cv", "ca"


def _cut_graph_trim(keep: list[tuple[float, float]],
                    mute: list[tuple[float, float]] | None) -> tuple[str, str, str]:
    """The pre-2026-08-28 N-trims-and-concat body. Kept for rollback only.

    See cut_graph for why it was replaced and what it costs in memory. The
    asplit here is what the select path retires: a filter OUTPUT label may only
    be consumed once, so the muted stream has to be split once per kept span.
    """
    def _mute_pre(n: int) -> tuple[str, list[str]]:
        if not mute:
            return "", ["0:a"] * n
        spans = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in mute)
        if n == 1:
            return f"[0:a]volume=0:enable='{spans}'[am0];", ["am0"]
        outs = "".join(f"[am{k}]" for k in range(n))
        return (f"[0:a]volume=0:enable='{spans}'[amx];"
                f"[amx]asplit={n}{outs};", [f"am{k}" for k in range(n)])

    pre, labs = _mute_pre(len(keep))
    parts, labels = [pre], []
    for k, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[kv{k}];")
        parts.append(f"[{labs[k]}]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[ka{k}];")
        labels += [f"[kv{k}]", f"[ka{k}]"]
    if len(keep) == 1:
        return "".join(parts), "kv0", "ka0"
    parts.append("".join(labels) + f"concat=n={len(keep)}:v=1:a=1[cv][ca];")
    return "".join(parts), "cv", "ca"


# what each render mode needs the source to actually be doing
# What each render mode needs the source to actually be doing.
# "gallery" is a wall of faces with no shared screen and no centre divider. Only
# `head` can use one, and only with an explicit head_crop picking a face out of
# it - `share` and `duo` applied to a gallery crop a rail and a divider that are
# not there. A gallery stretch was mislabelled "share" on one master and would
# have shipped eleven seconds of the wrong picture.
# ---------------------------------------------------------- THE TEMPLATES ----
# THREE, AND ONLY THREE. The owner, 2026-08-28:
#
#   "There's only going to be three templates. First is a single person just
#    talking, plus b-roll. Second is a conversation between two people, and it
#    switches based on who's talking - the whole screen switches. Third is that
#    same idea but with the screen share at the bottom. And there's no other way
#    to do it."
#
# | template | mode                  | what is on screen                        |
# | -------- | --------------------- | ---------------------------------------- |
# | 1        | `head`                | one person, full frame                   |
# | 2        | `conversation`        | one person full frame, CUTTING to whoever |
# |          |                       | is talking                               |
# | 3        | `conversation_share`  | whoever is talking on top, the shared     |
# |          |                       | screen below                             |
#
# TWO PEOPLE ARE NEVER ON SCREEN AT ONCE. That is the whole point of the change
# and it is an editorial judgement, not a technical one:
#
#   "When you have two people on the same clip it makes it not seem very
#    professional, because then people are just sitting there waiting. It should
#    always be one person talking at one time. You're losing real estate on the
#    phone."
#
# He is right about the real estate, and the pipeline had already measured him
# right about the rest without drawing the conclusion: a fixed crop on a two-up
# scores 0.90x on whether the face on screen is the one talking - BELOW 1.0,
# which is the signature of showing the listener - and `duo`'s lower band
# structurally cannot keep a mouth clear of the platform chrome, because only
# 463px of its 953px band sits above the line.
#
# `share` survives as template 3 with ONE speaker, which is the degenerate case
# rather than a fourth template - a solo presenter has nobody to cut to.
#
# `duo` and `duo_share` are RETIRED. They are the two modes that put two people
# on one screen, and they are refused rather than deleted so that a re-cut of an
# archived show fails loudly with a pointer instead of a KeyError.
TEMPLATES = ("head", "conversation", "conversation_share")
MODE_ALIASES = {
    # head_follow was this mode's name for the few hours between building it and
    # the owner naming the templates. Kept so slates authored in that window,
    # and the verification set, still resolve.
    "head_follow": "conversation",
}
RETIRED_MODES = {
    "duo": "conversation",
    "duo_share": "conversation_share",
}


def canonical_mode(mode: str, allow_legacy: bool = False) -> str:
    """The slate's mode name, resolved to one of the three templates."""
    m = (mode or "head").strip()
    m = MODE_ALIASES.get(m, m)
    if m in RETIRED_MODES and not allow_legacy:
        raise SystemExit(
            f"\nmode {mode!r} is retired: it puts TWO PEOPLE on screen at once, "
            f"and the house\nrule since 2026-08-28 is that only the person "
            f"talking is on screen.\n\n"
            f"  use {RETIRED_MODES[m]!r} instead - it cuts the WHOLE frame to "
            f"whoever is speaking.\n"
            f"  it needs \"follow_tiles\" (who is where) and "
            f"{'\"follow_crops\"' if m == 'duo' else '\"follow_pips\"'} "
            f"(one crop each).\n\n"
            f"Set \"allow_legacy_duo\": true on the clip only to re-cut an "
            f"archived show as it shipped.\n")
    return m


MODE_NEEDS = {"head": {"head", "two_up", "gallery"}, "duo": {"two_up"},
              "share": {"share"}, "duo_share": {"share"},
              # conversation is a HEAD clip whose crop moves between two
              # people, so it needs the layout that has two people in it.
              "conversation": {"two_up"},
              # conversation_share is a SHARE clip whose camera tile moves.
              "conversation_share": {"share"}}


# A share panel is packed from two pieces that must ADD UP to PANEL_H exactly.
# How the panel is split between the speaker and the shared screen.
#
# The old rule was one-sided: give the app its natural height at full width and
# hand every remaining pixel to the face. That was defensible at a 1560 panel and
# is wrong at 1920, because the whole 360px the panel gained went to the face.
# Measured on a real slide clip (a 1385x872 crop of a PowerPoint deck): the app's
# share of the frame FELL from 44% to 35% when the panel grew, and the face went
# to 64% - two thirds of a vertical video spent on an empty room behind a speaker,
# with the thing the clip exists for squeezed underneath.
#
# So the app now has a FLOOR on its share of the panel, and the face takes what is
# left. Nothing about the app's own size changes - a 16:9 slide at full width is
# 608px tall and no packing can make it taller without cutting words off the ends
# of the bullets. What changes is that the surplus stops inflating the face.
#
# Do not read the floor as "the app is drawn this big". It is the size of the BAND;
# the app is fitted inside it and the remainder is filled by extending the app's
# own edge pixels (see fit_chain), which on a solid-coloured slide is invisible and
# on a chart continues its own background.
APP_MIN_FRAC = _num("app_min_frac", 0.52)
# ...and the most of a band that may be extended edge rather than real app.
PAD_MAX_FRAC = 0.30
# ...and the most of a camera tile's HEIGHT the app floor may cost. A meeting tile
# burns its name badge into the bottom strip, so a squeezed face band cuts the
# name in half - which the skill's own rule calls out as reading like a mistake.
TILE_TRIM_MAX = 0.12

# The face band's floor and ceiling, both as the same fraction of the panel they
# were tuned at when it was 1560 tall (380/1560 = 24%, 960/1560 = 62%). They are
# not independent taste values, so scale them together with PANEL_H rather than
# nudging one.
#
# Note what the ceiling does NOT fix: how sharp the face is. The band is always
# PANEL_W wide, so a 228px-wide meeting tile is a 4.74x blow-up whatever height the
# band has - measured at 1226, 908 and 700, identical every time. The ceiling is a
# COMPOSITION control, not a resolution one. If the face is soft, the tile is small
# and nothing in the packer can help.
FACE_MIN, FACE_MAX = 470, 1300


def pack_share(sw: int, sh: int, fh: int | None,
               tile: tuple[int, int] | None = None,
               tile_w: int | None = None) -> tuple[int, int]:
    """
    Split PANEL_H between the face band and the shared screen's BAND.

    Returns (face_h, band_h), which always satisfy face_h + SPLIT_GAP + band_h ==
    PANEL_H. band_h is the space the app gets, not the height the app is drawn at:
    fit_chain scales the app to fit and extends its edges into whatever is spare.

    With fh=None the app gets whichever is larger of its natural height at full
    width and APP_MIN_FRAC of the panel, and the face takes the rest. An explicit
    fh wins outright - that is the per-clip override for a shot where the speaker
    matters more than the screen.

    `tile` is the camera crop (w, h), and it is not optional in spirit. A camera
    tile has ONE band height that needs no cropping at all - `tile_w * h / w` -
    and any shorter band cuts a strip off it. On a meeting tile the bottom strip
    is usually the burned-in name badge, and a half-cut name reads as a mistake
    rather than as a crop. So the band is PULLED toward the tile's own height,
    to within TILE_TRIM_MAX of it - but the pull loses two ties, and this used
    to claim otherwise: the app's natural height caps the band from below, and
    the PAD_MAX_FRAC budget (no band more than 30% flat fill) lifts it from
    above. Measured: a 280x132 meeting tile under a 16:9 slide lands at 969,
    1.9x the tile's own 509, and keeps 52% of its width. When the tile and the
    app cannot both be had, the packer does not guess: preflight's PACK line
    prints the real trim and blow-up, and `face_h` on the clip decides. The
    08.21.26 reference clip was authored exactly that way - face_h 1067, the
    tile's own height, with the app at 44% of the panel and no fill at all.
    """
    natural = int(round(PANEL_W * sh / sw))
    authored = fh
    if fh is None:
        band = max(natural, int(PANEL_H * APP_MIN_FRAC))
        # ...but do not inflate a band so far past the app that most of it is
        # smear. An ultrawide terminal crop is only 338px tall at full width, and
        # giving it 998 would be two thirds extended edge. The floor is there to
        # stop the face eating the frame, not to invent screen that is not there.
        band = min(band, int(natural / (1.0 - PAD_MAX_FRAC)))
        fh = max(FACE_MIN, min(FACE_MAX, PANEL_H - SPLIT_GAP - band))
        if tile and tile[0] and tile[1]:
            # A tile has exactly ONE band height that crops nothing: tile_w * h/w.
            # Deviating in EITHER direction costs something, and which thing it
            # costs depends on the tile's shape. A portrait meeting tile in a band
            # that is too short loses height off the bottom, which is the name
            # badge. A landscape tile in a band that is too TALL loses width off
            # both sides, which is the badge's ends. So pull the band back toward
            # the tile's own height from whichever side it landed on.
            uncropped = int(round((tile_w or PANEL_W) * tile[1] / tile[0]))
            lo = int(round(uncropped * (1.0 - TILE_TRIM_MAX)))
            hi = int(round(uncropped * (1.0 + TILE_TRIM_MAX)))
            want = min(max(fh, lo), hi)
            # ...but never so far that the app cannot fit, and never so far that
            # the band turns mostly into flat fill. A big flat band is worse than
            # a cropped tile, so the pad budget wins the tie. Where both cannot be
            # had, preflight's PACK line prints the trade and face_h overrides it.
            floor = PANEL_H - SPLIT_GAP - int(natural / (1.0 - PAD_MAX_FRAC))
            # FACE_MIN guards against the face becoming a sliver, and it is sized
            # for a band that spans the whole panel width. A duo_share strip is
            # two half-width tiles, whose uncropped height is naturally under it -
            # so let the tile lower the floor rather than have FACE_MIN stretch
            # the strip and crop the tiles it was meant to protect.
            fmin = min(FACE_MIN, uncropped)
            fh = max(fmin, min(FACE_MAX, max(floor,
                     min(want, PANEL_H - SPLIT_GAP - natural))))
    # An authored face_h is trusted, but not past the panel: a face_h left over
    # from the 1560 era is only ever too SMALL, while one typo'd too large would
    # give the screen a negative height and ffmpeg would fail with a filter error
    # naming neither the number nor the file it came from.
    fh = int(max(120, min(int(fh), PANEL_H - SPLIT_GAP - 120)))
    band = PANEL_H - SPLIT_GAP - fh
    # AND IT SAYS WHEN THE OVERRIDE COSTS SOMETHING. The whole PAD_MAX_FRAC
    # budget above sits inside `if fh is None`, so an authored face_h skips it
    # entirely - deliberately, "face_h overrides it" - and then nothing reports
    # the band it produced. Measured on the delivered Alan Ellman clip, an
    # authored face_h of 814 leaves 510px of a 1092px band as flat extended edge:
    # 47% smear, against a 30% budget, and the build log said nothing. preflight
    # prints it as a PACK warning; the renderer, which is where the number is
    # actually decided, was silent.
    #
    # Not a refusal. It is the author's explicit number and the reference clip
    # was authored exactly this way - but a 47% band is worth knowing you chose.
    if authored is not None and band > 0:
        pad = band - min(band, natural)
        if pad > band * PAD_MAX_FRAC:
            sys.stderr.write(
                f"WARNING: authored face_h {authored} leaves {pad} of the "
                f"{band}px app band as flat fill ({100 * pad / band:.0f}%, "
                f"budget {100 * PAD_MAX_FRAC:.0f}%). Clearing \"face_h\" lets "
                f"the packer size it; keep it if the slide is solid.\n")
    return fh, band


def fit_geometry(box: tuple[int, int, int, int], bw: int,
                 bh: int) -> tuple[int, int, int, int, int, int]:
    """
    The arithmetic under fit_chain, on its own so preflight can print the SAME
    numbers the render will use: (w, h, x, y) of the crop after the 2% bleed on
    any padded axis, and (dw, dh) it is drawn at inside bw x bh. preflight used
    to re-derive "app drawn" as min(band, natural) and was 40px off on a real
    clip, because it did not know about the bleed.
    """
    w, h, x, y = box
    # First pass: does this need padding at all, and on which axis?
    scale = min(bw / w, bh / h)
    pad_v = bh - int(round(h * scale)) > 2
    pad_h = bw - int(round(w * scale)) > 2
    if pad_v:
        bleed = max(2, int(round(h * 0.02)))
        y += bleed
        h -= 2 * bleed
    if pad_h:
        bleed = max(2, int(round(w * 0.02)))
        x += bleed
        w -= 2 * bleed
    scale = min(bw / w, bh / h)
    dw, dh = int(round(w * scale)) // 2 * 2, int(round(h * scale)) // 2 * 2
    dw, dh = min(dw, bw), min(dh, bh)
    return w, h, x, y, dw, dh


def fit_chain(src: str, box: tuple[int, int, int, int], bw: int, bh: int,
              out: str, sharpen: str = "unsharp=3:3:0.3:3:3:0",
              vanchor: str = "top") -> str:
    """
    Fit a crop into a box WITHOUT trimming it, filling the spare with its own edge.

    The app used to be re-cut to fill its band, which is fine on a chart and cuts
    words off a text slide. Fitting instead keeps every pixel, and the leftover is
    filled with the AVERAGE COLOUR of the app's outermost rows or columns. On a
    solid-coloured slide that is literally invisible - the blue simply continues.
    On a chart it continues the chart's own background rather than introducing a
    slate bar, which is the thing that reads as a broken encode.

    The average, not the row itself. Stretching the row was the first version and
    it turns any structure in those two lines into vertical streaks running the
    height of the pad - a chart with a blue element at the left edge of its top
    row grew a blue stripe up the frame. Collapsing to one pixel first (area
    averaging) and then stretching gives a flat field, which is what "the
    background continues" should look like.

    On an axis that is being padded, the outermost 2% of the crop is DROPPED
    before drawing, and the smear then continues from the new outermost row. That
    makes the join seamless by construction, and it costs nothing real: an
    authored crop routinely overshoots its content by a few pixels, and the Ellman
    slide crop ran 5px past the bottom of the slide into PowerPoint's black
    surround. Drawn, that sliver is a black hairline straight across the frame;
    smeared, it was a 146px black bar. Two percent of a screen crop is its border,
    not its content.

    The drop only happens on an axis that is ALREADY being padded. Where the app
    fills its band exactly, nothing is taken off it.

    vanchor="top" puts ALL the vertical fill at the bottom, and it is the default
    for a reason that is worth two lines. The app band is the bottom of the frame,
    and the bottom of the frame is where every app draws its own chrome - so fill
    parked there costs nothing that was not already going to be covered. Centring
    it instead spends half the fill above the app, which pushes the app's content
    DOWN into the caption band: on a slide that is the title landing under the
    words. Top-anchored, the title clears them.
    """
    w, h, x, y, dw, dh = fit_geometry(box, bw, bh)
    if vanchor == "top":
        pt, pb = 0, bh - dh
    else:
        pt, pb = (bh - dh) // 2, bh - dh - (bh - dh) // 2
    pl, pr = (bw - dw) // 2, bw - dw - (bw - dw) // 2

    parts = [f"{src}crop={w}:{h}:{x}:{y},scale={dw}:{dh}:flags=lanczos,{sharpen}"
             f"[{out}_f];"]
    cur = f"{out}_f"
    if pt or pb:
        parts.append(f"[{cur}]split=3[{out}_c][{out}_t][{out}_b];")
        # The outermost rows, now that the bleed above has removed any overshoot.
        top = (f"[{out}_t]crop={dw}:2:0:0,scale=1:1:flags=area,"
               f"scale={dw}:{pt}:flags=neighbor[{out}_tp];" if pt else "")
        bot = (f"[{out}_b]crop={dw}:2:0:{dh - 2},scale=1:1:flags=area,"
               f"scale={dw}:{pb}:flags=neighbor[{out}_bp];" if pb else "")
        parts += [top, bot]
        stack = ((f"[{out}_tp]" if pt else "") + f"[{out}_c]" +
                 (f"[{out}_bp]" if pb else ""))
        n = 1 + bool(pt) + bool(pb)
        parts.append(f"{stack}vstack={n}[{out}_v];")
        cur = f"{out}_v"
        # split=3 always produces three outputs; drop the one we did not use so
        # ffmpeg does not fail with an unconnected pad.
        if not pt:
            parts.append(f"[{out}_t]nullsink;")
        if not pb:
            parts.append(f"[{out}_b]nullsink;")
    if pl or pr:
        parts.append(f"[{cur}]split=3[{out}_hc][{out}_l][{out}_r];")
        lef = (f"[{out}_l]crop=2:{bh}:0:0,scale=1:1:flags=area,"
               f"scale={pl}:{bh}:flags=neighbor[{out}_lp];" if pl else "")
        rig = (f"[{out}_r]crop=2:{bh}:{dw - 2}:0,scale=1:1:flags=area,"
               f"scale={pr}:{bh}:flags=neighbor[{out}_rp];" if pr else "")
        parts += [lef, rig]
        stack = ((f"[{out}_lp]" if pl else "") + f"[{out}_hc]" +
                 (f"[{out}_rp]" if pr else ""))
        n = 1 + bool(pl) + bool(pr)
        parts.append(f"{stack}hstack={n}[{out}_h];")
        cur = f"{out}_h"
        if not pl:
            parts.append(f"[{out}_l]nullsink;")
        if not pr:
            parts.append(f"[{out}_r]nullsink;")
    parts.append(f"[{cur}]null[{out}];")
    return "".join(parts)


_AUTOX: dict[tuple, int | None] = {}
_FACEC: dict[tuple, float | None] = {}


def face_centre(x0: int, x1: int, at: float, dur: float) -> float | None:
    """Horizontal centre of the face inside [x0, x1), in source px. Cached."""
    key = (int(x0), int(x1), round(at, 2), round(dur, 2))
    if key in _FACEC:
        return _FACEC[key]
    c = None
    try:
        import faces
        _sw, sh = src_size() or (1920, 1080)
        fb = faces.face_box(str(SRC), int(x0), int(x1), at=at,
                            dur=min(max(dur, 1.0), 20.0), h=sh)
        if fb:
            c = (fb[0] + fb[2]) / 2
    except Exception:                                            # noqa: BLE001
        c = None
    _FACEC[key] = c
    return c


def centre_on_face(box: tuple[int, int, int, int], bounds: tuple[int, int],
                   at: float, dur: float) -> tuple[int, int, int, int]:
    """
    Re-point a crop at the face inside `bounds`, keeping its SIZE exactly.

    THE AUTHORED CROP SAYS HOW TIGHT THE SHOT IS; THE FACE SAYS WHERE IT POINTS.
    Those are different decisions and only one of them is a matter of taste. The
    owner's rule is flat - "whoever's talking, their face needs to be centred, a
    lot of times they're shifted to the side, everybody has to be centred" - and
    a hand-authored x cannot follow a speaker who leans, or survive a guest
    sitting differently next week.

    Measured on the 08.26 two-up: the authored left crop starts at x=0 and the
    speaker's face sits at 348, which lands him **+189px** off centre once the
    516px window is blown up to a 1080 panel. Re-pointed, +1px. The right crop
    happened to be right already, at +0px - which is why this was never spotted
    by looking at one speaker.

    Clamped to `bounds`, which is that speaker's own TILE - a crop that slid far
    enough to centre a face would otherwise show the edge of the other person.
    """
    cw, ch, cx, cy = box
    x0, x1 = int(bounds[0]), int(bounds[1])
    c = face_centre(x0, x1, at, dur)
    if c is None:
        return (cw, ch, cx, cy)
    want = int(round(c - cw / 2))
    return (cw, ch, max(x0, min(want, max(x0, x1 - cw))), cy)


def auto_crop_x(cw: int, at: float, dur: float) -> int | None:
    """
    x for a `cw`-wide window that puts the SPEAKER'S HEAD in the middle.

    THE DEFAULT CROP CENTRED THE FRAME, NOT THE FACE. A webcam sitter is rarely
    dead centre in their own picture, so a window centred on the source put them
    off centre in the panel and left the empty half of their room on screen.
    Measured on the 08.28 head clip by arithmetic rather than by a detector
    reading the delivered frame - a cascade run over the panel gave answers that
    disagreed with each other AND with the picture, in both directions, which is
    the trap recorded at "A MEASUREMENT THAT WAS WRONG". The face centre in the
    source is 866 of 1920; the frame-centred window at x=656 put it at panel
    x=373, **167px LEFT** of centre. The owner saw it without measuring: "whoever's
    talking, their face needs to be centred, a lot of times they're shifted to
    the side."

    Cached, because render and preflight must agree on the rectangle - the whole
    reason head_box has one owner - and because the detection samples video.
    Returns None when no face is convincingly there, and the caller keeps the
    geometric centre rather than inventing one.
    """
    key = (int(cw), round(at, 2), round(dur, 2))
    if key in _AUTOX:
        return _AUTOX[key]
    sw, _sh = src_size() or (1920, 1080)
    c = face_centre(0, sw, at, dur)
    x = None if c is None else max(0, min(int(round(c - cw / 2)), sw - cw))
    _AUTOX[key] = x
    return x


def head_box(head_crop: list[int] | None = None,
             crop_x: int | None = None, at: float | None = None,
             dur: float | None = None) -> tuple[int, int, int, int]:
    """
    The source rectangle a `head` clip actually puts on screen.

    ONE OWNER, because preflight needed the same answer and was modelling an
    unauthored head crop as the WHOLE 1920x1080 frame. That is not conservative,
    it is blind: every burned-in graphic is then 100% contained, so check_graphics
    could never fail the dominant mode (8 of 28 archived head clips carry no
    head_crop), while simultaneously firing a false proximity WARN on a mark the
    renderer excludes outright - which trains the operator to ignore the line.

    It also ignores `crop_x`, the per-clip slate key, so an authored head_crop was
    mismodelled too.
    """
    box = head_crop or HEAD_CROP
    if box:
        cw, ch, cx, cy = box
        if crop_x is not None:
            cx = crop_x
    else:
        # DERIVED FROM THE SOURCE, NOT FROM 1920x1080. This branch used to build
        # its rectangle out of two literals, and it is the branch that runs on
        # every head clip with no authored head_crop - 8 of 28 in the archive.
        # On a 1280x720 master (a Zoom cloud recording, an older webinar, a
        # re-encoded download) it asked for a crop 1080 pixels tall out of a
        # frame 720 tall, and the render died a hundred seconds in, inside the
        # filtergraph, with a message naming neither the clip nor the reason.
        #
        # As tall as the source, as wide as 9:16 needs, never wider than the
        # source, and the x clamped so it cannot run off either edge whatever
        # face_crop_x says.
        sw, sh = src_size() or (1920, 1080)
        ch, cy = sh, 0
        cw = min(sw, int(round(sh * PANEL_W / PANEL_H)))
        # AUTHORED WINS, THEN CONFIGURED, THEN MEASURED, THEN GEOMETRY. Only
        # the last case changes: an unauthored crop used to take the middle of
        # the SOURCE and leave the speaker wherever they happen to sit in their
        # own camera. See auto_crop_x.
        want = crop_x
        mid = (sw - cw) // 2
        cfg_x = CFG.get("face_crop_x")
        # A CONFIGURED face_crop_x THAT IS EXACTLY THE GEOMETRIC CENTRE IS NOT A
        # DECISION. analyze.py wrote that value into every project under a
        # face-named key without ever looking for a face, so the "override"
        # that beat the measurement was itself the bug. A hand-tuned value is
        # kept and still wins; the auto-written one steps aside.
        if want is None and cfg_x is not None and int(cfg_x) != mid:
            want = cfg_x
        if want is None and at is not None:
            want = auto_crop_x(cw, at, dur if dur is not None else 20.0)
        if want is None:
            want = mid if cfg_x is None else cfg_x
        cx = max(0, min(int(want), sw - cw))
    return fill_crop((int(cw), int(ch), int(cx), int(cy)), PANEL_W / PANEL_H)


def fill_crop(box: tuple[int, int, int, int], want: float,
              anchor: str = "centre") -> tuple[int, int, int, int]:
    """
    Re-cut a crop to an exact aspect by TRIMMING it. Never pads, never stretches.

    anchor="bottom" takes the height off the TOP only. That is the right default
    for a camera tile and the wrong one for anything else: a webcam frames a head
    with dead ceiling above it and puts the name badge along the bottom, so a
    centred trim spends half its cut on the one strip worth keeping. analyze.py's
    half_crop is bottom-aligned for the same reason.
    """
    w, h, x, y = box
    # EVEN sizes. ffmpeg's crop rounds an odd width or height DOWN on yuv420p
    # (exact=0), so an odd re-cut was a 1px mismatch against the scale that
    # followed it - invisible, and also not the "never stretched" the docstring
    # promises. Rounding to even here keeps the promise literally.
    if w / h > want:
        nw = int(round(h * want)) // 2 * 2; x += (w - nw) // 2; w = nw
    else:
        nh = int(round(w / want)) // 2 * 2
        y += (h - nh) if anchor == "bottom" else (h - nh) // 2
        h = nh
    return w, h, x, y


def _touches(start: float, end: float, mode: str) -> bool:
    """Does this span overlap a run of the given layout?"""
    path = WORK / "sections.json"
    if not path.exists():
        return False
    return any(r["end"] > start and r["start"] < end and r["mode"] == mode
               for r in json.loads(path.read_text()))


def _authored_tile_holds(start: float, end: float,
                         box: list[int]) -> tuple[bool, str] | None:
    """
    Judge the AUTHORED rectangle instead of a discovered band.

    `railcheck.tiles()` finds tiles by brightness, and it MERGES neighbours when
    the separator between them is only a few pixels. On a three-guest rail it
    returned ONE band, (144, 904), for three tiles whose tops were measured at
    146 / 410 / 675 - so the edge the persistence test was judging was the bottom
    of somebody else's tile. That bottom belonged to the darkest guest on the
    call, whose lower rows drift in and out of threshold, and a span where all
    three tops were byte-identical in all 52 sampled frames was refused for
    "the cropped tile moves".

    So when the band comes back much taller than the crop, measure the crop.
    Two things, both of which a real re-flow breaks and a brightness dropout
    does not: the separator directly above the crop stays where it was authored,
    and the crop's own rows never go dark. A re-flow moves the tile and leaves
    black; neither survives that.

    Returns (ok, detail), or None when it cannot measure - in which case the
    caller keeps its own verdict rather than assuming the span is fine.
    """
    w, h, x, y = box
    try:
        raw = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start:.3f}",
             "-t", f"{end - start:.3f}", "-i", str(SRC),
             "-vf", f"fps=1,crop={w}:1080:{x}:0,format=gray",
             "-f", "rawvideo", "-"], capture_output=True).stdout
        n = len(raw) // (w * 1080)
        if n < 3:
            return None
        prof = (np.frombuffer(raw, np.uint8)[: n * w * 1080]
                .reshape(n, 1080, w).astype(np.float32).mean(axis=2))
    except Exception:
        return None

    tops, lit = [], []
    lo, hi = max(1, y - 24), min(1078, y + 24)
    for i in range(n):
        r = prof[i]
        d = np.diff(r)
        # A tile top is a hard step up out of the near-black separator row.
        cand = [t + 1 for t in range(lo, hi) if d[t] > 14 and r[t] < 26]
        tops.append(min(cand, key=lambda t: abs(t - y)) if cand else None)
        lit.append(float(r[y: y + h].mean()))

    found = [t for t in tops if t is not None]
    if len(found) < n * 0.6:
        return None                              # cannot see the separator at all
    med = sorted(found)[len(found) // 2]
    moved = [i for i, t in enumerate(tops) if t is not None and abs(t - med) > 8]
    floor = sorted(lit)[len(lit) // 2] * 0.35
    dark = [i for i, v in enumerate(lit) if v < floor]
    bad = sorted(set(moved) | set(dark))
    longest, run, prev = 0, 0, None
    for i in bad:
        run = run + 1 if prev is not None and i == prev + 1 else 1
        longest = max(longest, run)
        prev = i
    detail = (f"top holds at y{med} (authored {y}), "
              f"crop brightness {min(lit):.0f}-{max(lit):.0f}")
    if longest >= 3:
        return False, (f"crop top moves off y{med} / goes dark at "
                       + ", ".join(f"{start + i:.0f}s" for i in bad[:8]))
    return True, detail


def check_rail(start: float, end: float, mode: str,
               pip_crop: list[int] | None = None) -> None:
    """
    Refuse a share span if THE TILE THIS CLIP CROPS moves part way through.

    A share clip crops a fixed rectangle out of the camera rail, and the
    compositor moves the rail: drop a speaker and the remaining tile re-centres
    and resizes. A fixed crop through that shows the speaker for part of the clip
    and a BLACK GAP for the rest. `check_layout` cannot see it, because the layout
    is "share" the whole way and only the furniture inside it moved.

    It asks about the ONE band the crop sits in, not the whole rail signature.
    Comparing the whole signature refused a perfectly good clip whose two speaker
    tiles never budged from (272, 800) while a comment overlay lower down the rail
    jittered by eight pixels - seventeen "re-flows" that were all the same two
    faces in the same two places.
    """
    if mode not in ("share", "duo_share", "conversation_share"):
        return
    try:
        import railcheck
    except Exception:
        return
    try:
        seq = railcheck.rail_frames(start, end - start, 1.0)
        if len(seq) < 3:
            return
        keys = [railcheck.tiles(f) for f in seq]
    except Exception:
        return

    box = pip_crop or CFG.get("pip_crop")
    mid = (box[3] + box[1] / 2) if box else None

    def band(k: tuple) -> tuple | None:
        """The band this clip's crop lives in, or the whole signature if unknown."""
        if mid is None:
            return k
        for a, b in k:
            if a - 12 <= mid <= b + 12:
                return (a, b)
        return None                              # the tile vanished from the rail

    # A tile that has really left the rail STAYS gone - the compositor dropped it
    # and re-flowed what was left. An ISOLATED missing sample is instead this test
    # failing to see a tile that is plainly there, because it finds tiles by
    # BRIGHTNESS and a guest against a dark step-and-repeat backdrop (a Bloomberg
    # Intelligence banner, an unlit room) barely clears the threshold.
    #
    # Measured on one master: 1 missing sample in 63 and 2 in 50 on rails that never
    # moved - a frame was pulled at each and the tile was in place every time -
    # against 13 of 60, contiguous, for a genuine two-tile-to-one re-flow. So
    # require persistence here, exactly as the edge test below does.
    seen = [band(k) for k in keys]
    miss = [i for i, b in enumerate(seen) if b is None]
    longest, run, prev = 0, 0, None
    for i in miss:
        run = run + 1 if prev is not None and i == prev + 1 else 1
        longest = max(longest, run)
        prev = i
    if longest >= 3:
        raise SystemExit(
            f"\nTHE CROPPED TILE LEAVES THE RAIL inside {start:.1f}..{end:.1f}\n"
            f"  missing at {', '.join(f'{start + t:.0f}s' for t in miss[:6])} "
            f"({len(miss)} of {len(seen)} samples, {longest} consecutive)\n"
            f"That renders a black gap. Find a stretch that holds still:\n"
            f"  python3 railcheck.py <run_start> <run_end> --windows\n")
    if miss:
        print(f"note: rail tile not detected at "
              f"{', '.join(f'{start + t:.0f}s' for t in miss)} "
              f"({len(miss)} of {len(seen)} samples, never 3 in a row) - too brief "
              f"to be a re-flow, treating as a dark-backdrop dropout.")
        seen = [b for b in seen if b is not None]
        if not seen:
            return

    # Allow a few px of jitter in the band's own edges - but judge on PERSISTENCE,
    # not on the extremes. `tiles()` finds a tile by brightness, so a single dark
    # second (the speaker raising his hands over his face, a dark shirt filling the
    # lower half) drops the bottom rows below threshold and the band reads short for
    # one sample. Comparing min against max turns that blip into a refusal: on one
    # master the tile top never left 408 while the bottom read 664/648/608/664, and
    # a perfectly stable 74s span was refused on three samples out of ninety.
    #
    # A REAL re-flow is the compositor re-centring, which moves both edges and holds
    # the new position for seconds. So measure deviation from the median and refuse
    # only when it persists.
    med_top = sorted(b[0] for b in seen)[len(seen) // 2]
    med_bot = sorted(b[1] for b in seen)[len(seen) // 2]
    off = [i for i, b in enumerate(seen)
           if abs(b[0] - med_top) > 16 or abs(b[1] - med_bot) > 16]
    # CONSECUTIVE, not merely numerous. A re-flow holds its new position for
    # seconds; three separate one-second dropouts scattered through a minute are
    # three separate dark frames, not three moves.
    longest, run = 0, 0
    prev = None
    for i in off:
        run = run + 1 if prev is not None and i == prev + 1 else 1
        longest = max(longest, run)
        prev = i
    if longest >= 3:
        # Before refusing, ask whether the band even belongs to this crop. See
        # _authored_tile_holds: a thin separator makes the finder merge tiles,
        # and then this test is watching a stranger's edge.
        if box and (med_bot - med_top) > box[1] * 1.6:
            v = _authored_tile_holds(start, end, box)
            if v and v[0]:
                print(f"note: rail band ({med_top}, {med_bot}) is {med_bot - med_top}px "
                      f"for a {box[1]}px crop - the tile finder merged neighbours, so "
                      f"the authored rectangle was measured instead: {v[1]}.")
                return
            if v:
                raise SystemExit(
                    f"\nTHE CROPPED TILE MOVES inside {start:.1f}..{end:.1f}\n"
                    f"  {v[1]}\n"
                    f"A fixed crop cannot follow it. Find a stretch that holds still:\n"
                    f"  python3 railcheck.py <run_start> <run_end> --windows\n")
        raise SystemExit(
            f"\nTHE CROPPED TILE MOVES inside {start:.1f}..{end:.1f}\n"
            f"  band sits at ({med_top}, {med_bot}) but differs at "
            f"{', '.join(f'{start + i:.0f}s' for i in off[:8])}"
            f"{' ...' if len(off) > 8 else ''} ({len(off)} of {len(seen)} samples)\n"
            f"A fixed pip_crop cannot follow it. Find a stretch that holds still:\n"
            f"  python3 railcheck.py <run_start> <run_end> --windows\n")
    if off:
        print(f"note: rail band blips off ({med_top}, {med_bot}) at "
              f"{', '.join(f'{start + i:.0f}s' for i in off)} - "
              f"too brief to be a re-flow, treating as a brightness dropout.")


def check_speaker(slug: str, start: float, end: float, mode: str,
                  pip_crop: list[int] | None,
                  head_crop: list[int] | None = None,
                  crop_x: int | None = None) -> str:
    """
    Confirm the crop this clip ships is the person actually TALKING.

    The transcript carries no speaker labels, so who is speaking is inferred -
    and when that is wrong the clip shows one person while a different person's
    voice plays. It is the most obvious way a clip can be broken and the owner
    has caught it twice.

    IT COVERS `head` NOW, WHICH IS WHERE THE GAP WAS. It only ever ran on the
    share modes, because those carry an explicit `pip_crop`. But a `head` clip
    cut from a TWO-UP has exactly the same failure - the crop takes one half and
    the other person may be the one talking - and it was the mode with the most
    clips and no check at all. A single-camera source is skipped: with one person
    in frame there is nothing to get wrong.

    IT USES turns' MEASUREMENT, NOT whospeaks'. Two changes matter and both were
    established by validating against frames: the mouth region comes from the
    face the cascade FINDS rather than a fixed fraction of the tile (a fixed box
    put one speaker's animated background inside his mouth region), and the
    sample rate is 0.10s rather than 0.25s (a mouth moves several times a second,
    and at 0.25s it is undersampled - measured, that alone flipped a verdict).

    RETURNS WHY, because "said nothing" used to have seven different meanings and
    preflight printed "authored tile matches the voice" over all of them. The
    value is "match" or "mismatch" when it actually measured; anything else is a
    reason it could not.
    """
    tiles = CFG.get("tiles")
    if not tiles or len(tiles) < 2:
        return "no \"tiles\" map in project.json (name: [w,h,x,y] per camera)"
    # Which rectangle does this clip actually ship?
    if mode in ("share", "duo_share"):
        box = pip_crop
    elif mode == "head":
        if not (head_crop or HEAD_CROP):
            return "a single-camera head clip - one person in frame, nothing to pick"
        box = list(head_box(head_crop, crop_x, at=start,
                            dur=(end - start) if end else None))
    else:
        # conversation / conversation_share FOLLOW the schedule, so there is no
        # authored tile to get wrong - render() checks the NAMEPLATE instead.
        return "this mode follows the turn schedule; nothing authored to check"
    if not box:
        return "no crop authored for this mode"

    try:
        import turns as _t
        src = SRC
        faces = {n: _t._face_of(src, start, min(end - start, 20.0), tuple(b))
                 for n, b in tiles.items()}
        who, margin = _t.score_segment(start, end - start, tiles, faces)
    except Exception as e:                                       # noqa: BLE001
        return f"the measurement raised {type(e).__name__}: {e}"
    if who is None:
        return "could not decide - too few usable samples in this span"

    # WHICH NAMED TILE DOES THE AUTHORED CROP SIT IN? By AREA overlap in two
    # dimensions. The old test compared only the vertical midpoint, which is
    # right for a stacked rail and cannot tell left from right on a two-up -
    # exactly the layout `head` is cut from.
    bw, bh, bx, by = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
    chosen, best_area = None, 0
    for name, t in tiles.items():
        tw, th, tx, ty = (int(t[0]), int(t[1]), int(t[2]), int(t[3]))
        ox = max(0, min(bx + bw, tx + tw) - max(bx, tx))
        oy = max(0, min(by + bh, ty + th) - max(by, ty))
        if ox * oy > best_area:
            chosen, best_area = name, ox * oy
    if chosen is None or best_area < bw * bh * 0.25:
        return ("the authored crop does not sit inside any named tile, so there "
                "is nothing to compare it against - check \"tiles\"")

    if chosen == who:
        return "match"
    if margin < 1.25:
        return (f"crop is on {chosen!r} and {who!r} measures louder, but only "
                f"{margin:.2f}x ahead - too close to act on. Pull a frame and "
                f"see whose mouth is open")
    sys.stderr.write(
        f"WARNING: {slug} crops to {chosen!r} but {who!r} is the one talking "
        f"({margin:.2f}x ahead).\n"
        f"         Pull a frame and check whose mouth is open before shipping "
        f"this.\n")
    return "mismatch"

def kept_source_spans(start: float, end: float,
                      drop: list[list[float]] | None) -> list[tuple[float, float]]:
    """
    The source windows a welded clip actually SHOWS.

    Module scope, and it takes SOURCE times, because three tools need the same
    answer: check_layout scores the halves rather than the outer span, preflight
    reports them, and pick.py builds them. keep_spans is its span-time sibling
    and deliberately not reused - that one owns the post-removal timeline and
    knows nothing about `start`.
    """
    if not drop:
        return [(start, end)]
    out: list[tuple[float, float]] = []
    t = start
    for a, b in sorted((float(d[0]), float(d[1])) for d in drop):
        if a > t:
            out.append((t, a))
        t = max(t, b)
    if t < end:
        out.append((t, end))
    return out


def layout_modes(start: float, end: float) -> set[str]:
    """Layout names touching a source window. Empty when there is no map."""
    path = WORK / "sections.json"
    if not path.exists():
        return set()
    # HAND-WRITTEN sections.json IS INVITED BY THIS PIPELINE, so it must not
    # die with a raw KeyError from a comprehension. A missing key, a string
    # where a number belongs, or a top-level object instead of a list all
    # arrive here from a human editing the file the docs tell them to edit.
    try:
        runs = json.loads(path.read_text())
    except ValueError as e:
        raise SystemExit(f"\n{path} is not valid JSON: {e}\n") from None
    if isinstance(runs, dict):
        runs = runs.get("runs", [])
    bad = [r for r in runs
           if not isinstance(r, dict) or not {"mode", "start", "end"} <= set(r)
           or not isinstance(r.get("start"), (int, float))
           or not isinstance(r.get("end"), (int, float))]
    if bad:
        raise SystemExit(
            f"\n{path} has {len(bad)} malformed run(s); each needs "
            f'"mode", "start" and "end" with numeric times.\n'
            f"  first bad entry: {bad[0]!r}\n")
    return {r["mode"] for r in runs if r["end"] > start and r["start"] < end}


def check_layout(start: float, end: float, mode: str,
                 layout_ok: bool = False,
                 drop: list[list[float]] | None = None) -> None:
    """
    Refuse a span that crosses a layout change, or that does not match its mode.

    This exists because it happened. A duo clip was cut from 3:55 to 4:34 on a
    master that only becomes a two-up at 4:07, so for the first eleven seconds the
    two bands were slicing a SINGLE solo frame down the middle - the same man's
    face on top and his shoulder underneath. It renders perfectly happily and
    looks obviously broken, and nothing in the pipeline objected.

    Picking spans off a transcript is what causes it: the transcript has no idea
    what the picture is doing, so a span chosen for what is said will cross a cut
    sooner or later. Checking is a second of work; noticing by eye is not reliable.
    """
    # A WELDED CLIP IS ITS KEPT HALVES, NOT ITS OUTER SPAN. Scoring start..end
    # on a two-moment clip asks whether three minutes NOBODY WILL SEE crosses a
    # layout change, and over that distance the answer is almost always yes - so
    # the check that exists to stop a crop meeting the wrong frame would refuse
    # every legal weld instead. Each half is checked on its own terms, and then
    # the halves are required to agree with EACH OTHER, which is the constraint
    # that actually protects the crop: one set of crops is authored per clip.
    if drop:
        halves = kept_source_spans(start, end, drop)
        for _a, _b in halves:
            check_layout(_a, _b, mode, layout_ok=layout_ok)
        names = sorted({n for _a, _b in halves for n in layout_modes(_a, _b)})
        if len(names) > 1:
            where = ", ".join(f"{_a:.1f}..{_b:.1f}" for _a, _b in halves)
            raise SystemExit(
                f"\nWELD JOINS TWO LAYOUTS: the halves ({where}) are "
                f"{' and '.join(names)}.\n"
                f"One set of crops is authored per clip, so both halves have to "
                f"be laid out the same way. Pick a payoff inside the same run as "
                f"the hook.\n")
        return

    path = WORK / "sections.json"
    if not path.exists():
        # NO MAP IS UNVERIFIED, NOT FINE. This used to return silently and the
        # caller then printed "[ok] LAYOUT covered, mode fits" - a pass reported
        # off no evidence at all, which is the one class of defect this codebase
        # keeps finding in itself. It stays non-fatal, because a job can
        # legitimately be preflighted before analyze.py has run, but it says so.
        sys.stderr.write(
            "note: no sections.json, so the layout of this span was NOT checked. "
            "Run analyze.py, or hand-write one if detect_sections mislabels this "
            "material.\n")
        return
    runs = json.loads(path.read_text())
    touched = sorted((r for r in runs if r["end"] > start and r["start"] < end),
                     key=lambda r: r["start"])
    if not touched:
        return

    # A HOLE in the map is not agreement. analyze.py drops runs shorter than its
    # minimum without closing the gap, so sections.json has uncovered seconds -
    # and a span crossing one used to pass, because a hole contributes no mode
    # name. That is the exact failure this function exists to stop: a duo clip
    # over an uncovered stretch slices a single solo frame down the middle.
    holes: list[tuple[float, float]] = []
    if touched[0]["start"] > start:
        holes.append((start, touched[0]["start"]))
    for a, b in zip(touched, touched[1:]):
        if b["start"] > a["end"]:
            holes.append((a["end"], b["start"]))
    if touched[-1]["end"] < end:
        holes.append((touched[-1]["end"], end))
    holes = [(a, b) for a, b in holes if b - a > 0.5]
    if holes:
        where = ", ".join(f"{a:.1f}..{b:.1f}" for a, b in holes)
        raise SystemExit(
            f"\nSPAN CROSSES UNMAPPED VIDEO: {start:.1f}..{end:.1f} has no layout "
            f"classification over {where}.\n"
            f"Those seconds were dropped as too short to classify, which usually "
            f"means the picture is changing there. Pick a span inside one mapped "
            f"run, or look at a frame in that gap before overriding.\n")

    names = sorted({r["mode"] for r in touched})
    if len(names) > 1:
        edges = ", ".join(f"{r['mode']} {r['start']}..{r['end']}" for r in touched)
        raise SystemExit(
            f"\nSPAN CROSSES A LAYOUT CHANGE: {start:.1f}..{end:.1f} covers {edges}.\n"
            f"Pick a span inside ONE run, or the crops will be applied to a frame "
            f"that is laid out differently than they assume.\n")
    if names[0] not in MODE_NEEDS.get(mode, set()):
        # `"layout_ok": true` on the clip is the escape, and it exists for ONE
        # shape the map cannot name: a rig that puts the camera tiles in a RAIL
        # beside the shared screen, where a duo cut from those two tiles is a
        # perfectly ordinary two-shot and the layout is still, correctly,
        # `share`. Author the crops against that rail and the picture is right;
        # the map is right too. It relaxes only THIS branch - a span that
        # crosses a layout change, or an unmapped hole, still refuses, because
        # those are the cases where the crops meet a frame laid out differently
        # than they assume.
        if layout_ok:
            sys.stderr.write(
                f"note: {mode!r} over a {names[0]!r} stretch, allowed by "
                f"\"layout_ok\" on this clip. The crops must be authored against "
                f"the {names[0]!r} frame, not against a {mode!r} one.\n")
            return
        raise SystemExit(
            f"\nMODE MISMATCH: mode '{mode}' over a '{names[0]}' stretch "
            f"({start:.1f}..{end:.1f}).\n"
            f"'duo' needs two_up; 'share' needs share; 'head' takes either a solo "
            f"shot or one half of a two_up.\n"
            f"If the crops really are authored against this layout (a duo cut "
            f"from the camera tiles of a share rail), set \"layout_ok\": true "
            f"on the clip.\n")


POSTER_AT: dict[str, float] = {}   # slug -> the second the cover frame came from


def poster(clip: Path) -> Path:
    """
    Pick the frame the feed will judge this clip on, and write it beside the mp4.

    A vertical feed shows a still before anyone presses play, and by default that
    is frame zero - which lands on a blink, a mouth mid-syllable, or a head turned
    away about as often as not. This scores the first few seconds and keeps the
    best one: sharp (in focus, not motion-blurred), bright enough to read as a
    face, and while the hook is still up so the still carries its own headline.

    Sharpness is the gradient energy of the frame. A blink or a fast head turn is
    softer than a held expression, so the sharpest frame in the window is very
    nearly always a good one, and it costs one decode pass to find.

    AND THE FRAME IT PICKS HAS TO REACH THE PERSON UPLOADING, or none of the above
    happens. This function has always written a correct `.jpg` next to the mp4 and
    the posting sheet has never shown it - measured 2026-08-24, `<img` and
    `data:image` both appear ZERO times across all 42 delivered POSTING-SHEET.html
    files, while 71 of 91 delivered clips have an unused `.jpg` sitting beside
    them. So every clip ever posted went up on frame 0.

    Frame 0 is wrong BY CONSTRUCTION, not by luck. The hook card arrives over
    HOOK_IN (0.30s) from HOOK_SLIDE_IN (60px) at HOOK_ALPHA0 (0.85), so at t=0 the
    headline is always 60px right of where it was designed to sit and always
    translucent - measured on a delivered clip, card interior luma 224.0 (sd 7.11)
    against 253.0 (sd 0.13) on the poster, i.e. the wall behind the speaker is
    visibly coming through the words.

    The chosen time is recorded in POSTER_AT so make_sheet.py can print it beside
    the thumbnail: most upload forms let you scrub to a frame, and a number is
    what makes that a two-second job.
    """
    end = min(HOOK_HOLD, 3.2)
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-t", f"{end:.2f}",
         "-vf", "fps=6,crop=1080:900:0:180,scale=180:150,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    n = len(p.stdout) // (180 * 150)
    best_t = 0.6
    if n:
        F = np.frombuffer(p.stdout[:n * 180 * 150], dtype=np.uint8) \
              .reshape(n, 150, 180).astype(float)
        gx = np.abs(np.diff(F, axis=2)).mean(axis=(1, 2))
        gy = np.abs(np.diff(F, axis=1)).mean(axis=(1, 2))
        lum = F.mean(axis=(1, 2))
        score = (gx + gy) * np.clip(lum / 90.0, 0, 1.4)
        if n > 3:
            score[:3] = 0                  # never the very first frames
        best_t = float(np.argmax(score)) / 6.0
    out = clip.with_suffix(".jpg")
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{best_t:.2f}", "-i", str(clip),
         "-frames:v", "1", "-q:v", "2", str(out)])
    POSTER_AT[clip.stem] = best_t
    sys.stderr.write(f"poster: {clip.stem} cover frame at +{best_t:.2f}s\n")
    return out


# ------------------------------------------------ sampling the background ----
def split_labels(mode: str) -> tuple[int, str]:
    """
    How many copies of the source the reframing chain needs, and their labels.

    One per picture element: a head is one crop, duo and share are two, duo_share
    is three. There used to be one more for the blurred backdrop; the panel is the
    frame now, so nothing is drawn behind it.
    """
    # head_follow is ONE, not two. It crops the same source twice and switches
    # between them, but it does that split INSIDE its own branch - exactly as
    # the punch ladder does on a head clip - so the outer graph hands it a
    # single source. Asking for two here leaves [fgsrc2] unconnected and ffmpeg
    # refuses to bind the graph.
    # conversation splits INSIDE its own branch, like the punch does, so it asks
    # for one. conversation_share asks for two - the face (which splits again
    # inside) and the app.
    n = {"head": 1, "conversation": 1, "conversation_share": 2,
         "duo": 2, "share": 2, "duo_share": 3}[mode]
    return n, "".join(f"[fgsrc{i}]" for i in range(2, n + 1))


# How many frames to look at. Eight is plenty - we are after the character of the
# background, not a per-frame answer - and eight input-seek single-frame decodes
# off a 2GB master measure at about a second in total, so this is free next to a
# render. Do not raise it without re-measuring.
BG_SAMPLES = 8


def sample_caption_bg(start: float, end: float, mode: str, fg: str,
                      splits: int, extra: str) -> dict | None:
    """
    Measure what will be behind the captions, through the clip's own reframing.

    The naive version of this samples the SOURCE frame and is wrong in three of
    the four modes: in `share` the caption zone lands on the shared app, in `duo`
    on the lower speaker, and in `head` on whatever the crop happens to select.
    Running the real `fg` chain and cropping the caption rectangle out of the
    result is the only way to be sampling the pixels the words will sit on.

    Returns None if nothing decoded, and the caller keeps the house colours.
    """
    # The INK rectangle, not the band. flags=area is deliberate: box averaging is
    # the right downscale for a statistical sample, where lanczos would ring and
    # inflate the tails the median is there to ignore.
    x0 = (W - CAP_INK_W) // 2
    graph = (f"[0:v]split={splits}[fgsrc]{extra};"
             f"[fgsrc]{fg}[fgv];"
             f"[fgv]crop={CAP_INK_W}:{CAP_PROBE_H}:{x0}:{CAP_PROBE_Y},"
             f"scale=72:20:flags=area[o]")
    frames = []
    lo, hi = start + 1.0, max(start + 1.2, end - 1.0)
    for i in range(BG_SAMPLES):
        t = lo + (hi - lo) * (i / max(1, BG_SAMPLES - 1))
        # probe_panel, not a one-frame decode: see its docstring for why a
        # single frame of a share chain is the empty slate stack.
        raw = probe_panel(t, graph, 72 * 20 * 3, pix_fmt="rgb24")
        if raw is not None:
            frames.append(np.frombuffer(raw, dtype=np.uint8))
    if not frames:
        return None

    a = np.stack(frames).reshape(len(frames), 20, 72, 3).astype(float) / 255.0
    lin = _srgb_to_lin(a)
    lum = (lin * np.array([0.2126, 0.7152, 0.0722])).sum(-1)

    # The MEDIAN, not the mean. A caption zone regularly contains a small very
    # bright thing - a shirt collar, a chart's white gridline, a lamp - and a mean
    # is dragged by it into calling a dark room mid-grey. The median describes what
    # most of the area is doing, which is what the type has to survive.
    med = float(np.median(lum))
    per_frame = np.median(lum, axis=(1, 2))

    mx, mn = a.max(-1), a.min(-1)
    df = mx - mn
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        hr = np.where(df > 0, ((g - b) / np.where(df > 0, df, 1)) % 6, 0)
        hg = np.where(df > 0, ((b - r) / np.where(df > 0, df, 1)) + 2, 0)
        hb = np.where(df > 0, ((r - g) / np.where(df > 0, df, 1)) + 4, 0)
    hue = np.where(mx == r, hr, np.where(mx == g, hg, hb)) * 60.0
    # Weight each pixel's hue by how much colour it actually carries. An unweighted
    # average over a dark room returns a confident hue for what is essentially
    # black, and the accent would then be chosen to avoid a colour nobody can see.
    weight = np.where(mx > 0, df / np.maximum(mx, 1e-6), 0.0) * mx
    if weight.sum() > 1e-6:
        rad = np.radians(hue)
        dom = float(np.degrees(np.arctan2((weight * np.sin(rad)).sum(),
                                          (weight * np.cos(rad)).sum())) % 360.0)
    else:
        dom = 0.0

    return {
        "lum": med,
        "hue": dom,
        "chroma": float(weight.mean()),
        # A clip that swings across the light/dark boundary, or across a third of
        # the luminance range, cannot be served by one confident decision.
        "split": bool(per_frame.max() - per_frame.min() > 0.30 or
                      (per_frame.max() > CAP_FLIP_L > per_frame.min())),
        "frames": len(frames),
        "range": (float(per_frame.min()), float(per_frame.max())),
    }


# What each rendered clip ended up with, keyed by slug. render() fills it in;
# build_all reads it after the run. Deliberately a record rather than a return
# value, so the signature of render() does not change under its other callers.
HOOK_TOOK_ATTR = [False]   # did the card carry the credential this render?
RAGGED_ENDS: list[str] = []   # clips shipped with allow_ragged_end, for build_all
LOUDNESS: dict[str, tuple[float, float]] = {}   # slug -> (I, TP), for build_all
TIMBRE: dict[str, float] = {}                  # slug -> 4-6kHz dB rel. core
CHOSEN_COLOURS: dict[str, dict] = {}

# Below this much colour in the caption zone the background is effectively grey -
# a dark room, a black terminal - and hue distance means nothing. Measured on real
# frames: a lit face against a dark study came back at 0.09, a navy shirt at 0.31.
BG_GREY = 0.12


def caption_colours(start: float, end: float, mode: str, fg: str, splits: int,
                    extra: str, slug: str = "", clip_cfg: dict | None = None) -> dict:
    """
    The base, stroke and keyword colours for one clip.

    ONE decision for the whole clip, deliberately. A colour that re-picks itself
    per caption reads as a glitch rather than as a system, and the point of the
    keyword highlight is that a viewer learns what the colour MEANS over the first
    few words. A clip that genuinely changes background mid-way is reported and
    given the choice that survives both halves.
    """
    house = {"base": BONE, "stroke": (7, 10, 14), "key": CAP_KEY,
             "key_name": "cyan", "set": "light", "note": ""}

    cfg = dict(clip_cfg or {})
    forced_key = parse_colour(cfg.get("key", cfg.get("cap_key")))
    forced_base = parse_colour(cfg.get("base", cfg.get("cap_base")))
    if not CFG.get("adaptive_captions", True):
        col = dict(house)
    elif forced_key and forced_base:
        col = dict(house)                      # nothing to measure, both are set
    else:
        bg = sample_caption_bg(start, end, mode, fg, splits, extra)
        if bg is None:
            sys.stderr.write(
                f"note: {slug} could not sample the caption background; "
                f"keeping the house cyan.\n")
            col = dict(house)
        else:
            # No usable hue. Let contrast and the house prior decide, rather than
            # steering away from a colour that is not really there.
            bg = dict(bg, grey=bg["chroma"] < BG_GREY)
            col = choose_caption_colours(bg)
            rng = bg["range"]
            sys.stderr.write(
                f"captions: {slug} background L={bg['lum']:.2f} "
                f"({rng[0]:.2f}-{rng[1]:.2f}) hue={bg['hue']:.0f} "
                f"chroma={bg['chroma']:.2f}{' SPLIT' if bg['split'] else ''} "
                f"-> {col['set']}/{col['key_name']}\n")
            if col["note"]:
                sys.stderr.write(f"WARNING: {slug} {col['note']}\n")
            if bg["split"]:
                sys.stderr.write(
                    f"WARNING: {slug} the background changes a lot across this "
                    f"span, so one colour has to serve both halves. If it reads "
                    f"badly, split the clip or set \"cap_colour\" in the slate.\n")

    # An override wins, but it must not leave the palette half-mixed: a forced ink
    # base with the light set's near-black stroke is dark type inside a dark
    # outline, which is the one combination that cannot be read at all. Derive the
    # stroke from the base that is actually going to be used.
    if forced_base:
        dark = rel_lum(forced_base) < 0.4
        col = dict(col, base=forced_base, set="dark" if dark else "light",
                   stroke=(255, 253, 249) if dark else (7, 10, 14))
    if forced_key:
        col = dict(col, key=forced_key,
                   key_name=str(cfg.get("key", cfg.get("cap_key"))))
    return col


PANEL_BG = "0x0E1319"


def panel_base(lab: str) -> str:
    """
    Put the first band on the panel, and make a REAL stream the main input.

    All three packed modes - share, duo, duo_share - used to build their panel
    from a generated source:

        color=c=...:s=1080x1920:r=30:d=58.4[stack];[stack][first]overlay=0:0[s1]

    and that is a 72 GB memory bug. A `color` source is infinitely fast and
    unbounded, so ffmpeg's scheduler pulls frames from it as quickly as the
    overlay will take them, while the band feeding the OVERLAY input arrives
    slowly (select -> split -> crop -> lanczos scale -> unsharp -> punch
    overlay). framesync then holds the fast side waiting for the slow one, and
    the queue is the whole clip.

    Measured on the 2026-08-28 duo clip that would not render, output discarded
    so the encoder cannot be blamed:

        color + two overlays    72.27 GB   killed by the OS at 590s
        pad  + one overlay       2.49 GB   exit 0 in 53s

    A 29x reduction, and it turns a clip that could not be made into one that
    takes under a minute. Padding the first band to the panel is EXACTLY the
    same composite - pad places it at (0,0) on a panel-coloured canvas of the
    panel's own size - and it drops one overlay stage as well, because the
    first band no longer has to be overlaid at all.

    Every other mode composites onto a real, decode-limited stream, which is
    why `head` and `head_follow` were never affected. share and duo_share were
    at risk for the same reason duo was; duo simply hit it first, being the
    heaviest of the three.
    """
    return f"[{lab}]pad={PANEL_W}:{PANEL_H}:0:0:{PANEL_BG}"


# ---------------------------------------------------- the frame is never dead ----
# A TALKING HEAD MUST NEVER SIT PERFECTLY STILL. `punch` is a two-state A/B
# toggle - 1.06x, minimum PUNCH_DWELL between flips - so BETWEEN flips the
# camera does not move at all. Not subtly: mathematically zero. Measured on the
# 08.28 delivered clip, 10 framing changes with a median 5.0s apart and a
# LONGEST UNCHANGED HOLD OF 9.1 SECONDS. Nine seconds of a frozen frame.
#
# Meanwhile the cutaways drift the whole time - BROLL_MOVES, five move pairs -
# so the stock footage breathes and the person talking does not. That is exactly
# backwards, and it is the difference between a clip that reads as edited and
# one that reads as exported.
#
# SO THE PUNCH BECOMES THE ACCENT AND THIS IS THE FLOOR. The picture is scaled
# DRIFT_OVERSCALE larger than the panel and a panel-sized window is walked
# slowly around inside the margin. Two sines on different periods, so the path
# never visibly repeats and never reaches the edge of its margin.
#
# BY OVER-SCALE AND A MOVING CROP, NOT BY zoompan. zoompan recomputes an integer
# crop per frame, and at these speeds - single pixels per second - the rounding
# IS the motion: it would sit still and then jump, which is judder rather than
# drift. This is the same shape broll_drift already uses for cutaways, including
# its `2*round(../2)` even-grid trick, for the same reason: yuv420p chroma wants
# even offsets, and rounding spreads the sub-pixel error either side of the true
# curve instead of always trailing it.
#
# THE VERTICAL CENTRE IS BIASED UP. A larger crop y takes the window lower in
# the scaled picture, which puts the FACE HIGHER in frame - the safe direction,
# because HEADROOM's whole complaint is chins running under the platform chrome.
# So the drift averages slightly kinder to that check than the still frame did.
# A TRIANGLE, NOT A SINE, AND A 1px GRID. Both were measured, not chosen.
#
# A sine spends most of its time near a turning point, where its velocity goes
# to zero - and a pixel grid turns "very slow" into "stopped". Measured on the
# first build of this: at the peaks the frame SAT STILL FOR 1.8 SECONDS and then
# jumped 2px, twice per period, which is judder rather than drift and it lands
# exactly where the eye has settled. A triangle holds constant speed the whole
# way and only turns twice per period.
#
# THE GRID IS 2px WHETHER WE ASK FOR IT OR NOT, and an earlier version of this
# comment claimed otherwise. ffmpeg FLOORS crop x/y to even on yuv420p, so an
# odd offset renders identically to the even one below it - measured directly:
#     crop=32:32:10  vs  :11  ->  byte-identical output
#     crop=32:32:11  vs  :12  ->  mean abs diff 27.17
# The first build of this drift "fixed" the judder by rounding to whole pixels
# and measured the improvement by evaluating the EXPRESSION in Python, which is
# not what ships. The delivered step was 2px all along.
#
# So the fix is velocity, not rounding: at 8px/s a 2px step lands every 7.5
# frames, which is visible; the amplitudes and periods below are set to ~14px/s,
# which puts a step on each axis every ~4 frames and, because the two axes are
# on different periods, moves the frame about every 2. Verified on delivered
# pixels rather than on the expression.
DRIFT_ON = bool(CFG.get("drift", True))
DRIFT_OVERSCALE = _num("drift_overscale", 0.05)
DRIFT_AMP_X = _num("drift_amp_x", 20.0)
DRIFT_AMP_Y = _num("drift_amp_y", 26.0)
# Velocity is 4*amp/period, so these set the SPEED: 14.5 and 13.9 px/s,
# chosen so a 2px step lands about every 4 frames on each axis.
DRIFT_PERIOD_X = _num("drift_period_x", 5.5)
DRIFT_PERIOD_Y = _num("drift_period_y", 7.5)
DRIFT_BIAS_Y = _num("drift_bias_y", 10.0)   # + raises the face; see above

# A LIGHT GRADE, because the clips are only as good as the camera behind them
# and this is the one lever that narrows the gap between them. A guest on a flat
# webcam and the host on a good one currently ship as two different-looking
# shows. Deliberately small: contrast and saturation only, no curves, no
# vignette - enough to make them siblings, not enough to be a look of its own.
#
# It lives INSIDE reframe_chain on purpose. The caption-colour probe samples
# this same chain, so the words are coloured against the pixels that actually
# ship; a grade applied later would shift the picture out from under the colour
# that was chosen for it.
GRADE_ON = bool(CFG.get("grade", True))
GRADE_CONTRAST = _num("grade_contrast", 1.03)
GRADE_SATURATION = _num("grade_saturation", 1.05)


def _even(n: float) -> int:
    return int(round(n / 2.0)) * 2


def face_chain(sharpen: str = "unsharp=3:3:0.4:3:3:0.0") -> str:
    """
    scale -> sharpen -> [slow drift] -> [light grade], for a face framing.

    ONE definition, used by every mode that puts a face full-frame, so framings
    A and B of a punch drift TOGETHER - the toggle stays a discrete step laid
    over a continuously moving picture rather than the only motion in the clip.
    """
    if not DRIFT_ON:
        chain = f"scale={PANEL_W}:{PANEL_H}:flags=lanczos,{sharpen}"
        return chain + (f",eq=contrast={GRADE_CONTRAST}:saturation={GRADE_SATURATION}"
                        if GRADE_ON else "")

    sw, sh = _even(PANEL_W * (1 + DRIFT_OVERSCALE)), _even(PANEL_H * (1 + DRIFT_OVERSCALE))
    mx, my = sw - PANEL_W, sh - PANEL_H
    cxm, cym = mx / 2.0, my / 2.0 + DRIFT_BIAS_Y
    # Never let the window reach the edge of its own margin - a clamped drift
    # stops dead at the limit, which is worse than not drifting at all.
    ax = min(DRIFT_AMP_X, max(0.0, cxm - 2))
    ay = min(DRIFT_AMP_Y, max(0.0, min(cym, my - cym) - 2))
    # Triangle in [-1, 1]: 4*|mod(t/P + 0.25, 1) - 0.5| - 1.
    #
    # THE +0.25 PUTS t=0 AT THE MIDDLE OF THE TRAVEL, not at an end of it.
    # Without it the clip OPENS on the extreme of the drift - 14px right and
    # 18px low of the framing that head_box/centre_on_face computed and that
    # preflight's HEADROOM measured - so the composition checked before the
    # render is not the composition in the first frame. Starting centred means
    # the opening frame is exactly the intended crop and the drift moves away
    # from it in both directions.
    def tri(amp: float, per: float) -> str:
        # the comma inside mod() is ESCAPED - an unescaped one ends the filter
        return rf"{amp:.1f}*(4*abs(mod(t/{per:.2f}+0.25\,1)-0.5)-1)"
    x = f"round({cxm:.1f}+{tri(ax, DRIFT_PERIOD_X)})"
    y = f"round({cym:.1f}+{tri(ay, DRIFT_PERIOD_Y)})"
    chain = (f"scale={sw}:{sh}:flags=lanczos,{sharpen},"
             f"crop={PANEL_W}:{PANEL_H}:{x}:{y}")
    return chain + (f",eq=contrast={GRADE_CONTRAST}:saturation={GRADE_SATURATION}"
                    if GRADE_ON else "")


def reframe_chain(mode: str, out_dur: float, *, slug: str = "", punch: dict | None = None,
                  start: float = 0.0, end: float = 0.0,
                  head_crop: list[int] | None = None,
                  crop_x: int | None = None,
                  duo_crops: list[list[int]] | None = None,
                  pip_crop: list[int] | None = None,
                  share_crop: list[int] | None = None,
                  face_h: int | None = None,
                  follow_crops: list[list[int]] | None = None,
                  follow_pips: list[list[int]] | None = None,
                  follow_windows: list[tuple[float, float]] | None = None) -> str:
    """
    The ffmpeg chain that turns the source into the finished 1080x1920 picture.

    Lifted out of render() so it has exactly ONE definition. Two things need it
    now: the render itself, and the caption-colour probe, which has to sample the
    picture AFTER reframing or it measures pixels the words never touch. A second
    copy of this geometry that drifted from the first would pick colours for a
    crop that is not the one being shipped, and nothing would look wrong until a
    keyword vanished on a phone.
    """
    fg = ""
    if mode == "head":
        if not (head_crop or HEAD_CROP) and _touches(start, end, "gallery"):
            raise SystemExit(
                f"\n{slug}: this span is a GALLERY (several faces side by side) "
                f"and mode 'head' has no head_crop.\n"
                f"Without one it centre-crops the wall and lands between faces. "
                f"Give head_crop for the speaker's panel.\n")
        # Per-clip crop wins over the project default: on a two-up interview one
        # clip is the guest and the next is the host, so the half cannot be a
        # single global setting.
        # 608 at a 1080x1920 panel, centred by default; a per-clip crop wins over
        # the project default, because on a two-up interview one clip is the guest
        # and the next is the host. head_box() owns all of that AND the re-cut to
        # the panel's aspect - see it for why preflight has to ask the same
        # function rather than keep its own copy.
        if head_crop or HEAD_CROP:
            check_box(slug, "head_crop", head_crop or HEAD_CROP)
        cw, ch, cx, cy = head_box(head_crop, crop_x, at=start,
                                  dur=(end - start) if end else None)
        # A tightened crop means a real upscale, so a light unsharp goes back over
        # it. Keep it gentle - heavy sharpening on a webcam source finds the
        # compression blocks, not the detail.
        chain = face_chain()
        if punch and punch.get("windows"):
            # Framing B is cut from the SOURCE at the same quality as A, about
            # the face centre mapped back into source pixels.
            fx, fy = punch.get("face") or (PANEL_W / 2, 760)
            bw, bh, bx, by = _punch_box((cw, ch, cx, cy),
                                        (cx + fx * cw / PANEL_W, cy + fy * ch / PANEL_H))
            fg = (f"split[pA][pB];"
                  f"[pA]crop={cw}:{ch}:{cx}:{cy},{chain}[A];"
                  f"[pB]crop={bw}:{bh}:{bx}:{by},{chain}[B];"
                  f"[A][B]overlay=0:0:enable='{punch_enable(punch['windows'])}'")
        else:
            fg = f"crop={cw}:{ch}:{cx}:{cy},{chain}"
    elif mode == "conversation":
        # ONE FACE AT A TIME, AND IT FOLLOWS THE FLOOR. The owner, 2026-08-28:
        # "if we're doing a duo clip and it's single face, if, for example,
        # Steve is talking, and then Steve Flanagan talks after, it will switch
        # different talkers."
        #
        # This is the answer to a real gap rather than a fifth way to pack the
        # panel. On a two-up the slate has had exactly two options: `head` with
        # one fixed crop, which shows a SILENT FACE for every second the other
        # person holds the floor, or `duo`, which stacks both and halves
        # everybody. Neither is right for an exchange where the floor genuinely
        # moves, which is most of a two-hander - and the head crop is the
        # better-looking of the two whenever one person IS talking. So: take the
        # head crop, and move it.
        #
        # IT IS THE PUNCH LADDER'S SHAPE, NOT A NEW MECHANISM. Both crops are
        # cut from the source at full quality and one is overlaid on the other
        # under an `enable` gate - the same split/crop/crop/overlay the punch
        # already uses, for the same reason (a crop cannot be animated, so the
        # switch is a cut). What is new is only WHERE the gate's windows come
        # from: turns.plan() measures who is speaking, second by second.
        #
        # THE SWITCH IS A HARD CUT AND THAT IS DELIBERATE. A dissolve between
        # two framings of the same room reads as a mistake rather than a move -
        # it is the one place in this pipeline where two pictures are the same
        # scene, so any blend looks like a glitch. Broadcast cuts between
        # cameras; so does this.
        boxes = follow_crops or CFG.get("follow_crops")
        if not boxes or len(boxes) != 2:
            raise SystemExit(
                "mode 'conversation' needs follow_crops: two [w,h,x,y] head crops,\n"
                "one per speaker, in the SAME order as follow_tiles.\n"
                "analyze.py prints head_crop_left and head_crop_right for a two-up.")
        if not follow_windows:
            raise SystemExit(
                "mode 'head_follow' has no turn schedule. render() builds one\n"
                "from turns.plan(); a clip reaching here without it would show\n"
                "one speaker for its whole length, which is plain `head`.")
        # The same scale+sharpen every head crop gets: both framings are real
        # upscales of a half-frame, so they must be treated identically or the
        # switch shows a change in sharpness as well as in person.
        chain = face_chain()
        for i, bx in enumerate(boxes):
            check_box(slug, f"follow_crops[{i}]", bx)
        a = head_box(list(boxes[0]), None)
        b = head_box(list(boxes[1]), None)
        # POINT EACH CROP AT ITS OWN SPEAKER. See centre_on_face.
        _tl = list((CFG.get("follow_tiles") or {}).values())
        if end > start and len(_tl) == 2:
            a = centre_on_face(a, (_tl[0][2], _tl[0][2] + _tl[0][0]),
                               start, end - start)
            b = centre_on_face(b, (_tl[1][2], _tl[1][2] + _tl[1][0]),
                               start, end - start)
        fg = (f"split[fA][fB];"
              f"[fA]crop={a[0]}:{a[1]}:{a[2]}:{a[3]},{chain}[FA];"
              f"[fB]crop={b[0]}:{b[1]}:{b[2]}:{b[3]},{chain}[FB];"
              f"[FA][FB]overlay=0:0:enable='{punch_enable(follow_windows)}'")
    elif mode == "conversation_share":
        # TEMPLATE 3. Whoever is talking on top, the shared screen below, and
        # the top band CUTS between speakers exactly as `conversation` does.
        #
        # It is `share` with a following face band, not a new kind of panel: the
        # packing, the fill-the-face / fit-the-app split and the app's edge
        # extension are all pack_share's, unchanged. What moves is which camera
        # tile is scaled into the face band at any moment.
        #
        # It REPLACES duo_share, which put both tiles side by side across the
        # top. The owner, 2026-08-28: "they'll never be two people on the same
        # screen share. It'll just be one person at the top, and then the screen
        # share at the bottom. And then if it switches the talking, then the
        # person at the top will switch." Side by side also halves each face on
        # a band that is already the smaller half of the panel.
        pips = follow_pips or CFG.get("follow_pips")
        if not pips or len(pips) != 2:
            raise SystemExit(
                "mode 'conversation_share' needs follow_pips: two [w,h,x,y] "
                "camera tiles,\none per speaker, in the SAME order as "
                "follow_tiles.\n")
        if not follow_windows:
            raise SystemExit(
                "mode 'conversation_share' has no turn schedule. render() builds "
                "one from\nturns.plan(); without it the face band would hold one "
                "speaker for the whole\nclip, which is plain 'share'.\n")
        for i, bx in enumerate(pips):
            check_box(slug, f"follow_pips[{i}]", bx)
        sw, sh, sx, sy = check_box(slug, "share_crop",
                                   share_crop if share_crop else SHARE_CROP)
        # THE FIRST TILE SIZES THE BAND. pack_share needs one tile aspect to
        # decide how the panel splits, and a rig's two camera tiles are the same
        # shape - they come out of one compositor. Using the first rather than
        # averaging keeps the band identical to what `share` would produce for
        # that speaker, so switching a clip between the two modes does not move
        # the seam.
        p0 = tuple(pips[0])
        fh, band_h = pack_share(sw, sh, face_h, tile=(p0[0], p0[1]))
        chain = f"scale={PANEL_W}:{fh}:flags=lanczos,unsharp=5:5:0.7:5:5:0"

        def _pip(src: str, box, out: str) -> str:
            w, hh, x, y = fill_crop(tuple(box), PANEL_W / fh, anchor="bottom")
            return f"{src}crop={w}:{hh}:{x}:{y},{chain}[{out}];"

        # Split INSIDE the face chain, so split_labels still asks for two source
        # copies (one for the face, one for the app) rather than three.
        fg = ("split[cA][cB];" +
              _pip("[cA]", pips[0], "faceA") +
              _pip("[cB]", pips[1], "faceB") +
              f"[faceA][faceB]overlay=0:0:"
              f"enable='{punch_enable(follow_windows)}'[face];" +
              fit_chain("[fgsrc2]", (sw, sh, sx, sy), PANEL_W, band_h, "screen") +
              panel_base("face") + "[s1];"
              f"[s1][screen]overlay=0:{fh + SPLIT_GAP}")
    elif mode == "duo":
        # Both speakers stacked, for a stretch where they are actually talking to
        # each other. Cropping to one half in a genuine exchange leaves whoever is
        # off-frame talking over a silent face; this keeps the dialogue visible.
        #
        # The bands FILL, edge to edge. An earlier version fitted the crop to the
        # band height and let the leftover width show blurred - that kept whole
        # heads but put dead space down both sides, which is worse. With the panel
        # full bleed each band is 953px tall, which takes enough of a 1080p half to
        # keep the face intact; only hair comes off the top. Author duo_crops at
        # the band's aspect and they fill without distortion.
        boxes = duo_crops or CFG.get("duo_crops")
        if not boxes or len(boxes) != 2:
            raise SystemExit(
                "mode 'duo' needs duo_crops: [[w,h,x,y] top, [w,h,x,y] bottom].\n"
                "analyze.py prints a pair for a two-up master.")
        band = (PANEL_H - SPLIT_GAP) // 2
        want = PANEL_W / band
        pw = (punch or {}).get("windows") or []

        def _band(src: str, box: list[int], out: str) -> str:
            # re-cut to the band's aspect rather than stretching to it
            w, hh, x, y = fill_crop(check_box(slug, "duo_crops", box), want)
            chain = (f"scale={PANEL_W}:{band}:flags=lanczos,"
                     f"unsharp=3:3:0.4:3:3:0")
            if not pw:
                return f"{src}crop={w}:{hh}:{x}:{y},{chain}[{out}];"
            # BOTH BANDS PUNCH TOGETHER, on the same windows - see PUNCH_MODES.
            # The split is INSIDE the band chain, so split_labels is unchanged and
            # the top-level graph still asks for one source copy per band.
            #
            # keep_badge, for the reason _punch_box already records: a two-up half
            # burns its lower third into the bottom of the frame, and punching
            # about the face shaved the name off on the 08.22 clip. SKILL.md's
            # duo rule says the same thing from the other side - keep the badge
            # inside the crop, a half-cut name reads as a mistake. At a 6% shrink
            # the face stays framed either way; the badge does not.
            bw, bh, bx, by = _punch_box((w, hh, x, y), (x + w / 2, y + hh * 0.4),
                                        keep_badge=True)
            return (f"{src}split[{out}0][{out}1];"
                    f"[{out}0]crop={w}:{hh}:{x}:{y},{chain}[{out}A];"
                    f"[{out}1]crop={bw}:{bh}:{bx}:{by},{chain}[{out}B];"
                    f"[{out}A][{out}B]overlay=0:0:"
                    f"enable='{punch_enable(pw)}'[{out}];")

        fg = (_band("", list(boxes[0]), "top") +
              _band("[fgsrc2]", list(boxes[1]), "bot") +
              panel_base("top") + "[s1];"
              f"[s1][bot]overlay=0:{band + SPLIT_GAP}")
    elif mode == "duo_share":
        # Two people AND the shared screen: both camera tiles side by side in a
        # strip across the top, the app filling everything below.
        #
        # Side by side rather than stacked, because stacking them would eat twice
        # the height and this panel has none to spare - the screen is the reason
        # the clip exists. A short wide strip also matches what the source gives
        # us: meeting PIP tiles are landscape, so each one drops into half the
        # width with almost no trimming.
        boxes = duo_crops or CFG.get("duo_crops")
        if not boxes or len(boxes) != 2:
            raise SystemExit(
                "mode 'duo_share' needs duo_crops (the two camera tiles) and "
                "share_crop (the app).")
        half = (PANEL_W - SPLIT_GAP) // 2
        sw, sh, sx, sy = check_box(slug, "share_crop",
                                   share_crop if share_crop else SHARE_CROP)
        for b in boxes:
            check_box(slug, "duo_crops", b)
        # Same rule as `share`: no bars. The camera strip absorbs whatever height
        # the app does not want, and a two-tile strip has a floor, so clamp it.
        # face_h stays None when the clip does not set one, so pack_share can size
        # the strip from what the app actually wants. `face_h or DUO_SHARE_FACE`
        # was never None, so the deriving branch was unreachable and the strip was
        # pinned at 420 - which then forced the app to be trimmed to fill.
        # The strip is sized off the SHORTER of the two tiles, and each tile is
        # only half the panel wide, so the band height that needs no crop is
        # half * h / w rather than PANEL_W * h / w.
        short = min(boxes, key=lambda b: b[1] / b[0])
        fh, band_h = pack_share(sw, sh, face_h,
                                tile=(short[0], short[1]), tile_w=half)

        def _tile(src: str, box: list[int], out: str) -> str:
            w, hh, x, y = fill_crop(tuple(box), half / fh, anchor="bottom")
            return (f"{src}crop={w}:{hh}:{x}:{y},scale={half}:{fh}:flags=lanczos,"
                    f"unsharp=5:5:0.6:5:5:0[{out}];")

        fg = (_tile("", list(boxes[0]), "fa") +
              _tile("[fgsrc2]", list(boxes[1]), "fb") +
              fit_chain("[fgsrc3]", (sw, sh, sx, sy), PANEL_W, band_h, "scr") +
              panel_base("fa") + "[s1];"
              f"[s1][fb]overlay={half + SPLIT_GAP}:0[s2];"
              f"[s2][scr]overlay=0:{fh + SPLIT_GAP}")
    else:
        # Screen share: the speaker has to stay on screen, so their camera tile
        # goes above the shared screen. The browser chrome and the tile's own
        # meeting furniture are cropped away - visible tabs are the one thing
        # that makes a clip read as a screen recording rather than a post.
        #
        # Both crops are per-clip overridable: a show with TWO people in stacked
        # PIP tiles needs whichever of them is talking, and what is worth showing
        # of the shared screen changes with what is on it (a chart wants the
        # recent price action, a dashboard wants the full table).
        pw, ph, px, py = check_box(slug, "pip_crop", pip_crop if pip_crop else PIP_CROP)
        sw, sh, sx, sy = check_box(slug, "share_crop",
                                   share_crop if share_crop else SHARE_CROP)
        # The two bands add up to the panel exactly. They are packed differently
        # on purpose:
        #
        #   the FACE is FILLED - cropped to the band's aspect and scaled to cover
        #   it, because trimming the edges of a webcam tile costs nothing;
        #
        #   the APP is FITTED - never trimmed, with the spare filled by extending
        #   its own edge pixels, because trimming a text slide cuts words off the
        #   ends of the bullets and that is the one thing a share clip cannot
        #   afford. Extending the edge is not a bar: on a solid slide the colour
        #   simply continues, and on a chart it continues the chart's background.
        fh, band_h = pack_share(sw, sh, face_h, tile=(pw, ph))
        pw, ph, px, py = fill_crop((pw, ph, px, py), PANEL_W / fh, anchor="bottom")
        chain = f"scale={PANEL_W}:{fh}:flags=lanczos,unsharp=5:5:0.7:5:5:0"
        if punch and punch.get("windows"):
            # The punch is on the FACE TILE only; the chart below is built once
            # and never scales (its axis labels sit at its edge).
            fx, fy = punch.get("face") or (PANEL_W / 2, fh / 2)
            if not (0 <= fy <= fh):
                fx, fy = PANEL_W / 2, fh / 2
            bw, bh, bx, by = _punch_box((pw, ph, px, py),
                                        (px + fx * pw / PANEL_W, py + fy * ph / fh),
                                        keep_badge=True)
            face = (f"split[pA][pB];[pA]crop={pw}:{ph}:{px}:{py},{chain}[faceA];"
                    f"[pB]crop={bw}:{bh}:{bx}:{by},{chain}[faceB];"
                    f"[faceA][faceB]overlay=0:0:enable='{punch_enable(punch['windows'])}'[face];")
        else:
            face = f"crop={pw}:{ph}:{px}:{py},{chain}[face];"
        fg = (face +
              fit_chain("[fgsrc2]", (sw, sh, sx, sy), PANEL_W, band_h, "screen") +
              panel_base("face") + "[s1];"
              f"[s1][screen]overlay=0:{fh + SPLIT_GAP}")
    return fg


# ----------------------------------------------------------------- tempo ----
# Measured across 44 delivered clips: median 197 words per minute, mean 197,
# stdev 27, range 142 to 263. That is already fast, because the silence pass has
# taken about 19% of the runtime out before anyone sees it, so a BLANKET speed-up
# is the wrong instrument. At a flat 8% the median goes to 213 and the top of the
# range to 284, which no one produces naturally.
#
# So the rate is measured per clip and pulled toward a band. A 142 WPM speaker
# gets the full allowance, a 230 WPM speaker gets nothing, and most clips sit
# inside the band already and are left alone.
SPEED_BAND = (_num("wpm_min", 185.0), _num("wpm_max", 225.0))
SPEED_MAX = _num("speed_max", 1.12)   # transparent-ish; 1.15 is audible
SPEED_MIN = _num("speed_min", 0.96)   # slowing is for a sprinter only
SPEED_DEAD = 0.02                                # under 2% is not worth the resample


def measure_wpm(words: list[Word], dur: float) -> float:
    """Words per minute of the DELIVERED body, after silence has been removed."""
    if dur <= 0 or not words:
        return 0.0
    return len(words) / dur * 60.0


def tempo_for(words: list[Word], dur: float, override) -> tuple[float, str]:
    """
    How much to speed this clip up, and why. 1.0 means leave it alone.

    Returns (factor, reason). An explicit per-clip `speed` wins outright, because
    a clip whose whole point is a slow deliberate line should not be hurried by
    an average.
    """
    if override is not None:
        return max(0.5, min(2.0, float(override))), "set on the clip"
    if not CFG.get("adaptive_speed", True):
        return 1.0, ""
    wpm = measure_wpm(words, dur)
    if wpm <= 0:
        return 1.0, ""
    lo, hi = SPEED_BAND
    if wpm < lo:
        f = min(lo / wpm, SPEED_MAX)
    elif wpm > hi:
        f = max(hi / wpm, SPEED_MIN)
    else:
        return 1.0, f"{wpm:.0f} WPM, already inside {lo:.0f}-{hi:.0f}"
    if abs(f - 1.0) < SPEED_DEAD:
        return 1.0, f"{wpm:.0f} WPM, within {SPEED_DEAD:.0%} of the band"
    return round(f, 3), f"{wpm:.0f} -> {wpm * f:.0f} WPM"


# ---------------------------------------------------------------- b-roll ----
# Baked cutaways live in the SHARED library (see broll.py), so an asset approved
# on one show is reusable on the next. A per-project broll/ is still honoured -
# older show folders have one, and their archived slates must keep rendering.
BROLL_LIB = Path(os.environ.get(
    "QM_BROLL_LIB", Path.home() / ".claude/skills/qm-clip-cutter/broll-library"))


def broll_asset(name: str) -> Path | None:
    """The baked cutaway `name`, from the shared library or a local broll/."""
    for d in (BROLL_LIB, WORK / "broll"):
        f = d / name
        if f.exists():
            return f
    return None
# The cutaway budget. One owner for each number: broll.py imports these rather
# than keeping its own copy, because three different defaults for `hold` (2.6 at
# bake, 4.0 at render, 4.0 at preflight) meant an insert authored without one
# baked 2.6s of picture and was played for 4.0s, the last 1.4s a frozen frame.
# 4.2 -> 2.6 -> 4.0, and BROLL_EVERY 18.0 -> 11.0 -> 14.0, and the two MUST move
# together because what stays constant is their ratio: the share of the body the
# cutaways occupy.
#
# THE SECOND MOVE IS THE OWNER OVERRULING THE REFERENCE, AND HE IS RIGHT TO.
# 2.6 came from measuring gaRRMkRjoHE, whose cutaways run 1.60 to 2.40s. He
# watched a clip cut to it and said: "i feel like the broll is to short and its
# to fast it needs to be min 3 seconds so it doesnt feel rushed. cuz the broll +
# signup feels very rushed."
#
# The reference does not carry an invitation button inside its cutaways. Ours
# does, and that is the whole difference: a 2.0s cutaway has to land a picture,
# bring a button up, hold it long enough to read, take it away and cut back -
# five beats in two seconds, which is a cram however clean each individual cut
# is. The reference's holds are right for a reference that only has to show a
# picture. **Do not "correct" this back toward 1.9s on the grounds that the
# measurement says so.** The measurement was of a clip with less to do.
#
# So BROLL_HOLD_MIN is back to the owner's own 3.0 and BROLL_HOLD is 4.0: an
# insert gets 3.0 to 4.0 seconds, `propose` picking per clause inside that.
#
# Measured off the owner's own reference (see BROLL_STYLE) the
# thing to copy is not the amount of b-roll but its GRANULARITY - gaRRMkRjoHE
# spends 22% of its runtime on cutaways, exactly what we already spent, split
# into six inserts of a median 1.75s rather than three of 4.2s.
#
# On the 57.3s body of the 08.25 test clip:
#     original 3 inserts x 4.2s = 12.6s = 22.0% of body, one every 19.1s
#     08.25 a   5 inserts x 2.6s = 13.0s = 22.7% of body, one every 11.5s  (too fast)
#     08.25 b   4 inserts x 3.5s = 14.0s = 24.6% of body, one every 14.2s  <- ships
# The share is unchanged, the picture changes 67% more often, and the 30%
# ceiling is not approached. It does not go all the way to the reference's 8.6s
# because BROLL_MIN_FACE (6.0s of speaker between inserts) binds first: at 7
# inserts the layout needs 56.25s of a 57.3s body and one extra second of
# collapsed silence would make the clip infeasible. Going further means arguing
# BROLL_MIN_FACE down, and that number exists to stop the clip becoming a
# montage - the reference does run three of its gaps under 6s, so there is a
# case, but it is a separate decision and needs its own evidence.
#
# THIS IS ONLY AFFORDABLE BECAUSE THE TRANSITION IS NOW A CUT. Under the slide,
# 0.633s of every window was travel, so a 2.6s hold would have settled for 1.97s
# - under the old 3.0s floor and visibly a flash. With BROLL_IN = BROLL_OUT = 0
# the whole 2.6s is settled picture. Put BROLL_STYLE back to "slide" and these
# numbers are wrong; they are a matched set.
# 4.2 -> 3.6 with the floor drop. This is not only the longest an insert may be:
# broll_target divides the ceiling BY it, so a high max suppresses the COUNT -
# int(0.38 * 59.3 / 4.2) is 5 where int(0.38 * 59.3 / 3.6) is 6. Shortening the
# maximum is what buys the extra cutaway, which is the "more in each clip" half
# of the brief. Band is now 3.2..3.6 against 3.7..4.6 before.
BROLL_HOLD = _num("broll_hold", 3.6)          # what an insert is held for, in DELIVERED seconds.
                                                          # 4.2, not 4.0, since the cover/reveal transitions
                                                          # (2026-08-22): 0.433s of the window is travel, so
                                                          # the SETTLED picture is 3.77s
# BACK TO 3.0, AND IT IS THE OWNER'S NUMBER TWICE OVER. It was his floor on the
# settled picture originally; it was lowered to 2.0 on 2026-08-25 because the
# reference holds its cutaways 1.60 to 2.40s and a cut leaves the whole window
# settled; and he watched that and said "it needs to be min 3 seconds so it
# doesnt feel rushed". Twice now, unprompted, he has landed on three seconds.
#
# Note what this floor MEANS now that the travel is zero: it is the whole
# insert, not what is left of it after a rise and a swipe. A 3.0s insert is 3.0s
# of settled picture, where under the slide it would have been 2.37s.
# LOWERED TO 2.5 ON 2026-08-30, AND THAT REVERSES THE NOTE ABOVE. The owner had
# landed on three seconds twice, unprompted, so it doesn't "feel rushed" - and
# then watched a reference short cutting every 1.03 second and asked for quicker
# b-roll with more of it per clip: "I don't mind faster b-roll, but then we need
# to be having more b-roll in each clip ... lower the floor to 2 1/2 seconds."
#
# It is written down because it is a REVERSAL, not a tuning. If clips start
# reading as rushed, this is the number that did it, and 3.0 is where it was.
BROLL_HOLD_MIN = _num("broll_hold_min", 2.5)      # floor on the settled picture

# ---------------------------------------------------- HOW LONG, BY WHAT IT IS --
# THE OWNER, 2026-08-30: "Some of the clips can be shorter. Like, some of the
# b-rolls don't have to be the same length. Right? Like, a picture if it just
# says someone's name that I sent is, boom. Cut to Elon. Right? It's half a
# second, not even. You need to build it dynamically for the b-roll that's
# what's being shown."
#
# THE ONE FINDING THAT MAKES THIS SAFE. BROLL_HOLD_MIN is TWO rules welded into
# one number, and only one of them is about the picture:
#
#   1. how long a picture needs to be on screen to be read, and
#   2. how long the SIGN-UP needs to arrive, settle and leave.
#
# The recorded rejection of short b-roll names the second one, not the first -
# "the broll + signup feels very rushed" - and the note under it already
# answers itself: "The reference does not carry an invitation button inside its
# cutaways. Ours does, and that is the whole difference."
#
# So the floor belongs to the BUTTON, and the button rides ONE insert per clip.
# Splitting the two rules is what makes a half-second flash legal WITHOUT
# reversing anything he said. BROLL_HOLD_MIN keeps its value and its meaning -
# it is now the floor for an insert that CARRIES the invitation, and the top of
# a ladder instead of the whole ladder.
#
# THE GAP BETWEEN 1.60 AND 3.20 IS A WALL, NOT A HOLE. An insert at 2.0s is the
# length he rejected by name, and it was the button that made it rushed. A
# carrier must clear the button's five beats; a flash has no button and no beats
# to fit. Nothing should ever land in between, so the bands are deliberately
# DISCONTINUOUS and the spread check below reads a ratio under 2.0 as "these all
# fell to one floor" rather than as variety.
BROLL_FLASH_MIN = _num("broll_flash_min", 0.55)   # the shortest insert that is a picture and not a blink
BROLL_FLASH_MAX = _num("broll_flash_max", 1.60)   # above this an insert is a beat, and owes the button
# WHERE 0.55 COMES FROM, and it is two independent measurements landing together:
#   - the reference short (mx9x5ni_zAs, 26 shots) has a MINIMUM shot of 0.55s,
#     a median of 0.86 and a max of 1.65. Nothing in it is shorter.
#   - swept over all 25 BROLL_MOVES pairs, a DRIFTING insert uncovers the
#     speaker below a 0.53s window: the entrance drift is still running when the
#     exit drift starts and on a same-sign pair they ADD, reaching 96px of
#     excursion against BROLL_BLEED's 91.8px of margin. A flash is therefore
#     always static (see BROLL_DRIFT_MIN_HOLD) and 0.55 keeps a margin over the
#     point where even that would stop being true.
#
# Drift is off on a flash - see BROLL_DRIFT_MIN_HOLD, defined with the drift
# constants it is derived from.
# The insert COUNT is derived from the body length now, by broll_target() below,
# so there is no default cap and BROLL_BIG_BODY (3 inserts at 45s, 2 below it) is
# gone. The hard 3 was set when clips ran 45 to 60 seconds and it does not scale:
# on the 91s body of the 08.21.26 McGlone clip it gives one cutaway every 30
# seconds, which is more than double the 12s the CADENCE check warns at.
BROLL_MIN_INSERTS = _int("broll_min_inserts", 2)     # "obviously we want more than one"
BROLL_MAX_CFG = CFG.get("broll_max_inserts")                # an explicit project.json cap, when a show wants one
# "is not None", not truthiness. `int(x) if x else None` read 0, 0.0 and false as
# UNSET, so a project.json carrying "broll_max_inserts": 0 - which reads like "no
# cutaways at all" - silently became no cap and a 91s body still asked for 5.
# Silent, and in the wrong direction. The clamp up to BROLL_MIN_INSERTS is the
# other half: a cap of 0 or 1 is a nonsense value, and it must not be able to
# drive the target under the floor the rest of the pipeline enforces.
BROLL_MAX_CFG = (max(BROLL_MIN_INSERTS, int(BROLL_MAX_CFG))
                 if BROLL_MAX_CFG is not None else None)
# 16 -> 10 with the same brief: "more b-roll in each clip". On a 59.3s body that
# is 6 cutaways where 16.0 gave 4 - a 50% increase in how often the picture
# changes, which is the half of "faster" that shortening the hold does not buy.
# 10.0 -> 6.0 on 2026-08-30. THE OWNER PUT A NUMBER ON IT: "I would almost
# wanna say in a minute clip, there needs to be at least ten." 6.0 is what makes
# a 60s body ask for 10, and it is the first time this constant has been set by
# a stated target rather than inferred from a reference.
#
# This ONLY works with the two changes that land beside it. At the old fixed
# 3.2s hold the budget cannot pay for the target at ANY length - simulated,
# the average seconds available per insert at the target is 2.85 / 2.53 / 2.44 /
# 2.28 for a 45 / 60 / 90 / 120s body, every one under the floor. A target of
# ten is arithmetically unreachable without variable holds, so shipping this
# number alone would produce a gate with no key.
BROLL_EVERY = _num("broll_every", 6.0)            # one cutaway per this many seconds of body
# 6.0 -> 5.5 on 2026-08-25, and this one is a JUDGEMENT CALL rather than a
# measurement, so it is flagged as such and is the easiest thing here to revert.
#
# The rule exists to stop a set of cutaways reading as a montage and it should
# not move to make one clip fit. What moved it is that it had started blocking
# the thing the owner keeps asking for: "all the different words that come up
# need to have the correct b roll for it". On the Ellman clip the three right
# pairings - a road on "long-term commitment", gears on "a lot of moving parts",
# scales on "weigh it all together" - are 5.67s apart at the tightest, so at 6.0
# the only legal anchors in that gap were the function words "That does not mean
# that you should", i.e. the choice was a correct picture on the wrong word or
# no picture at all.
#
# 5.5 is small enough to be honest about: it is an 8% change, it unblocks
# word-accurate placement, and it is still more than twice the 2.47s shortest
# face gap measured in the owner's own reference short. It is NOT licence to
# drift further - if a clip needs less than 5.5s of face between two cutaways,
# the answer is a different span, not a smaller number.
# 5.5 -> 4.5 -> 2.5, and the original note said this was "NOT licence to drift
# further". It has moved twice anyway, and this time it is MEASURED rather than
# argued. Instrumenting the rejection paths on a real clip, the placeable
# candidates were lost like this:
#
#     6 dropped  too close to the previous insert   <- this number
#     4 dropped  outside the placeable window       <- LEAD_IN / TAIL_CLEAR
#
# So the face gap was the binding constraint by a distance, and the owner's
# instruction after watching a delivered clip was flat: "you need to have more
# b-roll incorporated into all the clips going forward, almost double the
# amount". The subjects are THERE - 33 of 215 words in that body carry a
# picture - they were being rejected for sitting near each other, which is
# exactly what a dense stretch of speech looks like.
#
# 2.5s still keeps two cutaways from touching, which is what the rule was
# written for. If clips start reading as a montage rather than a person
# talking, this is the number that did it, and 4.5 is where it was.
#
# 2.5 -> 1.5 ON 2026-08-30, AND THIS IS THE THIRD MOVE. It is recorded as a move
# against a note that twice said not to move it, so the evidence has to carry it.
#
# THE OWNER NAMED A NEW REFERENCE and said "we don't want it exactly like it,
# but it's the feel": youtube.com/shorts/mx9x5ni_zAs. Measured - 25.4s, 26
# shots, 61 cuts a minute, shot lengths 0.55 / 0.86 / 1.65 (min / median / max).
# The thing that matters here is WHOSE shots those are. Pulling frames from the
# three shortest and the three longest, the SPEAKER is in both sets: he is in
# the rotation, not the bed under it. So the reference's face gaps - the time it
# returns to the presenter between two pictures - are themselves 0.55 to 1.65s.
#
# That is the measurement this constant never had. The 2.47s it was previously
# checked against came from the OTHER reference, which is a montage with a
# voice-over: it has no presenter to return to, so its "face gap" is not the
# same quantity. Comparing to it was comparing to a video that does not contain
# the thing being measured.
#
# 1.5 sits at the top of the reference's own range rather than at its median,
# which is the deliberate conservative end: this material is a person explaining
# something, not a highlight reel, and the face-on-screen rule still owns three
# quarters of the body. Measured on the 08.30 body it buys one more cutaway
# (6 -> 7); on denser speech it buys more.
#
# It is NOT the binding constraint on sparse material and lowering it further
# will not help there - the same body caps at 8 even at 1.0, because it carries
# an 18.7s stretch with no picturable word in it at all. That is an anchor
# supply problem and it belongs to the vocabulary, not to this number.
BROLL_MIN_FACE = _num("broll_min_face", 1.5)      # face time between the END of one insert and the NEXT
BROLL_LEAD_IN = _num("broll_lead_in", 5.0)       # clear of the hook card (opaque to 3.5s) and poster()
BROLL_TAIL_CLEAR = _num("broll_tail_clear", 3.0)    # clear of the frame endcard.append freezes for the wipe
BROLL_PAD = 0.25          # rounding allowance only - NOT a place to hide a short bake
# 0.30 -> 0.38, forced by the same request. Six inserts averaging ~3.6s is 21.6s
# of a 59.3s body - 36% - so the old ceiling would have refused the cadence the
# owner asked for by construction. This is the "more b-roll in each clip" half
# of it made legal, and it is the number that decides how much of the clip is
# NOT the speaker: at 0.38 he holds the frame for 62% of the body against 73%
# before. If clips start feeling like a slideshow with a voiceover, this is the
# one to walk back first.
BROLL_MAX_FRAC = _num("broll_max_frac", 0.38)     # never more than this share of the body. 0.14 when
                          # there was one end-placed insert, 0.24 when placement
                          # became word-synced, 0.30 on the user's retention
                          # push (2026-08-12): the picture changing often is the
                          # point, and six 2.4s cutaways in a 58s body is 25%.
                          # The face-on-screen rule still owns the other 70%.
# AND A FLOOR UNDER IT, new on 2026-08-30 with variable holds. See
# broll_floor_seconds: a cap alone is satisfiable by cutting to almost nothing,
# which is a real outcome once an insert can be half a second. Half the ceiling
# is the only non-arbitrary split and it clears every share the house has ever
# shipped (22%, 22%, 24.6%, 27.7%).
#
# DO NOT "TIDY" BROLL_MAX_FRAC DOWN AFTERWARDS. With short holds the spend lands
# around 17-24% against the 38% cap, so the cap reverts to being pure insurance,
# which is what it was before the density push made it load-bearing. Lowering it
# to match observed spend would make it the binding constraint again - the exact
# defect being removed from broll_target.
BROLL_MIN_FRAC = _num("broll_min_frac", round(BROLL_MAX_FRAC / 2.0, 3))
# ...AND A CEILING ON HOW LONG THE PICTURE MAY NOT CHANGE. BROLL_MIN_FACE is a
# floor on how CLOSE two cutaways may be and there has never been anything on
# the other side, so a clip could satisfy every rule and still sit on one shot
# for twelve seconds. The 08.26 Nike clip did exactly that - measured on the
# delivered file, the face ran unbroken for 12.8s at the open and 10.2s in the
# middle, against interior gaps of 3.0 to 5.9s everywhere else. That is the
# "not methodical" the owner was pointing at: not the cadence being irregular
# (it is, and so is the reference's), but two holes twice the size of the rest.
#
# DERIVED FROM THE CUT RATE so it moves when the cut rate moves. The reference
# short's longest shot is 1.65 against a mean of 0.98, i.e. 1.68x - so the
# longest gap a clip may show is 1.68 cut-intervals. At BROLL_EVERY 6.0 that is
# 10.1s.
#
# A WARN, NEVER A REFUSAL, and that is measured rather than cautious: re-scored
# over every slate on this machine, 19 of 19 clips carrying an approved insert
# exceed it, the worst at 36.1s. A gate that refuses the entire archive is the
# "--force it and then it protects nothing" failure this file already records.
# The best clip ever cut here sits at exactly 10.1s.
BROLL_GAP_MAX = round(BROLL_EVERY * 1.65 / 0.98, 1)
# HOW MUCH SPEAKER MUST FOLLOW A FLASH AT THE VERY END. BROLL_TAIL_CLEAR (3.0s)
# exists because endcard.append freezes the final frame for its wipe, so the
# last thing on screen must be the speaker. That is a rule about ONE frame, and
# applying three seconds of it refused a one-second portrait of a person the
# show names 2.1s from the end - see the flash exemption in broll.candidates.
# 1.0s is a second of face after the picture leaves: thirty frames, far more
# than the wipe reads, and short enough that a name at the end still lands.
BROLL_TAIL_FACE = _num("broll_tail_face", 1.0)
# The cutaway COMES UP and SWIPES OVER (the owner's words, 2026-08-22). It is a
# full-frame COVER over a static panel: it rises from below the frame to y=0
# over BROLL_IN, holds, and leaves to the LEFT over BROLL_OUT, revealing the
# speaker - whose framing has flipped underneath (see punch_windows), so every
# return is a new shot. Hard seam, no shadow, no dissolve, no zoom, no sound:
# the design panel rejected each of those as the CapCut/iOS card tell, and a
# whole-panel push as something that would move a share-mode chart with its
# axis labels at the edge. Both times are DELIVERED seconds; broll_chain scales
# them by the tempo.
#
# BOTH ARE SMOOTHSTEP, AND BOTH ARE LONGER THAN THE FIRST VERSION (0.233/0.200
# on a quart in and a cubic out), because the owner watched that one and called
# the transitions glitchy. He was right, and it was two faults measured on the
# delivered file:
#
#   THE RISE STROBED. An ease-out over a 1920px travel put 885px - 46% of the
#   frame height - into the first moving frame, then 536, 294, 140. There is no
#   motion blur here, so a jump that size does not read as a move at all, it
#   reads as a flash. On smoothstep over 10 frames the worst frame is 284px
#   (15%), and the whole curve is 54/146/215/261/284/284/261/215/146/54.
#
#   THE SWIPE NEVER FINISHED. The exit ran over [a1-BROLL_OUT, a1] but the gate
#   closes at a1-hb, so the last frame that was actually drawn sat at 58% of
#   the travel with 451px of the insert still on screen - and then the whole
#   451px disappeared between two frames. THAT was the pop. The travel now
#   completes one frame BEFORE the gate closes (see the denominator below), so
#   the last drawn frame is genuinely off the edge.
#
# The two together cost 0.633s of every window, so a 4.2s hold settles for
# 3.57s - still past the owner's 3.0s floor, which preflight measures as
# settled time. No motion blur: at 284px a frame the strobe is gone, and the
# only ways to fake blur here (tmix over the composite, sub-frame compositing)
# either soften the whole clip or cost more than the render.
# THE CUTAWAY IS A HARD CUT NOW, AND IT WAS THE OWNER'S OWN REFERENCE THAT
# SETTLED IT. This overturns the "COMES UP and SWIPES OVER" above, which was his
# instruction on 2026-08-22, so the evidence is written out in full rather than
# summarised - it is the only thing that justifies reverting a decision he made.
#
# On 2026-08-25 he watched the 08.25 clip and said "The transition is still not
# clean as the YT video i showed b4. needs to be more seemless ... seemless more
# transitions and smooth". "Still" is the word that matters: the slide had been
# tuned twice already (0.233/0.200 on a quart+cubic, then 0.333/0.300 on two
# smoothsteps) and it was still wrong. So the reference was DOWNLOADED and
# MEASURED instead of being tuned a third time.
#
# youtube.com/shorts/gaRRMkRjoHE, 1556 frames at 30fps, 51.87s. It is the SAME
# FORMAT as ours - a talking head on a dark studio background, karaoke captions
# burned on the picture, and b-roll cutaways that leave the speaker entirely and
# come back. Its picture changes were classified frame by frame:
#
#   EVERY CUTAWAY IS A HARD CUT. At all eleven measured changes the cut frame
#   is a clean member of the NEW picture (|cut - after| = 0.7 to 11.0 mean abs
#   luma) and shares nothing with the old one (|cut - before| = 48 to 156), and
#   on the cut frame ZERO of 360 columns and ZERO of 640 rows are closer to the
#   old picture than the new one. A slide, a wipe or a push leaves part of the
#   frame behind for a few frames by construction. Nothing is left behind. The
#   change occupies ONE frame.
#
#   IT CUTS TWICE AS OFTEN AS WE DO, FOR THE SAME SHARE OF THE RUNTIME. Six
#   cutaways in 51.87s - one every 8.6s, holds of 1.60 / 2.17 / 1.60 / 1.60 /
#   1.83 / 2.40s, median 1.75s - totalling 11.3s, which is 22% of the runtime.
#   Ours was 22% too. The share is identical; the GRANULARITY is not. That is
#   what "more transitions" means, and see BROLL_EVERY / BROLL_HOLD below.
#
# (The second reference, youtube.com/shorts/hYahU_Cqwp8, measures the same way:
# fourteen picture changes in 32.2s, every one a single-frame cut.)
#
# So a half-second sliding rectangle was never going to satisfy "seamless",
# however well its curve was cut - a cut has no seam to judge, which is the
# whole point. The slide is KEPT behind BROLL_STYLE = "slide" because he asked
# for it once and may want it back; do not delete it, and do not quietly make it
# the default again on the argument that a move is more designed than a cut.
#
# BROLL_IN / BROLL_OUT stay the ONE OWNER of the travel and are derived from the
# style, so everything downstream follows with no second switch to keep in step:
# punch_windows forces its framing flip at a1 - BROLL_OUT (which becomes a1
# exactly, the first uncovered frame - correct for a cut, where nothing is
# progressively exposed, so the return is ONE cut and not the double cut the
# comment there describes); preflight scores settled time as hold - (BROLL_IN +
# BROLL_OUT), which becomes the whole hold; broll.py derives MIN_HOLD and
# PAN_DONE from the same pair.
# BROLL_STYLE itself is read up beside CFG, because CTA_BROLL_PAD is derived
# from it a thousand lines above here.
# THE THIRD ANSWER, AND THE ONE THAT SHIPS. Three styles have now been put in
# front of the owner and the first two were both wrong in ways he named:
#
#   "slide"     the cover rises and swipes. Tuned twice. "The transition is
#               still not clean ... needs to be more seemless."
#   "cut"       a hard cut, measured off his own reference, which does exactly
#               this 28 times out of 28. He accepted it once - "that is good" -
#               and then watched a second clip and said "the way that this comes
#               in is still very kind of just, like, it's not smooth. It should
#               be like a seamless transition ... a little bit slower, a little
#               bit cleaner ... you can have it be smoother and kinda flow into
#               it." And then, unambiguously: "Every single b roll shot that
#               comes up has to transition into the video. That's the idea. The
#               smooth transition to the b roll, the smooth transition to the
#               sign up for free quasar markets, and then it should be a smooth
#               transition out."
#   "dissolve"  a cross-dissolve on the ALPHA, both directions. Ships.
#
# WHY THE REFERENCE MEASUREMENT DID NOT SETTLE IT. gaRRMkRjoHE hard-cuts every
# cutaway and that measurement is still correct; what it could not tell us is
# whether hard-cutting is what HE wants, and it is not. He has now said "smooth"
# or "seamless" about this element five times across three rounds. A measurement
# of somebody else's video is evidence about that video. Do not re-litigate this
# with the reference again - it has been asked and answered.
#
# NOTE WHAT THIS OVERRIDES. references/look.md rejected a dissolve by name as
# "the CapCut/iOS card tell", and the note at the top of this block still lists
# "no dissolve" among the things the design panel refused. That was a taste call
# made without the owner in the room; he has now asked for it three times in one
# message. Recorded so nobody reverts it as a regression.
#
# 0.35 rather than 0.25: "a little bit slower, a little bit cleaner". At 30fps
# that is ten and a half frames each way, which is long enough to read as a
# deliberate blend and short enough that the picture is fully itself for the
# middle of even the shortest legal insert.
BROLL_IN = 0.333 if BROLL_STYLE == "slide" else 0.35 if BROLL_STYLE == "dissolve" else 0.0
BROLL_OUT = 0.300 if BROLL_STYLE == "slide" else 0.35 if BROLL_STYLE == "dissolve" else 0.0


def broll_ramp(hold: float, k: float = 1.0) -> tuple[float, float]:
    """
    The dissolve for an insert of THIS length. One owner for the ramp.

    THE SENTENCE ABOVE BROLL_IN WAS AN OBSERVATION, NOT AN INVARIANT. It says
    the ramp is "short enough that the picture is fully itself for the middle of
    even the shortest legal insert" - true only because the shortest legal
    insert was 3.2s. The two `fade ... alpha=1` filters in broll_chain are
    CHAINED, so they SCALE the same alpha plane and therefore MULTIPLY wherever
    they overlap, which is any insert shorter than BROLL_IN + BROLL_OUT.

    MEASURED, on delivered pixels - a red insert composited over a blue base
    through the exact chain broll_chain emits, peak alpha of the centre pixel:

        hold  0.40 -> 0.275     hold 0.70 -> 0.996
        hold  0.50 -> 0.498     hold 1.50 -> 0.996
        hold  0.60 -> 0.675     hold 3.60 -> 0.996

    So a half-second cutaway today is not a cutaway. It is a 50%-opaque double
    exposure of the picture over the speaker's face that rises and falls without
    ever landing - "a luma spike that jumps and returns", which is the thing the
    reference reel was measured NOT to do. The owner's "boom, cut to Elon, half
    a second" is unrenderable until this is fixed.

    THE FIX IS A SHARE, NOT A CONSTANT. The ramps together may never take more
    than half the insert, so the picture is opaque for the middle at EVERY
    length by construction rather than by the numbers happening to line up.

    IT IS AN IDENTITY ON EVERYTHING EVER SHIPPED. r reaches 1.0 at
    2*(BROLL_IN+BROLL_OUT) = 1.4s and broll.MIN_HOLD has never been below 3.2s,
    so every clip in the archive re-renders byte-identically. Re-measured with
    the ramp in: 0.40/0.50/0.60/0.90/1.20 all peak 0.996, monotone in and out,
    with 5/7/8/12/16 fully opaque frames.

    The 3-frame floor keeps it a BLEND and not a cut - a per-insert hard cut is
    refused for the same reason `"broll_style": "cut"` is refused whole-slate
    ("There's animations for every b roll cut"), and 3 frames is the shortest
    ramp that yields two intermediate values, which is the least that can
    establish the monotone blend this element was certified on.
    """
    if BROLL_STYLE != "dissolve":
        return BROLL_IN * k, BROLL_OUT * k
    r = min(1.0, hold / (2.0 * (BROLL_IN + BROLL_OUT) * k)) if hold > 0 else 1.0
    lo = 3.0 / FPS
    return (max(lo, BROLL_IN * k * r), max(lo, BROLL_OUT * k * r))


# WHEN A BAKED PAN HAS ARRIVED. 275 of the library's stills are baked with a
# slow push that completes at this point and lands ON the subject; before it the
# picture is still travelling. broll.py owns the BAKE, this file owns the
# CONSTANT, so the renderer can seek past the travel on a short insert without
# importing broll (broll imports qmclip, never the reverse).
#
# DERIVED FROM BROLL_HOLD_MIN, NOT FROM THE FLASH FLOOR, and that is deliberate:
# it is baked into 1,795 assets already on disk, so it must not follow the flash
# floor down. Re-parenting it would give every asset baked afterwards a 0.5s
# whip-pan while the ones already baked ramp over three seconds, with no
# migration path - `sweep` has no PAN_DONE awareness at all.
BROLL_PAN_DONE = round((BROLL_HOLD_MIN + BROLL_IN + BROLL_OUT) * SPEED_MIN, 3)


# ------------------------------------------------- THE SHAPE OF THE DISSOLVE --
# THE OWNER, 2026-08-30, WATCHING A TEN-CUTAWAY CLIP: "it's still coming across
# as kind of glitchy ... the transitions and the way how they come up need to be
# more methodical ... it's coming across right now just like kinda shitty."
#
# `fade` IS LINEAR, AND THE LINEAR MIDDLE IS THE PROBLEM. A cross-dissolve spends
# its time at alpha 0.5, where the frame is neither picture - and both of ours
# are busy (a face over a chart, against a full-bleed photograph). Pulled frame
# by frame, the speaker ghosts through the picture for five frames at each end.
# That superimposition is what reads as cheap; it is not the dissolve's LENGTH.
#
# MEASURED, on the delivered clip's own frames. A frame is "ambiguous" when it
# sits more than 12 grey levels from BOTH source images - i.e. it looks like
# neither. Sweeping ramp length against ramp shape:
#
#     ramp   linear   smoothstep   smoothstep^2
#     0.35s     8          6            4          <- 0.35 is the shipped length
#     0.30s     7          5            3
#     0.25s     6          4            4
#     0.20s     6          4            2
#     0.15s     4          2            2
#
# So SHAPE buys as much as LENGTH: easing the 0.35s ramp halves the mush (8 -> 4)
# and gets the same result as shortening it to 0.20s linear. That matters,
# because the length is not ours to shorten - 0.35 is the owner's own number
# ("a little bit slower, a little bit cleaner") and shortening it walks back
# toward the hard cut he has rejected three times. The transition keeps exactly
# the timing he approved and stops being mush in the middle of it.
#
# HOW, WITHOUT PAYING FOR IT. `fade` has no easing and `geq` on the alpha plane
# costs 2.10s per insert at 1080x1920 against 0.16s for the fades - 13x, on a
# filter that runs per pixel per frame. A `lut` is a 256-entry table applied to
# the alpha channel AFTER the fades: the fade still writes a linear ramp, and
# the table re-maps that ramp's VALUES onto an S-curve. It needs no notion of
# time, so it is a lookup rather than an evaluation. Measured: 0.20s against
# 0.16s, a 25% cost on the insert chain and invisible in a 210s render.
#
# Applied TWICE because once is not enough on this material: smoothstep^1 leaves
# 6 ambiguous frames, smoothstep^2 leaves 4. Delivered alpha ramps, measured:
#     linear         0.12 0.25 0.38 0.50 0.62 0.75
#     smoothstep     0.05 0.15 0.32 0.49 0.67 0.84
#     smoothstep^2   0.01 0.07 0.24 0.49 0.75 0.93
# The plateau is untouched - the table maps 0 to 0 and 255 to 255 - so peak
# alpha stays 1.0 and broll_ramp's guarantee is unaffected.
_ALPHA_U = "(val/255)"
_ALPHA_S1 = f"({_ALPHA_U}*{_ALPHA_U}*(3-2*{_ALPHA_U}))"
BROLL_ALPHA_LUT = f"255*({_ALPHA_S1}*{_ALPHA_S1}*(3-2*{_ALPHA_S1}))"


# --------------------------------------------- cutaway transition variety ----
# ONE VOCABULARY, SEVERAL SENTENCES. The owner, 2026-08-25: "We wanna be able to
# switch around the transitions from b roll clips to going out. Right? It should
# not always be fade ... all the animations are smooth and slow moving and clean,
# and it just flows across the screen ... We don't want any staticness."
#
# WHAT DOES NOT VARY: THE CROSS-DISSOLVE. Every entry below dissolves on the same
# BROLL_IN / BROLL_OUT ramp through the same two `fade` filters on the alpha
# plane. That is not conservatism, it is the third answer to a question this
# owner has now been asked three times - SKILL.md's "The cutaway CROSS-DISSOLVES,
# and that is the third answer" records him rejecting the slide ("still not
# clean") and then the hard cut ("it's not smooth") - so putting either back into
# a rotation would re-ship, on one insert in six, something he has already turned
# down by name. "It should not always be fade" is answered by giving the dissolve
# somewhere to come FROM, not by taking the dissolve away.
#
# WHAT VARIES: a small DRIFT underneath it, and its direction. The picture
# arrives already moving and settles, or holds and drifts off - which is what
# "it just flows across the screen" is a description of.
#
# BROLL_DRIFT IS 80px, AND THE SIZE IS THE ARGUMENT. Against the rejected slide's
# 1920px rise and 1080px swipe it is 4.2% of the frame's height and 7.4% of its
# width. Over the smoothstep it runs on, the worst single frame measures 8px -
# 0.4% of the frame - two orders of magnitude inside the 1/6-of-the-frame rule
# fx_ease cites. It is a drift, not a move.
#
# NOTE WHAT THIS RELAXES, BECAUSE IT IS A REAL DECISION AND NOT A DETAIL.
# references/look.md's compass is "picture arrives from BELOW, type arrives from
# the RIGHT, everything leaves LEFT", one rule for every element. A rotation with
# four directions in it is that rule relaxed FOR TRAVELS UNDER ABOUT 100px, on
# the argument that a 3% offset is beneath the resolution at which a direction
# reads as a rule at all. The compass still owns every large travel in the clip -
# the hook card's 60px arrival and full-frame exit, the end card's wipe, and
# BROLL_STYLE "slide" - and none of them is touched. It is recorded here because
# the alternative, keeping the compass, allows exactly one legal pair, which is
# no variety at all; it is not something to discover later from a diff.
BROLL_VARY = bool(CFG.get("broll_vary", True)) and BROLL_STYLE == "dissolve"
BROLL_DRIFT = 80.0          # DELIVERED px an insert travels under the dissolve
# THE DRIFT IS LONGER THAN THE DISSOLVE, AND THAT IS THE WHOLE DIFFERENCE
# BETWEEN THIS READING AS A MOVE AND NOT READING AT ALL.
#
# The first version ran the drift over BROLL_IN / BROLL_OUT - the dissolve's own
# 0.35s - on an out_quart, and measured on the delivered file that put 97% of
# the travel inside the frames where the insert is under 50% opaque. The picture
# finished moving before anybody could see it. Frame-stepping the second
# cutaway's entrance confirmed it: by the frame the trucks are readable, they
# have already stopped.
#
# So the drift gets its OWN clock, tied to the cutaway's beats rather than to
# the fade: it lands exactly as the invitation arrives (CTA_BROLL_LEAD) and it
# starts moving again exactly as the invitation finishes leaving
# (CTA_BROLL_TAIL). "The picture lands and holds ALONE" - the sentence that set
# those two numbers - becomes literally true, because the picture is still
# LANDING through that beat instead of standing still in it. About 38% of the
# travel, some 30px, now happens at full opacity.
BROLL_DRIFT_IN = CTA_BROLL_LEAD
BROLL_DRIFT_OUT = CTA_BROLL_TAIL
# A FLASH DOES NOT DRIFT, AND THE THRESHOLD IS THESE TWO CLOCKS ADDED.
# The entrance takes BROLL_DRIFT_IN to land and the exit starts BROLL_DRIFT_OUT
# before the end, so on any insert shorter than their sum the picture is taken
# off screen while it is STILL TRAVELLING - it never "lands and holds alone",
# which is the drift's entire stated purpose.
#
# It is also the point where the drift becomes actively wrong rather than merely
# pointless. Swept over all 25 BROLL_MOVES pairs in 0.01s steps, the worst
# horizontal excursion against BROLL_BLEED's 91.8px of margin:
#
#     hold 0.90 -> +10px   0.55 -> +2px   0.50 -> -96px   0.45 -> -106px
#
# Below ~0.53s the entrance and exit drifts overlap and ADD on a same-sign pair,
# the insert slides off its own over-scale, and a hard-edged strip of the
# speaker appears at the frame edge. BROLL_BLEED's assert cannot catch this: it
# is a compile-time check on BROLL_DRIFT against W and H with no hold in it.
# Under this threshold an insert renders soft/soft at scale=W:H, exactly as a
# "soft" pair already does today.
BROLL_DRIFT_MIN_HOLD = round(BROLL_DRIFT_IN + BROLL_DRIFT_OUT, 3)
# SMOOTHSTEP, NOT out_quart. fx_ease's rule is that the curve follows the
# distance, and a quart's 4x peak velocity is what it warns about - but the
# reason here is the other end of the same argument: a quart spends its travel
# in the first two frames, which are the frames this element is invisible on.
# The smoothstep is 1.5x peak and puts half the distance in the middle third,
# where the picture can be seen.
BROLL_DRIFT_EASE = "in_out"
# THE INSERT IS OVERSIZED SO A DRIFT NEVER UNCOVERS A SEAM, and this is the one
# thing that has to be right or the whole idea is worse than doing nothing.
#
# The bake is 1080x1920 EXACTLY (broll.py bake_video / bake, cover-cropped), so
# an insert translated BROLL_DRIFT px shows that much SPEAKER behind a hard edge at
# whatever opacity the dissolve has reached. That is a seam, on the one element
# this owner has called "seamless" in three separate rounds.
#
# So the bleed is DERIVED from the drift rather than picked: the insert is
# scaled up by whatever it takes to cover BROLL_DRIFT on the NARROW axis, with a
# 1.15x margin, and the assert below is what stops a later edit to BROLL_DRIFT
# from silently re-opening the seam. A hand-set 1.10 was tried first and is
# wrong: it gives 54px of horizontal bleed against an 80px drift. At the
# shipped numbers the margin is 91.8px horizontal and 163.2px vertical against
# 80px of travel, and it does NOT move with the tempo - the drift is a
# distance and the tempo scales time. See broll_offsets, where multiplying the
# distance by the tempo as well took that margin to exactly 0px at SPEED_MAX.
BROLL_BLEED = round(1.0 + 2.0 * BROLL_DRIFT * 1.15 / W, 3)      # 1.170
assert W * (BROLL_BLEED - 1.0) / 2.0 >= BROLL_DRIFT and \
       H * (BROLL_BLEED - 1.0) / 2.0 >= BROLL_DRIFT, \
    (f"BROLL_BLEED {BROLL_BLEED} does not cover a {BROLL_DRIFT}px drift: the "
     f"insert would uncover the speaker behind a hard edge")

# The direction the picture TRAVELS, as a unit vector in screen space (+x right,
# +y down). An ENTRANCE starts BROLL_DRIFT px against it and arrives at rest; an
# EXIT leaves BROLL_DRIFT px along it. One sign convention, so "up" means the
# same thing at both ends of an insert.
#
# There is no "zoom" here and its absence is deliberate. It reopens two vetoes
# nobody has overruled: look.md's design panel rejected a zoom-through "because
# it was a second vocabulary", and broll.py's bake_video says "NO KEN BURNS ON
# MOVING FOOTAGE ... two things moving at once" - which is what a render-time
# push on an asset already carrying a baked 1.00->1.06 push would be.
BROLL_MOVES: dict[str, tuple[float, float]] = {
    "soft":  (0.0, 0.0),     # the plain dissolve, exactly as it ships today
    "up":    (0.0, -1.0),    # compass-native: the picture arrives from below
    "down":  (0.0, 1.0),
    "left":  (-1.0, 0.0),    # compass-native on the way OUT
    "right": (1.0, 0.0),
}

# THE ROTATION. Deterministic by construction: a SHA-1 of the slug picks the
# starting offset and each insert takes the next entry, so one slate renders one
# file forever.
#
# hashlib, NOT the builtin hash(). hash() of a str is salted per process by
# PYTHONHASHSEED, so the same slate would pick a different rotation on every run
# and nobody would find out until a delivered clip was re-rendered and came back
# different - which is exactly the class of silent drift this file keeps
# recording.
#
# AT MOST ONE HALF OF ANY INSERT MOVES. Two different moves in one insert - in
# from the right, out downward - is an object with no consistent physical story,
# and that IS the "assembled rather than authored" failure recorded for type. A
# MATCHED pair is worse still: in from below and out downward is the picture
# retreating the way it came, which is why the compass says "arrives from BELOW,
# leaves LEFT" rather than "arrives and leaves the same way".
#
# Adjacent entries differ, wrap included, so "never the same pair twice running"
# is a property of the TABLE rather than a check at use time - and the assert
# guards it, because the table is the thing somebody will edit.
BROLL_ROTATION: tuple[tuple[str, str], ...] = (
    ("soft",  "soft"),     # today's insert, byte-identical
    ("up",    "soft"),     # rises into place, dissolves away
    ("soft",  "left"),     # dissolves in, drifts off left (the house compass)
    ("right", "soft"),
    ("soft",  "up"),
    ("left",  "soft"),
    ("soft",  "down"),     # settles downward on the way out
)
assert all(BROLL_ROTATION[i] != BROLL_ROTATION[(i + 1) % len(BROLL_ROTATION)]
           for i in range(len(BROLL_ROTATION))), \
    "BROLL_ROTATION: adjacent entries must differ, wrap included"
assert all(m in BROLL_MOVES for pr in BROLL_ROTATION for m in pr)
# AND EVERY DEFINED MOVE IS ACTUALLY REACHABLE. "down" was in BROLL_MOVES,
# documented, tested by the selftest's 25-pair sweep - and absent from the
# rotation, so no clip could ever use it. A move nobody can select is a move that
# is not really there, and the assert is what stops the next one going the same
# way.
assert set(BROLL_MOVES) == {m for pr in BROLL_ROTATION for m in pr}, \
    f"unreachable cutaway move(s): " \
    f"{sorted(set(BROLL_MOVES) - {m for pr in BROLL_ROTATION for m in pr})}"

# The (move_in, move_out) each window in BROLL_WINDOWS was rendered with,
# INDEX-ALIGNED with it. A second module record rather than a fourth return
# value, for the reason already recorded on BROLL_WINDOWS itself.
#
# ALIGNMENT IS THE WHOLE CONTRACT AND IT IS EASY TO BREAK: broll_chain can drop
# an insert in two places after `live` is built - a missing asset, and a window
# collapsed under 0.8s by the silence removal - so this is appended in the SAME
# statement as `windows.append`, never indexed off enumerate(live).
#
# Nothing in the RENDER reads it: the invitation's inset is a beat rather than a
# clearance (see cta_windows) and every move rides one ramp, so there is no
# per-insert number for the graph to look up. It is published because the
# VERIFICATION needs it - "did insert 2 actually drift left" is a question you
# can only ask a delivered file if you know what it was supposed to do - and
# because the alignment rule has to live next to something.
BROLL_STYLES: list[tuple[str, str]] = []


def broll_move_pairs(items: list[dict], slug: str) -> list[tuple[str, str]]:
    """
    (move_in, move_out) per insert, in the order broll_chain walks `items`.

    Indexed off the SLATE, not off what happened to bake, so fetching a missing
    asset cannot change the transitions on inserts that already rendered.

    A slate pins either half of any insert with "move_in" / "move_out". Named
    that way and not "in"/"out" because a bare "in" in a slate row greps to
    nothing and reads like a timestamp.
    """
    if not BROLL_VARY:
        # The off switch, and it returns the file to EXACTLY today's behaviour
        # rather than to something near it: ("soft", "soft") emits x = y = "0"
        # and the same two fade filters, which is the current code path.
        return [("soft", "soft")] * len(items)
    # THE RANK IS NOT PART OF THE CLIP'S IDENTITY. build_all passes render() the
    # DELIVERED name, "NN-slug", because that is what the file is called - so
    # hashing it made the rotation depend on the clip's position in the slate.
    # Re-ordering the slate, or dropping a clip, silently re-rolled the
    # transitions on every OTHER clip; measured, "no-good-answers-on-hormuz" and
    # "02-no-good-answers-on-hormuz" pick different rotations, and the delivered
    # file had the second. That breaks the promise two lines up - "one slate
    # renders one file forever" - which is the whole reason the seed is a hash
    # and not a counter.
    key = re.sub(r"^\d+-", "", slug)
    seed = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
    out: list[tuple[str, str]] = []
    prev: tuple[str, str] | None = None
    for i, b in enumerate(items):
        base = BROLL_ROTATION[(seed + i) % len(BROLL_ROTATION)]
        pair = (str(b.get("move_in") or base[0]).lower(),
                str(b.get("move_out") or base[1]).lower())
        for m in pair:
            if m not in BROLL_MOVES:
                raise SystemExit(
                    f"\nUNKNOWN CUTAWAY MOVE {m!r} on the insert at "
                    f"{b.get('at')}s of {slug}.\n"
                    f"Legal: {', '.join(sorted(BROLL_MOVES))}\n")
        if pair == prev:
            # ONLY REACHABLE THROUGH A PIN - the rotation cannot repeat a pair
            # inside its own length. An author's pin is not overruled, because
            # silently rewriting an explicit instruction is worse than the
            # repetition it prevents; it is REPORTED, because "I pinned two and
            # they came out identical" should not need a frame-by-frame.
            sys.stderr.write(
                f"note: insert {i} of {slug} repeats the move pair "
                f"{pair[0]}/{pair[1]} from the one before it - both halves are "
                f"pinned in the slate.\n")
        prev = pair
        out.append(pair)
    return out


def broll_offsets(move_in: str, move_out: str, a0: float, a1: float,
                  din: float, dout: float, k: float = 1.0) -> tuple[str, str]:
    """
    (x, y) overlay expressions for one insert, in SOURCE time.

    The insert is BROLL_BLEED oversized and RESTS at the negative half of that
    bleed, so it covers the frame at every point of both travels.

    ARRIVALS OF SMALL THINGS GET out_quart AND DEPARTURES in_cubic - fx_ease
    says so, and says why. 80px of 1920 is a small thing: the smoothstep that
    governs BROLL_STYLE "slide" is there because a 1920px travel on a quart puts
    46% of the frame into one frame. The quart also puts the fastest frame of
    the entrance at u=0, where the alpha is still near zero, which is the best
    place in the travel for it to be.

    The exit's denominator is dout MINUS ONE FRAME, so the travel finishes on
    the last frame the gate actually draws. That correction is already on the
    slide - see "THE SWIPE NEVER FINISHED" in look.md - and without it a drift
    would stop at 58% and the rest would pop.

    Both offsets land on EVEN pixels for the same reason the slide's do: the
    panel is yuv420p, so the chroma planes are half resolution and an odd offset
    splits a chroma sample across the moving edge and shimmers along it.
    """
    rx = W * (BROLL_BLEED - 1.0) / 2.0
    ry = H * (BROLL_BLEED - 1.0) / 2.0
    # NOT SCALED BY k, AND THAT WAS A BUG. `k` is the tempo, which compresses
    # TIME - the durations below already carry it. Multiplying the DISTANCE by it
    # too made a tempo'd clip drift further as well as faster, and BROLL_BLEED's
    # assert is written against the unscaled BROLL_DRIFT: measured over all 25
    # move pairs, the coverage margin fell from 11.8px at tempo 1.0 to exactly
    # 0px at SPEED_MAX 1.12 and went NEGATIVE above it - a hard-edged strip of
    # the speaker along the frame edge, which is the one failure this whole
    # over-scale exists to prevent.
    d = BROLL_DRIFT
    ix, iy = BROLL_MOVES[move_in]
    ox, oy = BROLL_MOVES[move_out]
    f1 = 1.0 / FPS
    # The drift's own durations, NOT the dissolve's - see BROLL_DRIFT_IN. `din`
    # and `dout` are still taken so the caller's tempo scaling flows through one
    # place, and so the exit can never start before the picture is whole.
    tin = max(din, BROLL_DRIFT_IN * k)
    tout = max(dout, BROLL_DRIFT_OUT * k)
    ein = fx_ease(BROLL_DRIFT_EASE, fx_unit(a0, tin))
    eout = fx_ease(BROLL_DRIFT_EASE, fx_unit(a1 - tout, max(f1, tout - f1)))

    def axis(rest: float, i: float, o: float) -> str:
        # No if() anywhere: fx_unit CLAMPS, so `ein` is already 1 after the
        # entrance and `eout` is already 0 before the exit. The two terms
        # compose on disjoint ranges by construction, which is one less place
        # for an off-by-one than the slide's paired if()s.
        # SIGNED FORMATTING, not a hand-written operator. Writing "-" and then
        # a value that is itself negative emits "--64.0", which ffmpeg's
        # expression parser is under no obligation to read as a plus. Let the
        # format spec carry the sign and there is only ever one operator.
        e = f"{-rest:.1f}"
        if i:
            e += f"{-i * d:+.1f}*(1-{ein})"
        if o:
            e += f"{o * d:+.1f}*{eout}"
        # round, NOT floor. Both keep the offset on the even grid the yuv420p
        # chroma planes want, but floor always errs the same way - so a travel
        # whose ideal per-frame step is under 2px (the first and last three
        # frames of every drift, measured: 0.71px and 2.03px against a 6.64px
        # peak) sat still for a frame and then moved 2px, twice. Rounding halves
        # the worst position error and spreads it either side of the true curve
        # instead of always trailing it.
        return f"2*round(({e})/2)"

    return axis(rx, ix, ox), axis(ry, iy, oy)


def delivered_body(dur: float, rem: list[tuple[float, float]],
                   speed: float | None = None) -> float:
    """The body the viewer actually watches: the span minus the silence the
    render cuts, played back at the clip's tempo.

    ONE OWNER, because there were two readings of it and both fed broll_target.
    propose() in broll.py measured `dur - sum(removed)` with no speed division;
    preflight divided the same figure by `speed`. Under the old flat 2-or-3 rule
    a few percent never changed the answer, but with a step every BROLL_EVERY
    seconds it can: at SPEED_MAX 1.12 the two readings differ by about 6% of the
    body, a third of a step at 91s. It stayed dormant only because every clip
    since 08.12.26 ships "speed": 1.0.

    Preflight's arithmetic is the correct definition and is reproduced here
    exactly. The tempo pass is applied to the finished picture, so a second of
    source at 1.12 reaches the viewer as 0.89 seconds, and the cadence rule
    counts DELIVERED seconds - that is what "one cutaway per 18s" means.
    """
    return (dur - sum(b - a for a, b in rem)) / float(speed or 1.0)


def broll_target(body: float) -> int:
    """How many cutaways a body of this length wants."""
    # WHERE 18.0 CAME FROM. The clip the owner called "literal perfect" on
    # 2026-08-21 (Mike McGlone / Bloomberg Intelligence) measured 5 inserts of
    # 4.0s in a 91s body: 20.0s of picture, 22% of the body, one cutaway every
    # 18 seconds. That cadence is the standard now. It also reproduces the old
    # fixed rule exactly at a 45s body (3 inserts), so re-scoring the archive
    # does not turn a shipped clip into a failure.
    #
    # ROUNDING IS LOAD-BEARING. Python's round() is banker's rounding, so
    # round(2.5) is 2, and a 45s body is exactly 2.5 cutaways - it would come
    # back 2 and silently break the one case this rule has to reproduce.
    # math.floor(x + 0.5) is what makes 45 -> 3.
    raw = math.floor(body / BROLL_EVERY + 0.5)
    # `ceiling` USED TO BE INSURANCE AND IS NOW LOAD-BEARING. At BROLL_EVERY 18.0
    # neither term was below `raw` for any body over about 13s, and SKILL.md
    # recorded the scan that fixed the threshold: "the first one to bite is the
    # 30% ceiling at BROLL_EVERY 15.95 ... Do not read the 30% ceiling as
    # protecting anything at the cadence we actually run."
    #
    # BROLL_EVERY is 14.0 now, which is BELOW that threshold. Re-measured over
    # every body from 41.0s to 200.0s in tenths, `ceiling` truncates `raw` on
    # 166 of 1591 - about one body length in ten, and they are lengths the house
    # ships in (50s, 63s, 80s, 91s, 120s). That is the ceiling doing exactly its
    # job, not a fault: at 14.0 and a 4.0s hold, `raw` would ask for more than
    # 30% of the body on those lengths. It is written down because the old
    # comment said the opposite and somebody reading it would trust the wrong
    # thing.
    #
    # `feasible` is still insurance and still never binds at these values.
    # THE CEILING TERM IS GONE, AND THAT IS THE CHANGE THAT BUYS THE DENSITY.
    # It converted a BUDGET into a COUNT by dividing by a per-item PRICE, and
    # the price it used was the MAXIMUM hold - so it charged a half-second name
    # flash 3.6 seconds. Measured at BROLL_EVERY 6.0, it was the binding term at
    # every length and it bound SILENTLY, with no warning and no preflight line:
    #
    #     body   raw  ceiling  ->  target      (asked for)
    #     45.0    8      4          4            8
    #     60.0   10      6          6           10
    #     90.0   15      9          9           15
    #
    # The identical term was already deleted from preflight's count ceiling for
    # exactly this reason ("it priced every insert at BROLL_HOLD 4.0 while real
    # slates hold 3.0 ... the fix is one owner each"). It survived here only
    # because broll_target runs before any hold exists to sum.
    #
    # The share of the body does NOT disappear - it becomes a budget in SECONDS,
    # spent where the holds are actually chosen (broll_budget below, enforced by
    # candidates(), by preflight's FRAC line and by render()'s hard raise, all
    # three of which already sum the REAL holds). BROLL_HOLD now means only what
    # it says: the longest an insert may be held. Raising it no longer silently
    # cuts the count.
    #
    # `feasible` IS RE-PRICED AT THE FLOOR. It is a permissive bound - "can this
    # many be laid out at all" - so pricing it at the maximum hold is what made
    # it dormant insurance that never bound on any real body. At the flash floor
    # it becomes a true upper bound and starts doing work on short bodies.
    feasible = int((body - BROLL_LEAD_IN - BROLL_TAIL_CLEAR + BROLL_MIN_FACE)
                   / (BROLL_FLASH_MIN + BROLL_MIN_FACE))
    n = min(raw, feasible)
    if BROLL_MAX_CFG is not None:   # an explicit project.json override still wins
        n = min(n, BROLL_MAX_CFG)
    # The floor outranks everything above it, including feasibility. Under a body
    # of about 22s that returns a count the timeline cannot lay out inside
    # BROLL_LEAD_IN and BROLL_TAIL_CLEAR, and under about 27s it returns one that
    # breaks the 30% ceiling render() enforces. Nothing b-roll has ever run over
    # is near either. RE-MEASURED over every slate.json on the Desktop, 92 clips
    # that carry a start and an end: the shortest body among the 23 that carry
    # inserts is 51.7s ("the-k-shaped-economy", 08.18.26). The 41.8s this line
    # used to give was measured over a population that missed a whole slate file.
    # Eight clips in the archive DO sit under 27s, the shortest 17.2s
    # ("thirty-four-ais"), and not one of them carries a single insert, so the
    # floor has never been asked about them. That is why this is stated rather
    # than handled: it is the floor's doing, not an error in the maths, and it
    # would only bite if one of those short clips were re-cut with cutaways.
    # The figures are span over speed, which is the body BEFORE silence removal
    # takes its couple of percent off - archive slates do not record the
    # removals. On the 08.21.26 standard clip that gap is a 93.5s span against a
    # 91.0s body, so it moves no clip across either threshold here.
    return max(BROLL_MIN_INSERTS, n)


def broll_budget(body: float) -> float:
    """
    The SECONDS of picture a body of this length may spend on cutaways.

    This is what BROLL_MAX_FRAC has always meant, given a name and one owner.
    It was previously an anonymous expression in three files, and the copy
    inside broll_target divided it by a hold to turn it into a count - which is
    the defect broll_target now records at length.

    Spend it against the REAL holds, which is what preflight's FRAC line and
    render()'s hard raise already do. A count cannot be derived from it without
    assuming a price per insert, and the whole point of variable holds is that
    there is no single price.
    """
    return BROLL_MAX_FRAC * body


def broll_floor_seconds(body: float) -> float:
    """
    The seconds of picture below which a clip is UNDER-covered.

    BROLL_MAX_FRAC caps the top and nothing has ever held the bottom, which is
    survivable while every insert is 3.2s and becomes a hole the moment they are
    not: ten 0.6s flashes hit a count target of ten with 6.0s of picture - 10%
    of a 60s body, LESS b-roll than the 16.4s that shipped before this change,
    while passing a gate that exists to ask for more. Counting cuts alone can be
    satisfied by cutting to nothing.

    Half the ceiling is the only non-arbitrary split, and it clears every value
    the house has ever shipped: the reference short 22%, the 08.21 "literal
    perfect" McGlone standard 22%, the 08.25b set 24.6%, the last delivered clip
    27.7%. It refuses the all-flash case and nothing else.
    """
    return BROLL_MIN_FRAC * body


# The (a0, a1) windows the last broll_chain call placed, in source time. Read
# by punch_windows, which forces a framing flip at every a1 - BROLL_OUT (under
# the cover, on its first exit frame) and freezes inside [a0 - 1.0, a1). A module record rather than a fourth return value, so the
# signature other callers use does not change.
BROLL_WINDOWS: list[tuple[float, float]] = []


def broll_chain(items: list[dict] | None, start: float,
                rem: list[tuple[float, float]], out_dur: float,
                first_input: int, hold_scale: float = 1.0,
                words: list["Word"] | None = None,
                slug: str = "") -> tuple[str, list[str], str]:
    """
    Timed full-frame cutaways, as a filter fragment plus the inputs it needs.

    Returns (filter_fragment, ffmpeg_input_args, output_label). With nothing to
    do it returns ("", [], "base") and the graph is byte-identical to before.

    THE TIMELINE. Windows are authored in SOURCE seconds, the way `mute` already
    is, because that is how you read them off a transcript. But the clip the
    viewer sees has had the silence cut out of it, so a source second is not a
    clip second. The conversion goes through the SAME remap the captions use -
    apply_removals' arithmetic over the same `rem` set - rather than a parallel
    calculation, because two ways of computing the same number is how the
    captions drifted off the words the first time this pipeline had a timeline.

    THE SPEAKER LEAVES THE FRAME. SKILL.md's rule is that the face is on screen
    at all times, and this is its one written exception, granted deliberately for
    a cutaway that returns. The insert is bounded hard - see BROLL_MAX_FRAC and
    the guards in render() - because the exception is for a beat, not for a
    montage.
    """
    live = [b for b in (items or []) if b.get("approved") and b.get("asset")]
    BROLL_WINDOWS[:] = []
    BROLL_STYLES[:] = []
    if not live:
        return "", [], "base"

    def to_clip(t_src: float) -> float:
        """
        A slate anchor (raw source seconds) -> its place on the composite.

        SOURCE SPACE, not delivered. Every overlay in this graph is applied
        BEFORE the trailing setpts, so the timeline these inserts land on is the
        pre-tempo one; render() passes the un-scaled removal set and the
        pre-tempo body length to match. The old version did its own walk over
        tempo-scaled windows and under-subtracted inside a window - see
        remap_time, which is now the single map everything uses.
        """
        return max(0.0, remap_time(t_src - start, rem))

    frag, inputs, cur = "", [], "base"
    windows: list[tuple[float, float]] = []
    styles: list[tuple[str, str]] = []
    # OFF THE SLATE, not off what survives the loop - see broll_move_pairs.
    moves = broll_move_pairs(live, slug)
    n = 0
    for bi, b in enumerate(live):
        path = broll_asset(str(b["asset"]))
        if path is None:
            sys.stderr.write(
                f"WARNING: b-roll asset {b['asset']} is missing from {BROLL_LIB}. "
                f"Run: python3 broll.py fetch\n")
            continue
        a0 = to_clip(float(b["at"]))
        # RE-SNAP onto the word in THIS render's decode. `words` here is the
        # exact list the caption PNGs are built from, already remapped through
        # the removals and the tempo - so after this, the picture and the
        # caption showing the word are synchronous by construction. The stored
        # anchor only gets the search into the right second; whisper moves word
        # boundaries a few hundred ms between decodes, and the slate's time came
        # from a different decode than this render's.
        on = str(b.get("on") or "").lower()
        if on and words:
            # 2.5s, not 1.5. The two decodes disagreed by 1.56s on a real word
            # ("exploded": 41.24s in the render's pass, 42.8s in the propose
            # pass), and a window tighter than the disagreement silently skips
            # the snap - which re-ships the exact lateness this exists to kill.
            # 2.5s is still far inside the spacing of repeated words: the other
            # "explode" in the same clip is 7s away.
            near = [w for w in words
                    if split_token(w.text)[0].lower() == on
                    and abs(w.start - a0) <= 2.5]
            if near:
                w0 = min(near, key=lambda w: abs(w.start - a0))
                a0 = max(0.0, w0.start - 0.15)     # the cut leads the word
                sys.stderr.write(
                    f"b-roll: snapped {b.get('term','?')!r} to the word "
                    f"{w0.text.strip()!r} at +{w0.start:.2f}s\n")
        # The hold is what the VIEWER sees, so it is delivered seconds, and the
        # composite runs pre-tempo - scale it on the way in. At tempo 1.0 this
        # is a no-op and the arithmetic below is unchanged.
        hold = float(b.get("hold", BROLL_HOLD)) * hold_scale
        a1 = min(a0 + hold, out_dur - BROLL_TAIL_CLEAR * hold_scale)
        # WHAT 0.8 WAS, AND WHY IT MOVED. This read as a "collapsed to nothing"
        # guard and was never written down as one, but 0.8 is exactly
        # BROLL_IN + BROLL_OUT + a frame: it is the shortest window at which the
        # OLD fixed ramp did not overlap itself. It was the anti-ghost guard,
        # spelled as a duration. broll_ramp now makes every length opaque, so
        # the guard reverts to what its message always claimed to be about - an
        # insert the silence-removal has crushed to less than a readable flash.
        if a1 - a0 < BROLL_FLASH_MIN * hold_scale:
            sys.stderr.write(
                f"note: b-roll at {b['at']}s collapsed to {a1-a0:.1f}s once the "
                f"silence was removed; skipped.\n")
            continue
        # AND SAY SO WHEN THE TAIL CLAMP MERELY SHORTENS IT. Only a collapse
        # under 0.8s was ever reported. An insert that the clamp cuts from 3.7s
        # to, say, 2.1s still renders - below BROLL_HOLD_MIN, the floor preflight
        # certified it against one command earlier - and nothing said a word.
        # The settled picture is what the floor is about, so the entrance and
        # exit come off before it is judged.
        # ONLY WHEN THE CLAMP ACTUALLY SHORTENED IT. The first version tested the
        # settled length alone, so it fired on every insert authored with a 3.0s
        # hold - which settles for 2.3s after the 0.7s of travel and is short for
        # a completely different reason - and reported it as "cut from 3.0s to
        # 3.0s by the tail clearance", which is both wrong and self-contradictory.
        # A short authored hold is preflight's BROLL line to make; this warning
        # is only about the clamp.
        clamped = a1 < a0 + hold - 0.005
        settled = (a1 - a0) - (BROLL_IN + BROLL_OUT) * hold_scale
        if clamped and settled < BROLL_HOLD_MIN * hold_scale - 0.05:
            sys.stderr.write(
                f"WARNING: b-roll {b.get('term','?')!r} at {b['at']}s is cut "
                f"from {hold / hold_scale:.1f}s to {(a1 - a0) / hold_scale:.1f}s "
                f"by the {BROLL_TAIL_CLEAR:.1f}s tail clearance, leaving "
                f"{settled / hold_scale:.1f}s settled against the "
                f"{BROLL_HOLD_MIN:.1f}s floor. Move it earlier.\n")
        idx = first_input + n
        # A SHORT INSERT STARTS WHERE THE PAN ENDS, because that is where the
        # subject is. 275 of the library's stills are baked with a slow push
        # that completes at BROLL_PAN_DONE (3.07s) and lands ON the subject -
        # broll.py's own measurement is that "the dome is not recognisable until
        # 89% of the travel". Played from zero, a 1.3s flash shows the first 42%
        # of that move and is taken off screen before its own picture arrives:
        # the viewer sees a corner of a building and a cut.
        #
        # Seeking in is the whole fix - the frames are already on disk. The
        # insert lands on the settled end of the push and reads immediately,
        # which is exactly what "boom, cut to Elon" needs. An asset with no pan,
        # and any insert long enough to complete one, are untouched.
        skip = 0.0
        if b.get("pan") and (a1 - a0) < BROLL_PAN_DONE:
            skip = max(0.0, BROLL_PAN_DONE - (a1 - a0))
        if skip > 0.0:
            inputs += ["-ss", f"{skip:.3f}"]
        inputs += ["-i", str(path)]
        # Hold the last frame if the baked clip is shorter than the window, so a
        # rounding difference cannot punch a hole in the picture.
        # tpad by a ROUNDING allowance, not by a whole hold. Padding by `hold`
        # let an asset that was baked short absorb the shortfall as an
        # arbitrarily long frozen frame - up to 4 seconds of still picture that
        # nothing reported. Anything more than a frame or two short is now the
        # bake's problem, and broll.py rebakes it.
        #
        # format=yuva420p + alpha=1 because a plain fade=t=in on an opaque
        # stream fades from BLACK: the first frame of every insert measured
        # RGB(0,0,0) full-frame, which reads as a flash on the cut. Fading the
        # ALPHA instead dissolves from the speaker, which is what a cutaway is.
        # The travel, as overlay x/y expressions in SOURCE time. Every pow() sits
        # inside a clamp (an unclamped p^3 puts the insert at x=-3000 on frame
        # 0), and the gate is gte*lt with a half-frame bias rather than
        # between(), which is inclusive at both ends and lets two adjacent
        # windows claim one frame.
        # THE RAMP IS DERIVED FROM THIS INSERT'S LENGTH, not from a constant.
        # See broll_ramp: two chained alpha fades multiply where they overlap,
        # so a fixed 0.35+0.35 on a sub-0.7s insert never reaches opacity.
        # Identity above 1.4s, so nothing in the archive moves.
        din, dout = broll_ramp(a1 - a0, hold_scale)
        hb, f1 = 0.5 / FPS, 1.0 / FPS
        pre = ""
        move = moves[bi]
        # A FLASH IS STATIC. Below BROLL_DRIFT_MIN_HOLD the entrance drift has
        # not landed before the exit drift starts; on a same-sign pair the two
        # ADD and the insert slides off its own over-scale, uncovering a hard
        # edge of the speaker. Falling back to soft/soft is not a compromise -
        # it is the same path a "soft" move already takes, at scale=W:H.
        moving = (BROLL_VARY and move != ("soft", "soft")
                  and (a1 - a0) >= BROLL_DRIFT_MIN_HOLD * hold_scale)
        if BROLL_STYLE in ("cut", "dissolve"):
            # NOTHING TRAVELS in either of these. The insert sits at the origin
            # and the transition is time, not distance: for "cut" the `enable`
            # gate is the whole of it, and for "dissolve" the alpha ramps below
            # do the work while the gate stays exactly as wide.
            #
            # It is written out rather than left to fall out of the travel
            # expressions with din = dout = 0 - which it would, since the gate
            # never evaluates them outside [a0, a1) - because a zero denominator
            # inside fx_unit is one refactor away from being a real division,
            # and because a reader should be able to see that it is deliberate.
            x = y = "0"
        if BROLL_STYLE == "dissolve":
            # THE ALPHA IS FADED, NOT THE PICTURE, and the difference is the
            # whole feature. This file already recorded why, back when the
            # cutaway last had a fade in it:
            #
            #   "format=yuva420p + alpha=1 because a plain fade=t=in on an
            #    opaque stream fades from BLACK: the first frame of every insert
            #    measured RGB(0,0,0) full-frame, which reads as a flash on the
            #    cut. Fading the ALPHA instead dissolves from the speaker, which
            #    is what a cutaway is."
            #
            # That is exactly the move the owner is asking for, so it is the
            # same two filters, restored. A `fade` on the alpha plane of a
            # yuva420p stream leaves the overlay compositing the insert OVER the
            # speaker at a ramping opacity - a true cross-dissolve between two
            # live pictures, not a dip through anything.
            #
            # Times are relative to the stream's own zero, which is why they are
            # din/dout and not a0/a1 - the setpts that puts it on the composite
            # clock comes AFTER these in the chain.
            hold_len = a1 - a0
            # THE FADE-OUT'S DURATION IS dout MINUS ONE FRAME, and that is a bug
            # fix, not a tweak. The alpha reached 0 at a1, but the overlay's gate
            # closes at a1 - hb, which the ramp never gets to: the last frame
            # actually drawn still carried the insert at 11% - SKILL.md's own
            # verification table records the exit ending "0.11  0.00" - and that
            # 11% vanished between two frames. It is the same off-by-one the
            # slide's swipe was fixed for ("THE SWIPE NEVER FINISHED"), on the
            # element whose entire brief is that it be seamless, and it costs one
            # max().
            pre = (f"format=yuva420p,"
                   f"fade=t=in:st=0:d={din:.3f}:alpha=1,"
                   f"fade=t=out:st={max(0.0, hold_len - dout):.3f}:"
                   f"d={max(f1, dout - f1):.3f}:alpha=1,"
                   # ...and then RESHAPE that linear ramp. See BROLL_ALPHA_LUT:
                   # the mush is the time spent near alpha 0.5, not the length
                   # of the dissolve, and a 256-entry table fixes it for 0.04s
                   # an insert. Must come AFTER both fades - it maps values, so
                   # it has to see the finished ramp.
                   f"lut=a='{BROLL_ALPHA_LUT}',")
            if moving:
                x, y = broll_offsets(move[0], move[1], a0, a1, din, dout,
                                     hold_scale)
        if BROLL_STYLE == "slide":
            # The exit's denominator is dout - one frame, so progress reaches 1
            # on the LAST frame the gate draws rather than at a1, which the gate
            # never reaches. Without it the swipe stopped at 58% and the rest
            # popped.
            rise = fx_ease("in_out", fx_unit(a0, din))
            swipe = fx_ease("in_out", fx_unit(a1 - dout, max(f1, dout - f1)))
            # ...and both land on EVEN pixels. The panel is yuv420p, so the
            # chroma planes are half resolution: an odd offset splits a chroma
            # sample across the moving seam and shimmers along it for the whole
            # travel.
            y = f"if(lt(t,{a0 + din:.3f}),2*floor({H}*(1-{rise})/2),0)"
            x = f"if(gte(t,{a1 - dout:.3f}),2*floor(-{W}*{swipe}/2),0)"
        # OVER-SCALED ONLY WHEN IT MOVES. A drifting insert has to be bigger
        # than the frame or it uncovers the speaker behind a hard edge (see
        # BROLL_BLEED); a "soft" insert does not move at all, so it keeps the
        # exact scale=W:H it has always had and renders byte-identically. The
        # alternative - over-scaling everything for uniformity - would put a
        # permanent 15% tighter crop on every cutaway in the archive to pay for
        # a property only some of them use.
        bw, bh = ((int(W * BROLL_BLEED) // 2 * 2, int(H * BROLL_BLEED) // 2 * 2)
                  if moving else (W, H))
        # DO NOT ADD in_range/out_range HERE. 23% of the library is full range
        # (measured: 278 of 1,200 bakes are yuvj420p/pc, the rest yuv420p/tv),
        # and an audit read that as "one pc asset re-grades the whole clip to
        # full range". It does not. The delivered file comes out tagged exactly
        # as the master is - yuv420p/unknown - and ffmpeg already converts yuvj
        # correctly through this scale plus the format=yuva420p below.
        #
        # Checked against ground truth, the asset decoded on its own at the
        # insert's size, on three pc assets:
        #     asset                     truth    as-is    with pc->tv
        #     automotive-assembly       113.04   113.21   111.79
        #     capitol-building          119.83   119.91   118.39
        #     conference-room           165.81   165.90   164.43
        # As-is tracks the source to within 0.1 mean RGB. Adding the conversion
        # moves every one of them 1.4 further AWAY and raises the per-pixel
        # residual (4.96 -> 5.53, 2.18 -> 2.91, 1.68 -> 2.43). It would darken a
        # quarter of the library for nothing.
        frag += (f"[{idx}:v]scale={bw}:{bh}:flags=lanczos,tpad=stop_mode=clone:"
                 f"stop_duration={BROLL_PAD:.2f},{pre}"
                 f"setpts=PTS-STARTPTS+{a0:.3f}/TB[br{n}];")
        nxt = f"brd{n}"
        frag += (f"[{cur}][br{n}]overlay=x='{x}':y='{y}':eof_action=pass:format=auto:"
                 f"enable='gte(t,{a0 - hb:.4f})*lt(t,{a1 - hb:.4f})'[{nxt}];")
        cur = nxt
        # LOCKSTEP. Both records are appended in the same statement so an insert
        # dropped above cannot slide the styles out of alignment with the
        # windows - see the note on BROLL_STYLES.
        windows.append((a0, a1))
        styles.append(move)
        n += 1
        sys.stderr.write(f"b-roll: {b['term']!r} at +{a0:.1f}s for {a1-a0:.1f}s "
                         f"({b['asset']}) [{move[0]}/{move[1]}]\n")
    BROLL_WINDOWS[:] = windows
    BROLL_STYLES[:] = styles
    return frag, inputs, cur


# ---------------------------------------------------------- punch-ins -----
# TWO FRAMINGS, A (100%) and B (PUNCH, 106%) about the face centre, both cut
# from the SOURCE crop and scaled once - never a zoom of the upscaled panel -
# and toggled at cuts so the invisible silence removals become VISIBLE picture
# changes. Measured before this: 23 cuts a minute and a median 29s on one
# unchanging frame, because a removal on a locked-off webcam leaves the
# speaker where he was. The toggle ladder, in DELIVERED seconds (scaled by
# the tempo in punch_windows): a sentence-end join once PUNCH_DWELL has passed
# since the last toggle; failing one of those by PUNCH_RUNG_SIL, a silence join
# that removed at least PUNCH_SIL_MIN; failing one by PUNCH_RUNG_KEY, two
# frames before the next keyword. A FORCED flip under every cutaway, at its
# first exit frame (a1 - BROLL_OUT, while the cover is still full-frame), so
# the reveal is always a new shot; frozen inside [a0 - PUNCH_FREEZE, a1), never
# inside the hook's travel, never in the last PUNCH_TAIL before the end card
# grabs its frame, and not before PUNCH_FIRST - one change inside the 1.3s
# stay-or-scroll window is deliberate. "punch": 1.0 in project.json turns it
# off.
#
# head, share AND DUO. Duo was excluded for years on the grounds that it "needs
# a per-band speaker attribution the pipeline does not have yet, and a default
# of the top band is the wrong person half the time". The first half of that is
# now measured and the second half is the answer to it.
#
# MEASURED, using whospeaks' speech-gated ratio (mouth-region motion while the
# room is loud over the same tile's motion while it is quiet, each tile against
# its OWN baseline) across three two-up spans of the 08.22 McGlone master:
#
#     14.0 +39s   top 1.01x  bottom 1.15x  -> BOTTOM  WEAK    margin 1.13x
#   1324.0 +56s   top 0.76x  bottom 1.69x  -> BOTTOM  CLEAR   margin 2.22x
#   1360.0 +50s   top 1.38x  bottom 1.23x  -> TOP     WEAK    margin 1.12x
#
# Two of three are WEAK over spans of 40 to 56 seconds. A punch window is 2 to 8
# seconds, with a fraction of the samples and often no quiet frames inside it at
# all, so per-window attribution would be worse than this - and a punch that
# follows a wrong verdict zooms in on the LISTENER, which is the same defect the
# old comment refused to ship, reached through more machinery.
#
# So BOTH BANDS PUNCH TOGETHER, on the same windows. The punch exists to turn
# invisible audio removals into visible picture changes; punching both delivers
# that in full and can never name the wrong person. Following the speaker would
# add emphasis on top, and emphasis is not worth being wrong about half the time.
#
# duo_share stays out, and NOT for want of attribution: it carries the shared
# app, and look.md's design panel rejected moving a chart with its axis labels at
# the frame edge.
# `CFG.get(k, default)` returns None when the KEY EXISTS with a null value, and
# project.json files in the archive carry `"punch": null` - so this crashed at
# IMPORT with "float() argument must be ... not 'NoneType'", which takes down
# every command in the pipeline on that job, not just the render. Found by
# running one clip of every mode: the `fit` job could not even be preflighted.
PUNCH = _num("punch", 1.06)
PUNCH_FIRST = 0.6
PUNCH_DWELL = 2.0
PUNCH_RUNG_SIL = 5.0
PUNCH_RUNG_KEY = 7.0
PUNCH_SIL_MIN = 0.30
PUNCH_FREEZE = 1.0
PUNCH_TAIL = 1.0
PUNCH_MODES = {"head", "share", "duo"}

# HOW MUCH OF A FOLLOW CLIP MUST BE MEASURED rather than held. turns.plan()
# carries the last decided verdict through windows it cannot call, which is the
# right behaviour frame by frame - staying on the wrong face beats cutting to
# it - but a schedule that is mostly held is one long guess, and the failure it
# produces is precisely the one this mode exists to remove. 0.45 is set from the
# 08.26 master, where a genuine two-hander measured 50% and a stretch with one
# person talking over a silent listener measured 22%: the first is a follow
# clip, the second is a `head` clip and should be refused as a follow.
# HOW FAR AHEAD OF THE VOICE THE FACE ARRIVES. Every cut in a follow clip is a
# binary overlay - the whole screen swaps on one frame - and landing it exactly
# on the boundary makes the switch read a beat late, because the viewer hears
# the new voice and the picture answers it. Editors cut the other way round: the
# picture leads the sound by a few frames, so the face is already there when the
# voice starts. It is the difference between a cut and a reaction.
#
# Three frames. Small enough that the outgoing speaker's last syllable is not
# orphaned on the wrong face, large enough to stop the switch feeling reactive.
# Applied as a UNIFORM shift of every window edge, which moves both directions
# of the cut at once - B arrives early, and so does A when B's window ends.
FOLLOW_LEAD = 0.10

FOLLOW_MIN_CONF = 0.45
# HOW LOPSIDED A "CONVERSATION" MAY BE before it is not one. Above this share of
# the floor held by one person, a FIXED crop on them measures better than a
# following one - see the warning in render() for the two measurements that set
# it. 0.65 sits between them.
FOLLOW_MAX_DOMINANCE = 0.65
# HOW BIG A FACE HAS TO BE for mouth-motion turn detection to be worth acting on.
#
# THE GUARD IS ON THE FACE, NOT THE TILE, and the first version had both the
# quantity and the number wrong. It warned when a camera tile was under 500px
# wide, justified by a sync ratio that was later retracted for measuring a fixed
# box in the delivered frame - one speaker's mouth and the other's cheek.
#
# Re-validated the way this file now says to validate: pulling a frame from the
# middle of every segment of a real clip and looking at whose mouth is open. On
# a 348px share rail the detector was right 5 of 5, with margins of 1.50x to
# 2.83x - and the faces inside those tiles measure 169px and 110px wide. So 348
# is fine and 500 was wrong; what matters is whether the FACE carries a readable
# mouth, and a tile is only a proxy for that when the framing is known.
#
# 80 is set below the 110px that is now validated, and above nothing - the
# signal has not been tested under it. A WARN, not a refusal.
FOLLOW_MIN_FACE_W = 80
# A LONG TURN THAT WAS NEVER MEASURED. The confidence floor above is GLOBAL, and
# a global pass hides the shape that matters: on the 08.28 test cut the schedule
# measured 63% overall and comfortably cleared the 45% floor while containing a
# single 25-second turn at confidence 0.00 - a quarter of the clip decided
# purely by inheriting the previous answer.
#
# It was RIGHT, checked by pulling frames: Steve's mouth is open at both ends of
# it. But it was right by inheritance rather than by measurement, and the
# operator was not told there was anything to look at. These two numbers name
# it: a turn long enough to matter, decided on nothing.
FOLLOW_HELD_MAX = 15.0     # seconds
FOLLOW_HELD_CONF = 0.25
# THE OPENING MOVE. The ladder is join-driven, so the first framing change
# lands wherever the speech happens to pause - and measured on the delivered
# files that is +7.2s on the 08.22 McGlone clip and +7.7s on the 08.21
# reference. The whole window in which a viewer decides to stay is therefore
# ONE unchanging frame with a card on it.
#
# THIS USED TO CITE TWO NUMBERS THAT DO NOT SURVIVE A CHECK - "Meta's 2025
# attention study puts the stay-or-scroll decision at 1.3s" and "VidMob measured
# visual hooks beating text-overlay hooks 2.4x". Neither traces to a primary
# source; both circulate in short-form marketing blogs. They are gone. The
# decision stands on the rig's OWN measurement, which is real: the first framing
# change landed at +7.2s and +7.7s on delivered files, and seven seconds of one
# still frame is on the wrong side of any plausible number.
# window every time, because a good span opens on someone talking, not pausing.
#
# So the first change is SEEDED rather than waited for: a punch IN, landing on
# the first KEYWORD inside PUNCH_OPEN (a noun, a number or a name, so the cut
# is motivated by a word rather than by a stopwatch), falling back to
# PUNCH_OPEN_AT when the opening carries no keyword.
#
# It is skipped entirely when the material already provides a change in that
# window - a SENTENCE join at or before PUNCH_OPEN_HI, the only kind that can
# toggle that early, since the silence rung needs PUNCH_RUNG_SIL of dwell it
# cannot have yet - because two toggles a few tenths apart is a flicker. Set "punch_open": false
# in project.json to turn it off and go back to waiting for a join.
PUNCH_OPEN = bool(CFG.get("punch_open", True))
PUNCH_OPEN_LO = 0.8       # never before this: the hook card is still arriving
PUNCH_OPEN_HI = 2.0       # and it has to be inside the decision window
PUNCH_OPEN_AT = 1.2       # where it goes when no keyword is spoken in there


def punch_windows(words: list[Word], rem_sent: list[tuple[float, float]],
                  rem_sil: list[tuple[float, float]], rem: list[tuple[float, float]],
                  inserts: list[tuple[float, float]], body: float,
                  tempo: float = 1.0) -> list[tuple[float, float]]:
    """
    The B-framing windows, in post-removal SOURCE time, from the toggle ladder.

    `words` are post-removal source-time words (what the captions use); the
    removal sets are in pre-removal span time and are mapped through
    remap_time, the one forward map, against the same `rem` cut_graph used -
    so a toggle lands on the join's own frame and not one beside it (off by
    one reads as flicker).
    """
    if PUNCH <= 1.0 or body <= 0:
        return []
    k = tempo
    sent = sorted({remap_time(a, rem) for a, _b in rem_sent})
    sil = sorted({remap_time(a, rem) for a, b in rem_sil if b - a >= PUNCH_SIL_MIN * k})
    lead = 2.0 / FPS
    keys = [w.start - lead for w in words if _keyword(w.text)]
    # The forced flip fires at a1 - BROLL_OUT: the first EXIT frame, while the
    # cover is still full-frame (x=0) - not at a1, the first uncovered frame.
    # Review caught it: at a1 the swipe had already exposed 5/40/135/320/625px
    # of the OLD framing over the previous five frames, then the whole frame
    # snapped 6% on the frame the cover vanished - a double cut on every
    # return. Under the cover the flip is invisible; what the swipe uncovers is
    # already B.
    events = ([(t, "sent") for t in sent] + [(t, "sil") for t in sil]
              + [(t, "key") for t in keys]
              + [(a1 - BROLL_OUT * k, "insert") for _a0, a1 in inserts])
    # The opening move - see PUNCH_OPEN above for why it is seeded and not
    # waited for. Only when the material does not already change in that
    # window, so it can never land a few tenths from a natural join.
    if PUNCH_OPEN and body > (PUNCH_OPEN_HI + PUNCH_DWELL) * k:
        lo_o, hi_o = PUNCH_OPEN_LO * k, PUNCH_OPEN_HI * k
        # ONLY "sent". A silence join in this window can never fire - it
        # carries PUNCH_RUNG_SIL (5.0s) of dwell and `last` is still 0.0, so
        # 2.0 < 5.0 by construction - and treating it as material that already
        # changes the framing suppressed the seed in exchange for NOTHING,
        # putting the clip straight back to opening on a static frame. Measured
        # over 376 real spans of this master, that fired on 11 of them (3%),
        # and the review that caught it also confirmed the two delivered clips'
        # +7.2s and +7.7s openings are the KEYWORD rung, the only other kind
        # that can go first. "sent" is the one kind with the first-toggle
        # exception below (dwell = PUNCH_FIRST), so it is the only kind that
        # can put a toggle inside [PUNCH_FIRST, PUNCH_OPEN_HI].
        natural = [t for t, kind in events
                   if kind == "sent" and PUNCH_FIRST * k <= t <= hi_o]
        if not natural:
            on_word = [w.start - lead for w in words
                       if _keyword(w.text) and lo_o <= w.start - lead <= hi_o]
            # AND IF THERE IS NO KEYWORD, IT STILL LANDS ON A WORD. This used to
            # fall through to PUNCH_OPEN_AT, a flat 1.2s - a stopwatch. The
            # framing snapped 6% at a time chosen by the clock, with no join, no
            # sentence end and no syllable under it: the only hard cut in the
            # clip with nothing motivating it, and the one the viewer is most
            # likely to be looking straight at.
            #
            # Every other rung in this ladder fires on something that happens -
            # a join, a pause, a keyword - and the seed can too. Any word ONSET
            # is a real event: the picture changes as the speaker starts a
            # syllable, which is what makes a cut read as intended rather than
            # as a glitch. This is the keyword branch with the keyword test
            # dropped, so it lands the same way for the same reason.
            #
            # Nearest to PUNCH_OPEN_AT rather than first, so the seed keeps
            # sitting where it was designed to sit inside the decision window;
            # only its exact frame moves, onto the nearest thing being said.
            if not on_word:
                any_word = [w.start - lead for w in words
                            if lo_o <= w.start - lead <= hi_o]
                if any_word:
                    on_word = [min(any_word,
                                   key=lambda t: abs(t - PUNCH_OPEN_AT * k))]
            events.append((on_word[0] if on_word else PUNCH_OPEN_AT * k, "open"))
    events.sort()
    locks = [(0.0, HOOK_IN * k), (HOOK_HOLD * k, (HOOK_HOLD + HOOK_OUT) * k)]
    locks += [(a0 - PUNCH_FREEZE * k, a1 - 1e-6) for a0, a1 in inserts]
    tail = body - PUNCH_TAIL * k
    need = {"sent": PUNCH_DWELL * k, "sil": PUNCH_RUNG_SIL * k,
            "key": PUNCH_RUNG_KEY * k, "insert": 0.0, "open": 0.0}
    toggles: list[float] = []
    # The START counts as the last toggle: the rungs are "this long since the
    # framing last changed", and with nothing before them the keyword rung
    # fired on the first keyword after the hook. The one exception is the
    # sentence rung, which may fire from PUNCH_FIRST so there is one change
    # inside the 1.3s stay-or-scroll window when a sentence ends there.
    last = 0.0
    for t, kind in events:
        if t >= tail or t <= 0:
            continue
        if kind != "insert":
            if t < PUNCH_FIRST * k or any(lo <= t < hi for lo, hi in locks):
                continue
            dwell = need[kind]
            if not toggles and kind == "sent":
                dwell = PUNCH_FIRST * k
            if t - last < dwell:
                continue
        if kind != "insert":
            # Snap to the frame grid - except the insert flip, which keeps the
            # exact float broll_chain formatted into its own gate, so
            # punch_enable emits the SAME threshold string and the B window
            # opens on precisely the frame the exit begins, whatever the
            # source's pts jitter (measured 2970/2970/3060 ticks: the frames
            # are not at N/30, and a re-derived frame number disagreed with
            # the gate on exact half frames).
            t = round(t * FPS) / FPS
        if toggles and t - toggles[-1] < 2.0 / FPS:
            continue
        toggles.append(t)
        last = t
    out = []
    for i in range(0, len(toggles), 2):
        e = toggles[i + 1] if i + 1 < len(toggles) else body
        if e - toggles[i] >= 1.0 / FPS:
            out.append((toggles[i], e))
    return out


def punch_enable(windows: list[tuple[float, float]]) -> str:
    """The overlay enable expression for the B framing: gte*lt with a half-frame bias."""
    hb = 0.5 / FPS
    return "+".join(f"gte(t,{a - hb:.4f})*lt(t,{b - hb:.4f})" for a, b in windows)


def _punch_box(box: tuple[int, int, int, int], anchor: tuple[float, float],
               keep_badge: bool = False) -> tuple[int, int, int, int]:
    """
    The B crop: `box` shrunk by PUNCH about `anchor` (source px), inside box.

    `keep_badge` anchors the shrink to the BOTTOM-LEFT instead of the face, and
    the share branch passes it for the camera tile. A meeting tile's bottom
    strip is the burned-in lower third and its left end is the start of the
    name - which is why the share branch already packs that tile with
    `fill_crop(anchor="bottom")`. Centring the punch on the face ignored that:
    on the 08.22 clip the anchor clamped on BOTH axes and B came out as A with
    18px shaved off the LEFT and 16px off the BOTTOM, which cut the M off
    "Mike McGlone" and dropped "Sr Commodity Strategist Bloomberg Intelligence"
    off the bottom of the band entirely. That was survivable while B was a
    4.7s window late in the clip; the moment the opening move made B the
    OPENING state it put the credential off screen for the whole hook, and on
    a finance clip the credential is the credibility. pack_share's own
    docstring says a half-cut name reads as a mistake rather than as a crop.

    The cost is that the punch stops tracking the face horizontally on a share
    tile. At a 6% shrink of a ~320px tile that is 18px, so the face stays
    framed; the badge does not survive the alternative.
    """
    w, h, x, y = box
    bw, bh = int(round(w / PUNCH)) // 2 * 2, int(round(h / PUNCH)) // 2 * 2
    if keep_badge:
        return bw, bh, x, y + h - bh
    bx = int(round(min(max(anchor[0] - bw / 2, x), x + w - bw)))
    by = int(round(min(max(anchor[1] - bh / 2, y), y + h - bh)))
    return bw, bh, bx, by


# -------------------------------------------------------------- render -----
LAYOUT_VERSION = 2        # full 9:16 panel, captions on the picture
_WARNED_LAYOUT = [False]


def _warn_layout_version() -> None:
    """
    Say so when re-rendering a project authored against the previous layout.

    SKILL.md's rule is that a delivered clip is finished and an archived project
    is the recipe for it. Across this boundary the recipe no longer reproduces the
    dish: the panel is 360px taller, the captions moved onto the picture, and any
    crop in that project.json is re-cut to a different aspect. Rendering it is
    fine - it is a NEW clip - but it must not be mistaken for the delivered one.
    """
    if _WARNED_LAYOUT[0] or _num("layout_version", 1) >= LAYOUT_VERSION:
        return
    _WARNED_LAYOUT[0] = True
    sys.stderr.write(
        f"WARNING: this project.json has no layout_version, so it was authored "
        f"against layout 1 (a 1560-tall panel with captions below it). These "
        f"renders will NOT match anything delivered from it. Run preflight - "
        f"CROPS and PACK will tell you which values need re-authoring - then add "
        f"\"layout_version\": {LAYOUT_VERSION} to project.json to silence this.\n")




def render(slug: str, start: float, end: float, hook: str, mode: str = "head",
           crop_x: int | None = None, beats: bool = True,
           head_crop: list[int] | None = None,
           pip_crop: list[int] | None = None,
           share_crop: list[int] | None = None,
           face_h: int | None = None,
           duo_crops: list[list[int]] | None = None,
           mute: list[list[float]] | None = None,
           drop: list[list[float]] | None = None,
           hard_out: float | None = None,
           cap_colour: dict | None = None,
           broll: list[dict] | None = None,
           speed: float | None = None,
           allow_ragged_end: bool = False,
           layout_ok: bool = False,
           follow_crops: list[list[int]] | None = None,
           follow_pips: list[list[int]] | None = None,
           follow_tiles: dict[str, list[int]] | None = None,
           allow_legacy_duo: bool = False,
           speakers: dict | None = None,
           speaker_verified: bool = False,
           speaker: str | dict | None = None) -> Path:
    # ONE RESOLUTION POINT. Aliases and retired modes are decided here, before
    # anything downstream branches on the name - see canonical_mode.
    mode = canonical_mode(mode, allow_legacy=allow_legacy_duo)
    if mode not in MODE_NEEDS:
        raise SystemExit(
            f"\nUNKNOWN MODE {mode!r}. The three templates are "
            f"{', '.join(TEMPLATES)}\n(plus 'share', which is template 3 with a "
            f"single speaker).\n"
            f"'two_up' and 'gallery' are LAYOUT names from sections.json, not "
            f"render modes - a two-up is cut with 'conversation' or 'head', a "
            f"gallery with 'head'.\n")
    ensure_audio()
    _warn_layout_version()
    check_layout(start, end, mode, layout_ok=layout_ok, drop=drop)
    check_rail(start, end, mode, pip_crop)
    check_speaker(slug, start, end, mode, pip_crop, head_crop, crop_x)

    # hard_out is a CEILING on the out-point, and it used to be consulted only
    # to veto the forward run-on - an out-point authored PAST it rendered
    # straight through. Clamp it first, so every guard below sees the real end.
    if hard_out is not None and float(hard_out) < end:
        sys.stderr.write(f"note: {slug} out-point {end:.2f}s pulled back to "
                         f"hard_out {float(hard_out):.2f}s.\n")
        end = float(hard_out)
    card = CARD_SECONDS if CFG.get("endcard", True) else 0.0
    want = MIN_CLIP - card
    if end - start < want:
        raise SystemExit(
            f"\nTOO SHORT: {slug} is {end - start:.1f}s of span and every clip must "
            f"finish at {MIN_CLIP:.0f}s or more.\n"
            f"With the {card:.0f}s end card that needs at least {want:.1f}s "
            f"of span, and silence removal only makes it shorter.\n"
            f"Widen the span, or pick a different moment - do not ship it short.\n")

    dur = end - start
    tmp = WORK / "tmp"
    tmp.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    # Decode a little PAST the requested out-point. The span was picked off a
    # transcript, so it ends wherever the timestamp fell - regularly mid-clause -
    # and knowing where the *next* full stop lands is what lets the clip grow into
    # it instead of being cut short. Costs nothing but a few seconds of decode.
    LOOKAHEAD = END_LOOKAHEAD
    env_full = envelope(start, dur + LOOKAHEAD)

    # Never hand whisper a long silent tail. Word-level decoding distributes a
    # chunk's words across the whole chunk, so trailing dead air DRAGS the last
    # words late - on one clip "traded hands already. That's a lot." was timed 1
    # to 4 seconds after the audio had stopped, which then looked like
    # hallucination to the guard below and got real speech deleted. Cutting the
    # decode at the last voiced frame removes the room for that drift.
    # A span must not END in silence. This is enforced on the AUDIO, before any
    # decoding, because it is also what causes the drift above: with the out-point
    # sitting seconds past the last spoken word, the decoder spreads its final
    # words into the dead air and they come back timestamped after the speech
    # stopped. Trimming here fixed a clip whose captions read
    # "...shares have already traded lot."
    # Trigger generously (1.2s, not 0.6s): this is meant to catch a clip that
    # runs SECONDS past the last word, not to shave a soft trailing one. At 0.6s
    # it ate the "right?" off "There's no protection in crypto, right?" - which
    # was that clip's whole hook - because a quiet trailing syllable dips under
    # the floor for about three quarters of a second.
    _last = last_speech(env_full, dur)
    if _last is not None and dur - _last > 1.20:
        dur = snap(_last + 0.35)
        end = start + dur
        sys.stderr.write(
            f"note: {slug} ended in silence; out-point pulled back "
            f"{start + dur:.1f}s to the last spoken word.\n")

    decode_dur = decode_window(env_full, dur, LOOKAHEAD)
    words = word_times(start, decode_dur, slug)

    # Then throw away anything whisper still invented over dead air, BEFORE the
    # out-point is chosen, or the clip ends on a sentence that was never spoken.
    words = drop_unspoken(words, env_full)
    if not words:
        raise SystemExit(
            f"\n{slug}: no speech in {start:.1f}..{end:.1f}. The transcript for "
            f"this span is whisper hallucinating over silence. Pick another span.\n")

    # END ON A FINISHED SENTENCE. A span picked off a transcript ends wherever the
    # timestamp fell, which is regularly mid-clause - and a clip that stops while
    # someone is still talking reads as a mistake no matter how good the moment
    # was. Snap the out-point back to the last word carrying a full stop.
    #
    # Capped: if the nearest sentence end is more than a third of the clip back,
    # the span was chosen badly and silently deleting a third of it would be worse
    # than the ragged ending. Say so instead.
    _inside = [w for w in words if w.start < dur]
    kind, chosen, cost = plan_ending(
        words, dur, hard_out=hard_out, start=start,
        layout_ok=lambda t: check_layout(start, t, mode,
                                         layout_ok=layout_ok, drop=drop))

    # S3/S4. THE TAIL AND THE CEILING, for every branch including "landed".
    #
    # The pad used to apply only when the out-point MOVED, so a span that already
    # ended on a full stop got whatever tail the picker happened to leave - and 57
    # of 82 delivered clips sit under END_PAD_MIN. It is not applied blindly: it
    # takes only the gap that is actually there, so on a speaker who runs straight
    # into the next sentence it adds nothing, which is the whole point of clamping
    # to the gap rather than flooring at END_PAD_MIN (SKILL.md calls padding into
    # live speech "the same defect in a hat").
    #
    # And `hard_out` is a CEILING the slate documents as never-cross, but the veto
    # in plan_ending tests the bare word end while the pad is added afterwards -
    # so the delivered out-point could land up to END_PAD plus a snap frame past
    # it, on the back branch as well as the forward one. Clamp here, where the pad
    # is actually applied, rather than making the veto conservative by the full
    # END_PAD (which would convert workable spans into `stuck`, now a refusal).
    _next_start: float | None = None
    _squeezed: list[float] = []

    def _pad_to(i: int, floor: float) -> float:
        nonlocal _next_start
        _next_start = words[i + 1].start if i + 1 < len(words) else None
        gap = (words[i + 1].start - words[i].end
               if i + 1 < len(words) else END_PAD)
        pad = max(floor, min(END_PAD, gap))
        out = snap(words[i].end + pad)
        if hard_out is not None:
            # THE CEILING WINS - and it says so. hard_out is the author's
            # never-cross line and the pipeline must not overrule it, but the
            # clamp silently defeats the END_PAD_MIN tail guarantee: measured on
            # 02-no-good-answers-on-hormuz, hard_out 640.62 sits 0.07s past the
            # last word, so a 0.30s tail was delivered as 0.07s and the out-fade
            # was squeezed into it. The clip ends clipped, and nothing said why.
            capped = min(out, hard_out - start)
            if capped < out - 0.005:
                _squeezed.append(capped - words[i].end)
            out = capped
        return max(out, snap(words[i].end + 0.02))

    if kind == "landed" and _inside:
        # The INDEX, not words.index(_inside[-1]) - Word compares by value, so a
        # repeated word ("that ... that") would find the first occurrence and pad
        # off the wrong one.
        _i = max(k for k, w in enumerate(words) if w.end <= dur)
        # END_PAD_MIN, NOT 0.0 - the same floor the forward and back branches
        # take. A 0.0 floor makes `max(floor, min(END_PAD, gap))` collapse to the
        # gap, so on a speaker who runs straight into the next sentence the only
        # backstop left is the `+ 0.02` below: a butt cut on the last phoneme,
        # with the 0.25s out-fade already running while the word is still
        # sounding. That is the exact defect END_PAD_MIN was introduced to fix on
        # the other two branches, and "landed" is the branch MOST clips take -
        # measured over the authored slates on this machine, 4 of 6 spans land.
        # Two of those shipped 0.007s and 0.020s of tail.
        _new = _pad_to(_i, END_PAD_MIN)
        if _new > dur or (hard_out is not None and start + dur > hard_out):
            dur = _new
            end = start + dur
        # AND TRUNCATE, exactly as the forward/back branch does. Without this the
        # word list still carries everything the lookahead decoded past the
        # out-point, so write_srt emitted cues for words that are not in the
        # delivered picture - including the straddling first word of the next
        # sentence, which then reads as the clip's ending to anybody on captions.
        words = words[:_i + 1]

    if kind in ("forward", "back"):
        # Pad past the last word so it does not sound clipped - but only into the
        # gap that is actually there. A flat END_PAD tail is right after a pause
        # and wrong in continuous speech, where it drags the first phoneme of the
        # NEXT sentence in under the end card. Ending on a finished sentence and
        # then playing 0.4s of the following one is the same defect in a hat.
        #
        # The FLOOR is the half that was wrong. It was 0.06s, which is not a tail
        # at all - it is a butt cut on the last phoneme, and with a 0.25s out-fade
        # sitting at a fixed distance from the end of the file the fade was
        # already running while the word was still sounding. See END_PAD_MIN.
        dur = _pad_to(chosen, END_PAD_MIN)
        words = words[:chosen + 1]
        end = start + dur
        why = (f"ran on {cost:.1f}s to finish the sentence" if kind == "forward"
               else f"pulled back {cost:.1f}s to the last full stop")
        sys.stderr.write(f"note: {slug} ended mid-sentence; {why}.\n")
    if _squeezed and min(_squeezed) < END_PAD_MIN - 0.005:
        _t = min(_squeezed)
        sys.stderr.write(
            f"WARNING: {slug} hard_out leaves only {_t:.2f}s after the last "
            f"word, under the {END_PAD_MIN:.2f}s tail every clip should end "
            f"with - the last word will sound clipped and the out-fade is "
            f"squeezed into it. Move hard_out to "
            f"{(hard_out or 0) + (END_PAD_MIN - _t):.2f} or pick an earlier "
            f"out-point.\n")

    if kind == "flat":
        sys.stderr.write(
            f"WARNING: {slug} has no sentence end at all - the transcript for "
            f"this span came back unpunctuated, so the ending cannot be "
            f"checked. Listen to the tail before shipping.\n")
    elif kind == "stuck":
        # There ARE sentence ends and none can be reached: the forward one is
        # past the run-on cap, or crosses hard_out, or crosses a layout change,
        # and the backward one is more than a third of the clip away. Every one
        # of those used to print at most a stderr line and render anyway, which
        # in a build_all run scrolls past six other clips and ships. The rule the
        # owner set is that a clip ends when the speaker stops talking, so this
        # is a refusal, in the same place and the same shape as the 45s floor.
        heard = _inside[-1].text.strip() if _inside else "?"
        if allow_ragged_end:
            sys.stderr.write(
                f"WARNING: {slug} ends mid-sentence on {heard!r} and no full "
                f"stop is reachable - shipping it anyway on "
                f"\"allow_ragged_end\".\n")
            RAGGED_ENDS.append(slug)
        else:
            raise SystemExit(
                f"\nENDS MID-SENTENCE: {slug} stops while {heard!r} is still "
                f"being said, and the out-point cannot be moved onto a full "
                f"stop.\n"
                f"The nearest one is {words[chosen].text.strip()!r} at "
                f"{start + words[chosen].end:.1f}s ({cost:+.1f}s from the "
                f"out-point).\n"
                f"Move `end` in the slate onto it, or pick a different moment. "
                f"A clip that stops mid-thought reads as a mistake however good "
                f"the moment was.\n"
                f"Set \"allow_ragged_end\": true on this clip to ship it "
                f"anyway.\n")

    # THE PAD IS MEASURED FROM THE AUDIO, NOT FROM THE TRANSCRIPT. whisper marks
    # a word's end where the phoneme is recognised, not where its release and the
    # room decay to nothing - measured on a real clip, the word pass put the
    # closing word at +65.24s while the envelope still carried speech-level energy
    # at +65.41s. So a tail of END_PAD_MIN counted off the transcript can be only
    # 0.13s of actual air, and the out-fade then runs over the tail of the word it
    # was placed to clear.
    #
    # Extend rather than move the fade. Shortening the fade leaves MORE speech in
    # the last quarter second, not less: measured, holding the fade back took the
    # final 250ms from +2.0 dB to +5.4 dB against median speech. Bounded by
    # END_PAD, so this can never run on into the next sentence, and by hard_out.
    if words:
        _ac = last_speech(env_full, dur)
        if _ac is not None and dur - _ac < END_PAD_MIN:
            _want = snap(min(_ac + END_PAD_MIN, dur + END_PAD))
            # NEVER INTO THE NEXT WORD. The gap clamp is what stops the ordinary
            # pad dragging the following sentence's first phoneme under the end
            # card, and an acoustic extension has to respect the same ceiling -
            # without it this pulled the next word's onset back into the clip and
            # made the tail worse than doing nothing.
            if _next_start is not None:
                _want = min(_want, snap(_next_start - 0.02))
            if hard_out is not None:
                _want = min(_want, hard_out - start)
            if _want > dur:
                sys.stderr.write(
                    f"note: {slug} tail extended {_want - dur:.2f}s - the closing "
                    f"word rings {_ac - words[-1].end:+.2f}s past its transcript "
                    f"end.\n")
                dur = _want
                end = start + dur

    # Whatever the rule decided, the lookahead tail is not part of the clip.
    words = [w for w in words if w.start < dur]

    # Then trim dead air. A span almost always overshoots the last word by a beat,
    # which used to be invisible - the clip simply ended. With a card following it
    # is silence staring at the viewer before the wipe. Only the END is trimmed;
    # the front is the picker's deliberate choice of where to come in.
    if words:
        tail = dur - words[-1].end
        if tail > 0.60:
            dur = snap(words[-1].end + END_PAD)
            end = start + dur
            words = [w for w in words if w.start < dur]

    rem: list[tuple[float, float]] = []
    out_dur = dur
    env = envelope(start, dur)
    # THE WELD RUNS FIRST, because it changes what the other two passes are
    # looking at. find_removals walks sentence ends in `words`, and a sentence
    # end inside a dropped passage is not a place to cut - it is not in the clip
    # at all. Dropping the words before the pass, rather than filtering its
    # output after, means the retention cut never sees the excised middle and
    # cannot try to trim a pause that no longer exists.
    rem_drop, _weld_bad = weld_windows(drop, start, dur, env)
    if _weld_bad:
        raise SystemExit(
            f"\nWELD REFUSED: {slug}\n  " + "\n  ".join(_weld_bad) +
            "\n\nA weld joins two moments of ONE idea. Run "
            "`pick.py --weld` for pairs that are already legal.\n")
    if rem_drop:
        _gone = sum(e - s for s, e in rem_drop)
        words = drop_words(words, rem_drop)
        sys.stderr.write(
            f"weld: {slug} drops {_gone:.1f}s in {len(rem_drop)} excision(s); "
            f"{len(rem_drop) + 1} moments welded into one clip.\n")
    # Retention cuts AND a hard no-silence pass. The first is pacing, the second
    # is a guarantee: a viewer must never be watching someone not talking.
    rem_sent = find_removals(words, env, dur) if beats else []
    rem_sil = collapse_silence(env, dur)
    rem = merge_windows(rem_sent, rem_sil, rem_drop)
    if rem:
        words, out_dur = apply_removals(words, dur, rem)
        # The graph and the arithmetic must agree about how long the body is.
        # They silently did not for one shape of removal list - see cut_graph -
        # and every overlay in the clip is authored against out_dur, so a
        # disagreement here mis-times the captions, the hook, the CTA and the
        # out-fade all at once.
        _kept = dur - sum(e - s for s, e in rem)
        assert abs(_kept - out_dur) < 1e-3, (
            f"{slug}: removal arithmetic disagrees - kept {_kept:.3f}s but "
            f"out_dur is {out_dur:.3f}s")
        left = residual_silence(env, rem, dur)
        cut = sum(e - s for s, e in rem)
        # THE WELD IS NOT SILENCE, so it is not counted as silence. Reporting
        # one number here would say "removed 214.6s of silence" on a two-moment
        # clip, which is the kind of log line that gets believed for a month.
        weld = sum(e - s for s, e in rem_drop)
        sys.stderr.write(
            f"note: {slug} removed {cut - weld:.1f}s of silence in "
            f"{len(rem) - len(rem_drop)} cut(s)"
            + (f" plus {weld:.1f}s welded out" if weld else "")
            + f"; longest pause left {left:.2f}s.\n")
        if left > MAX_GAP + 0.20:
            sys.stderr.write(
                f"WARNING: {slug} still holds a {left:.2f}s pause. Check the tail "
                f"before shipping.\n")

    # Tempo is decided here, between the silence pass and the floor check, and
    # the floor is then measured on the DELIVERED duration. Getting that order
    # wrong is the trap: check the floor first and a 41s body at 1.08 delivers
    # 38.0s plus the card, so 42.0s, and the guard waves it through.
    tempo, why = tempo_for(words, out_dur, speed)
    # THE NAMEPLATE FOLLOWS THE CLIP'S CLOCK. Its arrival is derived from the
    # hook card's exit, which is tempo-scaled; published here as a module record
    # for the same reason BROLL_WINDOWS is one - the four functions that need it
    # are reached through signatures that do not carry it.
    ATTR_TEMPO[0] = tempo
    if tempo != 1.0:
        sys.stderr.write(f"tempo: {slug} x{tempo:.3f}  ({why})\n")
        out_dur = out_dur / tempo
    elif why:
        sys.stderr.write(f"tempo: {slug} left alone ({why})\n")

    if out_dur + card > MAX_CLIP:
        raise SystemExit(
            f"\n{slug}: {out_dur + card:.0f}s is over the {MAX_CLIP:.0f}s "
            f"ceiling.\n"
            f"The span is {start:.1f}..{start + dur:.1f} - check `end` is the "
            f"time you meant. Raise \"max_clip\" in project.json if this really "
            f"is a long one.\n")
    if out_dur + card < MIN_CLIP:
        silence = dur - (out_dur * tempo)
        by_tempo = (out_dur * tempo) - out_dur
        extra = (f" and {by_tempo:.1f}s to the x{tempo:.3f} tempo" if tempo != 1.0
                 else "")
        raise SystemExit(
            f"\nTOO SHORT: {slug} delivers {out_dur + card:.1f}s, under the "
            f"{MIN_CLIP:.0f}s floor.\n"
            f"The span was {dur:.1f}s; it lost {silence:.1f}s to dead air{extra}.\n"
            f"Widen it by at least {(MIN_CLIP - card - out_dur) * tempo:.1f}s of "
            f"real speech"
            + (", or set \"speed\": 1.0 on this clip.\n" if tempo != 1.0 else ".\n"))

    # ------------------------------------------------------ TWO TIMELINES ----
    # This graph has two, and conflating them is what broke tempo for months.
    #
    #   SOURCE (pre-tempo)   the trims, the overlays, the b-roll. EVERY overlay
    #                        in this filter graph is applied BEFORE the trailing
    #                        setpts, so the stream they land on is still at the
    #                        master's rate. Length: body_src.
    #   DELIVERED            what the finished file measures. Only the audio
    #                        fades (they come after atempo) and the .srt.
    #                        Length: out_dur.
    #
    # The old code scaled `words` and `rem` into DELIVERED time here and then
    # handed them to consumers that composite in SOURCE time, which produced
    # three separate faults on any clip with tempo != 1.0:
    #   - cut_graph trimmed the un-sped source at delivered offsets, so 11 of 12
    #     jump cuts missed their silence entirely: ~4.7s of real speech spliced
    #     out mid-clip and ~5.1s of dead air left in, while the log reported the
    #     edit it INTENDED (residual_silence is computed off the unscaled list).
    #   - the caption, hook and address tracks were authored on the delivered
    #     timeline and then sped AGAIN by the trailing setpts, so the captions
    #     ran ahead of the voice by up to 3.3s and then froze.
    #   - every b-roll insert fired seconds early for the same reason.
    # The body also overran out_dur, and afade holds gain 0 past its end, so the
    # overshoot - the clip's real last words - was multiplied by zero: literal
    # digital silence before the end card. That is the 2.1s hole seen on
    # 08.12.26, and why every clip since has shipped "speed": 1.0.
    body_src = out_dur * tempo          # the composite's length, pre-setpts
    words_src = words                   # post-removal, source rate
    rem_src = rem                       # ditto
    words_out = ([Word(w.start / tempo, w.end / tempo, w.text) for w in words]
                 if tempo != 1.0 else words)

    # The picture first. The hook and caption layers are built after it, further
    # down, because where the face is and what colour sits behind the words are
    # both read off the REFRAMED picture, and that does not exist until this
    # chain does.
    # body_src, not out_dur: reframe_chain sizes a color= source that is the MAIN
    # input of the duo_share overlay stack, and overlay is main-driven - a
    # background shorter than the tiles truncates the picture. It is composited
    # pre-setpts like everything else here.
    # ------------------------------------------------- who holds the floor ----
    # head_follow needs its turn schedule BEFORE the chain is built, because the
    # chain IS the schedule - unlike the punch, which is layered on afterwards.
    # It also has to be in place before panel_faces and the caption-colour
    # probe run, or both measure a framing the clip never shows.
    fwin: list[tuple[float, float]] = []
    follow_names: list[str] = []
    if mode in ("conversation", "conversation_share"):
        import turns as _turns
        tiles = follow_tiles or CFG.get("follow_tiles")
        # THE MEASUREMENT TILES ARE WHERE THE FACES ARE, AND THAT MOVES WITH THE
        # LAYOUT. On a two-up they are the halves of the frame; in a screen
        # share they are the camera RAIL, which is somewhere else entirely.
        # project.json can only hold one set, so a conversation_share clip using
        # the two-up halves would score motion in two rectangles that contain
        # the shared app - and turns.plan would decide nothing, or decide wrong.
        #
        # In share the pips ARE the faces, so they are the right rectangles by
        # construction. Names come from follow_tiles so the nameplate check and
        # the schedule log still speak of people rather than indices.
        if mode == "conversation_share":
            pips = follow_pips or CFG.get("follow_pips")
            if pips and len(pips) == 2:
                names = list(tiles) if tiles and len(tiles) == 2 else ["a", "b"]
                tiles = {names[i]: list(pips[i]) for i in (0, 1)}
        if not tiles or len(tiles) != 2:
            raise SystemExit(
                f"\n{slug}: mode {mode!r} needs follow_tiles - two named "
                f"[w,h,x,y] boxes,\none per speaker, to measure who is talking. "
                f"Order must match follow_crops.\n")
        names = list(tiles)
        follow_names = names
        sched = _turns.plan(start, start + dur, tiles)
        if not sched:
            raise SystemExit(
                f"\n{slug}: could not measure who is speaking over this span, so "
                f"a follow clip\nwould be guessing. Check follow_tiles against a "
                f"real frame, or use mode 'head'\nwith the half that holds the "
                f"floor.\n")
        # CONFIDENCE IS A REFUSAL, not a note. A schedule that is mostly HELD
        # rather than measured is one long guess, and the failure it produces -
        # the crop sitting on a silent face while the other person talks - is
        # exactly the defect this mode exists to remove. Better to fall back to
        # `head`, which is at least honestly one person, than to cut to the
        # wrong one on a coin flip.
        span = max(1e-6, dur)
        conf = sum(t["confidence"] * (t["end"] - t["start"]) for t in sched) / span
        if conf < FOLLOW_MIN_CONF:
            raise SystemExit(
                f"\n{slug}: only {conf * 100:.0f}% of this span could be measured "
                f"(floor {FOLLOW_MIN_CONF * 100:.0f}%).\n"
                f"The rest would be a guess about who is talking, and a follow "
                f"clip that guesses\nwrong cuts to the LISTENER - worse than the "
                f"fixed crop it replaces.\n"
                f"Use mode 'head' with the speaking half, or 'duo' to show both.\n")
        # THE SCHEDULE MUST BE PROVED BY LOOKING, NOT BY ITS OWN NUMBER.
        # Measured on the 08.26 master against transcript ground truth, the
        # confidence this gate reads carries NO information about correctness:
        #
        #     boundary set     confidence     actually right
        #     tdrz only            69%             43%
        #     + cue edges          59%             39%
        #     + 5s spacing         68%             34%
        #     + 8s spacing         74%             36%
        #
        # Every variant is at or below chance for a two-person problem, and the
        # MOST confident was the second worst. The owner found the same failure
        # by watching: "Steven Flanagan is talking and it's showing a picture of
        # BigBeat... thirty seconds in, it's fucked." He is right, and no
        # threshold on this number can catch it.
        #
        # So a follow clip now needs a human to have looked at the frames.
        # verify_turns.py builds the sheet - both faces at the middle of every
        # turn, the schedule's pick framed - and the flag records that somebody
        # read it. It is deliberately not defaultable: the whole failure is that
        # a wrong schedule looks exactly like a right one from inside the code.
        # Satisfiable per clip OR once per show in project.json: with
        # per-speaker tracks the schedule is exact and the only thing
        # left to confirm is the name->tile mapping, which is a
        # show-level fact, not a per-clip one.
        # PER CLIP, NOT PER PROJECT. This read
        # `speaker_verified or CFG.get("speaker_verified")`, so one line in
        # project.json permanently satisfied the eye check for every clip in
        # every show - which is the whole gate, since the sheet is built from
        # THIS clip's schedule. A show-wide skip is what --force is for, and
        # that prints a banner.
        if not speaker_verified:
            raise SystemExit(
                f"\n{slug}: a follow clip must be checked by eye before it "
                f"renders.\n\n"
                f"    python3 verify_turns.py {slug}\n\n"
                f"That writes a sheet with BOTH faces at the middle of every "
                f"turn and the\nschedule's choice framed. Read it: if the framed "
                f"face is the one with the\nopen mouth on every row, set "
                f'"speaker_verified": true on the clip and render.\n'
                f"If it is not, the schedule is wrong - pick a calmer span or "
                f"use mode 'head'.\n"
                f"The confidence number does NOT answer this: measured, it runs "
                f"69% confident\nat 43% correct.\n")

        # A LONG TURN DECIDED ON NOTHING. See FOLLOW_HELD_MAX.
        _held = [t for t in sched
                 if (t["end"] - t["start"]) > FOLLOW_HELD_MAX
                 and t["confidence"] < FOLLOW_HELD_CONF]
        for t in _held:
            sys.stderr.write(
                f"WARNING: {slug} holds {t['who']!r} for "
                f"{t['end'] - t['start']:.0f}s from +{t['start'] - start:.0f}s "
                f"on confidence {t['confidence']:.2f}.\n"
                f"         That stretch was not measured - it inherited the "
                f"previous answer. Pull a frame\n"
                f"         from the middle of it and check whose mouth is "
                f"open.\n")

        # IS THERE A READABLE MOUTH IN EACH TILE? See FOLLOW_MIN_FACE_W. The
        # face width comes from turns' own cascade pass, so this asks about the
        # rectangle the detector actually scored rather than about the tile.
        try:
            import turns as _t
            _src = SRC
            _fw = []
            for _n, _b in tiles.items():
                _f = _t._face_of(_src, start, min(dur, 20.0), tuple(_b))
                _fw.append((_n, int(_f[2] * int(_b[0])) if _f else 0))
        except Exception:                                        # noqa: BLE001
            _fw = []
        _small = [(n, w) for n, w in _fw if w < FOLLOW_MIN_FACE_W]
        if _small:
            _fixed = "head" if mode == "conversation" else "share"
            _who = ", ".join(f"{n} {w}px" for n, w in _small)
            sys.stderr.write(
                f"WARNING: {slug} face too small to read a mouth in: {_who}, "
                f"under {FOLLOW_MIN_FACE_W}px.\n"
                f"         Turn detection is validated down to 110px and "
                f"untested below that, so the\n"
                f"         schedule here may cut to the wrong person. Pull a "
                f"frame from each turn and\n"
                f"         check whose mouth is open, or use mode {_fixed!r} on "
                f"whoever holds the floor.\n")

        # DOES THE FLOOR ACTUALLY MOVE? A conversation template only earns its
        # place when it does. Measured on the 08.28 demo pair, same rig, same
        # metric (does the face on screen move in time with the sound):
        #
        #   55/45 span, conversation  1.32x   against a fixed crop's 0.90x
        #   66/34 span, conversation  1.22x   against a fixed crop's 1.32x
        #
        # On the lopsided span the FIXED crop wins, and it wins for an obvious
        # reason: it sits on the person holding two thirds of the floor, so it
        # is right most of the time, while the following crop spends a third of
        # the clip cutting away on the weakest turn calls. The template is not
        # at fault - the SPAN is, and the answer is `head` or `share` on
        # whoever is talking.
        #
        # 0.65 sits between the two measured points. A WARN, because a lopsided
        # span can still be the right clip and the operator can see the split.
        held: dict[str, float] = {}
        for t in sched:
            held[t["who"]] = held.get(t["who"], 0.0) + (t["end"] - t["start"])
        _tot = sum(held.values()) or 1.0
        _top, _share = max(held.items(), key=lambda kv: kv[1])
        if _share / _tot > FOLLOW_MAX_DOMINANCE:
            _fixed = "head" if mode == "conversation" else "share"
            sys.stderr.write(
                f"WARNING: {slug} is not really a conversation - {_top} holds "
                f"{_share / _tot * 100:.0f}% of the floor.\n"
                f"         A following crop spends the rest cutting away on the "
                f"weakest turn calls, and\n"
                f"         measured on this rig a FIXED crop beats it on a "
                f"lopsided span (1.32x vs 1.22x).\n"
                f"         Consider mode {_fixed!r} on {_top}, or a span where "
                f"the floor genuinely moves.\n")

        # Framing B is the SECOND tile, so the enable windows are that person's
        # turns. Times are absolute source seconds; the graph's clock is
        # post-removal span time, which is what remap_time produces - the same
        # forward map punch_windows uses, against the same `rem`.
        for t in sched:
            if t["who"] != names[1]:
                continue
            a = remap_time(max(0.0, t["start"] - start), rem_src)
            b = remap_time(min(dur, t["end"] - start), rem_src)
            # See FOLLOW_LEAD: the picture leads the voice, so shift the whole
            # window earlier rather than only its start.
            a, b = max(0.0, a - FOLLOW_LEAD), max(1e-3, b - FOLLOW_LEAD)
            if b - a > 1e-3:
                fwin.append((a, b))
        # DOES THE NAMEPLATE NAME THE FACE THAT IS ON SCREEN WHILE IT IS UP?
        # This is the one clip shape where that question is answerable, and it
        # cost a re-render to learn it has to be asked: the 08.28 verification
        # clip was authored `speaker: Steven E. Orr` off a reading of the
        # transcript, the schedule put FLANAGAN in the frame for the first 29
        # seconds, and the bone card sat under the wrong man's face for the four
        # seconds it is up. Every other check passed - NAMED confirmed a name
        # was set, and being set is all it could ever confirm.
        #
        # SKILL.md lists "an authored speaker name is never checked against who
        # is actually talking" as an open problem needing voice embeddings. For
        # head_follow it does not: the turn schedule already says which TILE
        # holds the frame, and the tile is named.
        #
        # Matched by PREFIX on tokens, because a tile tag is a nickname for the
        # person - "steve" for "Steven E. Orr", "flanagan" for "Stephen
        # Flanagan". A WARN and not a refusal, because the tags are free-form
        # and a rig whose tiles are called "left" and "right" can never match.
        _nm, _rl = speaker_label(speaker, mode)
        if _nm:
            # OVER THE PLATE'S WHOLE LIFE, not just its arrival. The card is up
            # for ATTR_HOLD seconds and a turn boundary can fall inside that
            # window - measured on the 08.28 demo, the plate arrived 0.8s before
            # a switch and then sat under the OTHER person for 3.4s. Sampling
            # the arrival instant named the speaker who held it for a fifth of
            # the time.
            at = (HOOK_HOLD + HOOK_OUT) * tempo + ATTR_AFTER_HOOK
            lo, hi = at, at + ATTR_BAND_HOLD * tempo
            seen: dict[str, float] = {}
            for t in sched:
                a0, b0 = t["start"] - start, t["end"] - start
                ov = max(0.0, min(hi, b0) - max(lo, a0))
                if ov > 0:
                    seen[t["who"]] = seen.get(t["who"], 0.0) + ov
            holder = max(seen, key=seen.get) if seen else None
            if len(seen) > 1:
                _sp = ", ".join(f"{k} {v:.1f}s" for k, v in
                                sorted(seen.items(), key=lambda kv: -kv[1]))
                sys.stderr.write(
                    f"note: {slug} nameplate spans a speaker change ({_sp}) - "
                    f"it names the one who holds most of it.\n")
            toks = [w.strip(".,").lower() for w in _nm.split() if w.strip(".,")]
            tt = str(holder or "").lower()
            hit = tt and any(w.startswith(tt) or tt.startswith(w) for w in toks)
            if holder and not hit:
                sys.stderr.write(
                    f"WARNING: {slug} names {_nm!r} on the nameplate, but the "
                    f"tile holding the frame at +{at:.1f}s is {holder!r}.\n"
                    f"         If those are different people the card is under "
                    f"the wrong face for its whole life. Set \"speaker\" to "
                    f"whoever {holder!r} is, or rename the tile to match.\n")
            elif holder:
                sys.stderr.write(
                    f"name: {_nm!r} matches the tile holding the frame "
                    f"({holder!r}) at +{at:.1f}s\n")

        turns_n = len(sched)
        sys.stderr.write(
            f"follow: {slug} {turns_n} turn(s), {conf * 100:.0f}% measured; "
            f"{names[1]} holds the frame for "
            f"{sum(b - a for a, b in fwin):.1f}s of {body_src:.1f}s\n")
        for t in sched:
            sys.stderr.write(f"        {t['start'] - start:6.2f} -> "
                             f"{t['end'] - start:6.2f}  {t['who']} "
                             f"(conf {t['confidence']:.2f})\n")

    # Framing A only, first: the face search and the caption colour both sample
    # through it, and the punch windows are not known until the b-roll is placed.
    fg0 = reframe_chain(
        mode, body_src, slug=slug, start=start, end=end,
        head_crop=head_crop, crop_x=crop_x, duo_crops=duo_crops,
        pip_crop=pip_crop, share_crop=share_crop, face_h=face_h,
        follow_crops=follow_crops, follow_pips=follow_pips,
        follow_windows=fwin)
    fg = fg0

    # Mute windows are authored in SOURCE seconds (that is how you read them off
    # a transcript). Convert to clip-relative and hand them to cut_graph, which
    # owns applying them - see its docstring for why the caller must not.
    spans: list[tuple[float, float]] = []
    dropped: list[list[float]] = []
    for m in (mute or []):
        a0, b0 = max(0.0, float(m[0]) - start), min(dur, float(m[1]) - start)
        if b0 > a0:
            spans.append((a0, b0))
        else:
            dropped.append([float(m[0]), float(m[1])])
    # A MUTE THAT MISSES THE SPAN IS AN AUTHORING ERROR, not a no-op. These are
    # written in SOURCE seconds off a transcript, and the single easiest mistake
    # is to write them clip-relative - which lands every window outside the span
    # and silently keeps the word you were muting. Say so.
    if dropped:
        raise SystemExit(
            f"MUTE WINDOW OUTSIDE THE SPAN: {slug} spans {start:.1f}-"
            f"{start + dur:.1f}s but {dropped} falls outside it, so nothing "
            f"would be muted. Mute windows are authored in SOURCE seconds - "
            f"the same clock as `start`/`end` - not clip-relative.")
    # AND A MUTE THAT SWALLOWS THE CLIP IS ONE TOO. Muting more than half of a
    # clip is never the intent behind bleeping a word, and it is what a
    # units mix-up looks like when the windows happen to land inside the span.
    muted = sum(b - a for a, b in spans)
    if muted > dur * 0.5:
        raise SystemExit(
            f"MUTE WINDOWS COVER THE CLIP: {slug} would be muted for "
            f"{muted:.1f}s of {dur:.1f}s. That is not a bleep, it is a silent "
            f"clip - check the windows are in source seconds.")
    if spans:
        sys.stderr.write(f"note: {slug} muting {len(spans)} window(s).\n")

    pre, vlab, alab = cut_graph(rem_src, dur, spans)
    out = OUT / f"{slug}.mp4"
    splits, extra = split_labels(mode)

    # ---------------------------------------------------- the hook card ----
    # Placed off a measurement of where the face is in THIS clip's panel, not
    # pinned to the top. See place_hook() for the rule and HOOK_PREF for why.
    hookdir = tmp / f"{slug}_hook"
    faces = panel_faces(start, fg0, splits, extra, slug=slug)
    _name, _role = speaker_label(speaker, mode) if ATTR_ON else ("", "")
    # SHARE MODES SUPPRESS IT WHEN THE SOURCE ALREADY CARRIES A BADGE. A meeting
    # tile burns its own lower third in, `_punch_box(keep_badge=True)` already
    # anchors the share punch bottom-left to preserve it, and SKILL.md says that
    # badge attributes the speaker for free. Two nameplates on one frame is the
    # mistake read. Set "source_badge": false on a clip whose tile has none.
    # THE WHITE CARD ALWAYS CARRIES THE NAME. Owner, 2026-08-25, watching a share
    # clip of Dr Alan Ellman whose source burns in its own lower third:
    #
    #   "the white box will always have people's names in it. Even though that
    #    Dr Alan Ellman, the president of Blue Collar or whatever, is on there
    #    ... the white box that comes up, right, we wanna have their name in
    #    there the same way we did it this morning. Those are very good."
    #
    # This suppression defaulted ON for share and duo_share, on the reasoning
    # that a meeting tile burns its own lower third and "two nameplates on one
    # frame is the mistake read". That reasoning is sound and he has overruled
    # it, and the frame explains why: the source badge is inside the SHARED
    # PANEL, small, in the show's own typeface, and it says whatever the guest
    # typed into their rig. The card is ours, it is the thing the eye lands on,
    # and it is the only attribution that survives a crop. They are not two of
    # the same object.
    #
    # It is now OPT-IN: set "source_badge": true in project.json for a source
    # whose badge really does make ours redundant. Default is to draw ours.
    if mode in ("share", "duo_share", "conversation_share") and CFG.get("source_badge", False) \
            and not (isinstance(speaker, dict) and speaker.get("force")):
        if _name:
            sys.stderr.write(
                f"hook: attribution suppressed - {mode} already carries the "
                f"source's own badge. \"source_badge\": false to override.\n")
        _name, _role = "", ""
    _n, hook_y, card_w = build_hook_sequence(hook, hookdir, body_src, faces, slug,
                                             tempo, name=_name, role=_role)
    hook_pre, hook_x = hook_overlay(card_w, tempo)

    # ------------------------------------------------ the caption colour ----
    # This is the one decision that cannot be made until the reframing chain
    # exists, because it is read off the reframed picture: `fg` is exactly what
    # maps source pixels into the panel, so sampling through it is sampling what
    # will actually sit behind the words in this mode, with this crop.
    colours = caption_colours(start, end, mode, fg0, splits, extra,
                              slug=slug, clip_cfg=cap_colour)
    # Recorded so build_all can print the whole slate's picks together. Per-clip
    # stderr lines make one clip's choice visible; only the set side by side shows
    # whether the SET still looks like a set, which is the thing the scrim used to
    # guarantee and this system has to earn.
    CHOSEN_COLOURS[slug] = colours

    seqdir = tmp / f"{slug}_cap"
    ctadir = tmp / f"{slug}_cta"
    # out_dur, NOT dur. `dur` is the SPAN, before the silence pass removes its
    # pauses and before tempo; out_dur is what the body actually runs for, on the
    # same clock as words_out. Passing `dur` puts the ceiling above every cue and
    # the clamp never bites - measured, the last cue still ran 0.096s and 0.330s
    # past the body on the two nd-test clips.
    write_srt(words_out, CAPDIR / f"{slug}.srt", out_dur)  # the DELIVERED times

    # The panel IS the frame, so the graph is now four layers deep with nothing
    # underneath it. What used to sit here - a blurred, slate-tinted copy of the
    # shot scaled up to 1080x1920 and blended with a colour source, plus a
    # rounded-corner alpha mask - existed only to fill the margin around an inset
    # panel. There is no margin. Both are gone, and with them a gblur of a full
    # frame on every frame of every clip.
    # The tempo goes on the COMPOSITED streams, after every overlay - which is
    # precisely why every overlay above is authored in SOURCE seconds (body_src,
    # words_src, rem_src). This comment used to say the opposite: that authoring
    # the tracks on the delivered timeline was what kept them on the words. It
    # is backwards, and believing it cost the feature months - a track built in
    # delivered time and then composited pre-setpts gets the tempo applied to it
    # TWICE. See the TWO TIMELINES block above.
    # atempo, never asetrate: asetrate pitch-shifts, and a guest consented to
    # being recorded, not to being raised a semitone in material that ends on a
    # CTA to a raise.
    vspeed = f",setpts=PTS/{tempo:.4f}" if tempo != 1.0 else ""
    aspeed = f"atempo={tempo:.4f}," if tempo != 1.0 else ""

    # THE OUT-FADE IS PLACED OFF THE LAST WORD, NOT OFF THE END OF THE FILE.
    # It used to start at a flat out_dur - 0.25. The tail floor was 0.06s, so on
    # any clip where the speaker ran straight on from the closing sentence the
    # fade began 0.19s BEFORE the last word finished and took it down to about
    # -13 dB while it was still sounding. Measured across the 83 delivered clips
    # on 2026-08-24: two thirds of them, fifteen ending at or above their own
    # median speech level. Grammatically finished, audibly cut off - which is why
    # it survived every check that reads text.
    #
    # words_src is post-removal at the SOURCE rate; the delivered time of the
    # last word is therefore its end over the tempo. Taking the LATER of the two
    # positions leaves the ordinary case (a real pause before the out-point)
    # exactly as it was, and only moves the fade when it would otherwise bite.
    # HOLDING THE FADE BACK IS NOT THE LEVER - it only shortens the fade, which
    # leaves MORE speech in the last 250ms, not less. Measured on a real clip:
    # moving the fade off the acoustic end took the final 250ms from +2.0 to
    # +5.4 dB against median speech. The lever is the PAD, which is why the
    # acoustic tail is handled where `dur` is decided (see the tail guard in
    # render) rather than here. This stays off the transcript end.
    _last_out = (words_src[-1].end / tempo) if words_src else out_dur
    fade_at = max(0.0, min(out_dur, max(out_dur - END_FADE, _last_out)))
    fade_d = max(0.06, out_dur - fade_at)
    if fade_at > out_dur - END_FADE + 0.01:
        sys.stderr.write(
            f"note: {slug} out-fade held back to +{fade_at:.2f}s "
            f"({fade_d:.2f}s) so it starts after the last word.\n")

    total_b = sum(min(float(b.get("hold", BROLL_HOLD)), out_dur)
                  for b in (broll or []) if b.get("approved") and b.get("asset"))
    # ONE FRAME OF TOLERANCE, AND IT IS NOT SLOP. preflight scores this against
    # its PREDICTED body (q.delivered_body, from the removal list) and render
    # scores it against the MEASURED out_dur; SKILL.md already records those two
    # differing by 0.3s on a real clip. Since BROLL_EVERY went to 14.0 the
    # ceiling binds tightly - at a body of 80.0s the target costs 24.0s against a
    # 24.00s cap, and at 93.5s it is 28.0 against 28.05 - so a hundredth of a
    # second of disagreement between the two measurements would abort a render
    # that preflight had just passed, AFTER the encode. A montage overshoots this
    # by seconds, so a frame of tolerance cannot hide one.
    if total_b > out_dur * BROLL_MAX_FRAC + 1.0 / FPS:
        raise SystemExit(
            f"\nTOO MUCH B-ROLL: {slug} has {total_b:.1f}s of inserts on a "
            f"{out_dur:.1f}s body, over the {BROLL_MAX_FRAC:.0%} ceiling.\n"
            f"The face-on-screen exception is for a beat, not a montage. Drop one "
            f"insert or shorten a hold.\n")

    # B-roll goes on the PICTURE and under everything else, so the captions, the
    # hook and the address all keep running across a cutaway. That is deliberate:
    # the words are the product and they must not blink out because the picture
    # changed. Each insert is a ready-baked 1080x1920 clip (broll.py did the
    # scaling and the push-in once, at fetch time), so all that happens here is a
    # timed overlay - measured at 0.5s of extra encode on a 50s render.
    bfilt, binputs, blabel = broll_chain(broll, start, rem_src, body_src, 4,
                                         tempo, words_src, slug=slug)
    # BOTH sequences wait for broll_chain. The invitation rides the cutaways, and
    # the captions have to ride UP for exactly the frames it is on screen - so
    # they need the same window list, which broll_chain has only just worked out.
    # Building either earlier gave it an empty BROLL_WINDOWS: the invitation
    # silently vanished, and the captions would silently not move.
    # EVERY MODE, and no longer conditional on what the card did with it.
    #
    # It was "head only, and only when the card could not take it" because the
    # nameplate was a FALLBACK - tracked type on the picture, which landed on the
    # shared chart in share and on the seam in duo, so it was gated to the one
    # mode where there was nowhere else to put it. It is a card now, in the strip
    # at the bottom of the frame that the invitation already owns, and a card
    # sits ON the chart rather than in it. The gate went with the defect.
    #
    # duo and duo_share still name nobody, and that is unchanged and deliberate:
    # speaker_label refuses to fall back to the host on a two-up, because the
    # card is a QUOTE attribution and this pipeline has no per-band speaker
    # attribution reliable enough to say which of the two faces said the sentence.
    _band_attr = ("", "") if not ATTR_ON else (_name, _role)
    # RESET THE SECOND PLATE BEFORE ANYTHING READS IT. ATTR2 is a module record
    # and build_all renders a whole slate in one process, so leaving the clear
    # 25 lines below meant cta_windows saw the PREVIOUS clip's nameplate window
    # and pushed this clip's invitation around a card that is not in it.
    # Measured: a clip whose only cutaway is +18..+24 gets its invitation
    # DROPPED entirely when the clip before it had a second plate at +19..+23.2,
    # and stderr names a speaker the clip does not contain.
    ATTR2.clear()
    _cta_wins = cta_windows(body_src, attr=_band_attr[0])
    # THE CAPTIONS RIDE UP FOR THE NAMEPLATE TOO. Both tenants of the bottom
    # strip need the same clearance and for the same reason - at rest a caption
    # sits at y1228..1331 and the nameplate's plate lands on those rows.
    # THE RAISE FOLLOWS THE PLATE'S LEGIBILITY, NOT ITS ARITHMETIC END. A caption
    # card is raised if it OVERLAPS the window at all (see build_caption_
    # sequence), so a card starting 70ms before the window closed was riding
    # high for its whole second - while the plate under it was already at 15%
    # alpha and about to vanish. Measured on the first cut: three consecutive
    # cards at rows 987, then 1265, then 987 inside 1.1s. A 278px jump up and
    # back down for nothing, in the one element the viewer's eye is locked to.
    #
    # Two thirds of the fade-out is where the plate stops being something a
    # caption has to clear.
    # THE SECOND SPEAKER'S NAMEPLATE. See ATTR2. Placed at their FIRST
    # appearance, once, which is where broadcast plates a person and is the only
    # moment the viewer needs it: before it they have not seen this face, after
    # it they have.
    #
    # It has to clear three things, and each one is a defect if it does not.
    # The first plate, or two bone cards share the strip. A cutaway, for the
    # reason attr_window records - two cross-fades running through each other
    # is mud. And the tail, so it is not still fading as the outro wipe starts.
    # If nothing survives that, the second speaker goes unnamed and it SAYS so,
    # rather than being squeezed in somewhere it does not belong.
    # (already cleared above, before cta_windows read it)
    if (mode in ("conversation", "conversation_share") and speakers
            and fwin and len(follow_names) == 2):
        _p1name, _ = speaker_label(speaker, mode)
        _p1 = next((t for t, v in speakers.items()
                    if speaker_label(v, mode)[0] == _p1name), follow_names[0])
        _p2 = next((t for t in follow_names if t != _p1), None)
        _v2 = speakers.get(_p2) if _p2 else None
        if _v2:
            # When the second speaker is tile B their windows ARE fwin; when
            # they are tile A it is everything fwin is not.
            if _p2 == follow_names[1]:
                _w2 = list(fwin)
            else:
                _w2, _at = [], 0.0
                for _a, _b in sorted(fwin):
                    if _a - _at > 1e-3:
                        _w2.append((_at, _a))
                    _at = _b
                if body_src - _at > 1e-3:
                    _w2.append((_at, body_src))
            _aw1 = attr_window(body_src) if _band_attr[0] else None
            _floor = (_aw1[1] + ATTR_BAND_GAP) if _aw1 else 0.0
            _ceil = body_src - (CTA_TAIL if CTA_IN_BODY else 0.0) - ATTR_BAND_OUT
            _n2, _r2 = speaker_label(_v2, mode)
            for _a, _b in _w2:
                _s2 = max(_a, _floor) + ATTR2_SETTLE
                _e2 = min(_s2 + ATTR_BAND_HOLD, _b, _ceil)
                for _ba, _bb in BROLL_WINDOWS:
                    if _s2 < _bb and _e2 > _ba:
                        _e2 = min(_e2, _ba - ATTR_BAND_GAP)
                if _e2 - _s2 >= ATTR_BAND_MIN:
                    ATTR2.append((_s2, _e2, _n2, _r2))
                    sys.stderr.write(
                        f"name: {_n2!r} on a bone card at +{_s2:.1f}s to "
                        f"+{_e2:.1f}s - {_p2!r}'s first appearance\n")
                    break
            if not ATTR2:
                sys.stderr.write(
                    f"name: NO ROOM for {_n2!r} - the second speaker is not "
                    f"named on this clip. Their first appearance is under the "
                    f"first plate or a cutaway.\n")

    _aw = attr_window(body_src) if _band_attr[0] else None
    _attr_win = (_aw[0], _aw[1] - ATTR_BAND_OUT * 0.66) if _aw else None
    _aw2 = attr_window2()
    _attr_win2 = (_aw2[0], _aw2[1] - ATTR_BAND_OUT * 0.66) if _aw2 else None
    _raise = merge_raise(_cta_wins + [w for w in (_attr_win, _attr_win2) if w])
    build_caption_sequence(words_src, seqdir, body_src, tempo=tempo,
                           raise_wins=_raise, colours=colours)
    build_capsule_sequence(ctadir, body_src, colours=colours, attr=_band_attr,
                           wins=_cta_wins)
    # Now the punch-ins, which need the cutaway windows (forced flip on every
    # return, frozen under every cover). Framing B is only built when there is
    # at least one window, so a clip with none renders the A chain unchanged.
    pwin: list[tuple[float, float]] = []
    if mode in PUNCH_MODES:
        pwin = punch_windows(words_src, rem_sent, rem_sil, rem_src,
                             list(BROLL_WINDOWS), body_src, tempo)
    if pwin:
        anchor = None
        if faces:
            l, t_, r, b_ = faces[0]
            anchor = ((l + r) / 2, (t_ + b_) / 2)
        fg = reframe_chain(
            mode, body_src, slug=slug, start=start, end=end,
            head_crop=head_crop, crop_x=crop_x, duo_crops=duo_crops,
            pip_crop=pip_crop, share_crop=share_crop, face_h=face_h,
            follow_crops=follow_crops, follow_pips=follow_pips,
            follow_windows=fwin,
            punch={"windows": pwin, "face": anchor})
        edges = sorted({a for a, _b in pwin} | {b for _a, b in pwin if b < body_src})
        holds = [b - a for a, b in zip([0.0] + edges, edges + [body_src])]
        sys.stderr.write(
            f"punch: {len(edges)} framing change(s) at "
            f"{', '.join(f'+{e:.1f}' for e in edges[:12])}{'...' if len(edges) > 12 else ''}; "
            f"longest unchanged hold {max(holds):.1f}s, median {sorted(holds)[len(holds)//2]:.1f}s\n")
    elif mode in PUNCH_MODES and PUNCH > 1.0:
        sys.stderr.write("punch: no eligible join - the framing never changes on this clip\n")
    filt = (
        pre +
        f"[{vlab}]split={splits}[fgsrc]{extra};"
        # the reframed picture, which already fills 1080x1920 in every mode.
        #
        # settb + fps ON THE BASE, and it is a real fix rather than hygiene. The
        # source is opened at a FRACTIONAL -ss (a slate start is 189.34s, not a
        # frame boundary) and cut_graph then trims and concats spans, so the
        # composite's PTS grid is offset from k/FPS by a sub-frame constant. The
        # output "-r" then RE-GRIDS it by nearest PTS, and every overlay riding
        # the composite - the captions, the hook, the invitation, the cutaway -
        # gets locally duplicated and dropped rather than sampled 1:1.
        #
        # Measured on the delivered 08.25 file, the invitation's own plate top
        # through its first entrance: 1334, 1302, 1302, 1260, 1244, 1244, 1231
        # against the PNGs' 1334, 1302, 1277, 1258, 1244, 1235, 1231 - two frames
        # drawn twice and two never drawn, so the button hitched twice on the way
        # in. cta_state is NOT the cause (4000 random windows through it produce
        # no repeated entrance step); the frame mapping was.
        #
        # Putting the base on 1/FPS BEFORE the overlays means every secondary
        # lands on the frame it was authored for, and the output -r becomes the
        # no-op it was always assumed to be.
        f"[fgsrc]{fg},settb=1/{FPS},fps={FPS}[base];" + bfilt +
        # the hook card (its travel is the x expression), then the captions,
        # then the closing address
        f"[2:v]{hook_pre}[hk];"
        f"[{blabel}][hk]overlay=x='{hook_x}':y={hook_y}:format=auto[hookd];"
        f"[hookd][1:v]overlay=0:{CAP_BAND_Y}:format=auto[capd];"
        f"[capd][3:v]overlay=0:{CTA_BAND_Y}:format=auto,format=yuv420p{vspeed}[vout];"
        f"[{alab}]highpass=f=75,acompressor=threshold=-20dB:ratio=3:attack=6:release=180:makeup=1.5,{aspeed}"
        f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.08,"
        f"afade=t=out:st={fade_at:.3f}:d={fade_d:.3f}[aout]"
    )

    run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(SRC),
        "-framerate", str(FPS), "-i", str(seqdir / "%05d.png"),
        "-framerate", str(FPS), "-i", str(hookdir / "%05d.png"),
        "-framerate", str(FPS), "-i", str(ctadir / "%05d.png"),
        ] + binputs + [
        "-filter_complex", filt,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "19",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-x264-params", "keyint=50:min-keyint=25",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-r", str(FPS),
        str(out),
    ], cwd=WORK)

    denoise(out)
    # MEASURE THE BODY WHETHER OR NOT DENOISE RAN. This sat inside denoise() and
    # so existed only on its success path - it vanished silently with
    # "denoise": false, or with the deep-filter binary missing (the packaged
    # .skill does not carry it). Worse, one clip skipping it still left
    # len(LOUDNESS) > 1, so build_all printed a SET SPREAD computed without the
    # one clip that had skipped the second normalisation - the clip most likely
    # to be the outlier. Here it is on every path, and still before the end card
    # goes on, so it measures the body rather than the body plus a 4s card.
    #
    # It runs AFTER the file is written, so a crash in it would throw away a
    # finished render for the sake of a log line. It may never raise.
    try:
        report_loudness(out)
    except Exception as e:                                   # noqa: BLE001
        sys.stderr.write(f"note: loudness not measured ({type(e).__name__}).\n")
    poster(out)

    # Every clip closes on the same card. Set "endcard": false in project.json to
    # render without it; the address line inside the clip is unaffected either way.
    if CFG.get("endcard", True):
        import endcard
        endcard.append(out, FPS)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("hook")
    ap.add_argument("--mode", default="head",
                    choices=list(TEMPLATES) + ["share"])
    ap.add_argument("--crop-x", type=int, default=None)
    ap.add_argument("--head-crop", default=None,
                    help="w,h,x,y source box for a camera shot; overrides the "
                         "project default (use it to pick a two-up's half)")
    ap.add_argument("--no-beats", action="store_true")
    a = ap.parse_args()
    box = [int(v) for v in a.head_crop.split(",")] if a.head_crop else None
    print(render(a.slug, a.start, a.end, a.hook, a.mode, a.crop_x,
                 beats=not a.no_beats, head_crop=box))
