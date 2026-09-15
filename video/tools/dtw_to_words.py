#!/usr/bin/env python3
"""Turn a whisper.cpp `--dtw <model> -ml 1 -oj` token dump into a Scribe-shaped word list.

    whisper-cli -m ggml-small.en.bin -f a.wav --dtw small.en -ml 1 -oj -of out
    python3 dtw_to_words.py out.json -o edit/transcripts/take.json

With -ml 1 each JSON "segment" is one token. A token with a leading space starts a
new word; one without (a sub-word piece, or punctuation) is glued onto the previous
word. Non-speech markers ([BLANK_AUDIO], ], >>, [_TT_..]) are dropped. Word start is
the first piece's offset, word end the last piece's.
"""
import argparse, json, re
from pathlib import Path

JUNK = re.compile(r"^\s*(\[[^\]]*\]?|\]|>>|\(\s*[^)]*\)?|\[_\w+_\]|\.{3})\s*$")

def convert(raw):
    toks = raw["transcription"] if isinstance(raw, dict) else raw
    words = []
    for t in toks:
        text = t["text"]
        if not text.strip() or JUNK.match(text):
            continue
        s, e = t["offsets"]["from"] / 1000, t["offsets"]["to"] / 1000
        new_word = text.startswith(" ") or not words
        piece = text.strip()
        if new_word or not re.match(r"^[A-Za-z0-9'\-.,!?;:%$]+$", piece):
            if not new_word and words and re.match(r"^[.,!?;:]+$", piece):
                words[-1]["text"] += piece; words[-1]["end"] = max(words[-1]["end"], e); continue
            words.append({"text": piece, "start": s, "end": e, "type": "word", "speaker_id": "S0"})
        else:
            words[-1]["text"] += piece
            words[-1]["end"] = max(words[-1]["end"], e)
    for w in words:
        w["start"], w["end"] = round(w["start"], 3), round(max(w["end"], w["start"] + 0.01), 3)
    return {"words": words}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dtw_json"); ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    out = convert(json.loads(Path(a.dtw_json).read_text()))
    Path(a.out).write_text(json.dumps(out, indent=None))
    print(f"{len(out['words'])} words -> {a.out}")
