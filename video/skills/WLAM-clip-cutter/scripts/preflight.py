#!/usr/bin/env python3
"""
Check every clip in slate.json BEFORE rendering anything.

    python3 preflight.py            # check the whole slate
    python3 preflight.py <slug>     # just one

This exists because a render costs 80 to 170 seconds and I was using it as a
diagnostic. On one show a single clip was rendered SIX times, and every failure
was something answerable in a couple of seconds without touching ffmpeg: the
out-point crossed unmapped video, the reference transcript was collapsed over that
stretch, the in-point landed mid-word, the span came up short of the floor once
silence was removed.

So: answer all of it first, fix the slate, then render each clip once.

Reports per clip:
  MODE      is it a real render mode
  LAYOUT    does sections.json cover the span gaplessly, and does the mode fit
  RAIL      for share modes, does the tile this clip crops hold still
  SPEAKER   for share modes, is the authored tile the one talking
  CROPS     is this crop shaped for the CURRENT panel, or is the renderer about to
            trim a third of it away without saying so
  PACK      for share modes, how the panel splits and what it costs the app
  SAFE      does anything that has to be read sit under platform chrome
  TEXT      is the reference punctuated across the span (a flat stretch means the
            captions will render lowercase and the clip will lose its retention cuts)
  EDGES     the first and last whole words, so in/out can be placed exactly
  LENGTH    speech after silence removal, against the 45s floor
  ENDING    WHERE the out-point will actually land - render moves it onto a full
            stop, this says which one and whether the move is even available

CROPS, PACK and SAFE were added when the panel became the full 9:16 frame and the
captions moved onto the picture. They all guard the same shape of failure, which
is the one this change introduced: a value authored against the OLD geometry that
the renderer quietly re-cuts to fit instead of rejecting. Nothing errors, the clip
renders, and a third of the crop is simply gone.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

import broll
import pick
import qmclip as q

HERE = Path(__file__).resolve().parent
# Per-show state follows WLAM_WORK; HERE stays the CODE directory.
# One owner for this lives in qmclip.WORK - repeated here because these
# scripts must run without importing it (analyze.py in particular, which
# would delete the transcripts it is writing).
WORK = Path(os.environ.get("WLAM_WORK") or HERE)
OK, WARN, BAD = "ok  ", "warn", "FAIL"


def line(tag: str, label: str, msg: str) -> None:
    print(f"    [{tag}] {label:<8} {msg}")


def check_layout(c: dict) -> bool:
    try:
        q.check_layout(c["start"], c["end"], c["mode"],
                       layout_ok=bool(c.get("layout_ok")),
                       drop=c.get("drop"))
        line(OK, "LAYOUT", "cut from a share rail, allowed by \"layout_ok\""
             if c.get("layout_ok") else "covered, mode fits")
        return True
    except SystemExit as e:
        line(BAD, "LAYOUT", str(e).strip().split("\n")[0])
        return False


def check_mode(c: dict) -> bool:
    if c["mode"] in q.MODE_NEEDS:
        return True
    line(BAD, "MODE", f"{c['mode']!r} is not a render mode; use {sorted(q.MODE_NEEDS)}")
    return False


def check_rail(c: dict) -> bool:
    if c["mode"] not in ("share", "duo_share", "conversation_share"):
        return True
    # THE KEY THE RENDERER ACTUALLY READS. duo_share renders `duo_crops` and never
    # looks at `pip_crop`, so validating pip_crop on a duo_share clip checked a
    # rectangle that would not appear in the film while the two tiles that WOULD
    # went unchecked. A check aimed at the wrong value is worse than no check: it
    # prints a pass.
    box = ((c.get("duo_crops") or [None])[0] if c["mode"] == "duo_share" else
           (c.get("follow_pips") or q.CFG.get("follow_pips") or [None])[0]
           if c["mode"] == "conversation_share" else c.get("pip_crop"))
    try:
        q.check_rail(c["start"], c["end"], c["mode"], box)
        line(OK, "RAIL", "cropped tile holds still")
        return True
    except SystemExit as e:
        line(BAD, "RAIL", str(e).strip().split("\n")[0])
        return False


# -> None, not -> bool. Every return in here is True - advisory: it reports which tile is talking and cannot fail - and main()
# discarded the value anyway. The annotation was the only thing suggesting this
# could gate a render, which is worse than saying plainly that it does not.
def check_crosstalk(c: dict) -> bool:
    """
    Rapid back-and-forth, on the templates that have to FOLLOW the speaker.

    The cheap half of the wrong-face problem. Cutting between two people needs
    to know who is talking, and on 08.26 the span that got it wrong was the 73rd
    percentile of the show for crosstalk - four handovers inside eleven seconds,
    every one under two seconds long. The turn detector said so itself, dropping
    to 0.15 confidence, but only after a 90-second render.

    Measured off cues.json in milliseconds, so it runs here instead. The fix is
    always to PICK A CALMER MOMENT, which is a better clip anyway - not to cut
    the same crosstalk more cleverly.
    """
    if not c["mode"].startswith("conversation"):
        return True
    try:
        rate = pick.banter_rate(c["start"], c["end"])
    except SystemExit:
        line(WARN, "CROSSTALK", "NOT measured: no cues.json")
        return True
    if rate >= pick.BANTER_MAX:
        line(BAD, "CROSSTALK",
             f"{rate:.1f} short cues/min - too much back-and-forth for a "
             f"template that cuts to the talker (max {pick.BANTER_MAX}). "
             f"Pick a stretch where one person holds the floor, or set "
             f'"allow_crosstalk": true if you have watched it and it is right.')
        return bool(c.get("allow_crosstalk"))
    if rate >= pick.BANTER_WARN:
        line(WARN, "CROSSTALK", f"{rate:.1f} short cues/min - busy. Check the "
                                f"cuts land on the right face.")
        return True
    line(OK, "CROSSTALK", f"{rate:.1f} short cues/min")
    return True


def check_speaker(c: dict) -> None:
    # HEAD IS INCLUDED NOW. A head clip cut from a two-up takes ONE half, and
    # the other person may be the one talking - the same failure the share modes
    # were checked for, in the mode with the most clips and no check at all.
    if c["mode"] not in ("head", "share", "duo_share", "conversation_share"):
        return
    if c["mode"] == "conversation_share":
        # Nothing to pick: the face band FOLLOWS the measured turn schedule, so
        # the tile on screen is whoever turns.plan() says is talking. This check
        # exists to catch a hand-authored pip_crop naming the wrong person, and
        # that field is not read in this mode.
        line(OK, "SPEAKER", "conversation_share follows the turn schedule; "
                            "no tile to mis-author")
        return
    # NOT MEASURED IS NOT A PASS. q.check_speaker returns silently when the
    # project has no "tiles" map or the clip no pip_crop, and this used to print
    # "authored tile matches the voice" over that silence - a pass off no
    # evidence, the defect this file exists to stop.
    if c["mode"] == "duo_share":
        line(OK, "SPEAKER", "duo_share shows both tiles; nothing to pick")
        return
    if not q.CFG.get("tiles"):
        line(WARN, "SPEAKER", "NOT measured: project.json has no \"tiles\" map "
                              "(name: [w,h,x,y] per camera tile). Check a frame.")
        return
    if c["mode"] in ("share", "duo_share") and not c.get("pip_crop"):
        line(WARN, "SPEAKER", "NOT measured: the clip has no pip_crop")
        return
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        why = q.check_speaker(c["slug"], c["start"], c["end"], c["mode"],
                              c.get("pip_crop"), c.get("head_crop"),
                              c.get("crop_x"))
    out = buf.getvalue().strip()
    # THE VERDICT COMES FROM THE FUNCTION, NOT FROM WHETHER IT SPOKE. It writes
    # to stderr only on a mismatch, so empty stderr used to be read as a pass -
    # and it is also what every one of its seven bail-outs produces.
    if why == "match":
        line(OK, "SPEAKER", "authored tile matches the voice")
    elif why == "mismatch":
        line(WARN, "SPEAKER", (out.split("\n")[0].replace("WARNING: ", "")
                               if out else "the authored tile is not the one "
                                           "measured as talking"))
    else:
        line(WARN, "SPEAKER", f"NOT measured: {why}. Check a frame.")
    return


def check_crops(c: dict) -> bool:
    """
    Is this crop shaped for the panel it is about to be rendered into?

    Authored crops are ASPECT-SPECIFIC, and `fill_crop` re-cuts by TRIMMING rather
    than stretching - which is the right behaviour and is why a crop written for
    an older panel still renders. It just loses width from both sides, centred,
    silently. On the change to a 9:16 panel a duo crop authored at the old 1.397
    band aspect keeps 62% of its width, which is a visibly different clip and no
    error anywhere.
    """
    mode = c.get("mode", "head")
    if mode == "head":
        box = c.get("head_crop") or q.CFG.get("head_crop")
        want = [(q.PANEL_W / q.PANEL_H, box)] if box else []
    elif mode == "duo":
        band = (q.PANEL_H - q.SPLIT_GAP) // 2
        want = [(q.PANEL_W / band, b)
                for b in (c.get("duo_crops") or q.CFG.get("duo_crops") or [])]
    elif mode == "share":
        # The camera tile sits above the app; pack_share decides how tall, so the
        # aspect that matters is the panel width over that band.
        box = c.get("pip_crop") or q.CFG.get("pip_crop")
        want = [(q.PANEL_W / max(1, q.pack_share(
            *(c.get("share_crop") or q.SHARE_CROP)[:2], c.get("face_h"),
            tile=(box[0], box[1]), tile_w=q.PANEL_W)[0]), box)] if box else []
    elif mode == "duo_share":
        # TWO tiles side by side in a strip. Both are authored, both are cropped,
        # and neither was checked - the branch fell through to `want = []` and
        # printed "no authored crop" for a clip that has two.
        boxes = c.get("duo_crops") or q.CFG.get("duo_crops") or []
        half = (q.PANEL_W - q.SPLIT_GAP) // 2
        if boxes:
            short = min(boxes, key=lambda b: b[1] / b[0])
            fh = q.pack_share(*(c.get("share_crop") or q.SHARE_CROP)[:2],
                              c.get("face_h"), tile=(short[0], short[1]),
                              tile_w=half)[0]
            want = [(half / max(1, fh), b) for b in boxes]
        else:
            want = []
    elif mode == "conversation":
        # BOTH FOLLOW CROPS, and neither was checked. The branch fell through to
        # `want = []` and printed "no authored crop" for the template the
        # pipeline now mandates - which carries TWO authored crops, one per
        # speaker, each blown up to the full panel.
        want = [(q.PANEL_W / q.PANEL_H, b)
                for b in (c.get("follow_crops") or q.CFG.get("follow_crops") or [])]
    elif mode == "conversation_share":
        # The face band follows the turn schedule and is packed exactly as
        # `share` packs its camera tile, so the aspect that matters is the panel
        # width over that band - measured off the FOLLOW PIPS, which is what
        # this mode actually renders. It used to fall through, and the PACK
        # report beside it measured pip_crop, a rectangle this mode never uses.
        pips = c.get("follow_pips") or q.CFG.get("follow_pips") or []
        if pips:
            short = min(pips, key=lambda b: b[1] / max(1, b[0]))
            fh = q.pack_share(*(c.get("share_crop") or q.SHARE_CROP)[:2],
                              c.get("face_h"), tile=(short[0], short[1]),
                              tile_w=q.PANEL_W)[0]
            want = [(q.PANEL_W / max(1, fh), b) for b in pips]
        else:
            want = []
    else:
        want = []

    # DOES THE CROP EVEN FIT THE SOURCE? Scored aspect only, so a rectangle
    # running off the edge of the master passed - ffmpeg then clamps it and
    # ships a different framing than the one that was checked.
    _sw, _sh = q.src_size() or (1920, 1080)
    for _a, _b in want:
        if len(_b) >= 4 and (_b[2] < 0 or _b[3] < 0
                             or _b[2] + _b[0] > _sw or _b[3] + _b[1] > _sh):
            line(BAD, "CROPS",
                 f"{_b[0]}x{_b[1]} at ({_b[2]},{_b[3]}) runs outside the "
                 f"{_sw}x{_sh} master - ffmpeg clamps it and ships a framing "
                 f"nothing here checked")
            return False

    if not want:
        line(OK, "CROPS", "no authored crop; the default is derived from the panel")
        return True

    worst, detail = 0.0, ""
    for aspect, box in want:
        w, h = box[0], box[1]
        # Through q.fill_crop, the re-cut the renderer actually performs, so
        # this scores HEIGHT loss too. It used to score width only, and a crop
        # too tall for its band printed "authored at the current aspect" while
        # the render quietly took a third of its height off.
        w2, h2, _x, _y = q.fill_crop((w, h, 0, 0), aspect, anchor="bottom")
        kept = (w2 * h2) / (w * h)
        axis = "width" if w2 < w else "height"
        if 1 - kept > worst:
            worst = 1 - kept
            detail = (f"{w}x{h} (aspect {w/h:.3f}) keeps {kept*100:.0f}% of its "
                      f"{axis} at the panel's {aspect:.3f}")
    if worst > 0.15:
        line(BAD, "CROPS", f"{detail} - re-author it, do not rely on the trim")
        return False
    if worst > 0.05:
        line(WARN, "CROPS", detail)
    else:
        line(OK, "CROPS", "authored at the current aspect")
    return True


def check_pack(c: dict) -> bool:
    """
    How a share panel splits, and what that costs.

    Nothing is trimmed off the app any more - it is fitted and its edges extended
    - so the numbers worth reporting changed. What matters now is how much of the
    frame the app really occupies, how much of its band is smear rather than app,
    and how hard the camera tile is being enlarged.
    """
    if c.get("mode") not in ("share", "duo_share", "conversation_share"):
        return True
    sw, sh = tuple(c.get("share_crop") or q.SHARE_CROP)[:2]
    if c["mode"] == "duo_share":
        boxes = c.get("duo_crops") or q.CFG.get("duo_crops") or [[1, 1]]
        short = min(boxes, key=lambda b: b[1] / b[0])
        pw, ph = short[0], short[1]
        tile_w = (q.PANEL_W - q.SPLIT_GAP) // 2
    else:
        pw, ph = tuple(c.get("pip_crop") or q.PIP_CROP)[:2]
        tile_w = q.PANEL_W
    fh, band = q.pack_share(sw, sh, c.get("face_h"), tile=(pw, ph), tile_w=tile_w)
    # THE RENDERER'S OWN ARITHMETIC, not a re-derivation. `drawn` used to be
    # min(band, natural) and was 40px off on a real clip because fit_chain
    # takes a 2% bleed off a padded axis; the tile trim used to be height-only
    # and printed "0% cropped" for a tile that was keeping 52% of its WIDTH at
    # 7.3x. Both now come from the functions the render calls.
    _w, _h, _x, _y, dw, drawn = q.fit_geometry((sw, sh, 0, 0), q.PANEL_W, band)
    pad = band - drawn
    pw2, ph2, _x, _y = q.fill_crop((pw, ph, 0, 0), tile_w / fh, anchor="bottom")
    trim_w, trim_h = 1.0 - pw2 / pw, 1.0 - ph2 / ph
    trim = max(trim_w, trim_h)
    axis = "width" if trim_w >= trim_h else "height"
    blow = tile_w / pw2
    msg = (f"face {fh} ({100*fh/q.PANEL_H:.0f}%) + app band {band} "
           f"({100*band/q.PANEL_H:.0f}%), {pad} of it flat fill; app drawn "
           f"{dw}x{drawn}; tile {pw}x{ph} keeps {pw2}x{ph2} at {blow:.1f}x, "
           f"{100*trim:.0f}% of its {axis} cropped")
    notes = []
    if trim > q.TILE_TRIM_MAX:
        notes.append(f"the face band cuts {100*trim:.0f}% off the camera tile's "
                     f"{axis} (the packer's own limit is {100*q.TILE_TRIM_MAX:.0f}%). "
                     f"The tile's own height at this width is "
                     f"{int(round(tile_w * ph / pw))}; set \"face_h\" to that to "
                     f"keep it whole, at the app's expense - the 08.21.26 "
                     f"reference clip was authored exactly that way")
    if pad > band * q.PAD_MAX_FRAC:
        notes.append(f"over {100*q.PAD_MAX_FRAC:.0f}% of the app band is flat "
                     f"fill. Clearing \"face_h\" usually removes it; otherwise "
                     f"fine on a solid slide, worth a look on a busy one")
    # 4.5 IS CALIBRATED, and an audit read it as a dead threshold. It is not.
    # Measured across every share clip authored on this machine (24 of them, from
    # 08.05 to 08.25), the blow-up factor is bimodal: 20 clips sit at 3.13-3.55
    # on a 320-355px tile, and 4 sit at 4.62-4.91 on a 220-234px one. 4.5 falls
    # in the empty gap between those two populations, so it fires on exactly the
    # clips whose camera tile really is too small to carry a face - 4 of 24, 17%.
    # Do not lower it to "make it fire"; it already does.
    if blow > 4.5:
        notes.append("the tile is small, so that softness is in the source and "
                     "no packing fixes it. Use a stretch where the camera is "
                     "full frame if the face has to carry the clip")
    line(WARN if notes else OK, "PACK", msg)
    for n in notes:
        line(WARN, "PACK", "  " + n)
    return True


def check_safe(c: dict) -> bool:
    """Nothing that has to be read may sit under the platform chrome."""
    # q.CAP_SAFE_BOTTOM, not a literal. This carried its own 1437 while qmclip
    # floors the same line at 1430; two numbers for one constraint.
    edge = q.CAP_SAFE_BOTTOM
    # MEASURE THE INK AT REST, NOT THE CANVAS. Both bands are deliberately taller
    # than what they draw: the caption band carries 480px so a raised card can
    # ride high, and the invitation's carries 630 so the pill's whole 380px rise
    # fits inside it instead of being clipped (which is what made the entrance
    # read as a pop). Scoring the canvas failed a clip whose ink is comfortably
    # inside the line, which is a check calling correct work broken.
    lh = int(q.CAP_SIZE * 1.20)
    cap_bottom = (q.CAP_BAND_Y + (q.CAP_BAND_Y_REST - q.CAP_BAND_Y)
                  + (q.CAP_BAND_H_REST + lh * 2) // 2)
    # ASK THE RENDERER WHERE THE INVITATION ACTUALLY IS. This used to rebuild
    # the lockup's geometry from four constants - rest + PILL_H + 6 +
    # CTA_ADDR_SIZE + 6 - and got a DIFFERENT answer from the thing that draws
    # it: it reported "the invitation to y1422" on the 08.25 clip while the
    # address's ink, with its 3px stroke, actually reached y1448 - 18px under
    # this very line. CTA_ADDR_SIZE is a POINT SIZE, not an ink height, and the
    # stroke was not in the sum at all. Rendering the real PNG and measuring the
    # alpha is a few milliseconds and cannot drift from what ships.
    # AT ITS BIGGEST, NOT AT REST. The button overshoots to max(PILL_SCALE) on
    # the way in and BREATHES to 1 + PILL_PULSE_AMP while it sits, and it is
    # centre-anchored, so both push the bottom row down. Scoring the rest state
    # is a checker that cannot see the frames the element is largest on.
    peak = max(max(q.PILL_SCALE), 1.0 + q.PILL_PULSE_AMP)   # overshoot vs breath
    inv_bottom = q.CTA_BAND_Y + q.pill_ink_bottom(sx=peak)
    tenants = [("captions", cap_bottom), ("the invitation", inv_bottom)]
    # AND THE NAMEPLATE, WHICH NOTHING HAS EVER CHECKED. It was the third tenant
    # of this band for a day and a half and this function scored two - so the
    # credential rendered at y1460..1548 on every head clip the rig shipped,
    # 118px under this very line, and every run of preflight said SAFE. Asked of
    # the renderer, never rebuilt from constants, for the reason above.
    nb = None
    name, title = q.speaker_label(c.get("speaker"), c.get("mode", "head"))
    if name and q.ATTR_ON:
        nb = q.CTA_BAND_Y + q.attr_ink_bottom(name, title)
        tenants.append(("the nameplate", nb))
    bad = [n for n, b in tenants if b > edge]
    if bad:
        line(BAD, "SAFE", f"{' and '.join(bad)} cross the chrome line at y{edge}")
        return False
    line(OK, "SAFE", f"captions rest to y{cap_bottom}, the invitation to "
                     f"y{inv_bottom} at its {peak:.3f} peak"
                     + (f", the nameplate to y{nb}" if nb else "")
                     + f", chrome starts y{edge}")
    return True


def _crop_boxes(c: dict) -> list[list[int]]:
    """Every source rectangle this clip actually puts on screen."""
    mode = c["mode"]
    out: list[list[int]] = []
    if mode == "head":
        # THE RESOLVED RECTANGLE, from qmclip's own head_box - not the authored
        # box and not "the whole frame". The old fallback modelled an unauthored
        # head crop as 1920x1080, which made every burned-in graphic look
        # contained and left check_graphics structurally unable to fail the
        # commonest mode. head_box also applies crop_x and the aspect re-cut.
        out.append(list(q.head_box(c.get("head_crop") or q.CFG.get("head_crop"),
                                   c.get("crop_x"), at=c.get("start"),
                                   dur=(c["end"] - c["start"])
                                   if c.get("end") and c.get("start") else None)))
    if mode in ("duo", "duo_share"):
        out += [list(b) for b in (c.get("duo_crops") or q.CFG.get("duo_crops") or [])]
    if mode == "conversation":
        # THROUGH THE SAME FUNCTIONS THE RENDERER USES. These were the AUTHORED
        # rectangles, but reframe_chain ships head_box(box) re-pointed by
        # centre_on_face - a different rectangle - so GRAPHIC and BURNED were
        # scoring boxes that never reach the screen. The head branch above
        # already asks head_box for exactly this reason.
        _tl = list((c.get("follow_tiles") or q.CFG.get("follow_tiles") or {}).values())
        for _i, _b in enumerate(c.get("follow_crops") or q.CFG.get("follow_crops") or []):
            _box = q.head_box(list(_b), None)
            if len(_tl) == 2 and _i < 2 and c.get("end") and c.get("start"):
                _t = _tl[_i]
                _box = q.centre_on_face(_box, (_t[2], _t[2] + _t[0]),
                                        c["start"], c["end"] - c["start"])
            out.append(list(_box))
    if mode == "conversation_share":
        # The pips ARE the face band's source rectangles in this mode, packed by
        # pack_share exactly as `share` packs its camera tile.
        out += [list(b) for b in (c.get("follow_pips") or q.CFG.get("follow_pips") or [])]
    if mode in ("share", "duo_share", "conversation_share"):
        b = c.get("share_crop") or q.CFG.get("share_crop")
        if b:
            out.append(list(b))
    if mode == "share":
        b = c.get("pip_crop") or q.CFG.get("pip_crop")
        if b:
            out.append(list(b))
    return out


# Sampled frames used to find a static burned-in graphic. Cheap: 28 full-frame
# decodes off a 2.07GB master measured at 6.0s wall.
# Sampled by INPUT SEEK, one frame each - see _graphics_boxes for why that
# matters (a full sequential decode of the master cost ~340 CPU-seconds).
# Frames sampled ACROSS THE WHOLE SHOW, not across the clip. That distinction is
# the whole check. Inside one clip's span a great deal is legitimately static - a
# slide, a chart, a backdrop - and sampling there returned 10 to 77 "graphics"
# per clip including one component covering 335,592 source pixels. Sampled across
# the show, the only thing that holds still through every layout change is a
# graphic burned into the broadcast.
GFX_SAMPLES = 40
GFX_MAD = 6.0        # measured: the floor across a whole 59-minute master is 1.69
GFX_SAT = 35         # ... and the show's own bug is COLOURED
GFX_DILATE = 2       # merge the strokes of one mark into one region - see below
GFX_MIN_PX = 300     # source pixels, below which it is a compression artefact
GFX_MAX_FRAC = 0.02  # ... and above which it is a background, not a bug
GFX_MAX_BOXES = 4    # more than this and the detector is confused; say so
# How wide a burned-in caption plate has to be, as a fraction of the crop, before
# this file will look for it. 0.55 covers a centred caption box; the old test was
# effectively 1.0, which only a full-bleed bar satisfies.
PLATE_MIN_FRAC = 0.55
# How much of a graphic has to be visible for the crop to read as CUTTING it.
# Both extremes are fine and SKILL.md says so in as many words: kept whole it is
# free attribution, "excluded cleanly" it is simply not there. The defect is the
# middle - a half-logo, which reads as a mistake. Measured: the delivered duo
# clip that motivated this check keeps 67% of the mark; a full-frame head crop
# under the punch clips two rows off the top and keeps 98%, which is not a defect
# and must not be reported as one.
GFX_KEEP_LO = 0.08
GFX_KEEP_HI = 0.92
# How close to a crop edge a graphic may sit before the aspect trim is a risk.
# 0.15 is check_crops' own tolerance - the point past which it refuses a crop
# outright - so the two lines are talking about the same trim in the same units.
EDGE_MARGIN = 0.15
_GFX: list[tuple[int, int, int, int]] | None = None
_GFX_GAVE_UP = 0     # how many regions were found when the detector gave up


def _src_seconds() -> float:
    """Length of the master, for spacing the graphic samples across the show."""
    try:
        return float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(q.SRC)], capture_output=True, text=True).stdout)
    except ValueError:
        return 0.0


def _graphics_boxes() -> list[tuple[int, int, int, int]]:
    """
    Where the master carries a static coloured graphic burned into the picture.

    A show bug sits in the same pixels for the whole broadcast, so across frames
    sampled through the WHOLE show its temporal variance is near zero while
    everything else - including a static chart, which only holds still for one
    segment - moves. Measured on the 08.24 master, 40 frames across 59 minutes:
    the MAD floor over the entire frame is 1.69, and the only region under
    GFX_MAD that is also coloured is the QM mark.

    TWO THINGS THAT COST A VERSION EACH.

    Sample across the SHOW, not the clip. The first version sampled the clip's
    own span, where a slide or a backdrop is genuinely static: it returned 10 to
    77 components per clip, one of them 335,592 source pixels. Unusable.

    DILATE BEFORE LABELLING. A logo is not a blob, it is a set of STROKES, and
    4-way components returned the mark as five fragments of 216 to 396 source
    pixels each - every one under any sane floor, so the whole mark vanished. A
    2px dilation at the sampling scale merges the strokes into one region and the
    same master then returns exactly ONE box, x72..198 y72..138, against the
    audit's independently measured x74..195 y72..139.

    Bounded at both ends: under GFX_MIN_PX is a compression artefact, over
    GFX_MAX_FRAC of the frame is a background rather than a bug.

    Limits, stated rather than hidden. Colour only - a white-on-dark lower-third
    name badge is invisible here, and check_burned_in's bimodal plate-or-glyph
    test is the shape for that job. And a master whose bug is only up for part of
    the show raises the MAD and will be missed, which is the safe direction: this
    check only ever refuses, never approves something it did not measure.
    """
    global _GFX
    if _GFX is not None:
        return _GFX
    _GFX = []
    size = q.src_size()
    if not size:
        return _GFX
    sw, sh = size
    dur = _src_seconds()
    if dur < 1.0:
        return _GFX
    try:
        W = 320
        H = max(1, int(round(W * sh / sw)))
        # INPUT SEEKS, not an fps filter. `fps=N/dur` with no seek forces a full
        # sequential decode of the whole master - measured at ~340 CPU-seconds
        # against ~129 for everything else preflight does put together, on a
        # check that is meant to be cheap. Forty single-frame seeks give a
        # byte-identical verdict for about ten, and seeking is already this
        # file's idiom (see check_source and q.probe_panel).
        frames = []
        for k in range(GFX_SAMPLES):
            t = dur * (k + 0.5) / GFX_SAMPLES
            fp = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(q.SRC),
                 "-frames:v", "1", "-vf", f"scale={W}:{H}", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-"], capture_output=True)
            if len(fp.stdout) >= W * H * 3:
                frames.append(fp.stdout[:W * H * 3])
        n = len(frames)
        if n < 8:
            return _GFX
        F = (np.frombuffer(b"".join(frames), dtype=np.uint8)
               .reshape(n, H, W, 3).astype(np.float32))
        med = np.median(F, axis=0)
        mad = np.abs(F - med).mean(axis=0).mean(axis=2)
        mx, mn = med.max(axis=2), med.min(axis=2)
        sat = np.where(mx > 0, (mx - mn) * 255.0 / np.maximum(mx, 1.0), 0.0)
        mask = (mad < GFX_MAD) & (sat > GFX_SAT)
        if not mask.any():
            return _GFX

        # Dilate, so the strokes of one mark label as one region. Plain numpy:
        # OR the mask with itself shifted, GFX_DILATE times.
        grow = mask.copy()
        for _ in range(GFX_DILATE):
            g = grow.copy()
            g[1:, :] |= grow[:-1, :]
            g[:-1, :] |= grow[1:, :]
            g[:, 1:] |= grow[:, :-1]
            g[:, :-1] |= grow[:, 1:]
            grow = g

        sx, sy = sw / W, sh / H
        frame_px = sw * sh
        seen = np.zeros_like(grow, dtype=bool)
        ys_all, xs_all = np.nonzero(grow)
        for y0, x0 in zip(ys_all.tolist(), xs_all.tolist()):
            if seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            ys, xs = [], []
            while stack:
                y, x = stack.pop()
                ys.append(y); xs.append(x)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and grow[ny, nx] \
                            and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            bx0, by0 = int(min(xs) * sx), int(min(ys) * sy)
            bx1, by1 = int((max(xs) + 1) * sx), int((max(ys) + 1) * sy)
            area = (bx1 - bx0) * (by1 - by0)
            if area < GFX_MIN_PX or area > frame_px * GFX_MAX_FRAC:
                continue
            _GFX.append((bx0, by0, bx1, by1))
    except Exception:
        _GFX = []
    if len(_GFX) > GFX_MAX_BOXES:
        # Confused by a static background. SAY SO - the constant's own comment
        # said "say so" and the code said nothing, so the caller printed
        # "no persistent coloured graphic found", which is a different and much
        # more reassuring claim than "I could not measure this". It fires on two
        # of three real masters, and on one of them a discarded component IS the
        # QM mark.
        global _GFX_GAVE_UP
        _GFX_GAVE_UP = len(_GFX)
        _GFX = []
    return _GFX


def check_graphics(c: dict) -> bool:
    """
    Refuse a crop whose EDGE cuts through the show's own burned-in graphic.

    Measured 2026-08-24: 4 of 20 archived duo clips ship with the QM mark sliced
    by the crop edge. A half-logo reads as a mistake in a way a missing logo does
    not, and it is the brand's own mark, on a finance clip.

    Three verdicts, and the middle one is the reason this is not a one-liner:

      FAIL  the rectangle STRADDLES the graphic - part in, part out.
      WARN  the graphic is inside but within EDGE_MARGIN of an edge, so the
            renderer's aspect trim can still take it. `fill_crop` re-cuts every
            authored crop to the panel's aspect by TRIMMING, and on one archived
            clip an authored x=0 looked perfectly clean and then centre-trimmed
            to cut 107 of the mark's 122 columns. How much it trims is CROPS's
            business, not this check's - two owners of that arithmetic is how
            they drift apart - so this reports proximity and points at CROPS.
      OK    wholly inside (it is attribution, and SKILL.md wants it kept) or
            wholly outside.

    The PUNCHED rectangle is tested too, and it is deterministic so it needs no
    aspect: `_punch_box(..., keep_badge=True)` anchors bottom-left, which at
    PUNCH 1.06 on an 844-row band takes 48 rows off the top. Measured on a
    delivered clip the logo-coloured pixel count is tri-state - about 4,500, then
    197, then 0 - with FIVE on/off transitions across 69.6s. The mangled mark
    grows, shrinks, vanishes and returns, which is a feel-the-edit defect on top
    of the brand one.

    Limits, stated rather than hidden: colour bugs only (a white-on-dark name
    badge is invisible here), and a master whose layout changes mid-show will not
    register one at all.
    """
    # AN AUTHORED BOX BEATS THE DETECTOR, and on this material it is the only
    # thing that makes the check work at all. The detector gives up whenever it
    # finds more than GFX_MAX_BOXES static coloured regions, which is 4 of 4 real
    # masters here - a newsroom set is full of still colour - and on at least one
    # of them a discarded region IS the QM mark. So the check that exists to stop
    # a crop slicing the brand's own logo has never run on a master that has one.
    #
    # project.json may carry "graphic_box": [x0, y0, x1, y1] in SOURCE pixels,
    # measured off one frame. That is the same answer already used for the rig's
    # lower third ("source_badge_box"): measure it once, record it, and the check
    # becomes exact instead of a guess that a busy backdrop can defeat.
    authored = q.CFG.get("graphic_box")
    if authored and len(authored) == 4:
        boxes = [tuple(int(v) for v in authored)]
        line(OK, "GRAPHIC", f"using the authored graphic_box "
                            f"x{boxes[0][0]}..{boxes[0][2]} "
                            f"y{boxes[0][1]}..{boxes[0][3]}")
    else:
        boxes = _graphics_boxes()
    if not boxes:
        if _GFX_GAVE_UP:
            line(WARN, "GRAPHIC", f"NOT measured: {_GFX_GAVE_UP} static regions "
                                  f"found, more than GFX_MAX_BOXES ({GFX_MAX_BOXES}) "
                                  f"- the master has too much still colour to tell "
                                  f"a bug from a backdrop. Measure the mark once "
                                  f"off a frame and put it in project.json as "
                                  f"\"graphic_box\": [x0, y0, x1, y1] (source "
                                  f"pixels); this check is exact after that.")
        else:
            line(OK, "GRAPHIC", "no persistent coloured graphic found in the master "
                                "(white-on-dark name badges are not scored here)")
        return True

    mode = c.get("mode", "head")
    rects: list[tuple[str, tuple[int, int, int, int]]] = []
    boxes_l = _crop_boxes(c)
    for i, b in enumerate(boxes_l):
        box = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
        rects.append(("crop", box))
        # ONLY WHERE THE RENDERER ACTUALLY PUNCHES. This was gated on q.PUNCH
        # alone, so it scored punched rectangles in modes that never punch -
        # `duo_share` at all, and `share`'s shared-app tile. Swept over 75
        # archived clips that produced 6,834 positions where the punched rect
        # alone changed the verdict, EVERY ONE an over-refusal and 3,667 of them
        # a hard exit-1. A check that refuses correct work is worse than no
        # check, so it follows q.PUNCH_MODES, and inside `share` it punches only
        # the camera tile (the last box _crop_boxes appends for that mode).
        punches = (q.PUNCH > 1.0 and mode in q.PUNCH_MODES
                   and (mode != "share" or i == len(boxes_l) - 1))
        if punches:
            try:
                w, h, x, y = box
                pb = q._punch_box(box, (x + w / 2.0, y + h / 2.0), keep_badge=True)
                if tuple(pb) != box:
                    rects.append(("punched crop", tuple(int(v) for v in pb)))
            except Exception:
                pass

    ok, warned = True, False
    for gx0, gy0, gx1, gy1 in boxes:
        area = max(1, (gx1 - gx0) * (gy1 - gy0))
        for tag, (w, h, x, y) in rects:
            x1, y1 = x + w, y + h
            ov = (max(0, min(gx1, x1) - max(gx0, x))
                  * max(0, min(gy1, y1) - max(gy0, y)))
            keep = ov / area
            if keep <= GFX_KEEP_LO or keep >= GFX_KEEP_HI:
                pass                       # excluded cleanly, or kept whole
            else:
                line(BAD, "GRAPHIC",
                     f"the {tag} keeps {keep:.0%} of a burned-in graphic at "
                     f"x{gx0}..{gx1} y{gy0}..{gy1} - a half-logo reads as a "
                     f"mistake")
                line(BAD, "GRAPHIC",
                     f"  crop is {w}x{h}+{x}+{y}. Keep it whole with y<={gy0} "
                     f"and y+h>={gy1} and x<={gx0} and x+w>={gx1}, or move off "
                     f"it entirely and name the speaker in the caption.")
                ok = False
                break
            if keep < GFX_KEEP_HI:
                continue                   # cropped out; the trim cannot matter
            m = EDGE_MARGIN
            near = (gx0 - x < w * m or x1 - gx1 < w * m
                    or gy0 - y < h * m or y1 - gy1 < h * m)
            if near and not warned:
                line(WARN, "GRAPHIC",
                     f"a burned-in graphic (x{gx0}..{gx1} y{gy0}..{gy1}) sits "
                     f"within {m:.0%} of the {tag} edge; the aspect trim can "
                     f"still take it - read the CROPS line above")
                warned = True
    if ok and not warned:
        line(OK, "GRAPHIC", f"{len(boxes)} persistent graphic(s) in the master, "
                            f"kept whole or cleanly out of every crop")
    return ok


def check_burned_in(c: dict) -> bool:
    """
    Refuse a span whose SOURCE already has captions burned into it.

    The 08.18.26 master streamed with live captions on for the first six minutes:
    a dark plate with white text across the lower third of the stage. It is not in
    sections.json, `check_crops` is happy, and the render succeeds - it just ships
    with the show's captions arguing with ours, one sentence behind, cut off at
    both ends by the crop. Caught by eye on a contact sheet, which is not a check.

    Told apart from an ordinary dark background - a guest against a black wall, an
    unlit room - by two things a background does not do. The plate carries BRIGHT
    text inside it, and it comes and goes: on that master it was up in 11 of 40
    frames over one stretch and absent for the next 140 seconds straight. A wall
    is in every frame or none.

    WHAT IT CANNOT TELL APART, and the escape hatch for it. Luminance alone
    cannot separate a caption plate from a dark garment with something bright on
    it. Measured on the Morrison master: his maroon shirt with his hand and a
    gold bracelet across it is a 103px bimodal band in the lower third - taller
    than the plate threshold, in the right place, and not a caption. Persistence
    would separate them (a plate holds its position, a hand does not) but that is
    a different and much larger detector than this one.

    So `"burned_ok": true` on a clip skips the check, and it says that it did.
    Set it ONLY after pulling frames from the span and looking - which is what
    the failure message asks for anyway, and is how this false positive was
    found.
    """
    if c.get("burned_ok"):
        line(WARN, "BURNED", "not scored - \"burned_ok\" is set on this clip. "
                             "Only set it after looking at frames from the span.")
        return True
    boxes = _crop_boxes(c)
    if not boxes:
        return True
    dur = c["end"] - c["start"]
    # PER BOX. `hits` used to accumulate across every crop (a share clip has
    # two) against ONE box's frame count, and `always` was whichever box ran
    # last - so a share clip's percentage was double-counted.
    hits: list[float] = []
    worst_pct = 0.0
    always = False
    for w, h, x, y in boxes:
        try:
            raw = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{c['start']:.3f}",
                 "-t", f"{dur:.3f}", "-i", str(q.SRC),
                 "-vf", f"fps=2,crop={w}:{h}:{x}:{y},format=gray",
                 "-f", "rawvideo", "-"], capture_output=True).stdout
            n = len(raw) // (w * h)
            if n < 8:
                continue
            F = (np.frombuffer(raw, np.uint8)[: n * w * h]
                 .reshape(n, h, w).astype(np.float32))
        except Exception:
            continue
        lo = int(h * 0.55)                       # captions live in the lower half
        band = F[:, lo:, :]
        # A caption row is BIMODAL: plate or glyph, almost nothing between. Do NOT
        # test "mostly dark" and "has bright text" separately - the glyphs are 45%
        # of a text row, so the same row fails a >=80%-dark test and the detector
        # sat at zero on a span that plainly had captions burned into it.
        # A WINDOW, NOT THE WHOLE ROW. The bimodal test asked that 90% of the
        # ENTIRE row width be plate-or-glyph, which only a full-bleed caption bar
        # satisfies. A centred caption box - the common shape, and the one every
        # burned-in social caption uses - leaves ordinary picture either side of
        # it, so a plate covering 60% of the width scores 0.60 and the detector
        # reported a clean span. The check was blind to exactly the plates it
        # most needs to see.
        #
        # Slide a window of PLATE_MIN_FRAC of the width along each row and take
        # the best position: a plate anywhere in the row now registers, and the
        # 90% purity inside the window is what still keeps a bright background
        # from tripping it. Done per frame so the cumulative sums stay small.
        #
        # THE TRADE, measured on synthetics. A 60%-wide plate with glyphs goes
        # from 0 qualifying rows to 200 - it was invisible before. A full-width
        # bright band (a shirt edge, a sunlit wall) scores 160 either way, so
        # that false positive is pre-existing and unchanged. What IS new is that
        # a 60%-wide bright feature now scores 160 where it scored 0. The
        # contiguous-run test below is what handles both: a real plate is ONE
        # band of 60-180px in the lower third, and neither of those features is.
        # Re-checked on the Nathan Dean master, which has no burned-in captions:
        # still clean.
        bimodal = ((band < 70) | (band > 185))
        win = max(8, int(band.shape[2] * PLATE_MIN_FRAC))
        plate = np.zeros(bimodal.shape[:2], dtype=bool)
        for _f in range(bimodal.shape[0]):
            cs = np.cumsum(bimodal[_f], axis=1, dtype=np.int32)
            best = (cs[:, win - 1:] - np.concatenate(
                ([[0]] * cs.shape[0], cs[:, :-win]), axis=1)).max(axis=1)
            plate[_f] = (best / win) >= 0.90
        text = ((band > 185).mean(axis=2) >= 0.02)
        # A plate is TALL **AND CONTIGUOUS** - and until 2026-08-24 this asked
        # only for eighteen qualifying rows ANYWHERE in the band, which is a
        # different and much weaker claim. A guest against a bright background
        # trips it without a caption in sight: measured on the Morrison master,
        # 81 of 990 rows qualified on one frame, in FOUR separate runs of 29 to
        # 37px - the bottom edge of his shirt against the table at 97% height,
        # and the sunlit pergola columns behind his head at 13-16%. Summed they
        # clear eighteen easily; not one of them is a plate. It failed a clip
        # whose crop is provably clean.
        #
        # A real burned-in caption is ONE band, 60-180px tall, in the lower
        # third. So take the LONGEST RUN, not the count. n is the sampled frame
        # count (fps=2 over the span, so ~90 for a 46s clip) and the loop is
        # cheap next to the decode that produced it.
        mask = plate & text
        longest = np.zeros(mask.shape[0], dtype=int)
        for _i in range(mask.shape[0]):
            _row = mask[_i]
            if not _row.any():
                continue
            _d = np.diff(np.concatenate(([0], _row.astype(np.int8), [0])))
            _s = np.flatnonzero(_d == 1)
            _e = np.flatnonzero(_d == -1)
            longest[_i] = int((_e - _s).max())
        # AND THE RUN HAS TO BE PLATE-SIZED, which 18 rows is not. 18 was set when
        # this counted scattered rows and it survives as a floor, but a band that
        # actually holds legible text is 8-15% of the frame - the 08.18.26 master
        # this check was written for measured 182px of a 1080 source. Measured on
        # the Morrison master: the false-positive runs top out at 29px (his shirt
        # against the table at the crop's bottom edge), while a caption plate
        # painted onto the same frame measures 83px. 5% of the crop height puts
        # the line at 49px for a 990px crop - clear of one, well under the other -
        # and scales with the crop instead of assuming a size.
        per_frame = longest >= max(18, int(h * 0.05))
        if per_frame.any():
            box_hits = [i / 2.0 for i, v in enumerate(per_frame) if v]
            hits += box_hits
            worst_pct = max(worst_pct, 100.0 * len(box_hits) / max(1, n))
            # NEARLY every frame counts as always. The discriminator is
            # PERSISTENCE, and demanding literally 100% made it brittle: on the
            # Litt master the bimodal shape is his black t-shirt plus a bright
            # white-and-red chest logo, present in 88% of frames and absent only
            # where his own hand crosses it. Real burned-in captions are one
            # sentence behind the talking and gap out between them - the master
            # this check was written for measured 27% (11 frames of 40). 80%
            # leaves daylight either side of both.
            always = always or bool(per_frame.mean() >= 0.80)

    if not hits:
        line(OK, "BURNED", "no captions burned into the source over this span")
        return True
    pct = worst_pct
    where = ", ".join(f"{c['start'] + t:.1f}s" for t in sorted(set(hits))[:6])
    # The FAIL line is 8%, not 2%. Measured: the 08.18.26 span this check was
    # written for scored 16.5%; the 08.21.26 McGlone reference clip - approved,
    # delivered, no captions in it - scores 3.2% on its Bloomberg chart crop,
    # because a chart legend (small light text on a dark panel) is bimodal too.
    # Under 8% is a WARN with the timestamps, so the operator looks rather than
    # moves a span that was fine.
    if pct < 8.0:
        line(WARN, "BURNED", f"a caption plate flickers in {pct:.1f}% of frames "
                             f"({where}) - look at those frames before shipping; "
                             f"a chart legend or a lower-third reads this way too")
        return True
    if always:
        # Present in EVERY frame. Real captions come and go with the talking; a
        # background that happens to read bimodal - a lit sign, a bright logo on a
        # black wall - does not. Say so and let the contact sheet settle it.
        line(WARN, "BURNED", "something plate-shaped is in every frame of this "
                             "span, which is more like a background than a caption "
                             "- check the contact sheet")
        return True
    line(BAD, "BURNED", f"THE SOURCE HAS ITS OWN CAPTIONS over {pct:.0f}% of this "
                        f"span ({where}). They will fight ours. Move the span, or "
                        f"crop above the plate.")
    return False


def check_cadence(c: dict, words, rem, dur: float, tempo: float = 1.0) -> bool:
    """
    How long this clip will sit with nothing changing on screen.

    Measured across 63 delivered clips: the pipeline makes about 23 cuts per
    minute against the reference reel's 13.2, but only 1.6 of them per minute are
    a VISIBLE picture change, and the median clip holds one unchanging frame for
    29 seconds. On a locked-off webcam a removal takes out a quarter second of
    air and the speaker is in the same place either side of it, so the join is
    real in the audio and invisible in the picture.

    This reports the timing half, which is what preflight can know before a
    render: how far apart the joins are, and where the longest hole is. It is a
    PROXY for the rendered picture, not a measurement of it, and the thresholds
    are calibrated off those 63 clips rather than measured off a reference - so
    it warns and never fails.
    """
    if not rem or dur <= 0:
        line(WARN, "CADENCE", "no removals; the picture will not change at all")
        return True
    joins = sorted(s for s, _ in rem)
    # q.delivered_body, not a third hand-rolled `dur - sum(removed)`. This copy
    # skipped the speed division, so at SPEED_MAX 1.12 it read a body 1.12x
    # longer than the viewer watches and understated cuts per minute by 11%. It
    # does not feed broll_target, which is the only reason it survived the pass
    # that gave the arithmetic one owner - and one copy nobody was watching is
    # exactly how the arithmetic got into more than one place to begin with.
    body = q.delivered_body(dur, rem, tempo)
    # THE GAPS AND THE RATE ARE NOW IN ONE BASE. The rate became DELIVERED
    # seconds when body did, but the gaps kept being read straight off `joins`
    # and `dur`, which are SOURCE-span seconds - so one line printed cuts per
    # delivered minute and the next printed a hole measured over a span that
    # includes the silence the render cuts and is not played back at the clip's
    # tempo. At SPEED_MAX 1.12 that reads a gap 1.12x longer than the viewer
    # sits through, against thresholds of 12s and 20s.
    #
    # IT WAS NOT DORMANT, and the first version of this comment said it was.
    # The mismatch never needed a tempo to bite: the gaps were summed against
    # `dur` while `body` was already `dur` MINUS the removals, so every clip
    # was off by the length of its own collapsed silence. Measured on the
    # 08.21.26 McGlone reference at "speed": 1.0, the CADENCE line moved from
    # "longest gap 18.3s at +39s" to "17.9s at +38s" - 2.5s of removals, and
    # all of the difference. The direction is safe, a gap can only shrink, so
    # the 12s and 20s warnings fire less often rather than spuriously. But a
    # comment claiming a dormancy the data contradicts is the exact fault this
    # file exists to catch.
    def _seen_at(t: float) -> float:
        """Source-span second t, as the second the viewer reaches it."""
        return q.remap_time(t, rem) / tempo      # THE forward map, not a copy

    seen = [_seen_at(j) for j in joins]
    gaps = [j2 - j1 for j1, j2 in zip([0.0] + seen, seen + [body])]
    worst = max(gaps)
    at = ([0.0] + seen)[gaps.index(worst)]
    cpm = len(joins) / max(body, 1) * 60
    b = [x for x in (c.get("broll") or []) if x.get("approved")]
    msg = f"{len(joins)} joins, {cpm:.0f}/min; longest gap {worst:.1f}s at +{at:.0f}s"
    if b:
        msg += f"; {len(b)} b-roll insert(s) break it up"
    line(WARN if worst > 12 and not b else OK, "CADENCE", msg)
    if worst > 20 and not b:
        line(WARN, "CADENCE", f"  over 20s with no join. On a static camera that "
                              f"is a still frame for a third of the clip - the "
                              f"case b-roll exists for. broll.py propose {c['slug']}")
    return True


_DECODED: dict[str, dict | None] = {}


def decode_span(c: dict) -> dict | None:
    """
    ONE decode per clip, shared by EDGES, LENGTH, TEMPO, CADENCE and BROLL.

    There used to be two - check_edges_and_length at dur+3.0 under one slug and
    _delivered_body at dur under another - so LENGTH and BROLL scored two
    different bodies of the same clip, and BROLL's ignored the adaptive tempo
    that LENGTH applied (preflight.py divided by the slate's `speed` only, while
    render measures the FRAC ceiling and the count on the post-tempo body). It
    also runs q.drop_unspoken, as render does, so words whisper invented over
    dead air no longer count toward the WPM or supply a sentence end.

    Returns None when the span could not be decoded; every consumer says so
    rather than scoring the raw span as if nothing had been cut.
    """
    slug = c["slug"]
    if slug in _DECODED:
        return _DECODED[slug]
    start, dur = c["start"], c["end"] - c["start"]
    try:
        # MIRROR render(), IN ITS ORDER. Two things were different and both moved
        # the ENDING verdict: render pulls `dur` back off a trailing silence
        # BEFORE it plans the ending, and it decodes `decode_window(...)` rather
        # than the whole span plus the lookahead. Swept over 6,000 real spans,
        # 10.8% flipped direction between the two and 0.17% were green here and
        # then refused by the renderer - which, now that a stuck span is a hard
        # SystemExit, is a wasted render at best.
        #
        # The pull-back is about 60% of the divergence, so it has to come first;
        # mirroring the decode window alone closes the smaller half. `dur` is
        # deliberately NOT reassigned for the callers - EDGES, LENGTH, CADENCE and
        # BROLL all score the authored span, and this is only about which words
        # plan_ending gets to see.
        env_full = q.envelope(start, dur + q.END_LOOKAHEAD)
        _dur = dur
        _last = q.last_speech(env_full, _dur)
        if _last is not None and _dur - _last > 1.20:
            _dur = q.snap(_last + 0.35)
        _win = q.decode_window(env_full, _dur, q.END_LOOKAHEAD)
        words = q.word_times(start, _win, "pf_" + slug[:18])
        words = q.drop_unspoken(words, env_full)
        inside = [w for w in words if w.start < dur]
        env = env_full[: int(round(dur / q.HOP))]
        rem_sent = q.find_removals(inside, env, dur)
        rem_sil = q.collapse_silence(env, dur)
        rem = q.merge_windows(rem_sent, rem_sil)
        cut = sum(e - s for s, e in rem)
        tempo, why = q.tempo_for(inside, dur - cut, c.get("speed"))
        d = {"words": words, "inside": inside, "env": env, "rem": rem,
             "end_dur": _dur,
             "rem_sent": rem_sent, "rem_sil": rem_sil,
             "cut": cut, "tempo": tempo, "why": why,
             "body": q.delivered_body(dur, rem, tempo)}
    except Exception as e:                     # whisper missing, ffmpeg failing...
        line(WARN, "DECODE", f"could not decode this span ({type(e).__name__}: "
                             f"{e}); LENGTH, CADENCE and the BROLL count are NOT "
                             f"measured")
        d = None
    _DECODED[slug] = d
    return d


# -> None, not -> bool. Every return in here is True - advisory: it reports the punch-in plan and cannot fail - and main()
# discarded the value anyway. The annotation was the only thing suggesting this
# could gate a render, which is worse than saying plainly that it does not.
def check_punch(c: dict) -> None:
    """
    How often the FRAMING will change, from the renderer's own toggle ladder.

    This is the picture-change cadence the CADENCE line could only proxy: the
    punch-ins turn silence joins into visible cuts, and q.punch_windows is the
    function render() calls, fed the same decode. Informational; it warns when
    the framing never changes, because that is the 29-seconds-on-one-frame
    case the punch exists to end.
    """
    if c["mode"] not in q.PUNCH_MODES:
        # duo_share is the only mode left out, and NOT for want of attribution -
        # duo joined PUNCH_MODES without it, because both its bands punch
        # together. duo_share carries the shared app, and look.md's design panel
        # rejected moving a chart with its axis labels at the frame edge.
        line(OK, "PUNCH", f"not applied in {c['mode']} (it carries the shared app; "
                          f"moving a chart's axis labels was rejected by name)")
        return
    if q.PUNCH <= 1.0:
        line(OK, "PUNCH", "off (\"punch\": 1.0 in project.json)")
        return
    d = decode_span(c)
    if d is None:
        line(WARN, "PUNCH", "not measured (span not decoded)")
        return
    dur = c["end"] - c["start"]
    body_src = (dur - d["cut"])
    # the cutaway windows as render() will place them, before the re-snap
    ins = []
    for x in (c.get("broll") or []):
        if x.get("approved") and x.get("asset"):
            a0 = max(0.0, q.remap_time(float(x.get("at", 0)) - c["start"], d["rem"]))
            ins.append((a0, a0 + float(x.get("hold", q.BROLL_HOLD)) * d["tempo"]))
    words_src, _ = q.apply_removals(d["inside"], dur, d["rem"]) if d["rem"] else (d["inside"], dur)
    win = q.punch_windows(words_src, d["rem_sent"], d["rem_sil"], d["rem"], ins,
                          body_src, d["tempo"])
    edges = sorted({a for a, _b in win} | {b for _a, b in win if b < body_src})
    if not edges:
        line(WARN, "PUNCH", "no eligible join - the framing never changes; the "
                            "picture is a still frame between cutaways")
        return
    holds = [b - a for a, b in zip([0.0] + edges, edges + [body_src])]
    worst = max(holds) / d["tempo"]
    med = sorted(holds)[len(holds) // 2] / d["tempo"]
    # THE FIRST ONE IS ITS OWN NUMBER. A clip can have a healthy median hold
    # and still open on a static frame through the entire stay-or-scroll
    # window, which is what the seeded opening move (q.PUNCH_OPEN) exists to
    # stop - so report it, and say so when it did not happen.
    first = edges[0] / d["tempo"]
    late = first > q.PUNCH_OPEN_HI + 0.5
    line(WARN if (worst > 12 or late) else OK, "PUNCH",
         f"{len(edges)} framing change(s), first at +{first:.1f}s, longest "
         f"unchanged hold {worst:.1f}s, median {med:.1f}s "
         f"(plus {len(ins)} cutaway(s))")
    if late:
        line(WARN, "PUNCH", f"  the picture holds still for the first {first:.1f}s - "
                            f"the decision to stay is made around 1.3s. The opening "
                            f"move is " + ("OFF (\"punch_open\": false)" if not q.PUNCH_OPEN
                            else "on but was skipped; check for a join before "
                                 f"+{q.PUNCH_OPEN_HI:.1f}s"))
    return


def _delivered_body(c: dict) -> float | None:
    """The body the RENDERER will measure: the span minus the silence it cuts.

    The ARITHMETIC lives in q.delivered_body, not here. It used to live in
    THREE places - this function divided by speed, propose() in broll.py did
    not, and check_cadence above had a third copy that also did not - and the
    first two both fed broll_target. Under the old flat 2-or-3 rule the few
    percent between them never changed the answer; with a step every
    BROLL_EVERY seconds it can, by about 6% of the body at SPEED_MAX 1.12,
    which is a third of a step at 91s. check_cadence only reported its reading,
    so it outlived the first pass; it now calls q.delivered_body too. This side
    keeps only the decoding.
    """
    d = decode_span(c)
    return None if d is None else d["body"]


# --------------------------------------------------------- picture identity ---
_PICTURES: dict | None = None
_PICTURES_MTIME: int | None = None
_PICTURES_OK = False


def _load_pictures() -> None:
    """
    Group every index row into PICTURES, so two rows for one photograph collide.

    THE IDENTITY IS THE PHOTOGRAPH, NOT THE BAKE AND NOT THE SOURCE FILE. Keying on
    `src` alone was the first version and it has a hole a DELIVERED clip already fell
    through: `it-acts-before-you-feel-it` carries "hospital emergency equipment" and
    "heart monitor ecg hospital", which are two DOWNLOADS of one Pexels video
    (/video/hospital-heart-monitor-display-in-operation-33643950/) under two src
    filenames - identical page, identical title, and a byte-identical frame hash at
    t=1s. That clip shipped the same picture twice and src-keying passed it.
    `retire` had already learned this and widens by page AND src for the same
    reason; this is the same union, done once as a union-find so a chain (row A
    shares a page with B, B shares a src with C) closes properly.

    Cached against index.json's mtime, not forever: caching a FAILED read for the
    life of the process turned the whole check into a silent no-op, which is worse
    than not having it. `learned_vocab` in broll.py already caches this way.
    """
    global _PICTURES, _PICTURES_MTIME, _PICTURES_OK
    f = q.BROLL_LIB / "index.json"
    try:
        mt = f.stat().st_mtime_ns
    except OSError:
        mt = None
    if _PICTURES is not None and mt == _PICTURES_MTIME:
        return
    _PICTURES_MTIME, _PICTURES_OK, _PICTURES = mt, False, {}
    try:
        raw = json.loads(f.read_text())
    except (OSError, ValueError):
        return

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for name, row in raw.items():
        if not isinstance(row, dict):
            continue
        key = f"row:{_norm(name)}"
        find(key)
        for field in ("page", "src"):
            v = (row.get(field) or "").strip()
            if v:
                union(key, f"{field}:{v.casefold()}")
    _PICTURES = {}
    for name, row in raw.items():
        if not isinstance(row, dict):
            continue
        n = _norm(name)
        _PICTURES[n] = (find(f"row:{n}"),
                        (row.get("title") or row.get("src") or name))
    _PICTURES_OK = True


def _norm(asset: str) -> str:
    """One spelling per asset. APFS is case-insensitive, so two casings are one file."""
    return str(asset).strip().casefold()


def _picture(asset: str) -> tuple[str, str]:
    """(identity, human name) for the PICTURE behind a baked asset."""
    _load_pictures()
    n = _norm(asset)
    # Unknown rows fall back to their own normalised NAME, never to "" - two
    # different unknown assets must not be silently equal to each other.
    return (_PICTURES or {}).get(n, (n, asset))


def check_broll(c: dict) -> bool:
    """Approved inserts, their assets, and the share of the body they take."""
    b = c.get("broll") or []
    live = [x for x in b if x.get("approved")]
    # Every clip ships with at least one insert, in every mode. See SKILL.md's
    # non-negotiables: a clip whose picture never changes is not finished, and
    # b-roll is the only lever left once the speech is already cut tight.
    if not live:
        line(BAD, "BROLL", "no approved insert - every clip ships with at least "
                           f"one. Run: python3 broll.py propose {c['slug']}")
        return False
    missing = [x for x in live if not x.get("asset")
               or q.broll_asset(str(x["asset"])) is None]
    if missing:
        line(BAD, "BROLL", f"{len(missing)} approved insert(s) have no fetched "
                           f"asset - run: python3 broll.py fetch")
        return False
    ok = True
    # COUNT, DERIVED FROM THE BODY. This used to be a flat floor of 2 and a flat
    # ceiling of 3, and that is how a 91s body with 3 inserts passed while the
    # picture sat unchanged for 30 seconds at a stretch - over double the 12s
    # the CADENCE line warns at. The target is now q.broll_target(body), one
    # cutaway per q.BROLL_EVERY seconds, measured off the 08.21.26 McGlone clip
    # the owner set as the standard: 5 inserts in a 91s body. The body is taken
    # once, here, because _delivered_body decodes the span and is not cheap.
    body = _delivered_body(c)
    # Inserts must land INSIDE the span, and not under the hook card. render()
    # skips an insert that collapses past the tail but never checked the head
    # or an `at` outside the span at all; broll.py's propose respects the
    # lead-in, a hand-edited `at` did not have to.
    d = decode_span(c)
    placed: list[tuple[float, float, str]] = []
    for x in live:
        at = float(x.get("at", -1))
        if not (c["start"] <= at <= c["end"]):
            line(BAD, "BROLL", f"insert {x.get('term', '?')!r} is at {at:.1f}s, "
                               f"outside the span {c['start']:.1f}..{c['end']:.1f}")
            ok = False
        elif d is not None:
            seen = q.remap_time(at - c["start"], d["rem"]) / d["tempo"]
            # MIRROR THE RENDERER, the same discipline decode_span already
            # follows for the ending. Two things move a cutaway between this
            # scoring and the picture, and preflight modelled neither - so it
            # certified holds and spacing that were then quietly changed:
            #
            #   1. THE RE-SNAP. broll_chain snaps the anchor onto the word named
            #      in "on" within +/-2.5s, because the slate's time came from a
            #      different whisper decode than the render's. That window is
            #      wider than the 5.5s BROLL_MIN_FACE floor is deep, so a slate
            #      that passed the spacing check here could render below it.
            #   2. THE TAIL CLAMP. `a1 = min(a0 + hold, out_dur - TAIL_CLEAR)`
            #      shortens an insert near the end, and preflight scored the
            #      AUTHORED hold - so an insert certified at 3.7s could render
            #      at 2.1s, under the floor this file just checked it against.
            hold = float(x.get("hold", q.BROLL_HOLD))
            on = str(x.get("on") or "").lower()
            if on:
                near = [(q.remap_time(w.start, d["rem"]) / d["tempo"], w)
                        for w in d["inside"]
                        if q.split_token(w.text)[0].lower() == on]
                near = [(t, w) for t, w in near if abs(t - seen) <= 2.5]
                if near:
                    t0, w0 = min(near, key=lambda tw: abs(tw[0] - seen))
                    snapped = max(0.0, t0 - 0.15)
                    if abs(snapped - seen) > 0.05:
                        line(OK, "BROLL",
                             f"insert {x.get('term', '?')!r} will snap "
                             f"{snapped - seen:+.2f}s onto {w0.text.strip()!r} "
                             f"at +{t0:.2f}s - scored where it will LAND")
                    seen = snapped
            # d["body"] is delivered_body() off the AUTHORED span; the renderer
            # measures out_dur after plan_ending has moved the out-point. On the
            # nd-test set that leaves preflight about 0.4s short (46.8 against
            # 47.2), so it reports slightly less room than the render will have -
            # conservative, which is the direction a gate should err in. Both
            # fire on the same inserts; only the number differs.
            body_seen = d.get("body") or 0.0
            if body_seen:
                room = body_seen - q.BROLL_TAIL_CLEAR - seen
                if room < hold - 0.05:
                    # THE SAME TWO CONSTANTS AS THE RENDERER, DERIVED THE SAME
                    # WAY. This carried its own copy of the 0.8 collapse literal
                    # and its own fixed `q.BROLL_IN + q.BROLL_OUT` travel, so
                    # after broll_ramp landed preflight would hard-fail at 0.79s
                    # of room for a drop the renderer no longer performs - the
                    # gate that certifies the slate asserting something the thing
                    # it guards does not do. Both now read the renderer's own
                    # numbers.
                    settled = room - sum(q.broll_ramp(room))
                    _floor = (q.BROLL_FLASH_MIN if x.get("kind")
                              not in (None, "", "beat", "carrier") else 0.8)
                    if room < _floor:
                        line(BAD, "BROLL", f"insert {x.get('term', '?')!r} at "
                                           f"+{seen:.1f}s has no room before the "
                                           f"{q.BROLL_TAIL_CLEAR:.1f}s tail "
                                           f"clearance - render() DROPS it.")
                        ok = False
                    elif settled < q.BROLL_HOLD_MIN - 0.05:
                        line(BAD, "BROLL", f"insert {x.get('term', '?')!r} at "
                                           f"+{seen:.1f}s is cut from {hold:.1f}s "
                                           f"to {room:.1f}s by the tail "
                                           f"clearance, leaving {settled:.1f}s "
                                           f"settled against the "
                                           f"{q.BROLL_HOLD_MIN:.1f}s floor. Move "
                                           f"it earlier.")
                        ok = False
                    else:
                        line(WARN, "BROLL", f"insert {x.get('term', '?')!r} is "
                                            f"shortened to {room:.1f}s by the "
                                            f"tail clearance")
                    hold = max(0.0, room)
            if seen < q.BROLL_LEAD_IN:
                line(WARN, "BROLL", f"insert {x.get('term', '?')!r} lands at "
                                    f"+{seen:.1f}s, inside the {q.BROLL_LEAD_IN:.0f}s "
                                    f"lead-in the hook card owns")
            placed.append((seen, hold, str(x.get("term", "?"))))

    # EVERY PICTURE HELD FOR THE SAME NUMBER OF SECONDS IS A SMELL, and until
    # 2026-08-26 it was the norm: MIN_HOLD computes to exactly 3.7, the
    # idea-derived term in the hold formula contributed nothing in the common
    # case, and 16 of the 17 clips cut under that band held every insert for the
    # identical number of seconds. One line would have said so.
    #
    # It is a WARN, not a refusal - three sentences of the same length is a real
    # thing that happens - but on a clip with three or more inserts it is worth
    # a look, because the duration is supposed to come from how long the thought
    # runs and a constant means it did not.
    # A RATIO, NOT AN EQUALITY TEST. `len(set(holds)) == 1` only catches holds
    # that are EXACTLY flat, and 3.5/3.6/3.6 walks straight past it. Measured
    # over all 74 slates on this machine, the 44 clips with two or more approved
    # holds have a max/min ratio with median 1.00, p90 1.14 and max 1.55, and 31
    # of the 44 sit under 1.10 - so this pipeline had never once produced
    # variety, and the check that existed could see only 25 of the 37 flat ones.
    #
    # 2.0 is not a taste threshold: the flash band tops out at 1.60 and the
    # carrier band starts at 3.20, so a clip carrying one of each cannot have a
    # ratio under 2.0, and a clip whose holds all fell to one floor cannot have
    # one over it. The bands make the number for us.
    holds = [round(float(x.get("hold", q.BROLL_HOLD)), 2) for x in live]
    if len(holds) >= 3:
        spread = max(holds) / max(min(holds), 0.01)
        if spread < 2.0:
            line(WARN, "BROLL", f"every insert is held for about the same time "
                                f"({min(holds):.2f}..{max(holds):.2f}s, "
                                f"{spread:.1f}x) - the hold is meant to track "
                                f"what the picture IS and how long the subject "
                                f"is talked about, so a flat spread usually "
                                f"means they all fell to one floor. A name is a "
                                f"flash; a skyline is a scene.")

    # A CHAIN, NOT A LOOP. SKILL.md's rule is that no subject is used twice in a
    # clip, and until now nothing implemented it. `propose` de-dupes on the TERM
    # (`used_terms`), which is a DIFFERENT test and does not catch this.
    #
    # The library is what makes it expensive: 114 index rows (105 live) resolve
    # to 83 distinct pictures, 19 of them reachable from two or more live rows,
    # and TEN reachable under two or more live TERMS. The worst is one
    # supermarket clip answering to four terms that barely share a word -
    # "retail shopping supermarket aisle", "supermarket aisle shopper cart",
    # "shopping mall crowd shoppers", "grocery store shopping cart aisle" - so a
    # three-link chain asking three different words can be served that one piece
    # of footage three times and pass every other check in this function. It
    # gets worse as the vocabulary loop compounds, because every approval adds
    # another word pointing at a picture that already exists.
    #
    # Compared on the PICTURE - see _picture. Names are no guide: those four
    # bakes share no common stem, and conversely two rows for one JPEG can share
    # almost every character.
    seen_pic: dict[str, str] = {}
    _load_pictures()
    if not _PICTURES_OK:
        # Say so. The two lines below announce when they cannot score; a silent
        # no-op here reads identically to "no repeats found", which is the one
        # answer this check must never give by accident.
        line(WARN, "BROLL", f"{q.BROLL_LIB / 'index.json'} is unreadable; repeated "
                            f"pictures are NOT scored")
    for x in live:
        pid, name = _picture(str(x.get("asset")))
        first = seen_pic.get(pid)
        if first is not None:
            line(BAD, "BROLL", f"{x.get('term','?')!r} and {first!r} are the SAME "
                               f"picture ({name}) - a repeat reads as a loop, not "
                               f"a chain. Retype one term and re-run: "
                               f"python3 broll.py propose {c['slug']}")
            ok = False
        else:
            seen_pic[pid] = str(x.get("term", "?"))

    # SPACING, END-TO-START. BROLL_MIN_FACE is the term that stops a set of
    # cutaways reading as a montage, and it was enforced in propose and nowhere
    # else - which is word for word the situation the lead-in check above was
    # written for ("propose respects the lead-in, a hand-edited `at` did not
    # have to"). That fix was applied to the lead-in and not to the spacing
    # sitting next to it, so two inserts authored 2s apart passed everything.
    #
    # Delivered seconds on both sides: `seen` is remapped and de-tempo'd above,
    # and a slate's `hold` is already what the VIEWER sees (see broll_chain,
    # which scales it by the tempo on the way INTO the pre-tempo composite).
    # Sort on the TIME only. Sorting the whole tuple falls through to hold and then
    # to the term STRING on a tie, which named the two inserts in the wrong order.
    order = sorted(placed, key=lambda pl: pl[0])
    for (s0, h0, t0), (s1, _h1, t1) in zip(order, order[1:]):
        gap = s1 - (s0 + h0)
        if gap <= 0:
            line(BAD, "BROLL", f"{t0!r} and {t1!r} OVERLAP once the silence is "
                               f"removed - {t1!r} starts {-gap:.1f}s before "
                               f"{t0!r} has finished. Two inserts cannot share "
                               f"the frame; move one.")
            ok = False
        elif gap < q.BROLL_MIN_FACE - 0.05:
            line(BAD, "BROLL", f"only {gap:.1f}s of speaker between {t0!r} and "
                               f"{t1!r}; the floor is {q.BROLL_MIN_FACE:.0f}s "
                               f"end-to-start. Two cutaways that close together "
                               f"read as a montage, not as two beats.")
            ok = False

    if body is None:
        line(WARN, "BROLL", f"{len(live)} approved insert(s); the count, the "
                            f"spacing and the share of the body are NOT scored "
                            f"(span not decoded)")
        return ok
    target = q.broll_target(body)
    # THE FLOOR IS A REAL MINIMUM, NOT target-1. Tying it to the target made
    # the 2026-08-30 cadence change (one per 16s -> one per 10s) refuse clips
    # that are perfectly good: on the 08.26 master propose finds 3 placeable
    # subjects on a 59s body against a target of 6, because the binding
    # constraint is how many DISTINCT picturable subjects sit far enough apart -
    # not the ceiling, and not anything the operator can author around. A gate
    # that refuses every clip on a real master is a gate that gets --force'd,
    # and then it protects nothing.
    #
    # So: under the hard minimum is a REFUSAL, under the target is a WARNING
    # that names the gap. The target still drives propose, which is where it
    # does its work.
    floor = q.BROLL_MIN_INSERTS
    # THE COUNT CHECK OWNS THE EDITORIAL CAP AND NOTHING ELSE: target + 1. It
    # used to ALSO derive a cap from the share of the body - min(target + 1,
    # int(BROLL_MAX_FRAC * body / BROLL_HOLD)) - and that priced every insert at
    # BROLL_HOLD (4.0 then, 4.2 now), which is not what slates ask for. Counted over every
    # slate.json on the Desktop, 74 approved inserts across 23 clips: the median
    # hold is 3.0s, the mean 3.11s, 53 of the 74 are 3.0s or shorter, and only 9
    # are a full 4.0s - five of those being the 08.21.26 McGlone clip that set
    # the density rule in the first place.
    #
    # So the two derivations contradict each other on ordinary slates. A 45.0s
    # body with 4 inserts at the median 3.0s is 12.0s, 26.7% of the body, every
    # hold inside the window enforced below AS IT STOOD THEN: the FRAC line
    # prints OK while THIS line FAILs, quoting a 30% derivation it never
    # performed on the slate's real holds. (At a full hold each it would be
    # 35.6% at the 4.0 of the day, 37.3% at today's 4.2, which is the case the
    # frac term was reading.) Note the 3.0s median no longer passes the hold
    # check at all: travel is 0.633s now, so the raw window is 3.63..4.20.
    #
    # Two places computing one quantity from different inputs is what produced
    # this contradiction AND the mirror-image one the frac term was added to
    # fix, so the fix is one owner each rather than a third attempt at making
    # them agree: the SHARE of the body belongs solely to the FRAC check at the
    # bottom of this function, which sums the slate's ACTUAL holds.
    #
    # No floor guard on top of it. broll_target never returns less than
    # BROLL_MIN_INSERTS, so target + 1 can never land under
    # max(BROLL_MIN_INSERTS, target - 1). For the record, because the guard that
    # used to sit here had its number wrong: MIN_CLIP 45.0 is the floor on the
    # DELIVERED TOTAL, `body / tempo + card` with CARD_SECONDS 4.0, not on the
    # body. 41.0 / 1.0 + 4.0 = 45.0, so a body of 41.0s passes LENGTH and does
    # reach here - the archive's shortest bodies sit in the low 40s.
    ceiling = target + 1
    # THE COUNT FAILURES NAME THE BODY AND THE TARGET. Six clips in the archive
    # score under today's floor when re-measured, three of which were already
    # under the old flat floor of 2. THAT PAIR COUNTS ONLY THE CLIPS THAT CARRY
    # AN INSERT, which is the population this check can actually re-score;
    # counting every delivered clip on the Desktop, insert or none, gives 26
    # under today's floor and 23 under the old flat 2. SKILL.md quotes the
    # 26/23 pair, so name the population here rather than leaving two files
    # stating different numbers for a sentence that begins "in the archive".
    # An operator who opens one of those slates and reads "no approved insert"
    # style wording assumes the slate is damaged and goes looking for the
    # damage. It is not damaged, it is scored against a density that did not
    # exist when it was authored, and delivered clips are never re-run. Say
    # which body and which target produced the number.
    if len(live) < floor:
        line(BAD, "BROLL", f"{len(live)} approved insert(s) on a {body:.1f}s body; "
                           f"the floor is {floor} and the target {target}, at one "
                           f"per {q.BROLL_EVERY:.0f}s. Run: python3 broll.py "
                           f"propose {c['slug']}")
        ok = False
    elif len(live) < target:
        # One under target WARNS rather than refusing. The findability survey in
        # SKILL.md measured oil at 0.62 and the Fed at 0.48, so on an
        # institutional topic the last subject sometimes does not exist in the
        # free libraries. One short is a nudge; two short is the FAIL above.
        line(WARN, "BROLL", f"{len(live)} approved insert(s) on a {body:.1f}s body; "
                            f"the target is {target} at one per {q.BROLL_EVERY:.0f}s. "
                            f"One more: python3 broll.py propose {c['slug']}")
    if len(live) > ceiling:
        line(BAD, "BROLL", f"{len(live)} approved inserts on a {body:.1f}s body; "
                           f"the target is {target}, so the ceiling is {ceiling} "
                           f"- one over target, which is an EDITORIAL cap. What "
                           f"the inserts cost as a share of the body is a "
                           f"separate line below, off their real holds. Any more "
                           f"reads as a montage.")
        ok = False
    # HOLD, and the asset actually being that long. A slate can ask for 4.0s of
    # a 1.8s bake and the renderer will clone-pad the difference as a frozen
    # frame - which is what "the b-roll looked cheap" turned out to be.
    # THE BAND IS PER-INSERT NOW, because the hold is. This used to compute
    # `travel = q.BROLL_IN + q.BROLL_OUT` ONCE and score every insert against
    # the single window 3.20..3.60 - which is the one line that made a
    # sub-second insert impossible no matter what the renderer could draw.
    # Both halves of it were wrong once a hold became a band:
    #
    #   - the TRAVEL is no longer a constant. broll_ramp scales the dissolve to
    #     the insert, so charging a 0.9s flash 0.70s of travel reports it as
    #     settling for 0.20s when it actually settles for 0.45s.
    #   - the FLOOR is no longer one number. BROLL_HOLD_MIN is what an insert
    #     CARRYING THE SIGN-UP owes; a flash owes only what a picture needs to
    #     be read.
    #
    # An insert with no "kind" is scored as it always was, so every slate
    # authored before 2026-08-30 re-scores byte-identically.
    for x in live:
        h = float(x.get("hold", q.BROLL_HOLD))
        kind = x.get("kind")
        din, dout = q.broll_ramp(h)
        travel = din + dout
        if kind in (None, "", "beat", "carrier"):
            lo_h, hi_h = q.BROLL_HOLD_MIN + travel, q.BROLL_HOLD
            what = f"{q.BROLL_HOLD_MIN:.1f}s settled"
        else:
            lo_b, hi_b = broll.hold_band(kind)
            lo_h, hi_h = lo_b, hi_b
            what = f"a {kind} ({lo_b:.2f}..{hi_b:.2f}s)"
        if not (lo_h - 0.05 <= h <= hi_h + 0.05):
            line(BAD, "BROLL", f"hold {h:.2f}s on {x.get('term','?')!r} settles for "
                               f"{h - travel:.2f}s after {travel:.2f}s of travel; "
                               f"the band for {what} is "
                               f"{lo_h:.2f}..{hi_h:.2f}")
            ok = False
        f = q.broll_asset(str(x.get("asset")))
        if f is not None:
            try:
                # `adur`, NOT `d`. `d` is the decode dict from decode_span forty
                # lines up, and this loop used to shadow it with a float. Nothing
                # read it afterwards so nothing broke, but the spacing check above
                # is only safe because it sits ABOVE this line - which is not a
                # property worth leaving for the next person to discover.
                adur = float(subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout)
            except ValueError:
                adur = 0.0
            # THE ASSET IS CONSUMED IN SOURCE SECONDS, THE HOLD IS DELIVERED.
            # broll_chain composites PRE-tempo and scales the hold on the way in
            # (`hold * hold_scale`), so a 4.2s hold at SPEED_MAX 1.12 eats 4.704
            # source seconds. This line had no tempo term, so a 4.25s asset passed
            # while the render needed 4.70 - a 0.45s shortfall that BROLL_PAD then
            # clone-pads as a frozen tail, reported by nothing. `d` is never None
            # here: the `body is None` return above guarantees it.
            need = h * d["tempo"]
            if adur + 0.05 < need:
                line(BAD, "BROLL", f"{x['asset']} is {adur:.1f}s but the slate holds "
                                   f"it {h:.1f}s, which the tempo {d['tempo']:.2f} "
                                   f"makes {need:.2f}s of source - the rest would be "
                                   f"a frozen frame. Run: python3 broll.py sweep "
                                   f"--apply")
                ok = False
    # CEILING against the DELIVERED body, which is what render() measures. The
    # source span is 2s longer on a real clip, so three 5s inserts used to pass
    # here and hard-fail the render after 90 seconds of encoding. The body was
    # measured up in the COUNT block; do not re-measure it.
    total = sum(float(x.get("hold", q.BROLL_HOLD)) for x in live)
    # The line NAMES the target, because an operator reading only a percentage
    # cannot tell an under-inserted clip from a finished one: 3 inserts in a 91s
    # body is a comfortable 13% and still the wrong clip.
    holds = "/".join(f"{float(x.get('hold', q.BROLL_HOLD)):.1f}" for x in live)
    line(OK if total <= body * q.BROLL_MAX_FRAC else BAD, "BROLL",
         f"{len(live)} of {len(b)} approved, {total:.1f}s over {holds}s "
         f"({total/max(body,1):.0%} of the {body:.1f}s body, target {target} at "
         f"one per {q.BROLL_EVERY:.0f}s, ceiling {q.BROLL_MAX_FRAC:.0%})")
    # AND A FLOOR UNDER THE SHARE. The ceiling alone is satisfiable by cutting
    # to almost nothing, which stopped being hypothetical the moment an insert
    # could be half a second: ten 0.6s flashes hit a count target of ten with
    # 6.0s of picture - LESS b-roll than the clip that prompted "you need to
    # have more b-roll", while passing the count gate that exists to ask for
    # more. Counting cuts is not the same as showing pictures.
    # HOW LONG THE PICTURE NEVER CHANGES. The BROLL block enforces a FLOOR on the
    # face between two cutaways and nothing on the other side, so a clip can pass
    # every line above and still hold one shot for twelve seconds. Scored over
    # the whole body - the open, every interior gap, and the tail - because two
    # of the three holes on the clip that prompted this were at the edges, where
    # no end-to-start test looks.
    if order and body:
        # `order` is the same (delivered time, hold, term) list the spacing check
        # above uses - AFTER the re-snap, so these are the seconds the viewer
        # actually sees, not the authored anchors.
        _faces, _prev = [], 0.0
        for _a, _h, _t in order:
            _faces.append(("the open" if _prev == 0.0 else f"+{_prev:.1f}s", _prev, _a - _prev))
            _prev = _a + _h
        _faces.append((f"+{_prev:.1f}s", _prev, body - _prev))
        for _lbl, _at, _gap in _faces:
            if _gap > q.BROLL_GAP_MAX:
                line(WARN, "BROLL",
                     f"{_gap:.1f}s of unbroken face from {_lbl} - the picture "
                     f"never changes for {_gap/q.BROLL_EVERY:.1f} cut-intervals, "
                     f"against a ceiling of {q.BROLL_GAP_MAX:.1f}s. Add a "
                     f"cutaway in that stretch, or accept it.")
    floor_s = q.broll_floor_seconds(body)
    if live and total < floor_s:
        line(BAD, "BROLL",
             f"only {total:.1f}s of picture on a {body:.1f}s body "
             f"({total/max(body,1):.0%}); the floor is {floor_s:.1f}s "
             f"({q.BROLL_MIN_FRAC:.0%}). There are enough CUTS - they are too "
             f"SHORT. Lengthen the inserts whose subject is talked about "
             f"longest, or add one more.")
        ok = False
    # THE INVITATION MUST HAVE SOMETHING TO RIDE ON. CTA_IN_BODY is False
    # whenever the end card is on, so a cutaway is the ONLY carrier of the
    # sign-up inside the body, and it needs cta_insert_min() to fit the button's
    # five beats. Before variable holds every insert cleared that by accident of
    # the floor; now most will not, and a clip whose inserts are all flashes
    # ships with no sign-up anywhere in the body - silently, because cta_windows
    # reports a short window on stderr and nothing gates it.
    need = q.cta_insert_min()
    if live and not q.CTA_IN_BODY and not any(
            float(x.get("hold", q.BROLL_HOLD)) >= need - 0.05 for x in live):
        line(BAD, "BROLL",
             f"no insert is {need:.2f}s or longer, so NOTHING in the body "
             f"carries the sign-up - during a cutaway the speaker is gone too, "
             f"and the captions never lift either. Grow one insert to "
             f"{need:.2f}s, or set \"cta_in_body\": true.")
        ok = False
    return ok and total <= body * q.BROLL_MAX_FRAC


# The exposure band, read from the same config keys broll.py reads.
#
# COPIED, NOT IMPORTED, and deliberately: `broll` owns LUMA_BAND, but importing it
# here costs about six seconds on a tool whose entire argument is that it answers
# in a few seconds where a render costs 80 to 170. Same keys, same defaults, so a
# project that moves the band moves both. It is the same trade analyze.py already
# makes with qmclip's vad_args.
_LUMA_BAND = (float(q.CFG.get("broll_luma_lo", 45.0)),
              float(q.CFG.get("broll_luma_hi", 160.0)))
# ...and the deadband, for the same reason it exists in broll: a correction this
# small is not worth an encode generation, so the pass DECLINES it and records no
# marker. Testing the band alone therefore flagged an asset for a fix that will
# never be applied, on every run - which is the same false positive `sweep`'s own
# report had, fixed there and missed here until a real clip printed it.
_GAMMA_DEADBAND = 0.05


# -> None, not -> bool. Every return in here is True - advisory: it reports the picture's shape and cannot fail - and main()
# discarded the value anyway. The annotation was the only thing suggesting this
# could gate a render, which is worse than saying plainly that it does not.
# HOW BUSY AN INSERT MAY BE before it fights the captions. The words sit ON the
# picture, so what matters is not the insert's motion in the abstract but how
# much the CAPTION BAND moves underneath them. Measured on two delivered clips,
# asset motion against band motion at y1130:
#
#     asset  1.2 ->  4.0      speaker baseline 2.3 - 3.9
#     asset  2.5 ->  4.0
#     asset  4.5 ->  6.1
#     asset  5.6 ->  3.6
#     asset 15.5 ->  5.5
#     asset 21.2 ->  5.5
#     asset 37.2 -> 19.9      <- 5-9x the baseline
#
# Everything up to 21 keeps the band within a couple of points of the speaker;
# 37 is a step change. 28.5 is the library's own p90 and sits in the empty gap
# between those two populations, which is where a threshold belongs.
#
# It fires on 8.2% of the 195 approved inserts across every slate on this
# machine - about one in twelve, and each one is a real "is this picture too
# busy" judgement rather than noise. A WARN: a busy picture can be the right
# picture, and only a person looking at it can say.
BROLL_MAX_MOTION = 28.5


def check_picture(c: dict) -> None:
    """
    What the approved inserts actually LOOK like, and whether they went through
    the passes that decide it.

    IT REPORTS THE PICTURE AND POLICES THE PIPELINE, which is not the check that
    was originally asked for. The audit wanted a warn-band on luma - "nothing
    checks what is actually in the picture, a blown-out white wall and near-black
    neon are both fully legal". Both of those assets are corrected now (196 -> 163,
    12.7 -> 28) and the dead-still ones are pushed, so re-measured after those two
    changes a band would fire on 15 assets that are ALL in a deliberate state: the
    ones the black floor capped short of the band on purpose, the ones inside the
    gamma deadband, and two pictures that are simply monochrome. A line that cries
    wolf on correct work every single run is worse than no line.

    So what is warned about is an asset that never went THROUGH a pass - luma
    outside the band with no `eq` recorded - which is a fact about the pipeline
    rather than a judgement about the photograph, and is silent on everything the
    passes have already handled.
    """
    live = [x for x in (c.get("broll") or []) if x.get("approved") and x.get("asset")]
    if not live:
        return
    _load_pictures()
    if not _PICTURES_OK:
        line(WARN, "PICTURE", "index.json unreadable; the inserts are NOT scored")
        return
    try:
        raw = json.loads((q.BROLL_LIB / "index.json").read_text())
    except (OSError, ValueError):
        return
    lo, hi = _LUMA_BAND
    unrecorded, unprocessed, shown, busy = [], [], [], []
    for x in live:
        row = raw.get(str(x.get("asset"))) or {}
        if "luma" not in row:
            unrecorded.append(str(x.get("asset")))
            continue
        shown.append(f"{x.get('term','?')[:22]} L{row['luma']:.0f}"
                     f"/m{row.get('motion', 0):.0f}")
        if float(row.get("motion", 0)) > BROLL_MAX_MOTION:
            busy.append(f"{x.get('term','?')!r} at {float(row['motion']):.0f}")
        if not (lo <= row["luma"] <= hi) and not row.get("eq"):
            tgt = lo if row["luma"] < lo else hi
            want = math.log(max(row["luma"], 1e-6) / 255.0) / math.log(tgt / 255.0)
            if abs(want - 1.0) >= _GAMMA_DEADBAND:
                unprocessed.append(f"{x.get('term','?')!r} at luma {row['luma']:.0f}")
    if busy:
        line(WARN, "PICTURE",
             f"{len(busy)} insert(s) are BUSY enough to fight the captions: "
             f"{', '.join(busy)} (over {BROLL_MAX_MOTION:.0f}). Measured on a "
             f"37-motion bokeh asset, the caption band moves 19.9 against a "
             f"2.3-3.9 baseline on the speaker - the words sit on a flickering "
             f"field. Pull a frame and read them; swap the picture if you cannot.")
    if unrecorded:
        line(WARN, "PICTURE", f"{len(unrecorded)} insert(s) have no recorded "
                              f"metrics - run: python3 broll.py sweep --metrics --apply")
    if unprocessed:
        line(WARN, "PICTURE", f"{len(unprocessed)} insert(s) sit outside the luma "
                              f"band {lo:.0f}-{hi:.0f} and carry no exposure "
                              f"correction, so they never went through the pass: "
                              f"{', '.join(unprocessed)}. Run: python3 broll.py "
                              f"sweep --exposure --apply")
    if shown and not unrecorded and not unprocessed:
        line(OK, "PICTURE", "  ".join(shown))
    return


def check_text(c: dict) -> bool:
    """Is the reference punctuated across this span, in 25s sub-windows."""
    path = WORK / "cues.json"
    if not path.exists():
        line(WARN, "TEXT", "no cues.json; the word pass will be used unaided")
        return True
    cues = [x for x in json.loads(path.read_text())
            if x[1] > c["start"] and x[0] < c["end"]]
    if not cues:
        line(WARN, "TEXT", "no reference cues over this span")
        return True
    flat = []
    for i in range(0, int(c["end"] - c["start"]) + 1, 25):
        lo = c["start"] + i
        hi = min(c["start"] + i + 25, c["end"])   # never judge text past the out-point
        if hi - lo < 8:                           # a sliver tells you nothing
            continue
        w = " ".join(t for a, b, t in cues if b > lo and a < hi).split()
        if len(w) < 20:
            continue
        caps = sum(1 for x in w if re.search(r"[A-Z]", x)) / len(w)
        text = " ".join(w)
        ends = len(re.findall(r"[.!?]", text))
        # The caps RATIO is only a proxy for "has casing", and it misfires on a
        # stretch of ordinary prose that happens to contain no proper nouns: on
        # the AI Matters master, 366-391s is three correctly capitalised, fully
        # punctuated sentences whose only capitals are the three sentence-initial
        # ones, giving 0.028 against a 0.03 floor. Re-decoding it changes nothing,
        # because nothing is wrong with it. So ask the question directly as well:
        # does every sentence in the window START with a capital? That is the
        # thing the ratio was standing in for. A genuinely flat chunk - whisper
        # returning lowercase and unpunctuated - still has no sentence ends and
        # still fails, which is the case this check exists for.
        sents = [x.strip() for x in re.split(r"[.!?]+", text) if x.strip()]
        heads = [x.lstrip("\"'([")[:1] for x in sents]
        # ends >= 1, not 2. A window holding ONE long correctly-cased, correctly
        # -terminated sentence could never satisfy a two-sentence escape, so it was
        # failed for having only its sentence-initial capital - the same false
        # positive the note above records, one sentence instead of three. Measured
        # on AI Matters 08.26.26, 357-367s: 37 words, caps 0.027, one sentence
        # opening 'With' and closing 'passenger.' Nothing is wrong with it, and
        # re-decoding it changes nothing. The genuinely flat case - whisper
        # returning lowercase and unpunctuated - has NO sentence ends and is still
        # caught by the `ends < 1` clause below, and a punctuated-but-uncased
        # window still fails here because its heads are lower case.
        cased = ends >= 1 and len(heads) >= 1 and all(h.isupper() for h in heads if h.isalpha())
        if (caps < 0.03 and not cased) or ends < 1:
            flat.append(f"{lo:.0f}-{hi:.0f}s")
    if flat:
        line(BAD, "TEXT", f"reference is FLAT over {', '.join(flat)} - captions will "
                          f"render lowercase. Re-decode that window with a casing prompt.")
        return False
    line(OK, "TEXT", "reference is punctuated across the span")
    return True


def check_edges_and_length(c: dict) -> bool:
    """Word boundaries and the post-silence duration, from one decode."""
    dur = c["end"] - c["start"]
    d = decode_span(c)
    if d is None:
        line(BAD, "LENGTH", "not measured: the span could not be decoded")
        return False
    inside, rem, cut, tempo, why = d["inside"], d["rem"], d["cut"], d["tempo"], d["why"]
    if not inside:
        line(BAD, "EDGES", "no speech decoded in this span")
        return False
    first, last = inside[0], inside[-1]
    line(OK, "EDGES", f"opens {first.text.strip()!r} at +{first.start:.2f}s "
                      f"| closes {last.text.strip()!r} ending +{last.end:.2f}s")
    check_opening(c, inside)
    check_hook_relates(c, inside)
    check_about(c)
    card = q.CARD_SECONDS if q.CFG.get("endcard", True) else 0.0
    body = dur - cut

    # The tempo, and the floor measured on what is DELIVERED. Checking the floor
    # before the tempo is the trap: a 41s body at 1.08 delivers 38.0s plus the
    # card, and a pre-tempo check waves it through at 45.0.
    if tempo != 1.0:
        line(OK, "TEMPO", f"x{tempo:.3f}  ({why})")
    elif why:
        line(OK, "TEMPO", f"left alone ({why})")
    final = body / tempo + card

    lo, hi = q.CLIP_BAND
    tag = OK if final >= q.MIN_CLIP else BAD
    line(tag, "LENGTH", f"{dur:.1f}s span - {cut:.1f}s silence"
                        + (f" / x{tempo:.3f}" if tempo != 1.0 else "")
                        + f" + {card:.0f}s card = {final:.1f}s "
                          f"(house band {lo:.0f}-{hi:.0f}s)")
    check_cadence(c, inside, rem, dur, tempo)
    if final < q.MIN_CLIP:
        line(BAD, "LENGTH", f"widen by {(q.MIN_CLIP - final) * tempo:.1f}s of real speech"
                            + (", or set \"speed\": 1.0" if tempo != 1.0 else ""))
        return False
    if final > hi:
        # A WARN, not a refusal. The 08.21 McGlone clip the owner called
        # "literal perfect" ran 1:35, so the top of the band is a preference and
        # MAX_CLIP is the actual ceiling.
        line(WARN, "LENGTH", f"{final:.1f}s is over the {hi:.0f}s top of the "
                             f"house band - fine if the idea needs it, but check "
                             f"there is not a second idea in here that wants its "
                             f"own clip.")
    return check_ending(c, d, dur)


def check_ending(c: dict, d: dict, dur: float) -> bool:
    """
    HOW THE CLIP ENDS: the speaker finishes, it lands, then the card.

    This used to be one WARN line off `last.text.endswith((".","!","?"))`, which
    is a weaker test than the renderer's - it passes an ellipsis, an abbreviation
    and an initial, the three false positives finished_sentence was tightened
    against - and which said only "the out-point will move", never whether the
    move would WORK. It can fail four ways (past the run-on cap, across hard_out,
    across a layout change, or more than a third of the clip back), and in all
    four the clip used to render and ship on a stderr line. So preflight asks
    q.plan_ending, the same function render calls, and reports what will happen.
    """
    words = d["words"]
    # The span render will plan against - see decode_span. It differs from `dur`
    # only when the authored out-point runs seconds past the last spoken word.
    kind, i, cost = q.plan_ending(
        words, d.get("end_dur", dur), hard_out=c.get("hard_out"), start=c["start"],
        layout_ok=lambda t: q.check_layout(c["start"], t, c.get("mode", "head"),
                                           layout_ok=bool(c.get("layout_ok")),
                                           drop=c.get("drop")))

    if kind == "landed":
        last = d["inside"][-1].text.strip()
        line(OK, "ENDING", f"lands on {last!r} - no move needed")
        return _trail_off(last)
    if kind == "flat":
        line(WARN, "ENDING", "no full stop anywhere in this span - the transcript "
                             "came back unpunctuated, so the ending cannot be "
                             "checked here. Listen to the tail.")
        return True
    if kind == "stuck":
        heard = d["inside"][-1].text.strip()
        near = words[i].text.strip()
        # THE SANCTIONED ESCAPE IS HONOURED HERE TOO. render() ships a stuck span
        # when the clip sets "allow_ragged_end" - SKILL.md documents it as the
        # way to keep a moment whose sentence never closes - but preflight
        # refused regardless, so the only way to get one out was `--force`, which
        # switches off every other check on every other clip in the set. An
        # escape that can only be taken by disarming the whole gate is not an
        # escape.
        if c.get("allow_ragged_end"):
            line(WARN, "ENDING", f"stops mid-sentence on {heard!r} and no full "
                                 f"stop is reachable - shipping it anyway on "
                                 f"\"allow_ragged_end\"")
            return True
        line(BAD, "ENDING", f"stops mid-sentence on {heard!r} and no full stop is "
                            f"reachable")
        line(BAD, "ENDING", f"  nearest is {near!r} at {c['start'] + words[i].end:.1f}s "
                            f"({cost:+.1f}s). Move `end` onto it, or re-pick. "
                            f"render() REFUSES this span. Set "
                            f"\"allow_ragged_end\": true to ship it as it is.")
        return False

    word = words[i].text.strip()
    if kind == "forward":
        line(OK, "ENDING", f"runs on {cost:.1f}s to finish the sentence, landing "
                           f"on {word!r} at {c['start'] + words[i].end:.1f}s")
    else:
        # A pull-back SHORTENS the clip, and LENGTH above was measured on the
        # authored span - so a big one can put a passing clip under the floor.
        # Running on only ever makes it longer, which is the safe direction.
        line(OK if cost < 1.0 else WARN, "ENDING",
             f"pulls back {cost:.1f}s to the last full stop, landing on {word!r}"
             + (f" - LENGTH above is measured on the authored span, so read it "
                f"{cost:.1f}s shorter" if cost >= 1.0 else ""))
    return _trail_off(word)


def _trail_off(word: str) -> bool:
    """
    The clip ends on a finished sentence. Does the sentence LAND?

    A grammatical full stop is not the same as a finished thought. Read off the
    delivered archive, clips end on "go.", "that.", "this.", "about.", "good.",
    "way." and "through." - every one of them a sentence whose meaning lives in
    something already said, so the clip stops on a pronoun and the payoff is a
    sentence away in one direction or the other. That is the other half of the
    owner's note: the ending has to connect to the main idea.

    A WARN, never a fail. Whether "That's it." is a landing or a trail-off is an
    editorial call about the moment, and that is not decidable from a word list.
    """
    core = word.rstrip().rstrip('"\'”’)]}»').rstrip(".!?").lower()
    if core in q.TRAIL_OFF:
        line(WARN, "ENDING", f"  ...but it lands on {core!r}, which carries none of "
                             f"the meaning. Check the ending is the POINT of the "
                             f"clip and not the sentence after it.")
    return True


def check_speaker_named(c: dict) -> bool:
    """
    Is anybody on screen named?

    A REFUSAL since 2026-08-25, on the owner's instruction: "every clip needs to
    have the white box, and then their name comes on there ... that needs to be
    uploaded into the QM clip cutter skill as a nonnegotiable."

    It used to be a WARN on the reasoning that a montage or a cold open may
    legitimately have no single speaker and this check cannot tell that apart
    from a forgotten field. That reasoning still holds - which is why the escape
    is explicit rather than gone: set "allow_unnamed": true on the clip and it
    reports and passes. What it may not do is default to passing, because a WARN
    in a build_all run scrolls past six other clips and ships. Every one of this
    function's four exits returned True, so the non-negotiable was unenforceable
    by construction.

    It still cannot verify a name is RIGHT, and that is the failure that matters:
    the wrong name under a guest's face is worse than no name. So it reports what
    will be drawn, in full, for a human to read back against the picture.
    """
    # THE RIG NAMES THEM, SO THE CROP HAS TO KEEP IT. Owner, 2026-08-24: "the
    # nameplates will be there on the bottom anyway from the StreamYard. It will
    # just crop that in." That is the plan, and it only works if the crop
    # actually contains the badge - measured on the 08.24 master the rig draws it
    # at x15..600, y850..1058, and a 608-wide CENTRED head crop is x656..1264,
    # which clears it completely. So a head clip authored off the default crop
    # ships with nobody named at all, which is the thing this whole line exists
    # to prevent.
    # THE ESCAPE IS EXPLICIT AND IT IS LOGGED. A clip that genuinely has nobody
    # to name says so in the slate; it does not get there by nobody noticing.
    allow = bool(c.get("allow_unnamed"))

    def _unnamed(msg: str) -> bool:
        if allow:
            line(WARN, "NAMED", f"{msg}  (allowed by \"allow_unnamed\")")
            return True
        line(BAD, "NAMED", f"{msg}  Set \"allow_unnamed\": true on the clip if "
                           f"this one really has nobody to name.")
        return False

    if c.get("mode", "head") == "head" and not q.ATTR_ON:
        box = q.head_box(c.get("head_crop") or q.CFG.get("head_crop"),
                         c.get("crop_x"), at=c.get("start"),
                         dur=(c["end"] - c["start"])
                         if c.get("end") and c.get("start") else None)
        bw, bh, bx, by = box
        badge = q.CFG.get("source_badge_box")          # [x0,y0,x1,y1] if measured
        if badge:
            gx0, gy0, gx1, gy1 = badge
            keeps = (bx <= gx0 and bx + bw >= gx1 and by <= gy0 and by + bh >= gy1)
            if keeps:
                line(OK, "NAMED", f"crop {bw}x{bh}+{bx}+{by} keeps the source's "
                                  f"own lower third whole")
            else:
                return _unnamed(
                    f"the crop ({bw}x{bh}+{bx}+{by}) does NOT contain the "
                    f"source badge at x{gx0}..{gx1} y{gy0}..{gy1}, so this clip "
                    f"names nobody. Widen or move the crop to keep it, or set "
                    f"\"name_card\": true to draw one.")
        else:
            return _unnamed(
                "nobody is drawn on this clip and there is no "
                "\"source_badge_box\" in project.json to check the crop "
                "against. Measure the rig's lower third once and record it, "
                "or set \"name_card\": true.")
        return True
    name, title = q.speaker_label(c.get("speaker"), c.get("mode", "head"))
    if not name:
        return _unnamed(
            "nobody is named on this clip. Set \"speaker\" on it, or \"host\" "
            "in project.json for the show's regular. The master burns a lower "
            "third into the bottom-left that the head crop discards.")
    src = "clip" if c.get("speaker") else "project host"
    # BOTH PEOPLE, ON A CLIP THAT SHOWS BOTH. A conversation clip cuts between
    # two faces and used to name one of them; the other could hold the screen
    # for forty seconds unidentified. render() plates the second speaker at
    # their first appearance, but only when "speakers" tells it who they are.
    if c["mode"].startswith("conversation"):
        sp = c.get("speakers") or {}
        tiles = list(c.get("follow_tiles") or q.CFG.get("follow_tiles") or {})
        if not sp:
            line(WARN, "NAMED2",
                 "only one person is named, and this clip cuts between two. "
                 'Add "speakers": {"<tile>": {"name": ..., "title": ...}} '
                 "for both, and the second is plated at their first appearance.")
        else:
            missing = [t for t in tiles if t not in sp]
            if missing:
                line(WARN, "NAMED2",
                     f"\"speakers\" has no entry for {', '.join(missing)} - "
                     f"that person appears unnamed.")
            else:
                who = ", ".join(f"{t}={q.speaker_label(v, c['mode'])[0]!r}"
                                for t, v in sp.items())
                line(OK, "NAMED2", f"both speakers named: {who}")
    # WHERE IT LANDS, NOT JUST WHAT IT SAYS. It used to read "on the HOOK CARD
    # where a clear band allows it, otherwise the lower band", which stopped
    # being true on 2026-08-25 when the credential came off the card and became
    # a card of its own - and which never gave a y anyway, on the one element
    # that had been drawing under the platform chrome for its whole life.
    if not q.ATTR_ON:
        # SAY NOTHING ABOUT A CARD THAT DOES NOT SHIP. The early return above
        # only covers head, so a share or duo_share clip in a project with
        # "name_card": false fell through here and printed a y-range, in the OK
        # colour, for an element render() draws nothing of.
        return _unnamed(
            f"names {name!r} in the slate, but \"name_card\" is off in "
            f"project.json - no nameplate ships, so nothing on screen says who "
            f"this is.")
    top, bot = q.attr_plate_rows(name, title)
    win = q.attr_window(50.0)
    line(OK, "NAMED", f"names {name!r}"
                        + (f", {title!r}" if title else " (no title)")
                        + f" from the {src} - a bone card at y{top}..{bot}, "
                        + (f"up from +{win[0]:.1f}s to +{win[1]:.1f}s"
                           if win else "no room on this clip")
                        + ", after the title card leaves.")
    if len(name) > 34 or len(title) > 52:
        line(WARN, "NAMED", f"  that is {len(name)}+{len(title)} characters on "
                              f"one tracked line; it will condense. Shorten the "
                              f"title - the affiliation matters, the job title "
                              f"rarely does.")
    return True


# How far back to look for the sentence the clip is cutting into. Four seconds
# is comfortably more than one clause at any speaking rate on this material.
START_LOOKBEHIND = 4.0


# How much of a span may be duplicated frames before the master is stalling.
# A broadcast feed drops a frame here and there; a stream that has buffered holds
# whole runs of them, and those runs ship into the clip as a picture that stops.
STALL_MAX_FRAC = 0.04


HOOK_STOP = set(
    "a an the and or but if of to in on at for with from by is are was were be "
    "been being this that these those it its as not no we you they he she i our "
    "your their his her will would can could should may might do does did done "
    "have has had about into over than then so just what which who how why when "
    "where more most other some any".split())


REQUIRED_CLIP_KEYS = ("slug", "start", "end", "hook")


def check_required(c: dict, i: int) -> bool:
    """
    Every key the renderer will index directly, checked BEFORE anything reads
    one.

    build_all.py:103 does c["hook"] and preflight never asked for it, so a slate
    missing the field got a green ALL CLEAR and then died mid-run with a bare
    KeyError naming neither the clip nor the field. The same is true of a key
    present with the wrong type - a string "start" reaches arithmetic before
    anything says which clip it came from.
    """
    slug = c.get("slug") or f"clip #{i}"
    ok = True
    for k in REQUIRED_CLIP_KEYS:
        if k not in c or c[k] is None:
            line(BAD, "SLATE", f"{slug}: no {k!r}. render() indexes it directly, "
                               f"so this dies mid-run without naming the clip.")
            ok = False
    for k in ("start", "end"):
        if isinstance(c.get(k), (int, float)):
            continue
        if k in c and c[k] is not None:
            line(BAD, "SLATE", f"{slug}: {k!r} is {type(c[k]).__name__}, not a number")
            ok = False
    if (isinstance(c.get("start"), (int, float))
            and isinstance(c.get("end"), (int, float))
            and c["end"] <= c["start"]):
        line(BAD, "SLATE", f"{slug}: end {c['end']} is not after start {c['start']}")
        ok = False
    if isinstance(c.get("hook"), str) and not c["hook"].strip():
        line(BAD, "SLATE", f"{slug}: 'hook' is empty - the title card needs words")
        ok = False
    return ok


def check_about(c: dict) -> None:
    """
    The clip is about a named person - do the TITLES say so?

    WHY THIS IS THE CHEAPER HALF OF THE CONTEXT PROBLEM. A clip cut from
    mid-segment inherits its subject and refers to him only as "he"
    (context.carried_subject). The portrait insert fixes that for the viewer who
    watches; the TITLE fixes it for everyone who only reads, which on a feed is
    most of them - and the owner made the point himself: "if we have it in the
    title, it's not gonna realistically matter that much."

    So it is worth one line. Reported, never refused: a title that deliberately
    withholds the name ("He says AI takes your job") is a real editorial choice,
    and a gate that refuses a good headline gets ignored.
    """
    who = (c.get("about") or "").strip()
    if not who:
        return
    surname = who.split()[-1].lower()
    fields = [c.get("hook") or ""] + list(c.get("titles") or []) + \
             [c.get("platform_caption") or "", c.get("linkedin_caption") or ""]
    named = any(surname in (f or "").lower() for f in fields)
    if named:
        line(OK, "ABOUT", f"this clip is about {who} without naming him in the "
                          f"body, and the titles say so")
    else:
        line(WARN, "ABOUT",
             f"this clip is about {who} - the show names him before the span and "
             f"only says 'he' inside it - but no title or caption mentions him. "
             f"A reader scrolling past has no idea who is being quoted. Put the "
             f"name in one of them, or take the portrait insert.")


def check_hook_relates(c: dict, inside: list) -> None:
    """
    Does the hook actually describe what is said? REPORTED, NEVER REFUSED.

    The owner's rule is that every clip refers to its title, and this is the
    honest limit of what can be checked without a language model: how many of the
    hook's content words are spoken in the clip.

    IT IS NOT A GATE, and the measurement is why. Across all 130 archived clips
    with a hook and a quote, the median overlap is 100% and the mean 79% - but
    the tail is full of hooks that are EDITORIALLY RIGHT and lexically empty:

        0%   'Oil is heading lower'            (a-glut-coming-back-on-the-market)
        0%   'HE COULD NOT NAME *$18.8T*'      (vought-household-debt)
        0%   'FIATO: ASKED 3X, NO PAY FIGURE'  (fiato-wont-say-his-pay)
        7%   'Banks waived hundreds of millions of dollars'

    Every one of those is a paraphrase, a negation, or a description of what did
    NOT happen - the three shapes a good hook most often takes on this material,
    and the three a word-overlap test cannot see. A 60% floor would flag 22% of
    the archive; even 25% flags 4%, and all of them wrongly. A gate that refuses
    good clips gets ignored, and then it is worse than no gate.

    So it prints the number and the words that are missing, and a human decides.
    """
    hook = (c.get("hook") or "").strip()
    if not hook or not inside:
        return
    _arc(c, hook, inside)

    def _stem(w: str) -> str:
        return w[:-1] if w.endswith("s") and len(w) > 4 else w

    hw = [_stem(w) for w in re.findall(r"[a-z']+", hook.lower())
          if w not in HOOK_STOP and len(w) > 2]
    if not hw:
        line(OK, "HOOK", f"{hook!r} - no content words to match on")
        return
    said = {_stem(w) for w in re.findall(r"[a-z']+",
                                         " ".join(x.text for x in inside).lower())}
    miss = [w for w in hw if w not in said]
    cov = 1 - len(miss) / len(hw)
    tag = OK if cov >= 0.34 else WARN
    line(tag, "HOOK", f"{hook!r} - {cov:.0%} of its content words are spoken"
                      + (f"; not heard: {', '.join(miss[:5])}" if miss else "")
                      + (". Lexical only: a paraphrase or a negation scores low "
                         "and can still be the right hook - read it against the "
                         "quote." if cov < 0.34 else ""))


# How many of the sampled frames must show a face before the tile counts as
# having one. Measured on a real share master (Alan Ellman, 345x260 tile): a
# present, well-lit, talking face registers on 6 to 7 of 12 sampled frames -
# Haar loses it whenever the head turns or a hand crosses the chin. So "some" is
# the signal and "none at all" is the finding; a majority test would fail a tile
# that plainly has a man in it.
PIPFACE_MIN_HITS = 0.20


def check_pip_face(c: dict) -> None:
    """
    Is there actually a FACE in the camera tile this clip crops to?

    Two findings meet here and they are the same defect wearing two hats. A share
    clip gives the whole upper band to pip_crop and nothing ever confirmed a face
    is in it, so a screen recording with the camera off renders a blown-up slab
    of application pixels in the face band for the length of the clip - with
    every other check passing, because the geometry is perfect. And the hook card
    is placed off panel_faces, which returns an empty list both when it measured
    and found nothing AND when the cascade simply missed, which sends the card to
    the default band - in share, exactly where the camera tile sits.

    IT SAMPLES THE PIP RECTANGLE, NOT THE COLUMN, and that distinction is the
    whole reason this works. faces.face_box crops `{w}:{h}:{x0}:0` - the full
    frame height at the tile's x - so for a 345x260 tile it hands the cascade a
    345x1080 strip that is mostly slide, scaled to 480 wide and 1503 tall, in
    which the face is a few dozen pixels. Measured on the Alan Ellman master it
    finds NOTHING there, on a frame where the man's face fills a third of the
    tile. Cropping to the tile's own rectangle finds him on 6 of 12 frames.

    ADVISORY. A cascade miss is not proof of an empty tile, and refusing a good
    clip on a detector's bad day is the failure this file keeps finding.
    """
    if c.get("mode") not in ("share", "duo_share", "conversation_share"):
        return
    pip = c.get("pip_crop")
    if c.get("mode") == "conversation_share":
        # Both tiles carry the clip in turn, so both have to have a face in
        # them. Scored on the first here; the second is covered by HEADROOM,
        # which measures the delivered panel.
        pip = (c.get("follow_pips") or q.CFG.get("follow_pips") or [None])[0]
    if not pip:
        line(WARN, "PIPFACE", "no pip_crop on this clip, so the camera tile was "
                              "not checked for a face")
        return
    try:
        import faces as _f
        if _f.cv2 is None:
            line(WARN, "PIPFACE", "NOT measured: opencv is not installed for "
                                  "this interpreter")
            return
        cv2 = _f.cv2
    except Exception as e:                                   # noqa: BLE001
        line(WARN, "PIPFACE", f"NOT measured: {type(e).__name__} importing faces")
        return

    pw, ph, px, py = (int(pip[0]), int(pip[1]), int(pip[2]), int(pip[3]))
    at = c["start"] + min(3.0, max(0.0, (c["end"] - c["start"]) / 4))
    dur = min(8.0, max(2.0, c["end"] - at))
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-t", f"{dur:.2f}",
         "-i", str(q.SRC), "-vf",
         f"fps=2,crop={pw}:{ph}:{px}:{py},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True).stdout
    n = len(raw) // max(1, pw * ph)
    if not n:
        line(WARN, "PIPFACE", f"NOT measured: could not decode the tile "
                              f"({pw}x{ph} at {px},{py})")
        return
    A = np.frombuffer(raw[: n * pw * ph], np.uint8).reshape(n, ph, pw)
    cc = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    hits = sum(1 for i in range(n)
               if len(cc.detectMultiScale(A[i], 1.1, 5, minSize=(30, 30))))
    if hits / n < PIPFACE_MIN_HITS:
        line(WARN, "PIPFACE",
             f"NO FACE in the camera tile on {n - hits} of {n} frames sampled "
             f"over {dur:.0f}s ({pw}x{ph} at {px},{py}). Either the tile has no "
             f"camera in it - a screen recording with the camera off renders a "
             f"blown-up slab of app pixels in the face band - or the cascade "
             f"lost it. Check a frame.")
        return
    line(OK, "PIPFACE", f"a face is in the camera tile on {hits} of {n} frames "
                        f"sampled over {dur:.0f}s")


# ------------------------------------------------------------- head placement --
# WHERE THE FACE LANDS IN THE PANEL, in every mode. The owner, 2026-08-28: "we
# need to make sure that the head placement of all the people in all different
# formats is correct."
#
# Nothing measured this. check_crops scores the crop's GEOMETRY (is it inside
# the source, does it match the panel's aspect), check_pip_face asks only
# whether a face EXISTS in the share tile, and panel_faces - which has always
# measured exactly the right thing, faces in the reframed 1080x1920 - existed
# solely to place the hook card away from them. Nobody asked whether the face
# was well placed for a viewer.
#
# MEASURED OVER 96 DELIVERED CLIPS, and this is why the check exists:
#
#   12  chin BELOW the platform chrome line - the speaker's mouth is behind the
#       TikTok UI. Worst was 463px past it, on a duo.
#   28  chin inside the caption band, so our own captions sit on the mouth
#    5  crown sliced off at the top of the frame
#    5  head-mode face under 300px wide of 1080 - a person sitting far from
#       their webcam, rendered as a small head in a large empty frame
#    7  head-mode face more than 170px off centre
#
# THE NUMBERS ARE READ OFF THE LAYOUT, not chosen. CAP_BAND_Y_REST is where our
# own captions start and CAP_SAFE_BOTTOM is where the platform's chrome does;
# a chin below either is behind something. The 300px floor and the 170px
# centring allowance are the archive's own: every clip the house considers good
# clears both comfortably (a typical delivered head is 560-820px wide with its
# centre inside 60px of 540), and all twelve that fail are visibly wrong.
#
# WHY IT IS A WARN AND NOT A REFUSAL, except for the chrome line. A cascade
# reports a box for a frontal face and nothing for a profile, so a low reading
# is sometimes the detector and not the framing - this file's own recurring
# lesson is that a check which refuses good work gets ignored. The one hard
# failure is a chin past CAP_SAFE_BOTTOM, because that is not a matter of taste:
# the mouth is behind a button on all three platforms and no viewer can see it.
HEAD_CHIN_SOFT = q.CAP_BAND_Y_REST          # our captions start here
HEAD_CHIN_HARD = q.CAP_SAFE_BOTTOM          # the platform's chrome starts here
# WHERE THE MOUTH IS INSIDE A CASCADE BOX. The refusal above says "the mouth is
# behind the platform UI" and then measured the box BOTTOM, which on a Haar
# frontalface rect sits below the chin - jaw, neck and all. Those are different
# lines and the gap between them is large enough to matter: on the 08.28 head
# clip, once the crop was centred on the face, the box bottom landed 49px under
# the chrome while the MOUTH was 118px clear of it. Checked against the frame,
# the mouth is plainly above the line and the composition is good.
#
# A proxy that disagrees with the frame is the bug, not the frame - this file's
# most expensive lesson, recorded at "A MEASUREMENT THAT WAS WRONG". So the
# refusal now measures the mouth, and a chin that clips the UI while the mouth
# is clear is reported as what it is: cosmetic, and worth a look, not a stop.
HEAD_MOUTH_FRAC = 0.85
HEAD_CROWN_MIN = 40                         # less than this and the crown is cut
HEAD_MIN_W = 300                            # of 1080, head mode
HEAD_OFF_CENTRE = 170                       # of 540, head mode


def _fix_hint(c: dict, bot: int) -> str:
    """
    What to change, in the slate's own units, to lift the chin clear.

    THE GEOMETRY, because the obvious guess is backwards. The panel is a SCALE
    of the crop, so a face at source row `sy` lands at

        panel_y = (sy - cy) * PANEL_H / ch

    and there are exactly two ways to make that smaller: move the crop DOWN the
    source (raise cy), or make the crop TALLER (raise ch, which shrinks
    everything inside it). A *shorter* crop enlarges the picture and pushes the
    face further down - the first version of this hint recommended it, which
    would have made every clip it fired on worse.

    head_box re-cuts to the panel's 9:16, so ch is capped by the source height
    and cw follows from it. On a 1080-tall master that ceiling is 1080x608, and
    a speaker who sits low in their own webcam frame cannot be lifted past it by
    any crop at all - so the hint says that plainly instead of inventing a
    number, because the honest fix is then a different span or a word with the
    guest about their camera.
    """
    box = c.get("head_crop") or q.CFG.get("head_crop")
    if c.get("mode") != "head" or not box or len(box) != 4:
        return ""
    cw, ch, cx, cy = (int(v) for v in box)
    _sw, sh = q.src_size() or (1920, 1080)
    want = HEAD_CHIN_SOFT - 60                       # 60px of clearance
    if bot <= want:
        return ""
    sy = cy + bot * ch / q.PANEL_H                   # the chin, back in source px

    # 1. Move the crop down, as far as the source allows.
    for ncy in (int(round(sy - want * ch / q.PANEL_H)),):
        if 0 <= ncy <= sh - ch and (sy - ncy) * q.PANEL_H / ch <= want:
            return (f' move head_crop down the source: '
                    f'[{cw}, {ch}, {cx}, {ncy}] (y {cy} -> {ncy}).')

    # 2. Otherwise grow it, keeping the panel's aspect, and re-centre on x.
    nch = min(sh, int(round((sy - cy) * q.PANEL_H / want)))
    ncw = int(round(nch * q.PANEL_W / q.PANEL_H)) & ~1
    if nch > ch and ncw <= _sw:
        ncx = max(0, min(_sw - ncw, cx - (ncw - cw) // 2))
        got = (sy - cy) * q.PANEL_H / nch
        how = "clear" if got <= want else f"y{int(got)}, better but still low"
        return (f' a TALLER crop shrinks everything inside it: '
                f'[{ncw}, {nch}, {ncx}, {cy}] puts the chin at {how}.')

    return (f' no crop can fix this: the window is already the full {sh}px of '
            f'the source and the speaker sits low in their own camera frame. '
            f'Pick a span where they sit up, or use a different framing.')


def check_head_placement(c: dict) -> bool:
    """Is the face well placed in the 1080x1920 the viewer actually sees?"""
    # THROUGH THE CLIP'S OWN CHAIN, exactly as render() and the caption-colour
    # probe do. A second copy of this geometry would measure a crop that is not
    # the one being shipped, and nothing would look wrong until a face was in
    # the wrong place on a phone.
    try:
        # A follow clip is measured in its FIRST framing. The turn schedule is
        # not built until render(), and building it here would decode the span a
        # second time for a question this check does not ask - where the face
        # sits is a property of each crop, and check_follow scores the pair.
        # A FOLLOW CLIP IS MEASURED IN ITS FIRST FRAMING. The turn schedule is
        # not built until render(), and building it here would decode the span a
        # second time for a question this check does not ask - where the face
        # sits is a property of each crop, and the pair is scored by CROPS.
        # Without this, both conversation modes reported "NOT measured", which
        # is honest and leaves head placement unchecked on two of three
        # templates.
        mode = {"conversation": "head",
                "conversation_share": "share"}.get(c["mode"], c["mode"])
        hc, pc = c.get("head_crop"), c.get("pip_crop")
        if c["mode"] == "conversation":
            fc = c.get("follow_crops") or q.CFG.get("follow_crops") or []
            hc = list(fc[0]) if fc else hc
        elif c["mode"] == "conversation_share":
            fp = c.get("follow_pips") or q.CFG.get("follow_pips") or []
            pc = list(fp[0]) if fp else pc
        fg = q.reframe_chain(
            mode, c["end"] - c["start"], slug=c["slug"],
            start=c["start"], end=c["end"],
            head_crop=hc, crop_x=c.get("crop_x"),
            duo_crops=c.get("duo_crops"), pip_crop=pc,
            share_crop=c.get("share_crop"), face_h=c.get("face_h"))
        splits, extra = q.split_labels(mode)
        faces = q.panel_faces(c["start"], fg, splits, extra)
    except SystemExit as e:
        line(WARN, "HEADROOM", f"NOT measured: {str(e).strip().splitlines()[0]}")
        return True
    except Exception as e:                                       # noqa: BLE001
        line(WARN, "HEADROOM", f"NOT measured: {type(e).__name__} in panel_faces")
        return True

    # None and [] are DIFFERENT ANSWERS and this file has been bitten by
    # collapsing them before: None is "could not look" (no OpenCV, nothing
    # decoded), [] is "looked and found nobody".
    if faces is None:
        line(WARN, "HEADROOM", "NOT measured: opencv missing or nothing decoded")
        return True
    if not faces:
        line(WARN, "HEADROOM",
             "no face found in the panel over the opening seconds. On a profile "
             "or a turned head the cascade simply misses, so this is not proof "
             "the framing is wrong - but 14 of 96 delivered clips read this way "
             "and some of them were genuinely empty. Pull a frame and look.")
        return True

    ok, said = True, False
    for i, (l, t, r, b) in enumerate(faces):
        w, cx = r - l, (l + r) // 2
        who = f"face {i + 1}" if len(faces) > 1 else "the face"
        # THE MOUTH, not the box bottom. See HEAD_MOUTH_FRAC.
        mouth = int(round(t + (b - t) * HEAD_MOUTH_FRAC))
        # AND THE DRIFT MOVES IT AFTER THIS SAMPLE. Every geometric check here
        # reads the chain at t=0, which is exactly where face_chain centres the
        # drift by design - so the position measured is the MIDDLE of the travel
        # and the check never sees either extreme. Measured on the current
        # settings the crop y runs 38..82 against 58 at t=0, so the face sits up
        # to DRIFT_AMP_Y lower than what was scored. Charge that against the
        # chrome line or the check certifies a mouth the viewer sees under the
        # platform UI for part of every cycle.
        _drift_down = int(round(q.DRIFT_AMP_Y)) if getattr(q, "DRIFT_ON", False) else 0
        mouth += _drift_down
        b += _drift_down
        if mouth <= HEAD_CHIN_HARD < b:
            line(WARN, "HEADROOM",
                 f"{who}'s chin runs {b - HEAD_CHIN_HARD}px under the chrome "
                 f"line (y{HEAD_CHIN_HARD}), but the mouth is {HEAD_CHIN_HARD - mouth}px "
                 f"clear of it. Cosmetic - pull a frame if the jaw matters.")
            said = True
        elif mouth > HEAD_CHIN_HARD:
            # THE LOWER BAND OF A DUO CANNOT CLEAR THE CHROME, and that is
            # geometry rather than a bad crop. Band 2 starts at panel y967 and
            # the chrome starts at y1430, so only 463px of a 953px band sits
            # above the line - and a head-and-shoulders crop of a 16:9 half puts
            # a face 700px+ tall inside it. Solved on paper for the 08.26
            # master: lifting the chin clear needs cy >= 378 and the source only
            # allows cy <= 233, so no authored pair exists. SKILL.md already
            # called this "an accepted cost" of duo, and the archive bears it
            # out - 4 of the 12 delivered clips with a chin under the chrome are
            # duos, by 217 to 463px.
            #
            # So it WARNS on a duo's lower band and FAILS everywhere else. A
            # check that makes a documented mode unusable gets switched off,
            # which is this file's most repeated lesson - and there is now a
            # real answer to point at instead of an apology.
            lower = c["mode"] in ("duo", "duo_share") and t > q.PANEL_H // 2
            if lower:
                line(WARN, "HEADROOM",
                     f"{who}'s mouth runs to y{mouth}, {mouth - HEAD_CHIN_HARD}px below the "
                     f"chrome line - the mouth is behind the platform UI. This "
                     f"is duo's band geometry, not this crop: only 463px of the "
                     f"953px lower band is above y{HEAD_CHIN_HARD} and a "
                     f"head-and-shoulders crop is taller than that. If one "
                     f"person holds the floor use 'head'; if the floor moves, "
                     f"'head_follow' shows each of them full size and clear.")
                said = True
            else:
                line(BAD, "HEADROOM",
                     f"{who}'s mouth runs to y{mouth}, {mouth - HEAD_CHIN_HARD}px BELOW the "
                     f"chrome line (y{HEAD_CHIN_HARD}) - the mouth is behind "
                     f"the platform UI on TikTok, Reels and Shorts."
                     f"{_fix_hint(c, b)}")
                ok, said = False, True
        elif b > HEAD_CHIN_SOFT:
            line(WARN, "HEADROOM",
                 f"{who} runs to y{b}, {b - HEAD_CHIN_SOFT}px into the caption "
                 f"band (starts y{HEAD_CHIN_SOFT}) - our own words sit on the "
                 f"mouth.{_fix_hint(c, b)}")
            said = True
        if t < HEAD_CROWN_MIN:
            line(WARN, "HEADROOM",
                 f"{who} starts at y{t}: the crown is cut off at the top of frame.")
            said = True
        if c["mode"] == "head":
            if w < HEAD_MIN_W:
                line(WARN, "HEADROOM",
                     f"{who} is only {w}px wide of 1080 - a small head in a large "
                     f"empty frame. Tighten head_crop toward the speaker.")
                said = True
            off = cx - q.PANEL_W // 2
            if abs(off) > HEAD_OFF_CENTRE:
                box = c.get("head_crop") or q.CFG.get("head_crop")
                # The panel is a SCALE of the crop, so an offset in panel pixels
                # is off * crop_w / PANEL_W in the source.
                src_off = int(off * int(box[0]) / q.PANEL_W) if box else off
                line(WARN, "HEADROOM",
                     f"{who} sits at x{cx}, {off:+d}px off centre. Move "
                     f"head_crop's x by {src_off:+d} source px to centre it.")
                said = True
    if not said:
        where = ", ".join(f"x{l}..{r} y{t}..{b}" for l, t, r, b in faces)
        line(OK, "HEADROOM", f"{len(faces)} face(s) well placed - clear of the "
                             f"caption band and the chrome: {where}")
    return ok


def _arc(c: dict, hook: str, inside: list) -> None:
    """
    Does the clip come back to what its title promised?

    The owner's rule for this half of the run: "every clip really makes sense
    from start to finish. There's an idea that starts it and an idea that ends
    it. If you're bringing up X, the clip will start with X and then end with Y."

    preflight checked both EDGES and never checked them against EACH OTHER -
    check_opening_edge owns the in-point, check_ending owns the out-point, and
    nothing asked whether the thing promised at the top is still there at the
    bottom. Measured over the 96 delivered clips: 39% never return to the hook's
    subject after the first third, and the hook's subject is first SPOKEN a
    median 10.8s into a clip whose title card lives 3.0s - the viewer reads a
    promise and then waits eight seconds for it.

    A REPORT, NOT A GATE, and for the same reason the hook overlap check is:
    measured on this archive, no lexical statistic separates a clip that lands
    from one that trails off well enough to refuse on. What it can do honestly is
    put both numbers in front of a person before the render.
    """
    def _stem(w: str) -> str:
        return w[:-1] if w.endswith("s") and len(w) > 4 else w

    hw = {_stem(w) for w in re.findall(r"[a-z']+", hook.lower())
          if w not in HOOK_STOP and len(w) > 2}
    if not hw:
        return
    t0, t1 = inside[0].start, inside[-1].end
    span = max(0.1, t1 - t0)
    said = [(w.start, _stem(x)) for w in inside
            for x in re.findall(r"[a-z']+", w.text.lower())]
    hits = [t for t, x in said if x in hw]
    if not hits:
        line(WARN, "ARC", f"the hook's words are never spoken in the clip - "
                          f"nothing to trace from the title to the ending")
        return
    first = hits[0] - t0
    last_third = t0 + span * 2 / 3
    returns = [t for t in hits if t >= last_third]
    card = q.HOOK_HOLD
    bits = []
    if first > card + 0.5:
        bits.append(f"the subject is first spoken at +{first:.1f}s but the title "
                    f"card is gone by +{card:.1f}s")
    if not returns:
        bits.append("it never comes back in the final third")
    if bits:
        # WHERE TO MOVE IT, not just that it is wrong. A warning that names the
        # defect and leaves the operator to find the fix gets read once and
        # skipped after that. The clip promises something at +0s and pays it off
        # ten seconds later; the cheapest repair is almost always to START on
        # the payoff, so this reports the sentence boundary that would do it.
        fix = ""
        if first > card + 0.5:
            at = t0 + first
            ends = [w.end for w in inside
                    if q.finished_sentence(w.text) and w.end <= at]
            if ends:
                # IN SOURCE SECONDS, because that is what the slate is written
                # in. Reporting the clip-relative number makes the operator do
                # the addition, and the whole point of this line is that the fix
                # takes ten seconds.
                cut = max(ends)
                fix = (f" Starting at {c['start'] + (cut - t0):.1f} instead "
                       f"(+{cut - t0:.1f}s in) would open on the payoff.")
        line(WARN, "ARC", f"{hook!r} - " + " and ".join(bits) + "." + fix)
    else:
        line(OK, "ARC", f"opens on its subject (+{first:.1f}s) and returns to it "
                        f"{len(returns)}x in the final third")


def _lavfi_path(p) -> str:
    """A path safe inside an ffmpeg lavfi graph description."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace(",", "\\,").replace("'", "\\'")


def check_stall(c: dict) -> bool:
    """
    Is the MASTER holding frames over this span?

    Nothing counted this. A stalling stream - a re-buffer, a dropped encoder -
    repeats frames rather than skipping time, so the file plays at the right
    length with the picture frozen inside it. Every gate downstream is happy: the
    duration is right, the audio is continuous, the captions line up, and
    selftest's freezedetect only looks at 2-second stretches of the DELIVERED
    clip, which a scatter of 3 to 10 frame holds never reaches.

    ffmpeg's own mpdecimate does the counting - it exists to find exactly this -
    and the span is decoded at source scale over the authored window only.
    """
    span = c["end"] - c["start"]
    if span <= 0:
        return True
    # COUNT THE FRAMES THAT SURVIVE, DO NOT PARSE THE LOG. mpdecimate reports
    # its per-frame keep/drop decisions at DEBUG, not INFO - so this ran at
    # "-v info", `out.count(" drop ")` was 0 for every input ever passed to it,
    # frac was 0.0, and `frac > STALL_MAX_FRAC` was unreachable. Measured on a
    # master built so 9 of every 10 frames are literal repeats: 0 drops at
    # info, 119 at debug, and the check printed "runs clean ... 0.0%".
    #
    # This is the SAME defect selftest.check_detectors exists to prevent for
    # blackdetect/freezedetect/silencedetect - "-v error deleted exactly the
    # output the regexes read" - reappearing in a fourth detector that had no
    # such control. Rather than depend on a log level at all, mpdecimate is now
    # asked to actually DROP the frames and the survivors are counted: a number
    # ffmpeg reports as data, not as a debug line.
    fps = q.SRC_FPS or 30
    total = max(1, int(round(span * fps)))
    kept = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         f"movie={_lavfi_path(q.SRC)}:seek_point={c['start']},"
         f"trim=duration={span},mpdecimate=hi=64:lo=32:frac=0.33",
         "-show_entries", "stream=nb_read_frames", "-count_frames",
         "-of", "default=nw=1:nk=1"],
        capture_output=True, text=True).stdout.strip()
    try:
        drops = max(0, total - int(kept))
    except (TypeError, ValueError):
        line(WARN, "STALL", "NOT measured: the repeat-frame probe did not run")
        return True
    frac = drops / total
    if frac > STALL_MAX_FRAC:
        line(BAD, "STALL", f"the master repeats {drops} of {total} frames "
                           f"({100 * frac:.1f}%) over this span - it is holding, "
                           f"not running. Those held frames ship into the clip "
                           f"as a picture that stops.")
        line(BAD, "STALL", f"  pick the span from a clean stretch, or re-pull "
                           f"the master; the ceiling is "
                           f"{100 * STALL_MAX_FRAC:.0f}%.")
        return False
    line(OK, "STALL", f"the master runs clean over this span "
                      f"({drops} repeated frame(s) of {total}, "
                      f"{100 * frac:.1f}%)")
    return True


def check_opening_edge(c: dict) -> bool:
    """
    Does the clip START on a sentence, or drop in halfway through one?

    THE OTHER HALF OF THE NON-NEGOTIABLE. The owner's rule is about both edges -
    "the way it starts, the way it finishes, is it has a logical idea behind
    every clip" - and only the ending was ever checked. plan_ending moves the
    out-point onto a full stop and refuses when it cannot; the in-point had
    nothing at all behind it, so a clip could open on the back half of somebody
    else's sentence and preflight printed EDGES ok and ALL CLEAR.

    The test is the word IMMEDIATELY BEFORE `start`. If it finishes a sentence,
    the clip opens on a fresh one. If there is no word before it - the master's
    own opening, or a pause longer than the lookbehind - there is nothing being
    cut into, and that is also fine. Only a live word running into the in-point
    is a mid-sentence start.

    It decodes its own short window rather than reusing decode_span, which only
    ever looks forward from `start`.
    """
    start = c["start"]
    if start < 0.5:
        line(OK, "OPENING", "starts at the top of the master")
        return True
    back = min(START_LOOKBEHIND, start)
    try:
        env = q.envelope(start - back, back)
        prev = q.word_times(start - back, back, "pfb_" + c["slug"][:16])
        prev = q.drop_unspoken(prev, env)
    except Exception as e:                                   # noqa: BLE001
        line(WARN, "OPENING", f"could not decode the {back:.1f}s before the "
                              f"in-point ({type(e).__name__}), so a mid-sentence "
                              f"start is NOT ruled out")
        return True
    # word_times returns times relative to its own window start
    before = [w for w in prev if w.end <= back + 0.05]
    if not before:
        line(OK, "OPENING", f"nothing spoken in the {back:.1f}s before the "
                            f"in-point - it opens out of a pause")
        return True
    last = before[-1]
    gap = back - last.end
    txt = last.text.strip()
    if q.finished_sentence(txt):
        line(OK, "OPENING", f"opens on a fresh sentence - the words before it "
                            f"end {txt!r}")
        return True
    # A CLAUSE BOUNDARY IS A LEGITIMATE PLACE TO COME IN, and this is the line
    # between a useful check and one that gets switched off. Measured on the
    # delivered nd-test set: 01-tariffs starts just after "...a strategic
    # direction on their part," and opens on "The reason why these tariffs really
    # don't take effect until Labor Day" - grammatically mid-sentence,
    # editorially a clean opening clause that reads as a complete thought.
    # Failing that would refuse a good clip, and a gate that refuses good clips
    # gets "allow_ragged_start" pasted onto every slate, which is worse than not
    # having the gate. So the refusal is reserved for coming in mid-CLAUSE: no
    # terminal punctuation of any kind AND no pause.
    if txt.rstrip('"\'”’)]}»').endswith((",", ";", ":", "-", "—", "–")):
        line(OK, "OPENING", f"opens on a clause boundary - the words before it "
                            f"end {txt!r}")
        return True
    # A LONG PAUSE IS ALSO A BOUNDARY even without a full stop: whisper drops
    # punctuation constantly, and somebody who stopped talking for most of a
    # second has finished their thought whatever the transcript says.
    if gap >= 0.60:
        line(OK, "OPENING", f"the words before it ({txt!r}) carry no full stop, "
                            f"but there is a {gap:.2f}s pause before the "
                            f"in-point - that is a boundary")
        return True
    if c.get("allow_ragged_start"):
        line(WARN, "OPENING", f"opens mid-clause - {txt!r} runs straight into "
                              f"the in-point - shipping it anyway on "
                              f"\"allow_ragged_start\"")
        return True
    _how = (f"straddles the in-point by {-gap:.2f}s" if gap < 0
            else f"stops only {gap:.2f}s before it")
    line(BAD, "OPENING", f"OPENS MID-CLAUSE. {txt!r} {_how} and carries no "
                         f"punctuation at all, so the clip starts in the middle "
                         f"of a thought the viewer never heard the start of.")
    line(BAD, "OPENING", f"  move `start` back onto the boundary, or set "
                         f"\"allow_ragged_start\": true if the fragment stands "
                         f"up on its own.")
    return False


def check_opening(c: dict, inside: list) -> None:
    """
    What the clip actually opens with, and whether it drops the viewer in cold.

    EDGES prints the first WORD, which on the clip that actually looks bad prints
    `opens 'In'` - true, and useless. SKILL.md's own kill rule for a candidate is
    "it opens on filler", and until now there was no reporting behind it. So print
    the opening CLAUSE - every word inside the hook card's life, which is the text
    a viewer reads while deciding to stay.

    The warn beside it is deliberately a SEPARATE line and not a re-tagged EDGES.
    Overloading EDGES with an editorial verdict was tried and undone once already;
    the answer that stuck was a distinct ENDING line, so this is its opposite
    number at the other edge.
    """
    if not inside:
        return
    # HOOK_HOLD is DELIVERED seconds - the card's life on screen - and this used
    # to filter raw source times, so on every clip it reported fewer words than
    # the viewer reads under the card, and the parenthetical was false. Remap
    # through the removals and the tempo, the same way everything else that
    # crosses those two clocks does.
    d = _DECODED.get(c["slug"]) or {}
    rem, tempo = d.get("rem") or [], d.get("tempo") or 1.0
    def _delivered(t: float) -> float:
        return q.remap_time(t, rem) / tempo
    words = [w for w in inside if _delivered(w.start) < q.HOOK_HOLD]
    if words:
        txt = " ".join(w.text.strip() for w in words)
        if len(txt) > 96:
            txt = txt[:93].rstrip() + "..."
        line(OK, "OPENER", f"{txt!r} (the first {q.HOOK_HOLD:.1f}s, under the card)")

    head = [q.split_token(w.text)[0].lower() for w in inside[:4]]
    head = [h for h in head if h]
    if not head:
        return
    marker = head[0] in q.OPEN_MARKER
    pronoun = any(h in q.OPEN_PRONOUN for h in head[:4])
    if marker and pronoun:
        nxt = next((w for w in inside
                    if q.split_token(w.text)[0].lower() not in q.OPEN_MARKER), None)
        at = f" the first real word is at +{nxt.start:.2f}s" if nxt else ""
        line(WARN, "OPENER",
             f"opens on {head[0]!r} and a bare pronoun - that lands the viewer "
             f"mid-conversation.{at} Consider moving `start` onto the sentence "
             f"that names the subject.")


def check_broll_style() -> bool:
    """
    Every cutaway animates in and animates out. That is the standard.

    preflight never read BROLL_STYLE at all, so setting "broll_style": "cut" in
    project.json - which sets BROLL_IN and BROLL_OUT to 0.0 and strips the
    transition off every insert in the show - produced an all-green run and a set
    of clips where the pictures snap. The owner's brief is explicit: "There's
    animations for every b roll cut. There's animations for every b roll going
    away."

    A refusal rather than a warn, because it is set once in project.json and
    silently applies to the whole show.
    """
    if q.BROLL_STYLE == "cut":
        line(BAD, "STYLE", "\"broll_style\": \"cut\" strips the transition off "
                           "EVERY cutaway in this show - BROLL_IN and BROLL_OUT "
                           "are both 0.0, so each insert snaps on and snaps off.")
        line(BAD, "STYLE", "  use \"dissolve\" (the default) or \"slide\". "
                           "Every cutaway animates in and out - that is a "
                           "non-negotiable, not a preference.")
        return False
    line(OK, "STYLE", f"cutaways {q.BROLL_STYLE} in over {q.BROLL_IN:.2f}s and "
                      f"out over {q.BROLL_OUT:.2f}s")
    return True


def check_source() -> bool:
    """
    The master decodes, and the audio beside it belongs to THIS master.

    Both were assumed. If SRC could not be read, ffmpeg returned nothing, the
    frame-count guards saw zero samples and RAIL and BURNED both reported
    affirmative passes off no evidence at all - and preflight printed ALL CLEAR
    for a slate it had not checked. And EDGES / LENGTH / TEMPO / CADENCE are all
    measured from audio16k.wav, which render() regenerates when it is stale but
    preflight never did, so a whole slate could be validated against the PREVIOUS
    show's audio with nothing said.
    """
    if not q.SRC.exists():
        line(BAD, "SOURCE", f"{q.SRC} does not exist - fix `source` in project.json")
        return False
    n = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets,width,height",
         "-of", "csv=p=0", str(q.SRC)], capture_output=True, text=True).stdout.strip()
    if not n:
        line(BAD, "SOURCE", f"{q.SRC.name} will not decode - every frame-based "
                            f"check below would pass on zero evidence")
        return False
    # PORTED FROM viral-clip-engine 2026-08-20. Not a fork decision - a hole.
    #
    # ensure_audio() re-extracts a mismatched cache and DELETES cues.json,
    # sections.json and the transcripts with it, because they belonged to the
    # old master too. That deletion is correct. What was wrong is what happened
    # next: this function printed "audio16k.wav matches it" and returned True,
    # and check_layout's first line is `if not path.exists(): return` - a silent
    # PASS. So pointing project.json at a new master and running preflight
    # reported "[ok] LAYOUT covered, mode fits" for every clip, on a map that
    # had just been deleted. That is the exact failure check_layout was written
    # for: a duo span slicing a single solo frame down the middle.
    had = [f for f in ("cues.json", "sections.json") if (q.WORK / f).exists()]
    try:
        q.ensure_audio()
    except SystemExit as e:
        line(BAD, "SOURCE", str(e).strip().split("\n")[0])
        return False
    except Exception as e:
        line(BAD, "SOURCE", f"could not prepare audio16k.wav for {q.SRC.name}: {e}")
        return False
    gone = [f for f in had if not (q.WORK / f).exists()]
    if gone:
        line(BAD, "SOURCE", f"audio16k.wav belonged to a different master; "
                            f"{', '.join(gone)} went with it. Run analyze.py "
                            f"before preflight.")
        return False
    line(OK, "SOURCE", f"{q.SRC.name} decodes ({n}), audio16k.wav matches it")
    return True


def note_broll_cap() -> None:
    """Say so when project.json's insert cap was clamped up to the floor.

    qmclip clamps `broll_max_inserts` up to BROLL_MIN_INSERTS at import, and
    said nothing about it. That is the same fault as the one the clamp was
    added to fix, pointed the other way: a project carrying
    "broll_max_inserts": 0 reads as "no cutaways on this show", becomes a cap
    of 2, and then hard-FAILs check_broll's floor with a message about approving
    more inserts that never mentions the setting being overridden. The clamp
    itself is right - a clip whose picture never changes is not finished - so
    the fix is to print it, not to relax it. Printed HERE and not in qmclip
    because a library that prints at import writes into every other tool's
    output.
    """
    cfg = q.CFG.get("broll_max_inserts")
    try:
        asked = int(cfg) if cfg is not None else None
    except (TypeError, ValueError):        # a string or a list; leave it alone
        return
    if asked is None or asked >= q.BROLL_MIN_INSERTS:
        return
    print(f"NOTE: project.json asks for \"broll_max_inserts\": {asked}; it is "
          f"clamped up to {q.BROLL_MIN_INSERTS}. Every clip ships with at least "
          f"one cutaway, so a cap under {q.BROLL_MIN_INSERTS} is not a setting "
          f"this pipeline honours.")


def check_set_broll(clips: list[dict]) -> bool:
    """
    The same PICTURE in two different clips of one set.

    `check_broll` fails a repeat inside ONE clip and has never looked next door.
    Measured 2026-08-24 across the delivered archive: 5 cross-clip collisions,
    all inside a single five-clip set, and THREE of the five are byte-identical
    downloads sitting under two different filenames. The right framing is
    concentration rather than rate - one clip in that set carries six inserts and
    FOUR of its six pictures were already used by a sibling. Watched back to back
    that is a loop, which is the exact thing the chain rule exists to prevent.

    Two implementation notes, both of which cost a version to learn:

    - This walks EVERY clip in the slate, not the ones named on the command line.
      `main()` skips unnamed clips, so a set-wide dict filled only by scored clips
      sees one clip when anyone runs `preflight.py <slug>` and passes silently -
      a gate with no key.
    - Cause worth naming when it fires: `broll.py` ranks the shared library first
      on every term, so the library outranks a fresh search. 7 of the last 18
      approvals pointed at a picture the library already held.

    `"repeat_ok": true` on a clip is the escape. Measured, 15 of 16 shows scoring
    clean, so a hard fail blocks one show and nothing else.
    """
    _load_pictures()
    if not _PICTURES_OK:
        line(WARN, "SET", "the b-roll index is unreadable; cross-clip repeats "
                          "are NOT scored")
        return True
    seen: dict[str, tuple[str, str]] = {}
    pics: set[str] = set()
    inserts = 0
    ok = True
    for c in clips:
        if c.get("repeat_ok"):
            continue
        for x in (c.get("broll") or []):
            if not x.get("approved") or not x.get("asset"):
                continue
            inserts += 1
            pid, name = _picture(str(x.get("asset")))
            pics.add(pid)
            term = str(x.get("term", "?"))
            first = seen.get(pid)
            if first is not None:
                line(BAD, "SET", f"{c['slug']} uses the same picture as "
                                 f"{first[0]} ({name})")
                line(BAD, "SET", f"  {term!r} here, {first[1]!r} there. Two clips "
                                 f"in one set cutting to one photograph reads as "
                                 f"a loop. Retype one term and re-run: "
                                 f"python3 broll.py propose {c['slug']}")
                ok = False
            else:
                seen[pid] = (c["slug"], term)
    if inserts:
        line(OK if ok else BAD, "SET",
             f"{len(pics)} distinct picture(s) across {inserts} insert(s) in "
             f"{len(clips)} clip(s)")
    return ok


def main() -> None:
    only = sys.argv[1:] or None
    slate = json.loads((WORK / "slate.json").read_text())
    clips = sorted(slate["clips"], key=lambda c: c.get("rank", 0))
    # A MISTYPED SLUG IS NOT AN EMPTY RUN. Both files filter the slate by name and
    # neither checked that the name matched anything, so `preflight.py
    # tarifs-timed-to-early-voting` skipped every clip, checked nothing, printed
    # ALL CLEAR and exited 0 - and build_all did the same and rendered nothing,
    # also exiting 0. Two green runs and no work done, which is the worst kind of
    # pass because it looks exactly like success.
    _known = {c.get("slug") for c in clips if c.get("slug")}
    _unknown = sorted(set(only or []) - _known)
    if _unknown:
        raise SystemExit(
            f"\nNo clip named {', '.join(repr(u) for u in _unknown)} in this "
            f"slate.\nThe slugs are:\n"
            + "".join(f"  {s}\n" for s in sorted(_known)))
    bad = []
    if not check_broll_style():
        print("\nREFUSED - fix project.json and run again.\n")
        sys.exit(1)
    if not check_source():
        print("\nNOT READY: the master itself. Nothing below was checked.\n")
        sys.exit(1)
    note_broll_cap()
    for _i, c in enumerate(clips, 1):
        if only and c.get("slug") not in only:
            continue
        # BEFORE ANY CHECK READS A KEY. A missing or mistyped required field
        # used to surface as a bare KeyError from somewhere deep in a check, or
        # worse from build_all AFTER preflight said ALL CLEAR.
        if not check_required(c, _i):
            bad.append(c.get("slug") or f"clip #{_i}")
            continue
        c.setdefault("mode", "head")             # build_all's default; a KeyError here was a crash
        # ONE RESOLUTION POINT, matching render()'s. Aliases resolve and a
        # retired mode is refused here rather than after a dozen checks have
        # branched on a name that no longer exists.
        try:
            c["mode"] = q.canonical_mode(c["mode"],
                                         allow_legacy=c.get("allow_legacy_duo", False))
        except SystemExit as e:
            print(f"\n{c.get('rank','?')}  {c['slug']}  [{c['mode']}]")
            line(BAD, "MODE", str(e).strip().splitlines()[0])
            for ln in str(e).strip().splitlines()[1:]:
                if ln.strip():
                    line(BAD, "MODE", f"  {ln.strip()}")
            bad.append(c["slug"])
            continue
        print(f"\n{c.get('rank', '?')}  {c['slug']}  [{c['mode']}]  "
              f"{c['start']:.2f} -> {c['end']:.2f}")
        # hard_out is a CEILING on the out-point and render() now clamps to it.
        # Score the span the render will actually cut, and say when it moved.
        ho = c.get("hard_out")
        if ho is not None and float(ho) < c["end"]:
            line(WARN, "EDGES", f"hard_out {float(ho):.2f}s is before the out-point "
                                f"{c['end']:.2f}s; the render pulls the end back to it")
            c["end"] = float(ho)
        good = check_mode(c)
        if good:
            good &= check_layout(c)
            good &= check_rail(c)
            check_speaker(c)
            good &= check_crosstalk(c)
            check_pip_face(c)
            good &= check_speaker_named(c)
            good &= check_crops(c)
            good &= check_head_placement(c)
            good &= check_graphics(c)
            good &= check_pack(c)
            good &= check_safe(c)
            good &= check_burned_in(c)
            good &= check_broll(c)
            check_picture(c)
            check_punch(c)
            good &= check_text(c)
            good &= check_stall(c)
            good &= check_opening_edge(c)
            good &= check_edges_and_length(c)
        if not good:
            bad.append(c["slug"])
    # SET-WIDE, and deliberately over every clip in the slate rather than the
    # ones named on the command line - see check_set_broll.
    print("\nTHE SET")
    if not check_set_broll(clips):
        bad.append("the set (repeated b-roll)")

    print()
    if bad:
        print(f"NOT READY: {', '.join(bad)}. Fix the slate, re-run preflight, "
              f"then render.\n")
        sys.exit(1)
    print("ALL CLEAR - render.\n")


if __name__ == "__main__":
    main()
