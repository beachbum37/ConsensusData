#!/usr/bin/env python3
"""Cut narration to a slide deck: audio segments keyed to slides, with a discard log.

The slides are the spine. Each kept segment is bounded by anchor phrases
looked up in the word-level transcript, so every cut lands on a word boundary
(Hard Rule 6) with padding (Rule 7) and 30ms fades at each seam (Rule 3).
Segments not mapped to a slide are logged, never silently dropped.

Plan format (JSON):
  {"gap": 0.30, "slide_gap": 0.60,
   "slides_dir": "...", "slide_files": {"os03": "/path/os03.png"},   # optional: named slides from another deck
  "sources": {"name": "file.mp3", ...},
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

def slide_image(plan, sid):
    """Slide ids are ints -> <slides_dir>/slideNN.png, or any key of plan["slide_files"] -> that path."""
    files = plan.get("slide_files", {})
    if str(sid) in files: return Path(files[str(sid)])
    return Path(plan["slides_dir"]) / f"slide{int(sid):02d}.png"

def voiced_bounds(f, a, b, thr=-40, mind=0.25):
    """Trim [a,b] to the first and last voiced audio inside it. Word timestamps
    from DTW can smear a short sentence across a long gap; the waveform cannot."""
    r = subprocess.run(["ffmpeg","-nostdin","-ss",f"{a:.3f}","-t",f"{max(0.05,b-a):.3f}","-i",f,
                        "-af",f"silencedetect=noise={thr}dB:d={mind}","-f","null","-"],capture_output=True,text=True).stderr
    sil = [(a+float(x), a+float(y)) for x,y in re.findall(r"silence_start: ([\d.]+)\n.*?silence_end: ([\d.]+)", r, re.S)]
    lead = next((e for s_,e in sil if s_ <= a+0.06), None)
    tail = next((s_ for s_,e in reversed(sil) if e >= b-0.06), None)
    na = lead if lead and lead < b else a
    nb = tail if tail and tail > na else b
    longest = max((e-s_ for s_,e in sil if s_>=na and e<=nb), default=0.0)
    return na, nb, longest

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
        # Anchors resolve from the start of the file every time: slide order is
        # the spine, so plan order need not follow source order.
        w = words[s["src"]]; st, en, i0, i1 = span(w, s.get("from"), s.get("to"), 0)
        # pad outward but never into a neighbouring kept word
        st = max(0.0, st - a.pad_in, w[i0-1]["end"] if i0 > 0 else 0.0)
        en = min(dur[s["src"]], en + a.pad_out, w[i1+1]["start"] if i1+1 < len(w) else dur[s["src"]])
        # snap to the waveform, then re-apply a small pad inside the voiced region
        va, vb, dead = voiced_bounds(plan["sources"][s["src"]], st, en)
        st2 = max(st, va - 0.05); en2 = min(en, vb + 0.10)
        if dead >= 1.5:
            print(f"  ⚠ {s['src']} {st2:.2f}-{en2:.2f} has {dead:.1f}s of dead air inside — check the anchors", file=sys.stderr)
        segs.append({**s, "start": round(st2,3), "end": round(en2,3), "dead": round(dead,2),
                     "text": " ".join(x["text"] for x in w[i0:i1+1])})

    # ---- resolve discards (the record the brief asks for) ----------------
    disc = []
    if plan.get("discards") == "auto":
        # Everything not kept, per source, labelled from the sentence table when
        # one exists. This is the complete record — nothing is dropped unlogged.
        sent = json.loads(Path("edit/sentences.json").read_text()) if Path("edit/sentences.json").exists() else []
        for n, f in plan["sources"].items():
            kept = sorted((x["start"], x["end"]) for x in segs if x["src"] == n)
            t, gaps = 0.0, []
            for a_, b_ in kept:
                if a_ > t + 0.3: gaps.append((t, a_))
                t = max(t, b_)
            if dur[n] > t + 0.3: gaps.append((t, dur[n]))
            for a_, b_ in gaps:
                ss = [x for x in sent if x["src"] == n and x["end"] > a_ + 0.05 and x["start"] < b_ - 0.05]
                kinds = {x["kind"] for x in ss}; quiet = any(x["mean"] < -45 for x in ss)
                if not ss: why = "no speech (blank audio)"
                elif kinds == {"banter"}: why = "host banter / reactive glue"
                elif quiet: why = "too quiet to use (below -45 dB)"
                else: why = "no slide this serves, a repeat of a point already kept, or an interjection"
                # a human-written note for this range wins over the category label
                for note in plan.get("discard_notes", []):
                    if note["src"] == n and note["from_s"] < b_ and note["to_s"] > a_ and \
                       min(b_, note["to_s"]) - max(a_, note["from_s"]) >= 0.5 * (b_ - a_):
                        why = note["reason"]
                disc.append({"src": n, "start": round(a_,3), "end": round(b_,3), "seconds": round(b_-a_,2),
                             "reason": why, "text": " ".join(x["text"] for x in ss) or "—"})
        plan["discards"] = []
    for d in plan["discards"]:
        w = words[d["src"]]; st, en, i0, i1 = span(w, d.get("from"), d.get("to"), 0)
        disc.append({**d, "start": round(st,3), "end": round(en,3), "seconds": round(en-st,2),
                     "text": " ".join(x["text"] for x in w[i0:i1+1])})

    # ---- merge segments that are contiguous in the source ------------------
    # Two kept segments with nothing discarded between them are one continuous
    # piece of speech; cutting them apart and inserting a pause would put an
    # artificial gap and a double fade mid-sentence. They become one span, and
    # a slide change inside it is a cue on the timeline, not an audio edit.
    spans = []
    for s in segs:
        # adjacency means the new segment begins where the span ends — not merely
        # somewhere before it, which a reordered plan makes common
        # lower tolerance must exceed pad_in, or a padded segment that starts a hair
        # before the previous one ends is treated as a separate take
        if spans and spans[-1]["src"] == s["src"] and spans[-1]["end"] - 0.20 <= s["start"] <= spans[-1]["end"] + 0.25:
            sp = spans[-1]; sp["end"] = max(sp["end"], s["end"])
            sp["cues"].append({"slide": s["slide"], "at": s["start"]}); sp["text"] += " " + s["text"]
        else:
            spans.append({"src": s["src"], "start": s["start"], "end": s["end"], "gap_before": s.get("gap_before"),
                          "cues": [{"slide": s["slide"], "at": s["start"]}], "text": s["text"]})

    # ---- audio: per-span extract with fades, gaps between spans only ------
    parts, timeline, t = [], [], 0.0
    for k, sp in enumerate(spans):
        L = sp["end"] - sp["start"]; p = W / f"a{k:02d}.wav"
        run(["ffmpeg","-y","-nostdin","-ss",str(sp["start"]),"-t",f"{L:.3f}","-i",plan["sources"][sp["src"]],
             "-af",f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.03,afade=t=out:st={L-0.03:.3f}:d=0.03",
             "-ar","48000","-ac","1",str(p)])
        parts.append(p)
        for c in sp["cues"]:   # one timeline entry per slide cue inside the span
            c_in = t + (c["at"] - sp["start"])
            timeline.append({"slide": c["slide"], "t_in": round(c_in,3), "src": sp["src"], "src_in": round(c["at"],3)})
        # close every cue's t_out at the next cue or the span end
        ends = [t + (c["at"] - sp["start"]) for c in sp["cues"][1:]] + [t + L]
        for e_, en_ in zip(timeline[-len(sp["cues"]):], ends): e_["t_out"] = round(en_,3); e_["src_out"] = round(sp["start"] + (en_ - t),3)
        gap = 0.0
        if k+1 < len(spans):
            # a segment may set "gap_before" (seconds) — used for a word-level trim inside a
            # sentence ("but [the research suggests] that's…"), where the default pause would read as a stumble
            gap = plan["slide_gap"] if spans[k+1]["cues"][0]["slide"] != sp["cues"][-1]["slide"] else plan["gap"]
            if spans[k+1].get("gap_before") is not None: gap = float(spans[k+1]["gap_before"])
            g = W / f"g{k:02d}.wav"; run(["ffmpeg","-y","-nostdin","-f","lavfi","-i",f"anullsrc=r=48000:cl=mono","-t",f"{gap:.3f}",str(g)]); parts.append(g)
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
    if any(r["hold"] <= 0 for r in runs) or any(b["t_in"] < a["t_in"] for a, b in zip(timeline, timeline[1:])):
        sys.exit("timeline is not monotonic — a span merged segments that are not adjacent")
    vparts = []
    for i, r in enumerate(runs):
        p = W / f"v{i:02d}.mp4"; img = slide_image(plan, r["slide"])
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
    print(f"\n{len(spans)} audio span(s) from {len(segs)} segments; slides used: {[r['slide'] for r in runs]}   total {total:.1f}s   discarded {sum(d['seconds'] for d in disc):.1f}s → edit/discards.md")

if __name__ == "__main__": main()
