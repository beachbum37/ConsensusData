"""Loading and filtering for the question corpus.

Standard library only - no install step, no virtualenv. Every other script in
this repo goes through here so there is exactly one definition of what a
question is and where the data lives.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
QUESTION_DIR = DATA_DIR / "questions"

REQUIRED_FIELDS = ("id", "text", "theme", "arc", "depth", "industries")
SLOT_RE = re.compile(r"\{(\w+)\}")


@dataclass
class Corpus:
    questions: list[dict]
    taxonomy: dict
    industries: dict
    packs: dict[str, str] = field(default_factory=dict)

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

    return Corpus(questions=questions, taxonomy=taxonomy, industries=industries, packs=packs)


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
    vocab = profile.get("vocabulary", {})

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


def matches(question: dict, *, industry=None, role=None, theme=None, arc=None,
            depth=None, tag=None, search=None, universal=True, general=True) -> bool:
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
