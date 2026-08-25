"""Loading and filtering for the question corpus.

Standard library only - no install step, no virtualenv. Every other script in
this repo goes through here so there is exactly one definition of what a
question is and where the data lives.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
QUESTION_DIR = DATA_DIR / "questions"
ARC_DIR = DATA_DIR / "arcs"

# The flavors of every arc beat, ordered by how much they presuppose about the
# guest's current situation. Least presuming last.
ANCHORING = ("current", "experience", "observed", "general")

# How wide a question opens. Narrow is the default and the whole corpus assumes
# it. Wide questions are for pre-interview emails, panels and trailers - they
# are deliberately kept out of briefs, where they would hollow out a running
# order, and every one of them carries a narrow_to follow-up that lands it.
APERTURE = ("narrow", "wide")

REQUIRED_FIELDS = ("id", "text", "theme", "arc", "depth", "industries")
SLOT_RE = re.compile(r"\{(\w+)\}")


@dataclass
class Corpus:
    questions: list[dict]
    taxonomy: dict
    industries: dict
    packs: dict[str, str] = field(default_factory=dict)
    arcs: dict[str, dict] = field(default_factory=dict)
    series: dict = field(default_factory=dict)

    @property
    def spine(self) -> list[dict]:
        """Themes every episode is required to touch."""
        return self.series.get("spine", [])

    @property
    def profiles(self) -> dict[str, dict]:
        return {p["slug"]: p for p in self.industries["profiles"]}

    def profile(self, slug: str) -> dict | None:
        return self.profiles.get(slug)

    def by_id(self, qid: str) -> dict | None:
        return next((q for q in self.questions if q["id"] == qid), None)


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load() -> Corpus:
    taxonomy = _read_json(DATA_DIR / "taxonomy.json")
    industries = _read_json(DATA_DIR / "industries.json")

    questions: list[dict] = []
    packs: dict[str, str] = {}
    for path in sorted(QUESTION_DIR.rglob("*.json")):
        blob = _read_json(path)
        pack = blob.get("pack", path.stem)
        packs[pack] = blob.get("description", "")
        for question in blob.get("questions", []):
            question["pack"] = pack
            question["source_file"] = str(path.relative_to(DATA_DIR.parent))
            questions.append(question)

    arcs = {}
    if ARC_DIR.is_dir():
        for path in sorted(ARC_DIR.glob("*.json")):
            blob = _read_json(path)
            arcs[blob["arc"]] = blob

    series_path = DATA_DIR / "series.json"
    series = _read_json(series_path) if series_path.exists() else {}

    return Corpus(questions=questions, taxonomy=taxonomy, industries=industries,
                  packs=packs, arcs=arcs, series=series)


def slots_in(text: str) -> set[str]:
    """Placeholder names in a question, e.g. {work_unit}."""
    return set(SLOT_RE.findall(text))


# An article immediately before a slot has to agree with whatever fills it:
# "a {work_unit}" becomes "an outage" but "a case".
ARTICLE_SLOT_RE = re.compile(r"\b(a|A)\s+\{(\w+)\}")

# Article choice follows sound, not spelling: "a user", "an hour".
_CONSONANT_SOUNDED_VOWEL = re.compile(r"^(?:u(?:n[ei]|se|ti|ni)|eu|one\b)", re.I)
_VOWEL_SOUNDED_CONSONANT = re.compile(r"^(?:hour|honest|honou?r|heir)", re.I)


def _article_for(word: str) -> str:
    if _VOWEL_SOUNDED_CONSONANT.match(word):
        return "an"
    if _CONSONANT_SOUNDED_VOWEL.match(word):
        return "a"
    return "an" if word[0].lower() in "aeiou" else "a"


def fill_slots(text: str, profile: dict | None) -> str:
    """Substitute industry vocabulary into a slotted question.

    Unknown slots are left alone rather than blanked - a visible {phrase} is a
    prompt to the host to supply the guest's own words, which is the intent for
    slots that no profile defines.
    """
    if not profile:
        return text
    # {industry} is derived rather than declared - it is just the profile's
    # label, and big-picture questions ask for the field by name.
    vocab = dict(profile.get("vocabulary", {}))
    vocab.setdefault("industry", profile.get("label", ""))

    def with_article(m: re.Match) -> str:
        article, slot = m.group(1), m.group(2)
        if slot not in vocab:
            return m.group(0)
        word = vocab[slot]
        if word.split()[0].lower() in ("a", "an", "the"):
            # Value already carries its own determiner - drop ours.
            return word
        article = _article_for(word)
        if m.group(1).isupper():
            article = article.capitalize()
        return f"{article} {word}"

    text = ARTICLE_SLOT_RE.sub(with_article, text)
    return SLOT_RE.sub(lambda m: vocab.get(m.group(1), m.group(0)), text)


def text_for(question: dict, setting: str | None = None) -> str:
    """The wording of a question for the setting in play.

    Some questions are right for both settings but land badly in one of them -
    "when you start work" assumes somewhere to arrive at. `setting_text` holds
    the reworded version, and everything that renders a question goes through
    here so the variant cannot be forgotten in one code path.
    """
    if setting:
        variant = (question.get("setting_text") or {}).get(setting)
        if variant:
            return variant
    return question["text"]


def matches(question: dict, *, industry=None, role=None, setting=None, theme=None,
            arc=None, depth=None, tag=None, search=None, aperture=None,
            universal=True, general=True) -> bool:
    """Apply the filters that `query.py` exposes. None means 'no constraint'.

    Industry and role are the two scoping axes and behave the same way: a
    filter admits questions scoped to that value, plus the unscoped ones
    (`universal` industries, or no `roles` at all) unless told not to.
    """
    if industry:
        applies = industry in question["industries"]
        if universal:
            applies = applies or "universal" in question["industries"]
        if not applies:
            return False
    if role:
        roles = question.get("roles", [])
        applies = role in roles
        if general:
            applies = applies or not roles
        if not applies:
            return False
    # Setting narrows rather than adding a source: choosing one excludes
    # questions written for the other, and keeps everything unscoped.
    if setting:
        settings = question.get("settings", [])
        if settings and setting not in settings:
            return False
    if aperture and question.get("aperture", "narrow") != aperture:
        return False
    if theme and question["theme"] != theme:
        return False
    if arc and question["arc"] != arc:
        return False
    if depth and question["depth"] != depth:
        return False
    if tag and tag not in question.get("tags", []):
        return False
    if search:
        needle = search.lower()
        haystack = " ".join([
            question["text"],
            question.get("lands_because", ""),
            " ".join(question.get("followups", [])),
            " ".join(question.get("tags", [])),
        ]).lower()
        if needle not in haystack:
            return False
    return True


def filter_questions(corpus: Corpus, **kwargs) -> list[dict]:
    return [q for q in corpus.questions if matches(q, **kwargs)]


# How many questions of each arc stage a brief aims for, in running order.
BRIEF_SHAPE = (("opener", 2), ("warmup", 2), ("core", 8), ("deep", 5), ("closer", 3))


def build_brief(corpus: Corpus, industry: str | None, role: str | None = None,
                seed: int = 0, setting: str | None = None) -> list[dict]:
    """Assemble a running order for one guest.

    Roughly half of each stage is written for this guest specifically - that is
    what stops the interview sounding generic. When both scoping axes are in
    play they get separate budgets, because the role packs are far larger than
    any industry pack and would otherwise crowd it out entirely. Ties favour
    the industry, which is the scarcer material.
    """
    rng = random.Random(seed)

    def in_setting(q: dict) -> bool:
        """Setting filters every pool rather than forming one of its own - it
        narrows which version of a question fits, it is not a third source."""
        scoped = q.get("settings", [])
        return not setting or not scoped or setting in scoped

    def pool(arc: str, kind: str) -> list[dict]:
        if kind == "industry":
            qs = [q for q in corpus.questions
                  if q["arc"] == arc and industry and industry in q["industries"]
                  and q.get("aperture", "narrow") == "narrow" and in_setting(q)]
        elif kind == "role":
            qs = [q for q in corpus.questions
                  if q["arc"] == arc and role and role in q.get("roles", [])
                  and q.get("aperture", "narrow") == "narrow" and in_setting(q)]
        else:
            # The unscoped core. Questions aimed at some other role are
            # excluded - an AI-leader question does not belong in a
            # manager's brief.
            qs = [q for q in corpus.questions if q["arc"] == arc
                  and "universal" in q["industries"] and not q.get("roles")
                  and q.get("aperture", "narrow") == "narrow" and in_setting(q)]
        rng.shuffle(qs)
        return qs

    selected: list[dict] = []
    for arc, want in BRIEF_SHAPE:
        budget = max(1, want // 2)
        industry_budget = budget - budget // 2 if role else budget

        picks = pool(arc, "industry")[:industry_budget]
        for q in pool(arc, "role")[: budget - industry_budget]:
            if q not in picks:
                picks.append(q)

        # Top up from the core, then from whatever specific material is left
        # over - a stage with no industry questions should not run short.
        for q in pool(arc, "core") + pool(arc, "role") + pool(arc, "industry"):
            if len(picks) >= want:
                break
            if q not in picks:
                picks.append(q)
        selected.extend(picks)
    return selected
