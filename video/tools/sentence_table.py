#!/usr/bin/env python3
"""Sentence table for a source: every sentence with its measured level, dead air and a banter label.

    python3 sentence_table.py edit/transcripts/take2.json take2.mp3 --src take2 -o edit/sentences.json [--append]

Splits the word list on terminal punctuation, then measures each sentence from the
waveform (20ms RMS windows): mean/max dB, the longest run below -40 dB ("dead"), and
labels short reactive glue (Exactly. Right. Yeah. That makes sense.) as "banter".
build_slide_cut.py reads this to explain every auto-discarded range.
"""
import argparse, json, re, subprocess
from pathlib import Path
import numpy as np

GLUE = re.compile(r"^[-\s]*(exactly|right|yeah|yes|no|okay|ok|wow|totally|absolutely|precisely|definitely( not)?|"
                  r"i see|ah,? okay|ah|oh|hmm|it really is|it certainly does|that makes (total )?sense|"
                  r"that('s| is) (a )?(really )?(good|great|fair|brilliant) (point|way to frame it|comparison|combination)|"
                  r"let'?s hear it|like a hobby|like what|which is|what do you mean.*|"
                  r"the worst|hindsight is 20 ?/ ?20|the email joke|a macro view|so\?)[.!?,]*\s*$", re.I)

def load_wave(f):
    raw = subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-i",f,"-vn","-ac","1","-ar","16000","-f","f32le","-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)

def stats(x, a, b, sr=16000, win=0.02, thr=-40.0):
    seg = x[int(a*sr):int(b*sr)]
    n = max(1, len(seg) // int(win*sr)); seg = seg[:n*int(win*sr)].reshape(n, -1)
    rms = np.sqrt((seg**2).mean(axis=1)) + 1e-9; db = 20*np.log10(rms)
    dead, run = 0, 0
    for v in db:
        run = run + 1 if v < thr else 0; dead = max(dead, run)
    return round(float(db.mean()),1), round(float(db.max()),1), round(dead*win, 2)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript"); ap.add_argument("audio"); ap.add_argument("--src", required=True)
    ap.add_argument("-o", "--out", required=True); ap.add_argument("--append", action="store_true")
    a = ap.parse_args()
    words = json.loads(Path(a.transcript).read_text())["words"]
    x = load_wave(a.audio)
    out, buf = [], []
    for w in words:
        if w["text"] == "-" and not buf: continue
        buf.append(w)
        if re.search(r"[.!?]$", w["text"]):
            st, en = buf[0]["start"], buf[-1]["end"]
            text = " ".join(t["text"] for t in buf).strip("- ").strip()
            mean, mx, dead = stats(x, st, en)
            nwords = len([t for t in buf if t["text"] != "-"])
            kind = "banter" if (GLUE.match(text) or (nwords <= 3 and en - st < 2.5)) else \
                   "quiet" if mean < -45 else "content"
            out.append({"src": a.src, "start": round(st,2), "end": round(en,2), "dur": round(en-st,2),
                        "mean": mean, "max": mx, "dead": dead, "kind": kind, "text": text})
            buf = []
    if a.append and Path(a.out).exists():
        prev = [s for s in json.loads(Path(a.out).read_text()) if s["src"] != a.src]; out = prev + out
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"{len([s for s in out if s['src']==a.src])} sentences for {a.src}; "
          f"{sum(1 for s in out if s['src']==a.src and s['kind']=='banter')} banter, "
          f"{sum(1 for s in out if s['src']==a.src and s['kind']=='quiet')} quiet")

if __name__ == "__main__": main()
