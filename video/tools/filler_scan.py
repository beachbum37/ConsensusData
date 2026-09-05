#!/usr/bin/env python3
"""List cut candidates — filler words, repeated false starts, and silence gaps.

This reports candidates; it does NOT decide the cut. The editorial call stays
with whoever reads the output, because "um" inside a deliberate pause and "um"
mid-sentence are different edits. Feed the report into the strategy discussion,
then write the EDL.

    python3 filler_scan.py edit/transcripts/take01.json --audio raw.mp4
    python3 filler_scan.py transcript.json --min-gap 0.6 --json

Reads either transcript shape (flat Whisper array or Scribe {"words": [...]}).

Pass --audio whenever you have the media file. whisper.cpp quantizes word
boundaries — measured on a 23s clip its largest inter-word gap was 0.13s, so
real pauses simply do not appear as gaps in its timestamps and gap-based
silence detection finds nothing. With --audio the silences come from ffmpeg's
`silencedetect` on the waveform instead, which is what actually happened.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Single-token fillers. Deliberately conservative: "like", "so", "right" and
# "well" are NOT here — they are load-bearing far more often than not, and
# cutting them mangles meaning. Add them per-project if the speaker overuses one.
FILLERS = {
    "um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "ahh",
    "hmm", "hm", "mhm", "mm",
}


def load_words(path: Path):
    raw = json.loads(path.read_text())
    words = raw["words"] if isinstance(raw, dict) and "words" in raw else raw
    out = []
    for w in words:
        if w.get("type", "word") != "word":
            continue
        t, s, e = (w.get("text") or "").strip(), w.get("start"), w.get("end")
        if t and s is not None and e is not None:
            out.append({"text": t, "start": float(s), "end": float(e)})
    return out


def norm(t):
    return t.lower().strip(".,!?;:—-…\"'")


def detect_silence(media: Path, min_gap: float, noise_db: int):
    """Real silences, measured from the waveform rather than inferred from
    word timestamps. Returns [{start, end, duration}]."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(media),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_gap}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 and "silence" not in proc.stderr:
        raise SystemExit(f"ffmpeg failed on {media}:\n{proc.stderr[-500:]}")
    out, start = [], None
    for m in re.finditer(r"silence_(start|end): ([0-9.]+)", proc.stderr):
        kind, val = m.group(1), float(m.group(2))
        if kind == "start":
            start = val
        elif start is not None:
            out.append({"start": start, "end": val,
                        "duration": round(val - start, 3),
                        "after": "", "before": ""})
            start = None
    return out


def scan(words, min_gap):
    fillers, gaps, repeats = [], [], []

    for i, w in enumerate(words):
        if norm(w["text"]) in FILLERS:
            fillers.append({"start": w["start"], "end": w["end"], "text": w["text"]})
        # Immediate single-word repeat ("the the", "I I") — a classic false start.
        if i and norm(w["text"]) == norm(words[i - 1]["text"]) and len(norm(w["text"])) > 1:
            repeats.append({
                "start": words[i - 1]["start"], "end": w["end"],
                "text": f'{words[i-1]["text"]} {w["text"]}',
            })

    for a, b in zip(words, words[1:]):
        gap = b["start"] - a["end"]
        if gap >= min_gap:
            gaps.append({"start": a["end"], "end": b["start"], "duration": round(gap, 3),
                         "after": a["text"], "before": b["text"]})

    return {"fillers": fillers, "repeats": repeats, "silence_gaps": gaps}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--min-gap", type=float, default=0.4,
                    help="silence gap in seconds to report as a cut candidate (default 0.4). "
                         "Gaps under ~0.15s are mid-phrase and unsafe to cut.")
    ap.add_argument("--audio", help="media file — detect real silence from the waveform "
                                    "(strongly recommended; see module docstring)")
    ap.add_argument("--noise-db", type=int, default=-32,
                    help="silence threshold in dBFS for --audio (default -32)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = ap.parse_args()

    words = load_words(Path(args.transcript))
    if not words:
        raise SystemExit("No words in transcript.")
    res = scan(words, args.min_gap)

    if args.audio:
        res["silence_gaps"] = detect_silence(Path(args.audio), args.min_gap, args.noise_db)
        res["silence_source"] = "waveform"
    else:
        res["silence_source"] = "word-gaps"
        print("warning: no --audio given; silence is inferred from word gaps, which "
              "whisper.cpp under-reports. Pass --audio for real pauses.\n", file=sys.stderr)

    if args.json:
        print(json.dumps(res, indent=2))
        return

    span = words[-1]["end"] - words[0]["start"]
    filler_time = sum(f["end"] - f["start"] for f in res["fillers"])
    gap_time = sum(g["duration"] for g in res["silence_gaps"])

    print(f"{len(words)} words over {span:.1f}s\n")
    print(f"FILLERS      {len(res['fillers']):3d}  ({filler_time:.2f}s)")
    for f in res["fillers"]:
        print(f"    {f['start']:7.2f}-{f['end']:7.2f}  {f['text']}")
    print(f"\nFALSE STARTS {len(res['repeats']):3d}")
    for r in res["repeats"]:
        print(f"    {r['start']:7.2f}-{r['end']:7.2f}  {r['text']}")
    print(f"\nSILENCE ≥{args.min_gap}s  {len(res['silence_gaps']):3d}  ({gap_time:.2f}s)"
          f"   [from {res['silence_source']}]")
    for g in res["silence_gaps"]:
        ctx = (f"   …{g['after']} | {g['before']}…"
               if g.get("after") or g.get("before") else "")
        print(f"    {g['start']:7.2f}-{g['end']:7.2f}  {g['duration']:.2f}s{ctx}")

    recoverable = filler_time + gap_time
    print(f"\nUpper bound if every candidate were cut: {recoverable:.1f}s "
          f"of {span:.1f}s ({100*recoverable/span:.0f}%).")
    print("That is a ceiling, not a plan — cutting every pause reads as breathless.")


if __name__ == "__main__":
    main()
