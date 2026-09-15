#!/usr/bin/env python3
"""Cut narration to a slide deck: audio segments keyed to slides, with a discard log.

The slides are the spine. Each kept segment is bounded by anchor phrases
looked up in the word-level transcript, so every cut lands on a word boundary
(Hard Rule 6) with padding (Rule 7) and 30ms fades at each seam (Rule 3).
Segments not mapped to a slide are logged, never silently dropped.

Plan format (JSON):
  {"gap": 0.30, "slide_gap": 0.60,
   "slides_dir": "...", "sources": {"name": "file.mp3", ...},
   "segments": [
     {"src": "Note", "slide": 2, "from": "It's the ultimate hedge",
      "to": "as our guide", "note": "why this maps"},
     ...],
   "discards": [
     {"src": "Note", "from": "You're doubling down", "to": null,
      "reason": "..."}]}

`from`/`to` are phrases; `to: null` means end of file, `from: null` start.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

def norm(t): return re.sub(r"[^a-z0-9']", "", t.lower())

def load_words(p):
    d = json.loads(Path(p).read_text())
    w = d["words"] if isinstance(d, dict) else d
    return [x for x in w if x.get("text","").strip()]

def find(words, phrase, start_at=0):
    toks = [norm(t) for t in phrase.split()]
    for i in range(start_at, len(words) - len(toks) + 1):
        if all(norm(words[i+k]["text"]) == toks[k] for k in range(len(toks))):
            return i, i + len(toks) - 1
    raise SystemExit(f"anchor not found: {phrase!r}")

def span(words, frm, to, cursor):
    """Return (start_s, end_s, i0, i1) for a segment bounded by phrases."""
    if frm is None: i0 = cursor
    else: i0, _ = find(words, frm, cursor)
    if to is None: i1 = len(words) - 1
    else: _, i1 = find(words, to, i0)
    return words[i0]["start"], words[i1]["end"], i0, i1

def run(cmd): subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--pad-in", type=float, default=0.08); ap.add_argument("--pad-out", type=float, default=0.14)
    ap.add_argument("--work", default="edit/slidecut")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text()); W = Path(a.work); W.mkdir(parents=True, exist_ok=True)
    words = {n: load_words(f"edit/transcripts/{n}.json") for n in plan["sources"]}
    dur = {n: float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f],capture_output=True,text=True).stdout) for n,f in plan["sources"].items()}

    # ---- resolve segments ------------------------------------------------
    segs, cursor = [], {n: 0 for n in words}
    for s in plan["segments"]:
        w = words[s["src"]]; st, en, i0, i1 = span(w, s.get("from"), s.get("to"), cursor[s["src"]])
        # pad outward but never into a neighbouring kept word
        st = max(0.0, st - a.pad_in, w[i0-1]["end"] if i0 > 0 else 0.0)
        en = min(dur[s["src"]], en + a.pad_out, w[i1+1]["start"] if i1+1 < len(w) else dur[s["src"]])
        cursor[s["src"]] = i1 + 1
        segs.append({**s, "start": round(st,3), "end": round(en,3), "text": " ".join(x["text"] for x in w[i0:i1+1])})

    # ---- resolve discards (the record the brief asks for) ----------------
    disc = []
    for d in plan["discards"]:
        w = words[d["src"]]; st, en, i0, i1 = span(w, d.get("from"), d.get("to"), 0)
        disc.append({**d, "start": round(st,3), "end": round(en,3), "seconds": round(en-st,2),
                     "text": " ".join(x["text"] for x in w[i0:i1+1])})

    # ---- audio: per-segment extract with fades, gaps between --------------
    parts, timeline, t = [], [], 0.0
    for k, s in enumerate(segs):
        L = s["end"] - s["start"]; p = W / f"a{k:02d}.wav"
        run(["ffmpeg","-y","-nostdin","-ss",str(s["start"]),"-t",f"{L:.3f}","-i",plan["sources"][s["src"]],
             "-af",f"afade=t=in:st=0:d=0.03,afade=t=out:st={L-0.03:.3f}:d=0.03","-ar","48000","-ac","1",str(p)])
        parts.append(p)
        gap = 0.0
        if k+1 < len(segs):
            gap = plan["slide_gap"] if segs[k+1]["slide"] != s["slide"] else plan["gap"]
            g = W / f"g{k:02d}.wav"; run(["ffmpeg","-y","-nostdin","-f","lavfi","-i",f"anullsrc=r=48000:cl=mono","-t",f"{gap:.3f}",str(g)]); parts.append(g)
        timeline.append({"slide": s["slide"], "t_in": round(t,3), "t_out": round(t+L,3), "src": s["src"], "src_in": s["start"], "src_out": s["end"]})
        t += L + gap
    lst = W / "audio.txt"; lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    audio = W / "audio.wav"; run(["ffmpeg","-y","-nostdin","-f","concat","-safe","0","-i",str(lst),"-c","copy",str(audio)])

    # ---- video: hold each slide for its run of segments --------------------
    runs = []
    for e in timeline:
        if runs and runs[-1]["slide"] == e["slide"]: runs[-1]["t_out"] = e["t_out"]
        else: runs.append({"slide": e["slide"], "t_in": e["t_in"], "t_out": e["t_out"]})
    total = t
    for i, r in enumerate(runs):   # each run holds until the next run starts (covers the gap)
        r["hold"] = (runs[i+1]["t_in"] if i+1 < len(runs) else total) - r["t_in"]
    vparts = []
    for i, r in enumerate(runs):
        p = W / f"v{i:02d}.mp4"; img = Path(plan["slides_dir"]) / f"slide{r['slide']:02d}.png"
        run(["ffmpeg","-y","-nostdin","-loop","1","-framerate","30","-i",str(img),"-t",f"{r['hold']:.3f}",
             "-vf","scale=1920:1080,format=yuv420p","-c:v","libx264","-preset","fast","-crf","18","-r","30",str(p)])
        vparts.append(p)
    vl = W / "video.txt"; vl.write_text("".join(f"file '{p.resolve()}'\n" for p in vparts))
    run(["ffmpeg","-y","-nostdin","-f","concat","-safe","0","-i",str(vl),"-i",str(audio),
         "-c:v","copy","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",a.out])

    Path(W/"timeline.json").write_text(json.dumps({"segments": timeline, "slide_runs": runs, "total": round(total,3)}, indent=2))
    # ---- discard log -------------------------------------------------------
    md = ["# Discarded audio — scifi", "", "Segments removed because they do not map to a slide, repeat a point already kept,",
          "or are interjections / fourth-wall moments rather than content. Source timestamps.", ""]
    for d in disc:
        md += [f"## {d['src']}  {d['start']:.2f}–{d['end']:.2f}s  ({d['seconds']:.1f}s)", "", f"**Why:** {d['reason']}", "", f"> {d['text']}", ""]
    md += ["", f"Total discarded: {sum(d['seconds'] for d in disc):.1f}s of {sum(dur.values()):.1f}s source. Kept: {total:.1f}s."]
    Path("edit/discards.md").write_text("\n".join(md))

    print(f"{'#':>2} {'slide':>5} {'out':>14}  {'src':<18} {'src range':>14}  text")
    for k, e in enumerate(timeline):
        print(f"{k:>2} {e['slide']:>5} {e['t_in']:6.2f}-{e['t_out']:6.2f}  {e['src']:<18} {e['src_in']:6.2f}-{e['src_out']:6.2f}  {segs[k]['text'][:58]}…")
    print(f"\nslides used: {[r['slide'] for r in runs]}   total {total:.1f}s   discarded {sum(d['seconds'] for d in disc):.1f}s → edit/discards.md")

if __name__ == "__main__": main()
