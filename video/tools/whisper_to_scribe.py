#!/usr/bin/env python3
"""Adapt a local-Whisper transcript into the shape video-use's render.py expects.

`npx hyperframes transcribe --json` writes a flat word array:

    [{"text": "Today,", "start": 0.13, "end": 0.25}, ...]

video-use's render.py (and its subtitle builder) reads the ElevenLabs Scribe
shape instead:

    {"words": [{"text": "Today,", "start": 0.13, "end": 0.25, "type": "word"}, ...]}

Without this adapter the free local-Whisper route silently produces no
subtitles — `_words_in_range` filters on `type == "word"` and a flat list has
no `.get("words")` at all, so every lookup comes back empty.

    python3 whisper_to_scribe.py transcript.json -o edit/transcripts/take01.json

Already-Scribe-shaped input passes through unchanged, so this is safe to run
over either route's output.
"""
import argparse
import json
import sys
from pathlib import Path


def adapt(raw):
    """Return Scribe-shaped {"words": [...]} from either input shape."""
    if isinstance(raw, dict) and isinstance(raw.get("words"), list):
        words = raw["words"]          # already Scribe-shaped
        passthrough = True
    elif isinstance(raw, list):
        words = raw                   # hyperframes flat array
        passthrough = False
    else:
        raise SystemExit(
            "Unrecognized transcript shape: expected a flat word list or "
            '{"words": [...]}. Got ' + type(raw).__name__
        )

    out = []
    for i, w in enumerate(words):
        text = (w.get("text") or "").strip()
        start, end = w.get("start"), w.get("end")
        if not text or start is None or end is None:
            continue
        out.append({
            "text": text,
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            # render.py skips anything whose type isn't "word". Scribe also
            # emits "spacing" and "audio_event" entries; Whisper emits neither,
            # so preserve an existing type and default the rest to "word".
            "type": w.get("type", "word"),
            "speaker_id": w.get("speaker_id", "S0"),
        })
    if not out:
        raise SystemExit("No usable words found in transcript.")
    return {"words": out}, passthrough


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="transcript.json from `hyperframes transcribe --json`")
    ap.add_argument("-o", "--output", required=True, help="where to write the Scribe-shaped JSON")
    args = ap.parse_args()

    raw = json.loads(Path(args.input).read_text())
    doc, passthrough = adapt(raw)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))

    w = doc["words"]
    print(f"{'passed through' if passthrough else 'adapted'} {len(w)} words "
          f"({w[0]['start']:.2f}s → {w[-1]['end']:.2f}s) → {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
