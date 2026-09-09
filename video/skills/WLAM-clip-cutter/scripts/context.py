#!/usr/bin/env python3
"""
WHO THE PASSAGE IS ABOUT, when the clip never says the name.

THE CLIP THAT FORCED THIS. On 2026-08-30 a clip was cut from the 08.26 show in
which the host walks through Bill Gates' essay on AI and jobs. It opens on the
words "HE'S saying that AI will hit both white and blue-collar jobs". Every
sentence in it is about Gates. The name "Bill Gates" is spoken at 158.0s - about
half a minute BEFORE the clip starts - and never again inside it.

So the pipeline had no way to know. Every anchor it can see is a common noun,
the portrait tier is never reached, and a clip whose entire subject is one of
the most recognisable faces in technology ships without ever showing him. The
owner watched it and said so: "he was talking about Bill Gates ... we need to
have another agent or a skill or a Python machine that gets very good at
context."

WHAT THIS IS NOT. It is not a language model and it does not resolve pronouns
grammatically. It answers one narrow question that the transcript can actually
support: WHICH NAMED PERSON WAS THE SHOW TALKING ABOUT when this span began, and
is the span still talking about them? That is a recency-and-density question
over words we already have, and it needs no model and no network.

HOW IT DECIDES, and every part of this is defensive.

  - It only ever returns a name that is IN `PEOPLE`, so a subject can always be
    turned into a portrait with a licence the library already knows how to get.
  - It looks BACK from the clip's start, never forward: the setup precedes the
    payoff, and a name that arrives later belongs to a different passage.
  - It weights by RECENCY, because a show moves on. A mention thirty seconds
    before the clip is worth far more than one three minutes before.
  - It requires the span to CONTINUE the subject - at least one third-person
    pronoun, or the name itself, inside the clip - or there is no carry-over to
    make and it returns nothing. This is what stops it stamping a face on a clip
    that has changed the subject.
  - It refuses when two people are close together. If the passage has been
    comparing Gates and Musk, "he" is genuinely ambiguous and a portrait would
    be a coin flip. Silence is correct there.
"""
from __future__ import annotations

import re

# How far back the setup may be. Chosen from the case that forced this module:
# the name is spoken 33s before the clip begins, and the segment it opens runs
# several minutes. Three minutes covers a normal segment on this show and stops
# well short of the previous one.
LOOK_BACK = 180.0

# The pronoun has to be third-person singular or plural, and it has to be a
# SUBJECT. "him" and "her" appear in object position where the topic is usually
# someone else ("I asked him about Gates"), so they are not evidence of the same
# strength and are left out.
# NOT "they" OR "their". On this material a company is almost always "they" -
# "Nike still sells shoes... THEY'RE still fingers into sports" - so admitting
# them made a clip about a shoe company resolve to a person. Measured: the
# 08.26 Nike clip carries two of them and no human subject at all, and the first
# version duly returned "Kevin Warsh", who is named in a different segment
# entirely. A false face is far worse than no face.
PRONOUNS = {"he", "she", "his", "her", "hes", "shes"}

# A mention this much more recent than the runner-up wins outright. Below it the
# two are treated as contending and nothing is returned - see the docstring.
DOMINANCE = 2.0


def _norm(w: str) -> str:
    """Lowercase with apostrophes REMOVED, not stripped from the ends.

    "He's" strips to "he's", which is not "hes" - so the commonest third-person
    pronoun in spoken English matched nothing, and the clip that forced this
    module (which opens on the word "He's") counted one pronoun instead of six.
    """
    return w.lower().replace("'", "").replace("\u2019", "")


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z']+", text or "") if w]


def _mentions(cues, lo: float, hi: float, people) -> list[tuple[str, float]]:
    """
    (canonical name, time) for every PEOPLE hit spoken in [lo, hi).

    Bigrams first: "bill gates" must not be read as "bill" and then "gates",
    because `gates` is an ordinary noun with its own picture (an iron gate) and
    `bill` is a banknote. The vocabulary already carries that trap and this is
    the same one at passage scale.
    """
    out: list[tuple[str, float]] = []
    # ONCE A FULL NAME IS ESTABLISHED, THE BARE SURNAME IS THE SAME PERSON, and
    # without this the count is hopelessly wrong. `gates` is deliberately NOT a
    # PEOPLE key - it is an ordinary noun with its own picture, an iron gate - so
    # only the bigram "bill gates" was ever counted. On the clip that forced this
    # module the show says "Bill Gates" once and then "Gates" five more times,
    # and the tally read 1. It lost to the journalist who wrote the piece, named
    # once in the same sentence.
    #
    # A surname only counts AFTER its full name has been heard in this window,
    # so an ordinary word never becomes a person on its own.
    surnames: dict[str, str] = {}
    for a0, _a1, txt in cues:
        if a0 < lo or a0 >= hi:
            continue
        ws = [_norm(w) for w in _words(txt)]
        i = 0
        while i < len(ws):
            pair = f"{ws[i]} {ws[i+1]}" if i + 1 < len(ws) else None
            if pair and pair in people:
                who = people[pair][0]
                out.append((who, a0, _possessive(_words(txt)[i + 1])))
                surnames[ws[i + 1]] = who
                i += 2
                continue
            if ws[i] in people:
                out.append((people[ws[i]][0], a0, _possessive(_words(txt)[i])))
            elif ws[i] in surnames:
                out.append((surnames[ws[i]], a0, _possessive(_words(txt)[i])))
            i += 1
    return out


def _possessive(raw: str) -> bool:
    """
    Was the name written possessively - "Bill Gates' warning", "Musk's plan"?

    THE CHEAPEST HONEST SIGNAL OF WHO A PASSAGE IS ABOUT. Two people are often
    named in one sentence and only one of them owns the subject: "Lindsay Ellis
    has now put this out about the three takeaways from BILL GATES' almost 6,000
    word warning on AI" names the reporter and the subject, and a plain count
    scores them equally. The apostrophe says which is which.

    It generalises past this clip - "Powell's comments", "Musk's plan", "the
    Fed's decision" - and it costs one character test.
    """
    return raw.endswith("'") or raw.lower().endswith("'s") or raw.endswith("\u2019s")


def carried_subject(cues, start: float, end: float, people,
                    look_back: float = LOOK_BACK):
    """
    The person this span is about but does not name, or None.

    Returns (name, evidence) where evidence is a short human-readable string for
    the proposal listing - this decision must be legible, because it is the one
    place the tool asserts something the transcript does not literally say.
    """
    if not cues or not people:
        return None

    inside = {n for n, _t, _p in _mentions(cues, start, end, people)}

    # PRONOUNS ARE COUNTED OVER CUES THAT OVERLAP THE SPAN, not over cues that
    # begin inside it. Cues on this show run ten seconds and a clip starts
    # mid-cue by design, so the opening sentence usually lives in a cue that
    # started before the span - and the case that forced this module opens on
    # the word "He's". Counting by cue start scored that clip 1 and dropped it.
    pron = 0
    for a0, a1, txt in cues:
        if a1 <= start or a0 >= end:
            continue
        pron += sum(1 for w in _words(txt) if _norm(w) in PRONOUNS)
    if pron < 2:
        return None

    before = _mentions(cues, max(0.0, start - look_back), start, people)
    if not before:
        return None

    # RECENCY-WEIGHTED. A mention decays with how long ago it was; several
    # mentions add up. The weight is 1/(1 + age/30), so a name said 30s before
    # the clip is worth half one said as it starts, and one said three minutes
    # back is worth a seventh.
    score: dict[str, float] = {}
    last: dict[str, float] = {}
    for name, t, poss in before:
        age = max(0.0, start - t)
        # A POSSESSIVE MENTION IS WORTH DOUBLE. See _possessive: it is what
        # separates the person a passage is ABOUT from the person who reported
        # it, when both are named in one breath.
        score[name] = score.get(name, 0.0) + (2.0 if poss else 1.0) / (1.0 + age / 30.0)
        last[name] = max(last.get(name, 0.0), t)
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    top, top_s = ranked[0]
    # THE SPAN NAMING SOMEONE ELSE ONCE IS NOT THE SAME AS CHANGING THE SUBJECT.
    # The first version returned nothing the moment any name was spoken inside
    # the span, and that is wrong on the very clip this was written for: it is
    # about Gates from first word to last and mentions Musk exactly once, in the
    # final sentence, as an aside. Suppressing the carry-over there left the
    # clip with no face at all.
    #
    # So only the SUBJECT being named inside suppresses it - at that point there
    # is nothing to carry, because the ordinary anchor path can see him.
    if top in inside:
        return None
    if len(ranked) > 1 and top_s < ranked[1][1] * DOMINANCE:
        # Two people are contending. "He" is genuinely ambiguous and a portrait
        # would be a guess - see the docstring.
        return None
    n = sum(1 for nm, _t, _p in before if nm == top)
    ago = start - last[top]
    return top, (f"named {n}x before this clip, last {ago:.0f}s before it starts; "
                 f"{pron} third-person pronoun(s) inside it and no other name")
