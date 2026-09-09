#!/usr/bin/env python3
"""
Glass letterforms, for the closing card.

The look asked for is the "glass alphabet" family - letters that read as cut
crystal: a bright bevel catching light along the top edge, a cool gradient through
the body, a darker foot, a faint outer bloom, and a specular highlight that travels
across them. This builds it from the type the rest of the system already uses, so
it stays Inter and stays on-brand rather than importing a second typeface.

    python3 glass.py out.png "Some text"

Everything is a mask operation on the rendered glyphs, which is why it works on any
string at any size without an asset per letter.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# the body gradient, top to bottom: cool white, brand blue, deep blue
TOP = (248, 253, 255)
MID = (146, 205, 233)
LOW = (26, 68, 108)
BEVEL = (255, 255, 255)
BLOOM = (120, 180, 214)


def _mask(text: str, font: ImageFont.FreeTypeFont, track: float,
          pad: int) -> tuple[Image.Image, int, int]:
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    w = probe.textlength(text, font=font) + track * max(0, len(text) - 1)
    h = font.size * 1.55
    img = Image.new("L", (int(w) + pad * 2, int(h) + pad * 2), 0)
    d = ImageDraw.Draw(img)
    x = float(pad)
    for ch in text:
        d.text((x, pad), ch, font=font, fill=255)
        x += probe.textlength(ch, font=font) + track
    return img, int(w) + pad * 2, int(h) + pad * 2


def render(text: str, font: ImageFont.FreeTypeFont, track: float = 0.0,
           sweep: float | None = None) -> Image.Image:
    """
    One line of glass type on transparent.

    `sweep` is 0..1, the position of the travelling highlight; None for none. The
    sweep is what sells it as glass rather than as a gradient fill - a static
    bevel reads as chrome, a moving one reads as light passing through.
    """
    pad = max(10, int(font.size * 0.30))
    m, W, H = _mask(text, font, track, pad)
    a = np.asarray(m).astype(float) / 255.0

    # body gradient down the glyph box
    ys = np.where(a.max(axis=1) > 0.02)[0]
    y0, y1 = (ys.min(), ys.max()) if len(ys) else (0, H - 1)
    t = np.clip((np.arange(H) - y0) / max(1, y1 - y0), 0, 1)[:, None]
    top, mid, low = (np.array(c, float) for c in (TOP, MID, LOW))
    body = np.where(t < 0.5, top + (mid - top) * (t / 0.5),
                    mid + (low - mid) * ((t - 0.5) / 0.5))
    rgb = np.repeat(body[:, None, :], W, axis=1)

    # bevel: the mask minus itself shifted down is the lit top edge; shifted up is
    # the shaded foot. Blurring each softens them into a rounded edge.
    sm = np.asarray(m.filter(ImageFilter.GaussianBlur(1.2))).astype(float) / 255.0
    up = np.roll(sm, -max(2, int(font.size * 0.035)), axis=0)
    dn = np.roll(sm, max(2, int(font.size * 0.035)), axis=0)
    lit = np.clip(sm - dn, 0, 1)
    shade = np.clip(sm - up, 0, 1)
    lit = np.asarray(Image.fromarray((lit * 255).astype(np.uint8))
                     .filter(ImageFilter.GaussianBlur(1.0))).astype(float) / 255.0
    shade = np.asarray(Image.fromarray((shade * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(1.6))).astype(float) / 255.0

    rgb = rgb + (np.array(BEVEL, float) - rgb) * (lit[:, :, None] * 1.00)
    rgb = rgb * (1 - shade[:, :, None] * 0.68)

    # travelling specular, clipped to the glyphs
    if sweep is not None:
        xx = np.arange(W)[None, :]
        cx = -W * 0.35 + sweep * (W * 1.7)
        band = np.exp(-((xx - cx) / (W * 0.085)) ** 2)
        rgb = rgb + (255 - rgb) * (band * 0.78)[:, :, None] * a[:, :, None]

    rgb = np.clip(rgb, 0, 255)

    out = np.dstack([rgb, a * 255]).astype(np.uint8)
    glass = Image.fromarray(out, "RGBA")

    # outer bloom, so the letters sit in the light rather than on top of it
    bloom = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bloom.putalpha(m.filter(ImageFilter.GaussianBlur(int(font.size * 0.22))))
    tint = Image.new("RGBA", (W, H), BLOOM + (0,))
    tint.putalpha(bloom.getchannel("A").point(lambda v: int(v * 0.42)))
    plate = Image.alpha_composite(tint, glass)
    # Trim to what is actually visible (ink plus its bloom). Returning the padded
    # canvas made every caller's layout maths dishonest: the block measured taller
    # than it looked, so a centred block sat visibly high.
    box = plate.getbbox()
    return plate.crop(box) if box else plate


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "glass.png"
    txt = sys.argv[2] if len(sys.argv) > 2 else "One Platform."
    f = ImageFont.truetype(
        str(__import__("pathlib").Path(__file__).resolve().parent.parent /
            "assets" / "fonts" / "QMInter500.ttf"), 96)
    im = render(txt, f, 1.0, sweep=0.45)
    bg = Image.new("RGB", im.size, (10, 14, 20))
    bg.paste(im, (0, 0), im)
    bg.save(out)
    print(out)
