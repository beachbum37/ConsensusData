#!/usr/bin/env python3
"""
Semantic re-rank for b-roll candidates. Local, no API, no torch.

WHY THIS EXISTS, and why the lexical ranking in broll.py could never have done
it. The keyword ranker is good and it works: for "gold bullion bars" it already
puts four gold clips above the junk. What it cannot do is notice that a result
matching the query PERFECTLY is about the wrong thing. Measured on the real
library, before this module:

    "boil"                              -> vibrant seafood boil steaming in pot
    "portfolio"                         -> woman holding blank frame
    "federal reserve"                   -> money and computer cooling fan
    "federal reserve building washington" -> stunning view of the us capitol

"Seafood boil" has total lexical overlap with "boil". No amount of token or
phrase scoring rejects it, because on the words it is a perfect hit. The thing
that rejects it is meaning, and meaning needs an embedding.

WHAT IT COMPARES. Not the search term - the SENTENCE the word was spoken in.
"boil" is meaningless on its own; "I just boil it down to its simplest
component... a gold price increasing again is a reflationary trade" is not, and
against that sentence a seafood pot scores 0.419 while gold sycees score 0.646.
The spread on that example was clean: every gold clip >= 0.568, every wrong one
<= 0.493.

HOW IT SORTS. Coarsely, on purpose. broll.py already returns hits in a tier
order that encodes the user's rule - what was approved before, then motion, then
stills - and a raw sort by similarity would throw that away and put a still
above a video for two hundredths of a point. So results are bucketed to one
decimal and the sort is STABLE: a real difference in meaning reorders, noise
does not, and inside a bucket the existing tier order survives untouched.

Degrades to a no-op if fastembed is not installed, so nothing here is a hard
dependency of the pipeline.
"""
from __future__ import annotations

import re
import sys

_MODEL = None
_TRIED = False

# bge-small-en-v1.5: 130MB, ONNX via fastembed, no torch. Similarities from this
# family sit in a compressed band (roughly 0.40-0.70 on this material), so the
# floor below is calibrated to that band and is NOT a general-purpose 0-1 score.
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Below this, the best hit for a term is not about the same subject as the
# sentence. Raised from 0.52 after testing on four real terms: at 0.52 the term
# "boil" kept "close up shot of egg in boiling water" at 0.528, which is not what
# a gold clip is about. Correct hits across those terms scored 0.568 to 0.686 and
# the best wrong one 0.528, so the line goes in that gap.
#
# It cannot fix everything and is not meant to. "portfolio" returns an artwork
# literally titled "Portfolio" at 0.655: right word, wrong sense, and no
# TEXT model can see that the picture is a painting. Two guards catch that case
# instead - NOT_A_PICTURE in broll.py already blocks the word, and the contact
# sheet means approval is always a look. Judging the frame rather than the
# caption needs an image model (CLIP/SigLIP on the thumbnail), which is the
# obvious next step and a much larger download.
FLOOR = 0.55

# The CLIP picture score at which a hit's PICTURE overrules its TITLE. See the
# rescue in rerank(). Set from the measured separation in visual.py's own probe:
# a correct retrieval ("people gambling in a casino" -> the casino clips, "a
# portrait of Donald Trump" -> the portraits) lands 0.27..0.30, while the
# incidental neighbours sit at 0.22..0.25. 0.26 is inside that gap. It is
# deliberately ABOVE visual.FLOOR, which is only a retrieval floor.
PICTURE_RESCUE = 0.26

# How much a picture that already SHIPPED for this exact term is worth, added to
# its score bucket. Small on purpose: it settles a near-tie and loses to a
# clearly better match on meaning. The measured table is in rerank(); 0.2 was
# the best of the values tried and the rescue is where most of the gain is.
SHIPPED_BONUS = 0.2


def _model():
    """Load once, or return None and say so once."""
    global _MODEL, _TRIED
    if _MODEL is not None or _TRIED:
        return _MODEL
    _TRIED = True
    try:
        from fastembed import TextEmbedding
        _MODEL = TextEmbedding(MODEL_NAME)
    except Exception as e:
        sys.stderr.write(
            f"note: semantic re-rank off ({type(e).__name__}). "
            f"Install with: python3 -m pip install --user fastembed\n")
        _MODEL = None
    return _MODEL


def scores(query: str, texts: list[str]) -> list[float] | None:
    """Cosine similarity of each text against the query, or None if unavailable."""
    m = _model()
    if m is None or not texts or not (query or "").strip():
        return None
    try:
        import numpy as np
        vecs = list(m.embed([query] + list(texts)))
    except Exception as e:
        sys.stderr.write(f"note: semantic re-rank failed ({type(e).__name__}).\n")
        return None
    import numpy as np
    q = vecs[0] / (np.linalg.norm(vecs[0]) or 1.0)
    out = []
    for v in vecs[1:]:
        v = v / (np.linalg.norm(v) or 1.0)
        out.append(float(q @ v))
    return out


def _bigrams(text: str) -> set[str]:
    # EVERY token, including the short ones. Filtering "in" and "of" out first
    # welds their neighbours together and invents phrases that were never in the
    # text: "a historic building in Washington" became the bigram
    # "building washington" and was rescued by a query about the Federal Reserve
    # Board Building in Washington. Adjacency has to mean adjacency.
    w = [x for x in re.split(r"[^a-z0-9]+", (text or "").lower()) if x]
    return {f"{a} {b}" for a, b in zip(w, w[1:]) if len(a) > 2 and len(b) > 2}


def _proper_bigrams(term: str) -> set[str]:
    """
    The two-word phrases in `term` that are PROPER NOUNS - both words capitalised.

    This is what separates the case phrase_rescue was built for from the case it
    broke. "US Federal Reserve Eccles Building" carries "Federal Reserve" and
    "Eccles Building"; "people hiking walking mountain trail" carries no proper
    noun at all.

    Sentence position is not a factor here because a search TERM is not a
    sentence - nothing in it is capitalised by grammar, so a capital is always a
    name.
    """
    w = [x for x in re.split(r"[^A-Za-z0-9]+", term or "") if x]
    return {f"{a} {b}".lower() for a, b in zip(w, w[1:])
            if len(a) > 2 and len(b) > 2 and a[:1].isupper() and b[:1].isupper()}


def phrase_rescue(term: str, title: str) -> bool:
    """
    Keep a hit whose title contains a two-word PHRASE from the query.

    The floor judges meaning, and meaning is the right judge - but it only knows
    what the embedding knows, and the embedding does not know that the Eccles
    Building IS the Federal Reserve. Measured: "Eccles Building" scores 0.327
    against a sentence about the Fed, and cleaning the Commons filename moved it
    to 0.348 - the noise was never the problem. The one correct answer in
    eighteen hits was ranked last and dropped, and the run said NOTHING ON TOPIC.

    A BIGRAM match is the safe way back in. It is a far stronger signal than a
    word: "US Federal Reserve Eccles Building" contains "federal reserve" and
    survives, while "stunning view of the us capitol building" and "charming fall
    day in olympia washington" match no phrase of that query and stay out. It
    cannot resurrect the failure this module was built for either - the term
    "boil" has no bigram at all, so a seafood pot has nothing to match.
    """
    # PROPER NOUNS ONLY, narrowed on 2026-08-26. The rescue was firing on any
    # shared bigram, which on a lowercase term is not a name - it is just two
    # ordinary words next to each other. Measured over the archive it overrode
    # the floor's whole-set "NOTHING ON TOPIC" verdict in 14 of the 18 entries
    # where the floor fired, on bigrams like "shopping cart" and "mountain
    # trail". That is not the Eccles Building problem, it is the floor being
    # switched off by a coincidence of adjacent words.
    #
    # The Eccles case still works, and it is the reason to narrow rather than
    # delete: "US Federal Reserve Eccles Building" contains the proper noun
    # "Federal Reserve" and a title naming the building survives at 0.327, where
    # a "stunning view of the us capitol building" matches no PROPER bigram of
    # that query and stays out.
    return bool(_proper_bigrams(term) & _bigrams(title))


def rerank(context: str, hits: list[dict], floor: float = FLOOR,
           term: str = "", passed: set | None = None,
           preferred: set | None = None
           ) -> tuple[list[dict], float | None]:
    """
    Re-order hits by what they are ABOUT, and drop the ones that are not.

    Returns (kept, best_score). best_score is None when the model is unavailable,
    which the caller should treat as "unchanged", not as "nothing matched".

    Each kept hit gains a "score" key so the listing and the contact sheet can
    show why something is where it is.
    """
    if not hits:
        return hits, None
    texts = [f"{h.get('title', '')}".strip() or "untitled" for h in hits]
    sc = scores(context, texts)
    if sc is None:
        return hits, None
    for h, s in zip(hits, sc):
        h["score"] = round(s, 3)
    best = max(sc)
    kept = []
    for h in hits:
        h["named"] = phrase_rescue(term, h.get("title", ""))
        # A PICTURE THAT MATCHES SURVIVES A TITLE THAT DOES NOT, and without
        # this the two halves of the search would fight each other. Everything
        # scored in this function is a TITLE - so an asset that visual.py found
        # precisely because its title uses different words from the caption is
        # exactly the asset this floor would throw away. That is the case the
        # picture index exists for ("manufacturing" reaching a clip titled
        # "workers on an assembly line"), so it would have shipped defeating
        # itself.
        #
        # Rescued, not promoted: it clears the floor and then takes its place in
        # the ordinary score buckets below, the same shape as `named`. The
        # threshold is well above visual.FLOOR (0.22, a retrieval floor) because
        # this is a stronger claim - not "worth showing the operator" but "the
        # picture is good enough to overrule its own caption".
        if h.get("picture_score", 0.0) >= PICTURE_RESCUE:
            h["named"] = True
        h["shipped_before"] = (
            (h.get("url") or "") in (preferred or set())
            or (h.get("page") or "") in (preferred or set()))
        if h["score"] >= floor or h["named"] or h["shipped_before"]:
            kept.append(h)
    # Bucketed, STABLE: meaning reorders, noise does not. See the module docstring.
    #
    # A hit that literally NAMES what was asked for sorts first, ahead of the
    # score buckets. The video-first tier is right almost always and wrong for a
    # named institution: asked for the "US Federal Reserve Eccles Building", the
    # library answered with a tracking shot of twenty dollar bills at the same
    # bucketed score, and video-before-stills put the generic motion above the
    # actual photograph of the actual building. When the caption says the words
    # you asked for, that is not a tie.
    # DEMOTED, not dropped: a picture the operator scrolled past for this term
    # before. It was on the sheet and it was not taken, which is real evidence
    # about the default - but it is not evidence that the picture is wrong, and a
    # shot that suits one sentence can suit another. So it sorts last and stays
    # visible, and the operator can still take it by asking for its index.
    # ONE BUCKET, not to the bottom. Sorting a passed-over picture last was
    # DELETION dressed as demotion: propose persists only the top few hits as the
    # shortlist, the contact sheet renders the shortlist, and fetch indexes into
    # it - so a picture pushed to the end of a twenty-hit list fell off all three
    # and could never be chosen again for that term. Docking it 0.1 keeps the
    # claim honest: it loses to anything comparable, and it still wins if it is
    # clearly the best thing available.
    passed = passed or set()
    # WHAT ALREADY WORKED, FOR THESE WORDS. `preferred` is the set of pictures
    # that have reached a DELIVERED clip under this exact term - a human chose
    # it, looked at it on the contact sheet, and it survived to the render. That
    # is the strongest evidence available about which of two on-topic pictures
    # to use, and until now nothing collected it, let alone read it.
    #
    # IT RESCUES, AND THAT IS WHERE ALL OF ITS VALUE IS. The first version made
    # it a last-position tie-break, on the reasoning that the floor judges the
    # SENTENCE and a picture that suited one sentence is not thereby about this
    # one. Measured leave-one-out over 180 approved inserts - building the ledger
    # from every clip EXCEPT the one being tested, so a picture never votes for
    # itself - that version changed nothing at all: 91/180 either way. A tie-break
    # in last position only fires when meaning and naming are both already tied,
    # which on real candidate sets is almost never.
    #
    #     placement                       rank 1   top 3
    #     none (baseline)                  30.6%   37.2%
    #     tie-break, last in the key       30.6%   37.2%   <- did nothing
    #     +0.1 score bonus                 31.7%   38.3%
    #     +0.2 score bonus                 33.3%   39.4%
    #     rescue over the floor            38.9%   48.3%
    #     bonus + rescue                   42.2%   51.1%   <- ships
    #
    # So the floor is exactly what it had to get past. A picture that a human
    # chose for THESE WORDS and that survived to a delivered render is evidence
    # about this term that a sentence embedding cannot see, and the floor was
    # discarding it. It is still not a free pass: the bonus is small enough that
    # a clearly better match on meaning still wins.
    #
    # And it is TERM-CONDITIONAL by construction (see broll.shipped_for). A bare
    # popularity count would be the hub problem again: the most-used asset would
    # start winning queries it has nothing to do with.
    preferred = preferred or set()
    for h in kept:
        h["passed_over"] = (h.get("page") or "") in passed or (h.get("url") or "") in passed
    # A passed-over hit also LOSES ITS NAMED PRIVILEGE. The two rules collided:
    # phrase_rescue puts a caption that names the query above everything, so a
    # picture the operator had explicitly scrolled past still came back first -
    # the demotion was computed and then out-voted one key to its left. Being
    # named is a reason to survive the floor, not a reason to outrank the
    # operator. Dropped into the ordinary tier it still keeps its score and stays
    # on the sheet; it simply stops being the default.
    # NAMED IS A TIEBREAK INSIDE THE BUCKET, NOT A KEY ABOVE IT. It used to sort
    # first, so a hit that repeated the query's words while scoring BELOW the
    # floor outranked the only hit that was actually on topic. That is the
    # `building` failure exactly: asked about "everyone is building some version
    # of that", a sub-floor coding shot that echoed the term beat the one
    # supra-floor answer in the set.
    #
    # This is also what the module already claims for itself - "meaning reorders,
    # noise does not". Inside a bucket `named` can only reorder near-equals,
    # which is the only place a lexical signal is safe, and it still resolves the
    # case it was introduced for: the Eccles Building photograph and a tracking
    # shot of dollar bills landed in the SAME bucket, and the caption naming the
    # building is the right tie-break between them.
    kept.sort(key=lambda h: (
        -(round(h["score"], 1)
          + (SHIPPED_BONUS if h.get("shipped_before") and not h["passed_over"] else 0.0)
          - (0.1 if h["passed_over"] else 0)),
        not (h.get("named") and not h["passed_over"])))
    return kept, best


if __name__ == "__main__":
    ctx = sys.argv[1] if len(sys.argv) > 1 else "a gold price increasing is reflationary"
    for s, t in sorted(zip(scores(ctx, sys.argv[2:]) or [], sys.argv[2:]), reverse=True):
        print(f"  {s:.3f}  {t}")
