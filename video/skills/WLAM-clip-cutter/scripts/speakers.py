#!/usr/bin/env python3
"""
Speaker labels from the STREAM'S OWN transcript, aligned onto the master.

    python3 speakers.py <transcript>            # inspect: who talks when
    python3 speakers.py <transcript> --map      # what names map to what tiles

WHY THIS BEATS EVERYTHING ELSE HERE. Inferring who is talking from a mixed
audio track and two faces measured 43% against transcript ground truth on real
QM footage - at or below chance for two people. The streaming platform already
knows the answer: it has each participant on a separate feed, so its transcript
says WHO said each line. Reading that is not a better guess, it is the fact.

THE TIMESTAMPS IN IT ARE NOT TRUSTED, AND MUST NOT BE. The downloaded video and
the platform's transcript do not share a clock - the stream has pre-roll, the
download starts somewhere else, and a few seconds of offset puts every cut on
the wrong face while looking perfectly plausible. So only the WORDS and the
NAMES are taken from it, and the timing comes from `cues.json`, which whisper
produced from the master itself and is therefore correct by construction.

The two word streams come from different ASRs and will not agree exactly
(~85-95% typically). difflib finds the matching blocks, and each labelled turn
is placed at the master's time for the words it matched. A turn that matches
nothing is dropped rather than guessed at.

SUPPORTED SHAPES - it sniffs, so you can hand it whatever the platform gives:
  * WebVTT with <v Speaker Name> voice tags       (StreamYard, Restream)
  * WebVTT / SRT with "Speaker: text" cue bodies  (Riverside, Descript)
  * Zoom's .txt and .vtt cloud-recording transcripts
  * plain text, "Speaker Name: text" per line, timestamps optional
  * JSON: [{"speaker": ..., "start": ..., "end": ..., "text": ...}]
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("WLAM_WORK") or HERE)

# A turn shorter than this is an interjection the platform heard but that is not
# worth cutting to - "Yeah.", "Right." - and cutting on it produces a flicker.
MIN_LABEL_TURN = 1.2
# How much of a labelled turn's words must be found in the master before its
# placement is believed.
MIN_MATCH = 0.34

WORD = re.compile(r"[a-z0-9']+")
TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})|(\d{1,2}):(\d{2})[.,](\d{1,3})")
VTT_V = re.compile(r"<v\s+([^>]+?)\s*>(.*?)(?:</v>|$)", re.I | re.S)
# "Steven E. Orr:" / "STEVEN ORR:" / "Speaker 1:" - a name is short and has no
# sentence punctuation inside it, which is what separates it from a clause that
# happens to contain a colon.
NAME_LINE = re.compile(r"^\s*([A-Z][^:\n]{1,44}?)\s*:\s*(.*)$")


def norm(text: str) -> list[str]:
    return WORD.findall(text.lower())


def _secs(m: re.Match) -> float:
    if m.group(1) is not None:
        h, mi, s, ms = m.group(1, 2, 3, 4)
    else:
        h, mi, s, ms = "0", m.group(5), m.group(6), m.group(7)
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


# ------------------------------------------------------------------ parsing --
def parse(path: Path) -> list[dict]:
    """[{speaker, start, end, text}] - start/end are the PLATFORM's, unused."""
    raw = path.read_text(errors="replace")
    if path.suffix.lower() == ".json" or raw.lstrip().startswith(("[", "{")):
        turns = _parse_json(raw)
        if turns:
            return turns
    if VTT_V.search(raw):
        return _parse_vtt_voice(raw)
    if raw.lstrip().upper().startswith("WEBVTT") or "-->" in raw:
        return _parse_cue_blocks(raw)
    return _parse_plain(raw)


def _parse_json(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if isinstance(data, dict):
        for k in ("segments", "turns", "results", "transcript", "utterances"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            return []
    out = []
    for d in data:
        if not isinstance(d, dict):
            continue
        who = d.get("speaker") or d.get("speaker_label") or d.get("name")
        txt = d.get("text") or d.get("transcript") or d.get("content") or ""
        if who is None or not str(txt).strip():
            continue
        out.append({"speaker": str(who).strip(), "text": str(txt).strip(),
                    "start": float(d.get("start", d.get("start_time", 0)) or 0),
                    "end": float(d.get("end", d.get("end_time", 0)) or 0)})
    return out


def _blocks(raw: str) -> list[tuple[float, float, str]]:
    out = []
    for blk in re.split(r"\n\s*\n", raw):
        if "-->" not in blk:
            continue
        lines = [x for x in blk.splitlines() if x.strip()]
        i = next((k for k, x in enumerate(lines) if "-->" in x), None)
        if i is None:
            continue
        ts = TS.findall(lines[i])
        stamps = [_secs(m) for m in TS.finditer(lines[i])]
        a = stamps[0] if stamps else 0.0
        b = stamps[1] if len(stamps) > 1 else a
        body = " ".join(lines[i + 1:]).strip()
        if body:
            out.append((a, b, body))
    return out


def _parse_vtt_voice(raw: str) -> list[dict]:
    out = []
    for a, b, body in _blocks(raw):
        for who, txt in VTT_V.findall(body):
            t = re.sub(r"<[^>]+>", "", txt).strip()
            if t:
                out.append({"speaker": who.strip(), "start": a, "end": b, "text": t})
    return out


def _parse_cue_blocks(raw: str) -> list[dict]:
    out, last = [], None
    for a, b, body in _blocks(raw):
        body = re.sub(r"<[^>]+>", "", body).strip()
        m = NAME_LINE.match(body)
        if m and not _looks_like_sentence(m.group(1)):
            last = m.group(1).strip()
            body = m.group(2).strip()
        if body and last:
            out.append({"speaker": last, "start": a, "end": b, "text": body})
    return out


def _parse_plain(raw: str) -> list[dict]:
    out, last, buf = [], None, []
    for line in raw.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        stamps = [_secs(m) for m in TS.finditer(line)]
        line = TS.sub("", line).strip(" \t-–—")
        m = NAME_LINE.match(line)
        if m and not _looks_like_sentence(m.group(1)):
            if last and buf:
                out.append({"speaker": last, "start": 0.0, "end": 0.0,
                            "text": " ".join(buf)})
            last, buf = m.group(1).strip(), ([m.group(2)] if m.group(2) else [])
            if stamps and out:
                out[-1]["end"] = stamps[0]
        elif line:
            buf.append(line)
    if last and buf:
        out.append({"speaker": last, "start": 0.0, "end": 0.0, "text": " ".join(buf)})
    return out


def _looks_like_sentence(s: str) -> bool:
    """
    Tell a name from a clause that happens to end in a colon.

    A PERIOD IS NOT THE SIGNAL. This tested `any(c in s for c in ".?!,;")`, so
    every name carrying an initial or a title was thrown away - and the host of
    this very show is "Steven E. Orr". Measured: 'Steven E. Orr', 'Sen. Warren'
    and 'Dr. Bell' were all classed as sentences and dropped, which on a
    "Name: text" transcript means those speakers are silently lost or their
    lines get attributed to whoever spoke last.

    What actually separates the two is SHAPE: a name is short, carries no
    clause punctuation, and is mostly capitalised. A sentence is long, or
    contains a comma or a question mark, or is mostly lower case.
    """
    t = s.strip()
    w = t.split()
    if not w or len(w) > 6:
        return True
    if any(c in t for c in "?!;,"):
        return True
    caps = sum(1 for x in w if x[:1].isupper())
    return caps < max(1, len(w) - 1)


# ---------------------------------------------------------------- alignment --
def cues() -> list[tuple[float, float, str]]:
    p = WORK / "cues.json"
    if not p.exists():
        raise SystemExit("no cues.json - run analyze.py first")
    return [(float(a), float(b), str(t)) for a, b, t in json.loads(p.read_text())]


def master_words() -> tuple[list[str], list[float]]:
    """Every word in the master, with a time, spread across its cue."""
    words, times = [], []
    for a, b, txt in cues():
        w = norm(txt)
        if not w:
            continue
        step = (b - a) / len(w)
        for i, x in enumerate(w):
            words.append(x)
            times.append(a + i * step)
    return words, times


def align(turns: list[dict]) -> list[dict]:
    """
    Retime labelled turns onto the master by matching WORDS, not clocks.

    Returns [{speaker, start, end, matched}] in master seconds. A turn whose
    words cannot be found is dropped - a labelled turn placed by guesswork is
    the exact failure this module exists to remove.
    """
    mw, mt = master_words()
    if not mw:
        return []
    tw, owner = [], []
    for i, t in enumerate(turns):
        for w in norm(t["text"]):
            tw.append(w)
            owner.append(i)
    if not tw:
        return []

    sm = difflib.SequenceMatcher(a=tw, b=mw, autojunk=False)
    # For each labelled word that matched, where it landed in the master.
    at: dict[int, float] = {}
    for i, j, n in sm.get_matching_blocks():
        for k in range(n):
            at[i + k] = mt[j + k]

    spans: dict[int, list[float]] = {}
    for idx, t_i in enumerate(owner):
        if idx in at:
            spans.setdefault(t_i, []).append(at[idx])

    out = []
    for i, t in enumerate(turns):
        hits = spans.get(i)
        total = sum(1 for x in owner if x == i)
        if not hits or not total or len(hits) / total < MIN_MATCH:
            continue
        out.append({"speaker": t["speaker"], "start": min(hits), "end": max(hits),
                    "matched": len(hits) / total})

    out.sort(key=lambda d: d["start"])
    # Overlaps are an artefact of spreading words evenly inside a cue; hand the
    # boundary to the midpoint rather than letting two turns claim one moment.
    for a, b in zip(out, out[1:]):
        if a["end"] > b["start"]:
            mid = (a["end"] + b["start"]) / 2
            a["end"] = b["start"] = mid
    return [d for d in out if d["end"] - d["start"] >= MIN_LABEL_TURN]


# -------------------------------------------------------------- the timeline --
def _configured() -> Path | None:
    try:
        cfg = json.loads((WORK / "project.json").read_text())
    except (OSError, ValueError):
        return None
    p = cfg.get("speaker_transcript")
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else (WORK / q)


def name_map(labels: list[str], tiles: list[str]) -> dict[str, str]:
    """
    Platform names -> tile names. "Stephen Flanagan" -> "flanagan".

    project.json's "speaker_names" overrides it outright; otherwise a tile name
    is matched as a whole word inside the label, longest tile first so "steve"
    cannot claim "Steven Flanagan" ahead of "flanagan".
    """
    try:
        cfg = json.loads((WORK / "project.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    explicit = {str(k): str(v) for k, v in (cfg.get("speaker_names") or {}).items()}
    out = {}
    for lab in labels:
        if lab in explicit:
            out[lab] = explicit[lab]
            continue
        low = lab.lower()
        hit = next((t for t in sorted(tiles, key=len, reverse=True)
                    if re.search(rf"\b{re.escape(t.lower())}", low)), None)
        if hit:
            out[lab] = hit
    return out


def timeline(start: float, end: float, tiles: list[str],
             path: Path | None = None) -> list[dict]:
    """Turn schedule over [start, end] from the platform transcript, or []."""
    path = path or _configured()
    if not path or not Path(path).exists():
        return []
    turns = align(parse(Path(path)))
    if not turns:
        return []
    mapping = name_map(sorted({t["speaker"] for t in turns}), tiles)
    if len(set(mapping.values())) < 2:
        sys.stderr.write(
            f"speakers: could not map the transcript's names {sorted(set(t['speaker'] for t in turns))} "
            f"onto the tiles {tiles}.\n"
            f'         Add "speaker_names": {{"<name in transcript>": "<tile>"}} '
            f"to project.json.\n")
        return []

    out, unmapped = [], set()
    for t in turns:
        who = mapping.get(t["speaker"])
        if not who:
            # A LABELLED SPEAKER WITH NO TILE IS NOT NOTHING. Dropping them
            # silently hands their seconds to whoever spoke before, via the gap
            # closure below, at full confidence - so a third participant, or a
            # name the mapping missed, becomes invisible airtime credited to the
            # wrong face. Say it.
            unmapped.add(t["speaker"])
            continue
        a, b = max(start, t["start"]), min(end, t["end"])
        if b - a <= 0:
            continue
        out.append({"who": who, "start": round(a, 2), "end": round(b, 2),
                    "source": "transcript", "degraded": False,
                    "aligned": round(b - a, 3), "confidence": 1.0})
    if unmapped:
        sys.stderr.write(
            f"speakers: {len(unmapped)} labelled speaker(s) map to no tile and "
            f"their time is being given to whoever spoke before them: "
            f"{sorted(unmapped)}.\n"
            f'         Add them to "speaker_names" in project.json, or use '
            f"mode 'head'.\n")
    if not out:
        return []
    # CLOSE THE GAPS FIRST, THEN MERGE. The other order leaves a run of turns
    # that are all the same person separated by the pauses between their own
    # sentences - a schedule of ten "cuts" where six are cuts to the man already
    # on screen. Silence belongs to whoever spoke into it.
    out[0]["start"], out[-1]["end"] = round(start, 2), round(end, 2)
    for a, b in zip(out, out[1:]):
        if b["start"] > a["end"]:
            a["end"] = b["start"]
    merged = [out[0]]
    for t in out[1:]:
        if t["who"] == merged[-1]["who"]:
            merged[-1]["end"] = t["end"]
            merged[-1]["aligned"] = round(merged[-1].get("aligned", 0.0)
                                          + t.get("aligned", 0.0), 3)
        else:
            merged.append(t)

    # CONFIDENCE IS THE SHARE THAT WAS ACTUALLY ALIGNED. Every turn used to
    # report 1.0 including the seconds invented by closing the gaps above, and
    # coverage() measured the schedule AFTER that closure - so it was
    # structurally incapable of returning anything but ~100%, whatever the
    # transcript matched. A turn that is mostly gap-fill now says so, and the
    # follow gate in render() reads the same number it does for the picture
    # route.
    for t in merged:
        span = t["end"] - t["start"]
        t["confidence"] = (round(min(1.0, t.get("aligned", 0.0) / span), 2)
                           if span > 1e-6 else 0.0)
    return merged


def coverage(start: float, end: float, sched: list[dict]) -> float:
    """
    How much of the span the transcript actually MATCHED, not how much the
    schedule covers.

    This summed the turn spans - which are gap-closed to cover the whole clip by
    construction - so it returned ~1.0 for every input including a transcript
    that aligned almost nothing. Sum the aligned time instead.
    """
    if end <= start:
        return 0.0
    aligned = sum(t.get("aligned", t["end"] - t["start"]) for t in sched)
    return min(1.0, aligned / (end - start))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--map", action="store_true", help="just show the name mapping")
    a = ap.parse_args()

    p = Path(a.transcript)
    turns = parse(p)
    if not turns:
        raise SystemExit(
            f"\n{p.name}: no speaker labels found.\n\n"
            f"This file has to say WHO said each line - '<v Name>' voice tags, "
            f"or 'Name: text'.\nA transcript with no names in it cannot answer "
            f"who is on screen, and YouTube's\nauto-captions do not carry them. "
            f"Download the one your streaming platform makes.\n")

    names = sorted({t["speaker"] for t in turns})
    print(f"\n{p.name}\n  {len(turns)} labelled turn(s), {len(names)} speaker(s): "
          f"{', '.join(names)}")

    try:
        cfg = json.loads((WORK / "project.json").read_text())
        tiles = list((cfg.get("follow_tiles") or cfg.get("tiles") or {}))
    except (OSError, ValueError):
        tiles = []
    if tiles:
        m = name_map(names, tiles)
        print(f"  tiles: {tiles}")
        for n in names:
            print(f"     {n!r:28s} -> {m.get(n) or 'UNMAPPED - add speaker_names'}")
    if a.map:
        return

    placed = align(turns)
    print(f"\n  {len(placed)} of {len(turns)} placed on the master by word match "
          f"(the platform's own timestamps are ignored)")
    if placed:
        span = placed[-1]["end"] - placed[0]["start"]
        print(f"  covering {placed[0]['start']:.1f}s -> {placed[-1]['end']:.1f}s "
              f"({span / 60:.1f} min)\n")
        for t in placed[:24]:
            print(f"    {t['start']:8.2f} -> {t['end']:8.2f}  {t['speaker']:24s} "
                  f"{t['matched'] * 100:3.0f}% of its words matched")
        if len(placed) > 24:
            print(f"    ... {len(placed) - 24} more")
    print()


if __name__ == "__main__":
    main()
