#!/usr/bin/env python3
"""
The closing card's sound: a whoosh across the wipe, an impact as it lands, and a
tail that decays under the mark.

Synthesised rather than sourced. A stock whoosh means a licence to track, a file to
keep next to the skill, and a sound every other channel also has; this is forty
lines of numpy, is identical on every render, and can be retuned by changing a
number. It is deliberately restrained - the clip's own audio has just ended and the
card is four seconds of quiet, so a big cinematic riser would be comic.

    python3 endcard_audio.py out.wav [seconds] [wipe_seconds]
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000


def _ma(x: np.ndarray, w: int) -> np.ndarray:
    """Moving average - a cheap lowpass, and the only one needed here."""
    if w < 2:
        return x
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = (c[w:] - c[:-w]) / w
    return np.concatenate([out, np.full(len(x) - len(out), out[-1] if len(out) else 0.0)])


def whoosh(dur: float, wipe: float, seed: int = 7) -> np.ndarray:
    """
    Air moving past, swept from low to bright and away again.

    Remade once. The first version put a sine falling 760Hz to 90Hz under the
    noise, which is what made it sound clogged: that band is where a voice lives,
    so it read as congestion rather than as movement. There is no tonal element
    now - the sweep is entirely in the noise's brightness, which is how real air
    sounds, and the low end is rolled off so nothing competes with the impact.

    It is also slower. Riding a 0.78s wipe, a 0.5s whoosh arrives before the
    picture does and reads as rushed.
    """
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)

    # four bands of the same noise, from dark to air
    b1 = _ma(noise, 40)
    b2 = _ma(noise, 12) - _ma(noise, 40)
    b3 = _ma(noise, 4) - _ma(noise, 12)
    b4 = noise - _ma(noise, 4)

    lead = 0.05
    span = wipe * 1.10
    p = np.clip((t - lead) / max(1e-3, span), 0, 1.6)

    # brightness climbs to just past the middle of the move, then falls
    x = np.clip(p / 1.05, 0, 1.35)
    w1 = np.exp(-((x - 0.10) / 0.26) ** 2)
    w2 = np.exp(-((x - 0.42) / 0.26) ** 2)
    w3 = np.exp(-((x - 0.70) / 0.26) ** 2)
    w4 = np.exp(-((x - 0.95) / 0.30) ** 2)
    body = b1 * w1 * 0.55 + b2 * w2 * 0.85 + b3 * w3 + b4 * w4 * 0.80

    # amplitude: an unhurried swell, a longer settle
    env = np.where(p < 0.80, np.clip(p / 0.80, 0, 1) ** 1.35,
                   np.exp(-(p - 0.80) * 4.4))
    env *= np.clip(1 - (t - (lead + span * 1.55)) / 0.7, 0, 1)
    return _ma(body * env, 2) * 0.62


def impact(dur: float, at: float) -> np.ndarray:
    """A soft low landing where the wipe finishes. Felt more than heard."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    d = np.clip(t - at, 0, None)
    hit = np.where(t >= at, 1.0, 0.0)
    # softer and lower than before: this should be felt under the wash, not heard
    # as a drum. A hard transient here was most of the "fast" feeling.
    body = np.sin(2 * np.pi * (46 * np.exp(-3.4 * d) + 30) * d) * np.exp(-6.0 * d)
    return body * 0.42 * hit


def shimmer(dur: float, at: float) -> np.ndarray:
    """A quiet high bed that settles under the mark, so the card is not dead air."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    d = np.clip(t - at, 0, None)
    # The ring Steven likes, but SHORT. It was given a long tail and that was wrong:
    # held under the mark it turns into a drone and draws attention to itself for
    # three seconds. A quick chime that is gone inside a second reads as punctuation.
    env = np.clip(d / 0.16, 0, 1) * np.exp(-4.2 * d)
    tone = sum(np.sin(2 * np.pi * f * t + ph) for f, ph in
               ((1046.5, 0.0), (1567.98, 1.1), (2093.0, 2.3), (3135.96, 0.6)))
    return tone / 4 * env * 0.075


def riser(dur: float, at: float) -> np.ndarray:
    """A short reverse swell into the wipe, so the whoosh is arrived at."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    lead = 0.42
    x = np.clip((t - (at - lead)) / lead, 0, 1)
    env = np.where(t < at, x ** 3.0, 0.0)
    tone = np.sin(2 * np.pi * np.cumsum(240 + 900 * x) / SR)
    return tone * env * 0.10


def build(dur: float, wipe: float) -> np.ndarray:
    """
    Stereo, with the two channels built from different noise seeds.

    Mono duplicated to both sides puts the whoosh dead centre in the head, which is
    exactly where the wipe is not - it crosses the frame. Decorrelated noise gives
    it width without any panning trickery.
    """
    hit = wipe * 0.92
    common = impact(dur, hit) + shimmer(dur, wipe) + riser(dur, hit)
    chans = []
    for seed in (7, 23):
        a = whoosh(dur, wipe, seed=seed) + common
        fade = int(0.12 * SR)               # never end on a click
        a[-fade:] *= np.linspace(1, 0, fade)
        a[:64] *= np.linspace(0, 1, 64)
        chans.append(a)
    st = np.stack(chans, axis=1)
    peak = float(np.abs(st).max()) or 1.0
    return st / peak * 0.74                 # headroom; platforms renormalise


def write(path: Path, dur: float, wipe: float) -> Path:
    a = build(dur, wipe)
    stereo = (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo)
    return path


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "endcard.wav")
    d = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    wp = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    print(write(out, d, wp))
