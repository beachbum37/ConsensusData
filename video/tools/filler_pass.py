#!/usr/bin/env python3
"""Locate filler words by re-transcribing with a disfluency-seeded prompt.

Whisper is trained to emit clean prose, so by default it deletes "um" and "uh"
before you ever see them — on one 90s sample of real narration the default pass
found 0 fillers and this prompted pass found 10. Seeding the decoder with
disfluencies stops the normalization.

    python3 filler_pass.py talk.mp4 --context edit/transcripts/talk.json

Prompting costs accuracy: in that same sample it turned "kick off our build
today" into "our bill today". So run TWO passes and use each for one job —
the clean pass for captions and anything on screen, this one ONLY for filler
timestamps. Never caption from this output.

Prints a review list; it does not cut. Some hits are real "uh"s inside a phrase
where cutting hurts the rhythm, so a person picks from the list.
Add --json to emit cut ranges for an EDL builder.
"""
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path

FILLERS = {"um","umm","uh","uhh","uhm","erm","er","ah","ahh","hmm","hm","mm","mhm"}
PROMPT = ("Um, uh, so, like, you know, I mean. Uh, um, er, ah. "
          "Well, uh, basically, um.")
WHISPER = Path.home()/".cache/hyperframes/whisper/whisper.cpp/build/bin/whisper-cli"
MODELS  = Path.home()/".cache/hyperframes/whisper/models"


def transcribe(media, model, prompt):
    if not WHISPER.exists():
        sys.exit(f"whisper-cli not found at {WHISPER}\n"
                 "Run `npx hyperframes transcribe <file>` once — it builds it.")
    mpath = MODELS/f"ggml-{model}.bin"
    if not mpath.exists():
        sys.exit(f"model not found: {mpath}\nFetch it with `npx hyperframes transcribe "
                 f"<file> --model {model}` once.")
    with tempfile.TemporaryDirectory() as td:
        wav, out = Path(td)/"a.wav", Path(td)/"o"
        subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-i",str(media),
                        "-vn","-ac","1","-ar","16000",str(wav),"-y"], check=True)
        # -ml 1 forces one token per segment, which is how word timings come out.
        subprocess.run([str(WHISPER),"-m",str(mpath),"-f",str(wav),
                        "-ml","1","-oj","-of",str(out),"-np","--prompt",prompt],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return json.loads((out.with_suffix(".json")).read_text())["transcription"]


def norm(t):
    return re.sub(r"[^a-z]", "", t.lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media")
    ap.add_argument("--context", help="clean transcript (Scribe-shaped) for surrounding words")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--pad", type=float, default=0.04,
                    help="widen each cut range by this on both sides (default 0.04)")
    ap.add_argument("--json", action="store_true", help="emit cut ranges instead of a report")
    args = ap.parse_args()

    segs = transcribe(args.media, args.model, PROMPT)
    hits = []
    for s in segs:
        if norm(s["text"]) in FILLERS:
            o = s["offsets"]
            hits.append({"start": round(o["from"]/1000, 3),
                         "end": round(o["to"]/1000, 3),
                         "text": s["text"].strip()})

    ctx = []
    if args.context and Path(args.context).exists():
        ctx = json.loads(Path(args.context).read_text())["words"]

    if args.json:
        print(json.dumps([{"start": round(h["start"]-args.pad, 3),
                           "end": round(h["end"]+args.pad, 3),
                           "text": h["text"]} for h in hits], indent=2))
        return

    total = sum(h["end"]-h["start"] for h in hits)
    print(f"{Path(args.media).name}: {len(hits)} filler(s), {total:.2f}s total\n")
    for i, h in enumerate(hits, 1):
        before = [w["text"] for w in ctx if w["end"] <= h["start"]+0.30][-7:]
        after  = [w["text"] for w in ctx if w["start"] >= h["end"]-0.30][:7]
        print(f"  #{i:<3} {h['start']:7.2f}-{h['end']:7.2f}  {h['end']-h['start']:4.2f}s  {h['text']!r}")
        if before or after:
            print(f"        …{' '.join(before)}  [{h['text']}]  {' '.join(after)}…")
    if hits:
        print(f"\nCut them with --json, or pick from the list — an \"uh\" mid-phrase "
              f"is sometimes load-bearing.")


if __name__ == "__main__":
    main()
