#!/usr/bin/env python3
"""
Search the b-roll library by what the PICTURE SHOWS. Local, no API, no torch.

WHY THIS EXISTS, and it is not a refinement of the text re-rank - it is the
other half of the problem.

`semantic.py` decides whether a candidate is ABOUT the right thing. It cannot
FIND anything: by the time it runs, the candidate list has already been chosen
by `broll.search_library`, which matches on token overlap against the stored
term and title. So a perfect asset whose title happens to use different words is
invisible. A caption about "manufacturing" never reaches a clip titled "workers
on an assembly line", because no word is shared.

MEASURED, over 135 distinct caption contexts taken from every slate on this
machine, scoring them against all 1,783 live library rows:

    only 291 of 1,783 assets (16.3%) can ever enter a top-5.

Eighty-four percent of the library is unreachable. And the reachable sixth is
dominated by whatever sits nearest the centre of the embedding space - a
close-up of a "Need a Job" sign came top-5 for 15.6% of ALL captions, a stock
photo of coins for 11.1%, a portrait of Warren Buffett for 8.9%. Those are not
answers, they are the shape of the space.

WHAT THIS DOES INSTEAD. CLIP puts images and text in ONE vector space, so a
frame can be compared to a phrase directly. Every baked asset is decoded to a
few frames, each frame is embedded once, and a query phrase is embedded with the
matching text tower. The library becomes searchable by what is in the picture
rather than by what a stock photographer happened to type.

FEED IT THE QUERY TERM, NOT THE SENTENCE. This is the one thing to get right and
I got it wrong first. CLIP is trained on short captions, and on a full spoken
sentence it returns noise. Measured on a 150-asset probe, same library, same
model, the only difference being what was embedded:

    query                          fed the SENTENCE        fed the TERM
    people gambling in a casino    graphics card and money  gambling machines  (1,2,3 all casino)
    a portrait of Donald Trump     Trump portrait 0.251     Trump portrait 0.298
    athletic shoes in a store      forklift, sale sign      shoe assets 1,2,3

So the division of labour is: `broll.query_for()` already turns a spoken word
into a caption-like phrase, and that phrase is what this module searches with.
`semantic.py` keeps the sentence and keeps the final say on whether a hit is on
topic. Retrieval by picture, judgement by meaning.

SEVERAL FRAMES PER ASSET, deliberately. One row per file means one title and one
moment for a thirty-second clip that may contain three different shots, and a
still baked with a pan is a different picture at its start and at its end (see
BROLL_PAN_DONE). Indexing FRAMES_PER frames spread across each asset and scoring
an asset by its BEST frame makes the same file reachable from several different
captions - which multiplies the effective library without buying anything.

DEGRADES TO NOTHING. If fastembed or the models are missing, `search()` returns
an empty list and `broll.search` behaves exactly as it did before. Nothing here
is a hard dependency, the same stance semantic.py takes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The 512-dim CLIP pair. Both towers must come from the SAME model or the
# vectors are not comparable - a mismatch here produces plausible-looking
# nonsense rather than an error, which is why they are named together.
MODEL_VISION = "Qdrant/clip-ViT-B-32-vision"
MODEL_TEXT = "Qdrant/clip-ViT-B-32-text"

# How many frames of each asset are indexed. Four is where the cost stops being
# free (1,783 assets x 4 = 7,132 embeddings, about 12 minutes) and the return
# starts flattening: a baked asset is BAKE_HOLD 4.7s long, so four frames sit
# roughly a second apart, which is the shortest interval on which a cut inside
# stock footage tends to happen.
FRAMES_PER = 4
INDEX_NAME = "picture-index.npz"

# A floor under a CLIP similarity, which is NOT on the same scale as
# semantic.FLOOR. CLIP cosines are compressed - the whole useful range on this
# library runs about 0.18 to 0.32 - so this is set from the measured separation
# rather than by analogy with the text model. At 0.22 the casino query keeps its
# three casino clips and drops the graphics card; below 0.20 everything returns
# everything. It is a RETRIEVAL floor only: semantic.rerank still has the final
# say on whether a hit is on topic.
FLOOR = 0.22

# How hard to discount a frame for being close to everything.
#
# ZERO, AND THAT IS THE MEASUREMENT, NOT AN OVERSIGHT. This correction was
# specified before the index existed, from a real problem in the TEXT space:
# scoring 135 captions against the 1,783 library titles, a close-up of a "Need a
# Job" sign came top-5 for 15.6% of them and only 16.3% of the library was
# reachable at all. Subtracting each row's average similarity fixed it there
# (reach 16.3% -> 23.7%, worst hub 15.6% -> 6.7%).
#
# It does the OPPOSITE here. Measured on the real 7,104-frame picture index
# against the 158 distinct query terms in the archive:
#
#     weight   reach            worst hub
#     0.0      528/1776 29.7%     5.7%
#     0.5      233/1776 13.1%    48.7%
#     1.0       39/1776  2.2%    96.8%
#
# Two reasons, and both are about the space rather than the idea. CLIP is far
# less hub-prone to begin with - raw cosine already reaches nearly twice as much
# of the library as the corrected TEXT search did, with a third of the worst
# hub. And the offline proxy is the wrong quantity: the text measurement used
# each row's closeness to real CAPTIONS, while this uses closeness to other
# ASSETS, which correlated at only r=0.72 even in the space it came from.
# Subtracting it does not suppress hubs, it promotes ANTI-hubs - one isolated
# congressional portrait went on to win 96.8% of all queries.
#
# The mechanism is kept because the hub array is already computed and stored and
# a future library may need it. It stays at 0.0 until somebody re-measures the
# table above and it comes out the other way.
HUB_W = 0.0

_VIS = _TXT = None
_TRIED_VIS = _TRIED_TXT = False
_CACHE = None


def _vision():
    """The image tower, or None once and quietly thereafter."""
    global _VIS, _TRIED_VIS
    if _VIS is not None or _TRIED_VIS:
        return _VIS
    _TRIED_VIS = True
    try:
        from fastembed import ImageEmbedding
        _VIS = ImageEmbedding(MODEL_VISION)
    except Exception as e:
        sys.stderr.write(
            f"note: picture search off ({type(e).__name__}). "
            f"Install with: python3 -m pip install --user fastembed\n")
        _VIS = None
    return _VIS


def _text():
    """The text tower of the SAME CLIP model. See MODEL_VISION."""
    global _TXT, _TRIED_TXT
    if _TXT is not None or _TRIED_TXT:
        return _TXT
    _TRIED_TXT = True
    try:
        from fastembed import TextEmbedding
        _TXT = TextEmbedding(MODEL_TEXT)
    except Exception as e:
        sys.stderr.write(f"note: picture search off ({type(e).__name__}).\n")
        _TXT = None
    return _TXT


def index_path(lib: Path) -> Path:
    return Path(lib) / INDEX_NAME


def _frames(asset: Path, n: int = FRAMES_PER) -> list[str]:
    """
    n frames spread across an asset, as PNG paths in a temp dir the caller owns.

    Sampled from 10% to 90% of the duration rather than 0 to 100: the first
    frame of a baked clip is often a fade-up from black and the last is whatever
    the bake ran out on, and both embed as "a dark rectangle" rather than as the
    picture. Measured on the library, a first-frame sample returned luma 0.0 on
    real assets - see the note in SKILL.md about "running shoes on track".
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(asset)], capture_output=True, text=True)
        dur = float((out.stdout or "0").strip() or 0.0)
    except Exception:
        dur = 0.0
    if dur <= 0.2:
        dur = 4.7
    tmp = tempfile.mkdtemp(prefix="qmpic")
    paths = []
    for i in range(n):
        frac = 0.10 + (0.80 * i / max(1, n - 1))
        f = os.path.join(tmp, f"f{i}.png")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{dur*frac:.3f}", "-i", str(asset),
             "-frames:v", "1", "-vf", "scale=224:224", f], check=False)
        if os.path.exists(f) and os.path.getsize(f) > 0:
            paths.append(f)
    return paths


def _sweep(frames: list[str]) -> None:
    """Delete the frames AND the temp directory _frames made for them."""
    import shutil
    seen = set()
    for f in frames:
        seen.add(os.path.dirname(f))
        try:
            os.remove(f)
        except OSError:
            pass
    for d in seen:
        # Only ever a directory this module made - _frames names them "qmpic*".
        if os.path.basename(d).startswith("qmpic"):
            shutil.rmtree(d, ignore_errors=True)


def build(lib: Path, names: list[str] | None = None, rebuild: bool = False,
          progress=None) -> dict:
    """
    Embed FRAMES_PER frames of every baked asset. Incremental unless `rebuild`.

    Returns a small report. The index is one row PER FRAME with a parallel array
    naming the asset each row belongs to, so a search scores frames and an asset
    takes its best one - see the module docstring.
    """
    import numpy as np
    lib = Path(lib)
    vis = _vision()
    if vis is None:
        return {"ok": False, "why": "no image model"}
    idx = json.loads((lib / "index.json").read_text())
    live = [k for k, v in idx.items()
            if isinstance(v, dict) and not v.get("retired") and (lib / k).exists()]
    if names:
        live = [k for k in live if k in names]
    have: set[str] = set()
    old_keys: list[str] = []
    old_vecs = None
    p = index_path(lib)
    # `rebuild` MEANS THE WHOLE INDEX, AND ONLY WHEN THE WHOLE INDEX IS ASKED
    # FOR. Passing names= with rebuild=True used to discard every asset not
    # named: "re-do these two" wrote an index containing exactly those two and
    # dropped the other 1,774. It cost a thirty-minute rebuild to find out, from
    # a one-line test that had nothing to do with indexing - the failure is
    # silent, and the only symptom is that search starts answering every query
    # with the same two pictures.
    #
    # Naming assets now always means "these rows, in place".
    _whole = rebuild and not names
    if p.exists() and not _whole:
        try:
            z = np.load(p, allow_pickle=False)
            old_keys = [str(x) for x in z["keys"]]
            old_vecs = z["vecs"]
            have = set(old_keys)
        except Exception:
            old_keys, old_vecs, have = [], None, set()
    # A named asset is re-embedded even if it is already in the index - that is
    # what asking for it by name means - and its stale rows are dropped below.
    todo = list(live) if names else [k for k in live if k not in have]
    if names:
        _drop = set(names)
        keep_i = [i for i, k in enumerate(old_keys) if k not in _drop]
        if old_vecs is not None and len(keep_i) != len(old_keys):
            old_vecs = old_vecs[keep_i]
            old_keys = [old_keys[i] for i in keep_i]
    new_keys: list[str] = []
    new_rows: list = []
    for i, name in enumerate(todo):
        if progress:
            progress(i + 1, len(todo), name)
        fs = _frames(lib / name)
        if not fs:
            continue
        try:
            vecs = list(vis.embed(fs))
        except Exception as e:
            sys.stderr.write(f"note: could not embed {name} ({type(e).__name__})\n")
            vecs = []
        for v in vecs:
            v = np.asarray(v, dtype="float32")
            n = np.linalg.norm(v) or 1.0
            new_rows.append(v / n)
            new_keys.append(name)
        # THE DIRECTORY TOO, not just the frames. The first version removed the
        # PNGs and left the mkdtemp behind, so a full index run over 1,776
        # assets left 1,798 empty directories in the system temp area - harmless
        # individually, invisible, and permanent. Remove the whole tree.
        _sweep(fs)
    if new_rows:
        add = np.vstack(new_rows).astype("float32")
        vecs = add if old_vecs is None else np.vstack([old_vecs, add])
        keys = old_keys + new_keys
    else:
        vecs, keys = old_vecs, old_keys
    if vecs is None or not len(keys):
        return {"ok": False, "why": "nothing indexed"}
    # RETIRED ROWS ARE DROPPED ON EVERY BUILD. A retired asset is gone for every
    # purpose (broll.search_library refuses it), and leaving its vectors in the
    # index would let picture search resurrect a picture somebody retired.
    # ...and RETIREMENT is only assessed on a whole-index build. On a named run
    # `live` is the named subset, so every other asset would look retired.
    dead = {k for k in keys if k not in set(live)} if not names else set()
    if dead:
        keep = [i for i, k in enumerate(keys) if k not in dead]
        vecs = vecs[keep]
        keys = [keys[i] for i in keep]
    # Each frame's average similarity to the rest of the index. Computed in
    # blocks so a 7,000-row index never materialises a 7,000x7,000 matrix.
    V = vecs.astype("float32")
    hub = np.zeros(len(V), dtype="float32")
    B = 512
    for i in range(0, len(V), B):
        hub[i:i+B] = (V[i:i+B] @ V.T).mean(axis=1)
    np.savez_compressed(p, keys=np.array(keys), vecs=V, hub=hub)
    return {"ok": True, "assets": len(set(keys)), "frames": len(keys),
            "added": len(set(new_keys)), "dropped": len(dead), "path": str(p)}


def load(lib: Path):
    """(keys, vecs, hub) or None. Cached per process."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    p = index_path(Path(lib))
    if not p.exists():
        return None
    try:
        import numpy as np
        z = np.load(p, allow_pickle=False)
        _CACHE = ([str(x) for x in z["keys"]], z["vecs"],
                  z["hub"] if "hub" in z.files else None)
    except Exception as e:
        sys.stderr.write(f"note: picture index unreadable ({type(e).__name__})\n")
        return None
    return _CACHE


def search(lib: Path, term: str, n: int = 8,
           floor: float | None = None) -> list[tuple[str, float]]:
    """
    (asset filename, score) for the assets whose PICTURE matches `term`.

    `term` must be the caption-like query phrase, not the spoken sentence - see
    the module docstring for the measurement that settles it.
    """
    if not (term or "").strip():
        return []
    got = load(lib)
    if got is None:
        return []
    t = _text()
    if t is None:
        return []
    keys, vecs, hub = got
    floor = FLOOR if floor is None else floor
    try:
        import numpy as np
        q = np.asarray(list(t.embed([term]))[0], dtype="float32")
        q = q / (np.linalg.norm(q) or 1.0)
        sims = vecs @ q
    except Exception as e:
        sys.stderr.write(f"note: picture search failed ({type(e).__name__})\n")
        return []
    # HUB CORRECTION. In a high-dimensional embedding a few points sit near the
    # centre of the space and are therefore close to EVERYTHING - they are not
    # answers, they are the shape of the distribution. Measured in the TEXT
    # space over 135 real captions, a close-up of a "Need a Job" sign came top-5
    # for 15.6% of them and a stock photo of coins for 11.1%, while only 16.3%
    # of the library could be reached at all.
    #
    # The standard fix is to subtract each candidate's own average similarity,
    # so a frame that is close to everything has to be MUCH closer than usual to
    # this query before it wins. `hub` is that average, computed once at build
    # time against the rest of the index - offline, no queries needed - and
    # stored alongside the vectors.
    #
    # HUB_W IS SET BY MEASUREMENT, NOT BY TASTE, and it is allowed to be zero:
    # if the correction does not widen how much of the library is reachable, it
    # is doing nothing but adding a term nobody can read. See selftest's
    # check_picture_index and the SKILL.md note for what it was measured at.
    if hub is not None and HUB_W:
        sims = sims - HUB_W * hub
    # AN ASSET SCORES ITS BEST FRAME. Averaging would punish a clip that is on
    # subject for one second of four, which is exactly the clip multi-frame
    # indexing exists to reach.
    best: dict[str, float] = {}
    for k, s in zip(keys, sims):
        s = float(s)
        if s > best.get(k, -1.0):
            best[k] = s
    out = [(k, s) for k, s in best.items() if s >= floor]
    out.sort(key=lambda kv: -kv[1])
    return out[:n]
