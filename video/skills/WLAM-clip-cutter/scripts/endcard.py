#!/usr/bin/env python3
"""
The closing card every clip ends on.

A whoosh and a wipe take the screen, then the Quasar Markets wordmark over the
brand starfield, the line, and the address. Four seconds, and it is the same four
seconds on every clip - that repetition is the point. Someone who sees six clips
this week should finish all six on the identical frame.

Built here rather than generated: it has to be frame-identical every time, it has
to match the clip's own palette and type exactly, and a generative pass would cost
minutes per clip to reproduce something deterministic.

    python3 endcard.py preview.mp4        # render the card on its own, to look at

Wording and both brand assets come from the brand film (COMPLETED QM PROJS/VIDEOS):
the wordmark, the starfield behind it, and "One Platform. Built for the Way You
Live."
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import endcard_audio
import glass
import qmclip as q

CARD_SECONDS = q.CARD_SECONDS   # one owner; qmclip's guards are measured against it
# HOW THE CARD TAKES THE FRAME.
#
# "rise" is the one that ships. The outro arrives from below and covers the
# picture, which is the SAME move a b-roll cutaway makes in this pipeline, on the
# same curve. That is the whole argument for it: the clip already has a motion
# compass - picture arrives from below, type from the right, everything leaves
# left - and an outro that obeys it stops reading as a card bolted onto the end
# and starts reading as the last beat of the same edit.
#
# "wipe" is what shipped before: a slanted sheet of light crossing the frame. It
# is kept because it works and because reverting should be one word, not an
# archaeology exercise. Its fault on the street plate is simple - the wash is
# near-white and hundreds of pixels across, so on a plate whose whole point is
# that it is dark, the first second is a blown-out flash.
ENTRANCE = "wipe"

# HOW THE TWO LINES UNDER THE WORDMARK ARE RENDERED.
#
# "glass" is the original: cut-crystal letterforms, a bevel along the top and a
# gradient running cool white -> brand blue -> deep blue down the glyph.
#
# "bone" is flat #fffdf9, the locked video look's one type colour.
#
# The tension is real and it is worth writing down. The glass treatment is what
# has shipped on every clip so far, and it is handsome at full size. But the QM
# video look says all copy is bone white and body copy is never tinted, and on a
# plate this dark the glass gradient's lower half (26,68,108) is the dimmest part
# of the glyph, so the CTA - the one line on the card that has a job to do - is
# also the least legible thing on it. Both are built; the choice is the owner's.
TYPE_STYLE = "bone"

# Type sizes for the two lines.
#
# TAG_PX IS A SAFE-AREA NUMBER, not a taste one. At 52 the tagline ran 6.2% to
# 93.5% of frame width and put 843px of ink under TikTok's like/comment/share
# rail, so the end of "Live." sat behind an icon on a phone. At 40 it spans
# 16.9%-83.1%, clear of the rail on every platform - and its glyph run comes out
# at 720px against the wordmark's 719, so the three elements of the lockup
# finally share one measure instead of the middle line running widest.
#
# Anything that lengthens TAGLINE has to be re-checked against this. The gate is
# in references/look.md; the quick version is that no ink may pass 86% of width.
TAG_PX = 40
URL_PX = 40

# 0.33 IS THE FLOOR, not a taste choice. The cover travels the full 1920 of the
# frame, so at 30fps the fastest smoothstep that still keeps its worst frame
# under the 1/6-of-frame rule broadcast pans are cut to is 10 frames: 0.33s
# moves 318px at peak (16.6%), 0.30s moves 354 (18.4%) and 0.28s moves 410
# (21.4%). Past the limit a full-frame jump with no motion blur stops reading as
# a move and starts reading as a flash. If the card has to feel faster still,
# take it out of the staging below or the plate's own speed - not out of this.
RISE = 0.33               # the cover, on a smoothstep. See build_frames.
WIPE = 0.78               # slow enough to read as a move, not a cut
# How far the light travels across a 1080-wide frame. Deliberately far past the
# 1920 the reveal needs: the wash is hundreds of pixels wide, so the bar is still
# 99% bright when the mask completes, and it takes until edge 2400 for the light
# to genuinely be off screen. See build_frames for the whole argument.
WIPE_TRAVEL = 3100

# HOW WHITE AND HOW WIDE THE SHEET OF LIGHT IS.
#
# Both exist because "make it brighter" cannot be done the obvious way here. The
# alpha already peaks at 0.992 - the core is opaque - so raising the coefficients
# does not add brightness, it just flattens a few hundred pixels to solid white
# and throws away the gradient core, lip and mix are computed for. Measured:
# 0.16/0.90/0.11 clips 249px, 0.20/0.96/0.12 clips 387px. Don't.
#
# What DOES read as brighter is colour and width.
#
# WIPE_WHITE lifts the base of the gradient toward bone. At 0.0 the wash outside
# the core sat at ACCENT_HOT, a pale slate blue, so the sheet read tinted; at
# 0.55 the mean colour spread across the visible band drops from 11.2 to 5.8,
# which is the difference between a blue-ish sweep and a white one.
#
# WIPE_CORE widens the hot core. 340 -> 460 grows the genuinely bright part of
# the band from 259px to 358px, with peak alpha unchanged and still zero clipped
# pixels. WIPE_TRAVEL went 2820 -> 3100 to pay for it: a wider bar needs further
# to go before it is actually off screen, and at 2820 the widened core still left
# ~2% alpha in the bottom corner on the last frame - faint, but this card has
# been bitten by exactly that before.
WIPE_WHITE = 0.55
WIPE_CORE = 460.0
LOGO_W = 720
DRIFT = 0.055             # how far the backdrop pushes in over the card
# Staging, in seconds from the top of the card. The wipe reveals the field and the
# mark; the two lines then slide up into place one after the other, and a specular
# travels across them once everything has landed. Nothing arrives at the same time
# as anything else - simultaneous entrances read as a slide build.
# LINE STAGING, MEASURED FROM THE END OF THE ENTRANCE - not from the top of the
# card. This matters more than it looks.
#
# The card face is built with t forced to 0.0 for every frame of the entrance
# and t = f/fps afterwards, so a line whose start time falls INSIDE the entrance
# has already passed by the time the first real frame is drawn: it appears fully
# formed, with no slide, in the frame the entrance ends on. Absolute times were
# therefore only ever correct for one entrance length, and the two entrances here
# differ by nearly half a second. Holding the offsets and deriving the times is
# what makes "rise" and "wipe" both work without a second set of numbers.
#
# The offsets themselves are cut fast, for a four second card: the lockup is
# fully assembled about 1.3s in, leaving the rest of the card as the street
# draining under a finished frame.
T_TAG_AFTER, T_URL_AFTER = 0.08, 0.26
SLIDE = 0.40              # how long a line takes to arrive. See place().
T_SWEEP_AFTER, SWEEP_LEN = 0.62, 0.95

TAGLINE = "One Platform. Built for the Way You Live."
BRAND = q.FONTS.parent / "brand" / "qm-wordmark.png"
FIELD = q.FONTS.parent / "brand" / "qm-starfield.png"
# A moving backplate, if one has been baked. Frames named 00000.png upward at the
# project's own fps, 1080x1920, exactly CARD_SECONDS long. bake_backplate() makes
# one; with the folder absent the card falls back to the still starfield and the
# slow push, which is what it did before there was a backplate at all.
PLATE = q.WORK / "tmp" / "_backplate"
# The backplate ships as a small mp4, not as frames. 4 seconds of 1080x1920 PNG is
# well over 100MB and this skill is distributed as a 1.2MB bundle; the same
# footage as h264 is a couple of megabytes because it is a soft gradient. Frames
# are extracted to the tmp cache on first use and reused for every clip after.
PLATE_MP4 = q.FONTS.parent / "brand" / "qm-backplate.mp4"
SWIPE = q.FONTS.parent / "brand" / "swipe.mp3"


def _ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _flat(text: str, font: ImageFont.FreeTypeFont,
          track: float = 0.0) -> Image.Image:
    """
    One line of flat bone-white type on transparent.

    Deliberately mirrors glass.render's box: same padding (0.30 * size), same
    1.55 * size line box, same manual per-character tracking. The card's block
    height is computed from these images, so a different box would move the whole
    lockup and the two styles would not be comparable.

    A hair of shadow under the glyphs, not a scrim. On a plate measured at 12-20
    luma this is not needed for contrast; it is there so the type keeps its edge
    over the two or three brighter reflections that cross the lower band.
    """
    pad = max(10, int(font.size * 0.30))
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    w = probe.textlength(text, font=font) + track * max(0, len(text) - 1)
    h = font.size * 1.55
    img = Image.new("RGBA", (int(w) + pad * 2, int(h) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = float(pad)
    for ch in text:
        d.text((x, pad), ch, font=font, fill=q.BONE + (255,))
        x += probe.textlength(ch, font=font) + track
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(img.getchannel("A").point(lambda v: int(v * 0.55)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, 2))
    out.alpha_composite(img)
    return out


def _line(text: str, font: ImageFont.FreeTypeFont, track: float,
          sweep: float | None) -> Image.Image:
    """One line, in whichever style the card is set to."""
    if TYPE_STYLE == "bone":
        return _flat(text, font, track)
    return glass.render(text, font, track, sweep=sweep)


def _smoothstep(x: float) -> float:
    """u*u*(3-2u). The curve every LARGE travel in this pipeline uses."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def entrance_seconds() -> float:
    """How long the entrance runs, in seconds. The sound is cut to this."""
    return RISE if ENTRANCE == "rise" else WIPE


def t_tag() -> float:
    """When the tagline starts arriving, in card time."""
    return entrance_seconds() + T_TAG_AFTER


def t_url() -> float:
    return entrance_seconds() + T_URL_AFTER


def t_sweep() -> float:
    return entrance_seconds() + T_SWEEP_AFTER


def entrance_frames(fps: int) -> int:
    """
    How many frames the card spends arriving.

    One owner, because two things need it and they must not disagree: the face
    cache uses it to know when the lines are allowed to start staging in, and
    build_frames uses it to know how many frames it is compositing a move over.
    """
    return int(round((RISE if ENTRANCE == "rise" else WIPE) * fps))


_PLATE_FRAMES: list[Path] | None = None


def _plate() -> list[Path]:
    """
    The backplate's frames, extracted from the shipped mp4 on first use.

    The extraction is stamped with the mp4's size and mtime and re-run when either
    changes. Without that the tmp frames outlive the asset: re-bake the plate and
    every render keeps using the old one, silently, because the folder is already
    there. That cost several renders during development before it was noticed, and
    the only reason the stale frames did not also poison the settled-frame cache is
    that _plate_key() happens to read the mp4 rather than the folder.
    """
    global _PLATE_FRAMES
    if _PLATE_FRAMES is None:
        if PLATE_MP4.exists():
            st = PLATE_MP4.stat()
            stamp = PLATE / ".from"
            want = f"{st.st_size}:{int(st.st_mtime)}"
            if not stamp.exists() or stamp.read_text() != want:
                shutil.rmtree(PLATE, ignore_errors=True)
                PLATE.mkdir(parents=True, exist_ok=True)
                q.run(["ffmpeg", "-y", "-v", "error", "-i", str(PLATE_MP4),
                       "-vf", f"scale={q.W}:{q.H}:flags=lanczos",
                       str(PLATE / "%05d.png")])
                stamp.write_text(want)
        _PLATE_FRAMES = sorted(PLATE.glob("*.png")) if PLATE.is_dir() else []
    return _PLATE_FRAMES


def backdrop(p: float, u: float | None = None) -> Image.Image:
    """
    What sits behind the mark for four seconds.

    A flat colour read as a placeholder - the eye needs something to be happening
    or four seconds feels like a stall.

    Two versions exist. A baked MOVING backplate is used when one is installed:
    real footage behind the card, which is what stops the ending reading as a
    generated slide. Without one it falls back to the brand starfield with a slow
    push, which is what shipped before and still works.

    The push is kept on the still and dropped on the plate. Footage already has
    its own motion, and a zoom on top of it reads as two things moving at once.

    `u` is the card's own progress, 0 at the first frame of the WIPE and 1 at the
    last frame of the card. The plate is indexed on that and nothing else. It was
    indexed on `p` at first - the SETTLED progress, which is 0 only once the wipe
    is over - and that produced the two faults the card was reported for: the
    plate stood still for the whole 0.78s wipe and then played its full four
    seconds inside the remaining 3.2, resampled unevenly onto 97 frames. A stall
    followed by juddering fast motion.
    """
    frames = _plate()
    if frames:
        pos = p if u is None else u
        i = min(len(frames) - 1, max(0, int(round(pos * (len(frames) - 1)))))
        im = Image.open(frames[i]).convert("RGB")
        return im if im.size == (q.W, q.H) else im.resize((q.W, q.H), Image.LANCZOS)

    z = 1.0 + DRIFT * (1.0 - _ease_out(p))
    im = Image.open(FIELD).convert("RGB")
    w, h = int(q.W * z), int(q.H * z)
    im = im.resize((w, h), Image.LANCZOS)
    return im.crop(((w - q.W) // 2, (h - q.H) // 2,
                    (w - q.W) // 2 + q.W, (h - q.H) // 2 + q.H))


def bake_backplate(src: Path, ss: float, out: Path, fps: int,
                   vf: str, dur: float = CARD_SECONDS) -> int:
    """
    Bake CARD_SECONDS of footage into the backplate frames the card reads.

    Done once and committed to the brand assets rather than decoded per clip, for
    the same reason the settled frames are cached: this card is identical on every
    clip in the set and re-deriving it per render is pure cost.
    """
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    q.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ss:.3f}", "-i", str(src),
           "-vf", f"{vf},fps={fps}", "-t", f"{dur:.3f}",
           str(out / "%05d.png")])
    return len(list(out.glob("*.png")))


def card_face(p: float = 1.0, t: float | None = None,
              u: float | None = None) -> Image.Image:
    """
    The card at drift position p, card-time t, and card progress u.

    t=None means the lines are fully settled. The WIPE passes t=0.0 instead, so
    the lines have not arrived yet and it reveals only the field and the mark.
    u drives the moving backplate and runs across the WHOLE card, wipe included.
    """
    img = backdrop(p, u).convert("RGBA")
    d = ImageDraw.Draw(img)

    # a cool bloom behind the mark so it sits in the field rather than on it
    glow = Image.new("RGBA", (q.W, q.H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = q.W // 2, 872
    for r in range(700, 0, -14):
        a = int(26 * (1 - r / 700) ** 2.0)
        gd.ellipse([cx - r, cy - int(r * 0.60), cx + r, cy + int(r * 0.60)],
                   fill=q.ACCENT + (a,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(22)))

    logo = Image.open(BRAND).convert("RGBA")
    lw = LOGO_W
    lh = int(round(logo.height * lw / logo.width))
    logo = logo.resize((lw, lh), Image.LANCZOS)

    f_tag = ImageFont.truetype(str(q.F_DISPLAY), TAG_PX)
    f_url = ImageFont.truetype(str(q.F_UI), URL_PX)
    url = q.INVEST.upper()

    sweep = None
    if t is not None and t_sweep() <= t < t_sweep() + SWEEP_LEN:
        sweep = (t - t_sweep()) / SWEEP_LEN
    tag_img = _line(TAGLINE, f_tag, 0.6, sweep)
    url_img = _line(url, f_url, 4.0, sweep)

    block = lh + 50 + tag_img.height + 40 + url_img.height
    top = (q.H - block) // 2
    img.alpha_composite(logo, ((q.W - lw) // 2, top))

    def place(plate: Image.Image, y: int, start: float) -> None:
        """
        Slide a line up into place, fading as it comes.

        Three things make this read as smooth rather than as a nudge, and the
        third is the one that actually mattered.

        SMOOTHSTEP, not the cubic ease-out. The travel is only 46px, so the
        distance rule that forces smoothstep on full-frame moves does not apply
        here - but the cubic's peak velocity is 3x its average against
        smoothstep's 1.5x, so it arrives in a rush and then crawls. Eased at both
        ends the same line reads as gliding in.

        LONGER. 0.30s is nine frames for the whole move; there is not enough room
        in that to be gentle.

        SUBPIXEL. This is the one. `dy` was an int, so a 46px travel over twelve
        frames stepped 3,4,4,3,4... - a 25% swing in per-frame velocity on a move
        slow enough for the eye to track, which is exactly what "not smooth"
        looks like. The line is now shifted by the fractional part with a
        bilinear affine before compositing, so the velocity is constant.
        """
        if t is None:
            e = 1.0
        elif t <= start:
            return
        else:
            e = _smoothstep(min(1.0, (t - start) / SLIDE))
        x = (q.W - plate.width) // 2
        if e >= 0.999:
            img.alpha_composite(plate, (x, y))
            return
        faded = plate.copy()
        faded.putalpha(plate.getchannel("A").point(lambda v: int(v * e)))

        dyf = (1 - e) * 46.0
        dyi = math.floor(dyf)
        frac = dyf - dyi
        if frac > 0.002:
            # one row of headroom so the bottom is not clipped as it shifts down,
            # then sample the plate `frac` of a pixel higher
            pad = Image.new("RGBA", (faded.width, faded.height + 1), (0, 0, 0, 0))
            pad.alpha_composite(faded, (0, 0))
            faded = pad.transform(pad.size, Image.AFFINE,
                                  (1, 0, 0, 0, 1, -frac), Image.BILINEAR)
        img.alpha_composite(faded, (x, y + dyi))

    y = top + lh + 50
    place(tag_img, y, t_tag())
    y += tag_img.height + 40
    if t is None or t > t_url():
        e = 1.0 if t is None else _smoothstep(min(1.0, (t - t_url()) / SLIDE))
        rule_w = int(148 * e)
        ry = y - 21                      # centred in the gap, clear of both lines
        d.rectangle([(q.W - rule_w) / 2, ry, (q.W + rule_w) / 2, ry + 2],
                    fill=q.ACCENT + (int(185 * e),))
    place(url_img, y, t_url())
    return img


def _draw_edge(frame: Image.Image, edge: float, slant: int,
               fade: float = 1.0) -> None:
    """
    A broad wash of light crossing the frame, with a hot core at its leading edge.

    This started as a hairline, which read as a template slide transition. The wash
    is the fix: a wide soft band, hundreds of pixels across, so what crosses the
    screen is a sheet of light rather than a line. Built as a distance field in
    numpy - drawing hundreds of stacked lines to fake the falloff was both slow and
    visibly banded.

    It is asymmetric on purpose. The trailing side (over the card that has just been
    revealed) carries more of the wash than the leading side, so the light reads as
    being dragged across rather than as a symmetric glow bolted to a mask edge.
    """
    w, h = frame.size
    yy, xx = np.mgrid[0:h, 0:w]
    # signed perpendicular distance to the wipe line through (edge, 0)
    norm = math.hypot(h, slant)
    dist = ((xx - edge) * h + yy * slant) / norm

    # np.where, NOT np.clip. Clipping the ARGUMENT to zero on the far side leaves
    # exp(0) = 1 there, so each term floored at 1.0 and `wash` was never below 1.0
    # anywhere in the frame. Every wipe frame carried a 0.13 alpha veil of accent
    # over all 2,073,600 pixels, and by frame 4 the mean alpha was 0.63 with 28%
    # of the frame clipped to solid bone. It read as a blown exposure rather than
    # as a sweep, and it is what the card was reported "glitchy" for.
    wash = np.where(dist < 0, np.exp(-(dist / 150.0) ** 2), 0.0)   # trail behind
    wash += np.where(dist > 0, np.exp(-(dist / 80.0) ** 2), 0.0)   # shorter ahead
    core = np.exp(-(dist / WIPE_CORE) ** 2)                    # the white bar itself
    lip = np.exp(-((dist - 250) / 170.0) ** 2)

    # `fade` is supplied by the caller and driven by the FRAME, not by the eased
    # p. Driven by p it died at frame 16 of 23 while the polygon still had ~800
    # uncovered pixels in the corner, so the wipe left a bright shard blinking out
    # instead of an edge leaving the screen.
    # Less haze, more bar. "Cleaner" means the trail carries less of the total
    # and the core carries more - a bright slab reads deliberate, a soft fog
    # reads like a render artefact.
    # The coefficients sum to just under 1.0 at the edge on purpose. At 0.97 the
    # core plus the lip peaked at 1.24, which flattened a ~290px span to solid
    # white and threw away the gradient that core, lip and mix are computed for.
    a = np.clip((wash * 0.13 + core * 0.85 + lip * 0.10) * fade, 0, 1)
    white = np.array(q.BONE, float)
    # the base the gradient starts from, lifted toward bone by WIPE_WHITE so the
    # wash outside the core is white with a cool cast rather than pale blue
    base = np.array(q.ACCENT_HOT, float)
    base = base + (white - base) * WIPE_WHITE
    mix = (core + lip * 0.5)[:, :, None]
    rgb = base + (white - base) * np.clip(mix, 0, 1)

    band = np.dstack([rgb, a * 255]).astype(np.uint8)
    frame.alpha_composite(Image.fromarray(band, "RGBA"))


def _plate_key() -> str:
    """
    Identify the backplate so the settled-frame cache can tell two apart.

    This bit the moment a moving plate existed: the cache is keyed on the text and
    the timings, so swapping the footage behind the card changed nothing on screen
    and three different backplates rendered byte-identical cards. Name, count and
    total size is enough - a re-bake of the same footage produces the same three.
    """
    if not PLATE_MP4.exists():
        return "still"
    st = PLATE_MP4.stat()
    return f"{PLATE_MP4.name}:{st.st_size}"


def _cache_dir(fps: int) -> Path:
    key = hashlib.sha1(
        f"{q.INVEST}|{TAGLINE}|{CARD_SECONDS}|{WIPE}|{fps}|{LOGO_W}|{DRIFT}"
        f"|{t_tag()}|{t_url()}|{SLIDE}|{t_sweep()}|{SWEEP_LEN}|{WIPE_TRAVEL}|glass6"
        # A VERSION TOKEN FOR THE DRAWING ITSELF, not just its constants. The key
        # hashes every knob the card exposes and nothing about the CODE that
        # turns them into pixels - so a change to the wipe curve, the mask, or
        # the compositing is silently ignored and the stale frames are reused
        # forever. That cost a real fix an hour: the entrance's first frame was
        # corrected to remove a one-frame freeze at the join, the clip was
        # re-rendered, and the freeze was still there because these frames never
        # rebuilt. Bump the token whenever you change how a frame is DRAWN.
        f"|{ENTRANCE}|{RISE}|{TYPE_STYLE}|{WIPE_WHITE}|{WIPE_CORE}|subpx1|entrance2"
        f"|{TAG_PX}|{URL_PX}"
        f"|{_plate_key()}"
        .encode()).hexdigest()[:10]
    return q.WORK / "tmp" / f"_endcard_{key}"


def settled_frames(fps: int) -> Path:
    """
    EVERY frame's card face, cached. Identical on every clip, so built once.

    It used to cache only the post-wipe frames, because the wipe composited one
    pre-rendered face over the outgoing picture and that face never changed. With
    a moving backplate it has to change: reusing a single face froze the plate for
    the whole wipe and then started it abruptly. The wipe now composites frame f's
    own face, so the cache has to carry them all.

    The extra cost is 23 more faces at 30fps, once per project, and it buys the
    thing the card was reported for.
    """
    cache = _cache_dir(fps)
    frames = int(round(CARD_SECONDS * fps))
    wipe_frames = entrance_frames(fps)
    done = cache / ".done"
    if done.exists():
        return cache
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    for f in range(frames):
        # p: the still-backdrop push, which only settles after the wipe.
        # u: the plate's position, which runs across the whole card.
        # t: 0.0 through the wipe, NOT None. The two are opposite and it matters.
        #    t=0.0 means the lines have not arrived, which is the staging this card
        #    was designed with: the wipe reveals the field and the mark, then the
        #    lines slide in. t=None means fully settled, and it put both lines on
        #    screen under the wipe, blanked them the instant the wipe finished, and
        #    animated them in a second time - a visible pop at frame 24.
        p = max(0.0, (f - wipe_frames) / max(1, frames - wipe_frames - 1))
        u = f / max(1, frames - 1)
        t = (f / fps) if f >= wipe_frames else 0.0
        card_face(p, t=t, u=u).convert("RGB").save(cache / f"{f:05d}.png")
    done.write_text("ok")
    return cache


def build_frames(seqdir: Path, base: Image.Image, fps: int) -> int:
    """The card arriving over the clip's last frame."""
    if seqdir.exists():
        shutil.rmtree(seqdir)
    seqdir.mkdir(parents=True)

    cache = settled_frames(fps)
    frames = int(round(CARD_SECONDS * fps))
    wipe_frames = entrance_frames(fps)
    slant = 420
    base_rgba = base.convert("RGBA")

    for f in range(frames):
        dst = seqdir / f"{f:05d}.png"
        if f >= wipe_frames:
            src = cache / f"{f:05d}.png"
            try:
                # os.link, not Path.hardlink_to: the latter is 3.10+, and
                # which python3 wins on PATH here is not stable (macOS ships 3.9).
                os.link(src, dst)
            except OSError:
                shutil.copy(src, dst)
            continue

        if ENTRANCE == "rise":
            # THE OUTRO COVERS THE PICTURE, arriving from below.
            #
            # Same move, same curve, as a b-roll cutaway in this pipeline, for
            # the reason given at ENTRANCE. Three things it has to get right:
            #
            # SMOOTHSTEP, not a quart. The travel is the full 1920 of the frame,
            # and the distance rule here is absolute: peak velocity is ~4x the
            # average on a quart, which puts 46% of the frame into one frame and
            # strobes. Smoothstep peaks at 1.5x.
            #
            # THE COVER LANDS ON THE LAST ENTRANCE FRAME, not one after it. u
            # divides by (wipe_frames - 1) so the final entrance frame has
            # e = 1.0 and dy = 0; dividing by wipe_frames leaves a few stray
            # pixels of the outgoing clip showing under the card and then snaps
            # them away, which is the "pop at the gate" this pipeline has been
            # bitten by before.
            #
            # EVEN OFFSETS. yuv420p subsamples chroma 2x2, so an odd y offset
            # puts the card's chroma on a half-sample grid and the edge crawls.
            # (f + 1), NOT f. At f = 0 the old form gave u = 0, so the first
            # end-card frame was the base image untouched - a byte-copy of the
            # clip's last frame, and the picture froze for one frame at the join.
            # Measured on the delivered file: mean |delta| 0.022 between two
            # consecutive frames at t=47.20 where every neighbour is 3 to 12.
            # Both curves still land on 1.0 at f = wipe_frames - 1.
            u = (f + 1) / wipe_frames
            top = int((1 - _smoothstep(u)) * q.H)   # H when off below, 0 landed
            top = (top // 2) * 2
            frame = base_rgba.copy()
            # frame f's OWN face, so the plate is already running as it arrives
            face = Image.open(cache / f"{f:05d}.png").convert("RGBA")
            frame.alpha_composite(face, (0, top))
            frame.convert("RGB").save(dst)
            continue

        # THE LIGHT MUST FULLY LEAVE THE FRAME, and the travel is what takes it
        # off - not a fade. Two numbers make that work.
        #
        # TRAVEL is 2820, not the 1920 the mask needs. The reveal is complete once
        # the line clears the bottom-left corner at edge 1500, but the wash is
        # hundreds of pixels wide, so at 1500 the bar is still 99% bright and
        # sitting on the card. It takes until edge 2400 for the light to actually
        # be gone. Stopping at 1590 and dimming in place is what the old fade did,
        # and because the bar is slanted the top cleared first, so what you watched
        # was the light dying at the bottom of the frame instead of exiting.
        #
        # The 0.85 exponent is a much gentler ease than the cubic. A cubic
        # front-loads so hard that the reveal finished at frame 7 of 23 and the
        # remaining two thirds were an empty tail. At 0.85 the card is fully
        # revealed at frame 14 with the bar still at full brightness, and frames
        # 15 to 22 are the light travelling off. White passes, then it goes.
        p = ((f + 1) / wipe_frames) ** 0.85
        # AND THE REVEAL STARTS AT THE FRAME EDGE, NOT 420px OFF IT. This is a
        # SECOND defect that sat behind the duplicate above, and both had to go.
        # `-slant + p*T` starts the leading edge at x=-420; the bar is slanted,
        # so nothing is revealed until p passes slant/T = 0.135, which on the
        # eased curve is the first two frames of every card. With the duplicate
        # gone, card frame 0 still changed only 65 pixels against the body's last
        # frame where frame 1 changes 215,000 - the wipe was drawing off-screen.
        # `p * (T - slant)` lands on the SAME endpoint (2680), so the light still
        # leaves the frame exactly as it did; only the start moves.
        edge = p * (WIPE_TRAVEL - slant)
        mask = Image.new("L", (q.W, q.H), 0)
        ImageDraw.Draw(mask).polygon(
            [(-slant, q.H), (edge - slant, q.H), (edge, 0), (-slant, 0)], fill=255)
        # frame f's OWN face, so the plate keeps moving under the wipe
        face = Image.open(cache / f"{f:05d}.png").convert("RGBA")
        frame = Image.composite(face, base_rgba, mask)
        # fade is 1.0 now and the parameter is kept only so the signature does
        # not change under anything that calls it directly. The light leaves
        # because it travels off, not because it is dimmed in place.
        _draw_edge(frame, edge, slant, 1.0)
        frame.convert("RGB").save(dst)
    return frames


# No card ink may pass this fraction of frame width. TikTok's like/comment/share
# rail sits over roughly the last 12-14%, and a tagline that reached 93.5% put
# the end of "Live." behind an icon. Vertical is not at risk - the block ends at
# 62% of height and the lowest platform chrome starts at 76% - so width is the
# only axis worth gating.
SAFE_X = 0.86


def safe_area(frame: Image.Image | None = None) -> tuple[bool, float, float]:
    """
    Does the settled card keep its ink out of the platform chrome?

    Returns (ok, left_pct, right_pct). A gate that is only written down is a
    comment; this one runs, and the preview prints it, so lengthening TAGLINE or
    adding a line fails loudly instead of shipping behind an icon.
    """
    im = (frame or card_face()).convert("L")
    a = np.asarray(im)
    cols = np.where((a > 60).any(axis=0))[0]
    if not len(cols):
        return True, 0.0, 0.0
    lo, hi = cols.min() / im.width, cols.max() / im.width
    return hi <= SAFE_X and lo >= (1 - SAFE_X), lo * 100, hi * 100


def card_audio(dur: float, tmp: Path) -> Path:
    """
    The card's sound: the real recorded swipe if one is installed, else the
    synthesised fallback.

    ONE OWNER, and that is the whole point of it being a function. This lived
    inside append(), and every other way of rendering the card - the preview at
    the bottom of this file, and any build script written against it - reached
    straight for endcard_audio.write() instead. So the clips Steven ships carried
    the recorded swipe while every outro rendered for him to APPROVE carried the
    numpy synth, which is a different sound. He caught it: "it needs to have that
    noise that we had before on the current clips."

    The transient sits about 0.4s in, which is mid-wipe at the current 0.78s, so
    it plays from the top of the card with no offset.

    The wav is a CACHE, keyed on everything that produces it: the swipe file's
    size and mtime, the filter string, and the card's length. It used to be one
    keyless `endcard.wav`, which meant the 2026-08-11 fix below (the 82ms atrim)
    never reached a single delivered clip - the stale Aug 7 wav was picked up
    every time - and the preview wrote the synthesised fallback to the same path,
    silently swapping every later clip's swipe.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    # loudnorm resamples to 192 kHz and does not honour apad=whole_dur after
    # it, which left every wav 40-65ms short of the card and the delivered
    # audio ending before the video. Resample back, pad generously, then trim
    # to the exact length.
    # ...and the trim is by SAMPLE COUNT, not by time: loudnorm shifts the
    # timestamps, so atrim=0:4.0 cut 4.0s of pts and delivered 3.9535s of
    # audio, and the concat then ended the sound 46ms before the picture.
    n_samples = int(round(dur * 48000))
    af = (f"atrim=start=0.082,asetpts=N/SR/TB,"
          f"aformat=sample_rates=48000:channel_layouts=stereo,"
          f"loudnorm=I=-19:TP=-1.5:LRA=11,"
          f"aresample=48000,apad=pad_dur=8,atrim=end_sample={n_samples},"
          f"asetpts=N/SR/TB")
    if SWIPE.exists():
        st = SWIPE.stat()
        key = hashlib.sha1(
            f"{st.st_size}:{int(st.st_mtime)}:{af}".encode()).hexdigest()[:12]
        wav = tmp / f"endcard-{key}.wav"
        # exists() IS TRUE THE MOMENT ffmpeg CREATES THE FILE, before it has
        # written a byte of audio - so a run interrupted mid-write leaves a
        # zero-length wav that every later run treats as a cache HIT, and the
        # card ships silent. Require a plausible size, not mere existence.
        if not (wav.exists() and wav.stat().st_size > 1024):
            q.run(["ffmpeg", "-y", "-v", "error", "-i", str(SWIPE),
                   # atrim first: the recorded swipe carries 82ms of bit-exact
                   # digital silence at its head, so the whoosh started an eighth
                   # of a second after the light did.
                   "-af", af, str(wav)])
        return wav

    # keyed on the entrance too, not just the length. The whoosh is cut to the
    # entrance's length, so flipping ENTRANCE at the same CARD_SECONDS would
    # otherwise reuse a wav shaped for the other move.
    wav = tmp / f"endcard-synth-{dur:.3f}-{ENTRANCE}{entrance_seconds():.2f}.wav"
    if not wav.exists():
        endcard_audio.write(wav, dur, entrance_seconds())
    return wav


def _probe_frames(path: Path) -> int:
    """How many video frames are actually in the file. Counted, not derived."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip()
    if not out.isdigit():
        raise SystemExit(f"could not count the frames in {path.name}: {out!r}")
    return int(out)


def append(clip: Path, fps: int) -> Path:
    """Put the card on the end of a finished clip, picture and sound together."""
    tmp = q.WORK / "tmp"
    tmp.mkdir(exist_ok=True)
    seq = tmp / f"{clip.stem}_end"

    # THE BODY IS TRIMMED TO A WHOLE NUMBER OF FRAMES BEFORE THE CARD GOES ON,
    # and this is what stops the join freezing for a frame.
    #
    # concat offsets the second input by the first input's duration, and for an
    # a/v pair that is the LONGER of the two streams. The body's audio runs to
    # the full span while its video stops on the last whole frame, so on a span
    # that is not an exact frame multiple the audio is up to one frame longer -
    # measured on this clip, video 1415 frames = 47.166667s against audio
    # 47.200000s. concat placed the card 33ms late, and the output frame rate
    # filled the gap by repeating the card's own first frame: it appeared at both
    # n=1415 and n=1416, changing 45 pixels where its neighbours change 300,000.
    # The picture stuck for a frame on the very last cut the clip makes.
    #
    # Trimming BOTH streams to frames/FPS makes the offset a whole frame by
    # construction. What is discarded is at most one frame of END_PAD silence
    # after the last word, which is why trimming the audio down is right and
    # padding the video up (a duplicated frame - the same freeze, moved) is not.
    nb = _probe_frames(clip)
    body_dur = nb / fps

    last = tmp / f"{clip.stem}_last.png"
    # -sseof -1 with -update, NOT -sseof -0.2 with -frames:v 1. The latter returns
    # the FIRST frame at or after duration-0.2s, which is five frames from the end
    # at 30fps - so the card froze on a stale frame and the picture jumped 167ms
    # backwards exactly as the whoosh landed. Verified by matching the grabbed
    # frame against every frame of the last half second: MAD 0.0000 against the
    # frame 5 from the end, 0.96 and 1.18 either side of it.
    q.run(["ffmpeg", "-y", "-v", "error", "-sseof", "-1", "-i", str(clip),
           "-update", "1", "-f", "image2", "-q:v", "1", str(last)])
    n = build_frames(seq, Image.open(last), fps)

    wav = card_audio(n / fps, tmp)

    out = clip.with_name(clip.stem + "_end.mp4")
    q.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(clip),
        "-framerate", str(fps), "-i", str(seq / "%05d.png"),
        "-i", str(wav),
        "-filter_complex",
        # settb on both sides so concat is comparing like with like, and both
        # body streams trimmed to the same whole-frame length (see above).
        f"[1:v]format=yuv420p,setsar=1,settb=1/{fps}[cv];"
        f"[0:v]setsar=1,settb=1/{fps},trim=end={body_dur:.6f},"
        f"setpts=PTS-STARTPTS[mv];"
        f"[0:a]atrim=end={body_dur:.6f},asetpts=N/SR/TB[ma];"
        "[2:a]aformat=sample_rates=48000:channel_layouts=stereo[ca];"
        "[mv][ma][cv][ca]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "19",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-x264-params", "keyint=50:min-keyint=25",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-r", str(fps),
        str(out),
    ], cwd=q.WORK)
    shutil.rmtree(seq, ignore_errors=True)
    # THE JOIN IS CHECKED, NOT ASSUMED. A duplicated frame here is invisible to
    # every other gate in the pipeline - the file plays, the duration is right,
    # nothing errors - and it shipped for months. Counting is cheap.
    got = _probe_frames(out)
    if got != nb + n:
        raise SystemExit(
            f"END CARD JOIN: {out.name} came out {got} frames but the body is "
            f"{nb} and the card is {n} ({nb + n}). A frame was duplicated or "
            f"dropped at the join, which reads as a freeze on the last cut.")
    out.replace(clip)
    return clip


if __name__ == "__main__":
    import sys
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "endcard-preview.mp4")
    seq = q.WORK / "tmp" / "endcard_preview"
    seq.parent.mkdir(exist_ok=True)
    n = build_frames(seq, Image.new("RGB", (q.W, q.H), (0, 0, 0)), q.FPS)
    # card_audio, NOT endcard_audio.write: the preview has to carry the same
    # sound the delivered clips do, or it is not a preview of them.
    wav = card_audio(n / q.FPS, q.WORK / "tmp")
    q.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(q.FPS),
           "-i", str(seq / "%05d.png"), "-i", str(wav),
           "-c:v", "libx264", "-preset", "slow", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-r", str(q.FPS), str(dest)])
    ok, lo, hi = safe_area()
    print(f"{dest}\n  safe area: ink spans {lo:.1f}%-{hi:.1f}% of width  "
          f"({'ok' if ok else f'BREACH - must stay inside {(1-SAFE_X)*100:.0f}%-{SAFE_X*100:.0f}%'})")
