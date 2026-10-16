#!/usr/bin/env python3
"""Join the Ireland segments into one cut.

    python3 build_ireland_cut.py --order B1 A B2 -o edit/ireland-cut.mp4

Each source segment is loudness-normalised as a whole (so a trim inside it does
not change level across the join), then sliced into the kept pieces, then the
pieces are concatenated. A segment that is followed by another gets a short
held-frame "breath" so the chapters land instead of colliding.

Trims are expressed in SOURCE seconds and are cut at waveform troughs, not at
transcript word boundaries — DTW timings drift tens of ms and a cut on a word
edge clips the consonant.
"""
import argparse, json, subprocess, sys
from pathlib import Path

# Removed spans, per source segment. Keep the reason with the numbers.
TRIMS = {
    "A": [(33.920, 35.020, "'from our source material' — attribution, trimmed mid-sentence; "
                           "leaves 'But I absolutely love this analogy, because it hits the nail right on the head.'")],
    "B1": [],
    "B2": [],
}
# Source defects where the picture drops out but the narration keeps going.
# Rather than cut (which would clip the line), hold a still from `hold_from`
# over the dead span. Audio is untouched, so duration and sync never move.
PATCHES = {
    "B1": [(65.5, 70.5, 70.60, "slide transition renders as a blank white frame for 5.0s while "
                               "'Information as trapped luxury' is spoken; hold the incoming "
                               "'Information as Luxury' slide across it")],
}
BREATH = 0.30   # held last frame + silence between segments
LUFS = -16

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.exit(f"ffmpeg failed:\n{' '.join(cmd)}\n{r.stderr[-2000:]}")

def dur(f):
    return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                                 "-of","csv=p=0",f],capture_output=True,text=True).stdout)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order", nargs="+", required=True, help="segment names in output order, e.g. B1 A B2")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--work", default="edit/build")
    a = ap.parse_args()
    W = Path(a.work); W.mkdir(parents=True, exist_ok=True)

    srcs = {n: f"ireland{n}.mp4" for n in a.order}
    for n, f in srcs.items():
        if not Path(f).exists(): sys.exit(f"missing {f}")

    # 1. patch picture dropouts, then normalise each whole segment so a
    #    mid-segment trim never shifts level across the join
    norm, patched = {}, []
    for n, f in srcs.items():
        src = f
        for pi, (ps, pe, hold, why) in enumerate(PATCHES.get(n, [])):
            still = W / f"hold{n}{pi}.png"
            run(["ffmpeg","-y","-nostdin","-loglevel","error","-ss",f"{hold:.3f}","-i",f,
                 "-frames:v","1",str(still)])
            out = W / f"patched{n}{pi}.mp4"
            run(["ffmpeg","-y","-nostdin","-loglevel","error","-i",src,"-i",str(still),
                 "-filter_complex",
                 f"[1:v]scale=1280:720,setsar=1[s];[0:v][s]overlay=0:0:enable='between(t,{ps},{pe})'[v]",
                 "-map","[v]","-map","0:a","-c:v","libx264","-preset","medium","-crf","20",
                 "-pix_fmt","yuv420p","-c:a","copy",str(out)])
            src = str(out)
            patched.append({"segment": n, "from_s": ps, "to_s": pe,
                            "seconds": round(pe-ps,3), "held_frame_s": hold, "reason": why})
        p = W / f"norm{n}.mp4"
        run(["ffmpeg","-y","-nostdin","-loglevel","error","-i",src,
             "-af",f"loudnorm=I={LUFS}:TP=-1.5:LRA=11",
             "-c:v","copy","-c:a","aac","-b:a","192k",str(p)])
        norm[n] = p

    # 2. slice each segment into kept pieces around its trims
    pieces, log = [], []
    for i, n in enumerate(a.order):
        keep, t = [], 0.0
        for s, e, why in TRIMS.get(n, []):
            if s > t: keep.append((t, s))
            log.append({"segment": n, "from_s": s, "to_s": e, "seconds": round(e-s,3), "reason": why})
            t = e
        total = dur(srcs[n])
        if total > t: keep.append((t, total))
        last_of_segment = len(keep) - 1
        for k, (s, e) in enumerate(keep):
            p = W / f"p{len(pieces):02d}.mp4"
            vf = "setsar=1"
            af = "anull"
            # breath only after the final piece of a non-final segment
            if k == last_of_segment and i < len(a.order) - 1:
                vf += f",tpad=stop_mode=clone:stop_duration={BREATH}"
                af += f",apad=pad_dur={BREATH}"
            run(["ffmpeg","-y","-nostdin","-loglevel","error","-ss",f"{s:.3f}","-to",f"{e:.3f}",
                 "-i",str(norm[n]),"-vf",vf,"-af",af,
                 "-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p",
                 "-c:a","aac","-b:a","192k","-video_track_timescale","30000",str(p)])
            pieces.append(p)

    lst = W / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces))
    run(["ffmpeg","-y","-nostdin","-loglevel","error","-f","concat","-safe","0","-i",str(lst),
         "-c","copy","-movflags","+faststart",a.out])

    Path("edit/ireland-trims.json").write_text(json.dumps(
        {"order": a.order, "breath_s": BREATH, "lufs": LUFS,
         "removed": log, "picture_patches": patched}, indent=2))
    print(f"{' -> '.join(a.order)}  {len(pieces)} pieces  {dur(a.out):.2f}s  -> {a.out}")
    for d in patched: print(f"  patched {d['segment']} {d['from_s']:.2f}-{d['to_s']:.2f} ({d['seconds']:.2f}s): {d['reason'][:70]}…")
    for d in log: print(f"  removed {d['segment']} {d['from_s']:.2f}-{d['to_s']:.2f} ({d['seconds']:.2f}s): {d['reason'][:70]}…")

if __name__ == "__main__": main()
