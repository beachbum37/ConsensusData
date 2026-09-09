#!/usr/bin/env python3
"""
The regression net. Run it before you commit anything, and after any render.

    python3 selftest.py            # the geometry and state machines, both fps
    python3 selftest.py <clip.mp4> # ...and the non-negotiables on a real file

WHY THIS EXISTS. Until 2026-08-25 this pipeline had NO automated protection of
any kind - no golden file, no checksum, nothing that would catch a change making
every clip slightly worse. Everything was verified by somebody measuring it once,
by hand, and the record of that is SKILL.md. That worked because the same person
did the measuring and the changing on the same afternoon; it does not survive a
second person, or a gap of a month, or an edit made to fix something else.

The owner's brief, 2026-08-25: "we want to be able to make a clip and not even
have to think about problems." A rule nothing checks is not a rule, it is a note.

WHAT IT COVERS. Every invariant this file's history says was broken once, because
those are the ones that break again:

  - the pill's two seams, its landing scale, its breath, and its ink against the
    platform chrome line - at its PEAK, not at rest
  - the nameplate's plate rows, its centring, its pure cross-fade, and its
    arrival AFTER the hook card has actually gone, at every tempo
  - the cutaway drift, all 25 move pairs, monotone, landing at rest, never
    uncovering the speaker - at every tempo
  - the feasibility gates, at every hold length the rig can produce
  - BOTH FRAME RATES. SRC_FPS defaults to 25 and this desk runs 30, and a
    hardcoded frame count is a different duration on each. That exact bug shipped.

It renders nothing, so it runs in about a second. The file-level checks at the
bottom are the ones that need a clip, and they are the non-negotiables.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FAILS: list[str] = []
CHECKS = [0]


def ok(cond: bool, label: str, detail: str = "") -> None:
    CHECKS[0] += 1
    if not cond:
        FAILS.append(f"{label}" + (f"\n      {detail}" if detail else ""))


def _load(fps: int):
    """Import qmclip against a throwaway project at a given frame rate."""
    d = Path(tempfile.mkdtemp(prefix=f"qmselftest{fps}"))
    (d / "project.json").write_text(json.dumps({
        "source": "none.mp4", "out_dir": str(d / "out"), "src_fps": fps,
        "layout_version": 2, "cta": "invest.quasarmarkets.com",
        "host": {"name": "Steven E. Orr", "title": "Founder and CEO, Quasar Markets"},
    }))
    os.environ["WLAM_WORK"] = str(d)
    for m in ("qmclip", "broll"):
        sys.modules.pop(m, None)
    import qmclip
    return qmclip


# ------------------------------------------------------------ the invitation --
def check_pill(q, fps: int) -> None:
    t = f"pill@{fps}"
    ok(q.PILL_IN_FRAMES == q.PILL_OUT_FRAMES, f"{t}: in and out frame counts differ",
       "both branches index one curve by their own k; unequal counts truncate the exit")
    ok(abs(q.pill_scale(q.PILL_IN_FRAMES - 1, q.PILL_IN_FRAMES) - 1.0) < 1e-9,
       f"{t}: the travel does not land on 1.0",
       "the pulse starts from the resting scale; anything else is a step at both seams")
    # pill_scale must be total for any n, including the degenerate ones
    for n in (1, 2, 3, 7, 15, 40):
        for k in (-2, 0, 1, n - 1, n, n + 5):
            try:
                v = q.pill_scale(k, n)
            except Exception as e:
                ok(False, f"{t}: pill_scale({k},{n}) raised {type(e).__name__}")
                continue
            ok(0.5 < v < 1.5, f"{t}: pill_scale({k},{n}) = {v} is out of range")

    # THE SHORTEST HOLD THAT CAN ACTUALLY OCCUR, not the settled floor. This
    # read (q.BROLL_HOLD, 3.7, q.BROLL_HOLD_MIN) and BROLL_HOLD_MIN is the
    # SETTLED floor - the picture after its travel - so it was modelling a 2.5s
    # insert the pipeline cannot produce: preflight requires h - travel >=
    # BROLL_HOLD_MIN, making the real minimum 3.2. It passed only because the
    # old floor of 3.0 happened to leave 1.95s against the button's 1.76s, and
    # it failed the moment the floor moved - on an insert length that does not
    # exist. The hardcoded 3.7 was the old derived minimum, now stale for the
    # same reason.
    _min_hold = q.BROLL_HOLD_MIN + q.BROLL_IN + q.BROLL_OUT
    for hold in (q.BROLL_HOLD, _min_hold):
        win = (0.0, hold - q.CTA_BROLL_LEAD - q.CTA_BROLL_TAIL)
        need = q.PILL_TRAVEL + q.PILL_SETTLE_MIN
        ok(win[1] >= need, f"{t}: hold {hold} leaves {win[1]:.2f}s, the button needs {need:.2f}s",
           "cta_windows would drop the invitation off this cutaway")
        n = int(round(win[1] * fps))
        st = [q.cta_state(k / fps, [win]) for k in range(n)]
        sc = [x[1] for x in st]
        hold_sc = sc[q.PILL_IN_FRAMES:n - q.PILL_OUT_FRAMES]
        if len(hold_sc) < 3:
            continue
        # both seams continuous
        ok(abs(sc[q.PILL_IN_FRAMES - 1] - hold_sc[0]) < 1e-6,
           f"{t}/{hold}: step into the hold of {abs(sc[q.PILL_IN_FRAMES-1]-hold_sc[0]):.4f}")
        ok(abs(hold_sc[-1] - 1.0) < 1e-6,
           f"{t}/{hold}: the breath does not close on 1.0 before the exit ({hold_sc[-1]:.4f})",
           "PILL_PULSE_TAPER must land the pulse on the resting scale")
        swing = (max(hold_sc) - min(hold_sc)) * 462
        ok(6 < swing < 20, f"{t}/{hold}: breath swing is {swing:.1f}px",
           "under ~6px it cannot be seen, over ~20px it is a throb")
        worst = max(abs(hold_sc[i + 1] - hold_sc[i]) for i in range(len(hold_sc) - 1))
        ok(worst * 462 < 3.0, f"{t}/{hold}: breath steps {worst*462:.2f}px in one frame")
        # the exit is the entrance played backwards: it must LEAVE gently
        dy = [x[2] for x in st]
        first = abs(dy[n - q.PILL_OUT_FRAMES + 1] - dy[n - q.PILL_OUT_FRAMES])
        ok(first < 5.0, f"{t}/{hold}: the exit's first frame moves {first:.1f}px",
           "u**3 read as a function of time is an ease-OUT; it must be 1-(1-u)**3")

    # the ink, at its BIGGEST, against the line the platform chrome starts at
    peak = max(max(q.PILL_SCALE), 1.0 + q.PILL_PULSE_AMP)
    bottom = q.CTA_BAND_Y + q.pill_ink_bottom(sx=peak)
    ok(bottom <= q.CAP_SAFE_BOTTOM,
       f"{t}: the invitation inks to y{bottom} at its {peak:.3f} peak, chrome starts "
       f"y{q.CAP_SAFE_BOTTOM}")


# -------------------------------------------------------------- the nameplate --
def check_nameplate(q, fps: int) -> None:
    t = f"nameplate@{fps}"
    name, role = "Nathan Dean", "Sr. Analyst, Bloomberg Intelligence"
    top, bot = q.attr_plate_rows(name, role)
    ok(bot <= q.CAP_SAFE_BOTTOM,
       f"{t}: the plate reaches y{bot}, chrome starts y{q.CAP_SAFE_BOTTOM}")
    ok(q.CTA_BAND_Y + q.attr_ink_bottom(name, role) <= q.CAP_SAFE_BOTTOM + 8,
       f"{t}: the plate's shadow crosses the chrome line")
    _fn, _fr, _wn, _wr, pw, _ph, _rest = q._attr_metrics(name, role)
    ok(pw % 2 == 0, f"{t}: plate width {pw} is odd - it cannot be centred on 1080")
    ok(pw <= q.CAP_INK_MAX, f"{t}: plate width {pw} exceeds the action-rail measure")

    # IT FADES. No horizontal travel, ever - that was the whole ask.
    ok(not hasattr(q, "ATTR_BAND_SLIDE"),
       f"{t}: ATTR_BAND_SLIDE is back; the nameplate must cross-fade, not swipe")
    dur = 50.0
    q.BROLL_WINDOWS[:] = []
    win = q.attr_window(dur)
    ok(win is not None, f"{t}: no nameplate window on a 50s clip")
    if win:
        a, b = win
        al = [q.attr_band_state(k / fps, dur, True) for k in range(int(a * fps), int(b * fps) + 2)]
        rise = al[:int(q.ATTR_BAND_IN * fps)]
        ok(all(x <= y + 1e-9 for x, y in zip(rise, rise[1:])),
           f"{t}: the entrance alpha is not monotone")
        ok(max(al) > 0.99, f"{t}: never reaches full opacity (max {max(al):.3f})")
        ok(al[-1] < 0.02, f"{t}: does not close (ends at {al[-1]:.3f})")

    # AND IT ARRIVES AFTER THE TITLE HAS GONE, at every tempo. ATTR_BAND_AT was a
    # bare constant while the hook's exit is tempo-scaled; at 1.04 they overlapped.
    for tempo in (0.96, 1.0, 1.04, 1.08, 1.12, 1.15):
        q.ATTR_TEMPO[0] = tempo
        gone = (q.HOOK_HOLD + q.HOOK_OUT) * tempo
        ok(q.attr_at() >= gone,
           f"{t}: at tempo {tempo} the nameplate arrives at {q.attr_at():.3f} but the "
           f"title card is still up until {gone:.3f}")
    q.ATTR_TEMPO[0] = 1.0


# ---------------------------------------------------------------- the cutaway --
def _ev(expr: str, tt: float) -> float:
    e = (expr.replace("pow(", "__p(").replace("min(", "__mn(")
             .replace("max(", "__mx(").replace("floor(", "__f("))
    return eval(e, {"__p": pow, "__mn": min, "__mx": max, "__f": math.floor, "t": tt})


def check_cutaway(q, fps: int) -> None:
    t = f"cutaway@{fps}"
    ok(q.W * (q.BROLL_BLEED - 1) / 2 >= q.BROLL_DRIFT
       and q.H * (q.BROLL_BLEED - 1) / 2 >= q.BROLL_DRIFT,
       f"{t}: BROLL_BLEED {q.BROLL_BLEED} does not cover a {q.BROLL_DRIFT}px drift")
    ok(all(q.BROLL_ROTATION[i] != q.BROLL_ROTATION[(i + 1) % len(q.BROLL_ROTATION)]
           for i in range(len(q.BROLL_ROTATION))),
       f"{t}: two adjacent rotation entries are the same pair")
    bw = int(q.W * q.BROLL_BLEED) // 2 * 2
    bh = int(q.H * q.BROLL_BLEED) // 2 * 2
    a0, a1 = 0.0, 3.7
    for tempo in (0.96, 1.0, 1.12, 1.30):
        for mi in q.BROLL_MOVES:
            for mo in q.BROLL_MOVES:
                x, y = q.broll_offsets(mi, mo, a0, a1, q.BROLL_IN * tempo,
                                       q.BROLL_OUT * tempo, tempo)
                xs = [_ev(x, k / fps) for k in range(int(a1 * fps))]
                ys = [_ev(y, k / fps) for k in range(int(a1 * fps))]
                margin = min(min(v + bw - q.W for v in xs), min(-v for v in xs),
                             min(v + bh - q.H for v in ys), min(-v for v in ys))
                ok(margin >= 0,
                   f"{t}: {mi}/{mo} at tempo {tempo} uncovers the speaker by {-margin:.0f}px")
                ok(all(v % 2 == 0 for v in xs + ys),
                   f"{t}: {mi}/{mo} lands on an odd pixel - yuv420p chroma will shimmer")
                # the travel must COMPLETE on the last frame the gate draws
                last_x = _ev(x, a1 - 0.5 / fps)
                last_y = _ev(y, a1 - 0.5 / fps)
                ok(math.isfinite(last_x) and math.isfinite(last_y),
                   f"{t}: {mi}/{mo} produced a non-finite offset")

    # the rotation must not depend on the clip's RANK
    items = [{"at": 1}, {"at": 2}, {"at": 3}]
    ok(q.broll_move_pairs(items, "some-slug") == q.broll_move_pairs(items, "07-some-slug"),
       f"{t}: the move rotation changes with the clip's rank prefix",
       "re-ordering a slate would silently re-roll every other clip's transitions")
    ok(q.broll_move_pairs(items, "a-slug") == q.broll_move_pairs(items, "a-slug"),
       f"{t}: broll_move_pairs is not deterministic")


# ------------------------------------------------------------------ the bands --
def check_bands(q, fps: int) -> None:
    t = f"bands@{fps}"
    # short gaps between raise windows are bridged, long ones are not
    m = q.merge_raise([(3.0, 6.0), (6.5, 9.0), (30.0, 33.0)])
    ok(m == [(3.0, 9.0), (30.0, 33.0)], f"{t}: merge_raise gave {m}")
    ok(q.merge_raise([]) == [], f"{t}: merge_raise([]) is not empty")
    # the nameplate and the invitation may never want the same frame
    q.BROLL_WINDOWS[:] = [(5.2, 8.9), (20.0, 23.7)]
    aw = q.attr_window(48.0)
    for a, b in q.cta_windows(48.0, attr="Nathan Dean"):
        ok(not (aw and a < aw[1] and b > aw[0]),
           f"{t}: an invitation window {a:.2f}-{b:.2f} overlaps the nameplate {aw}")
    q.BROLL_WINDOWS[:] = []


# ------------------------------------------------------------ the source crop --
def check_head_box(q, fps: int) -> None:
    """
    The default head crop must fit INSIDE the source, whatever shape it is.

    It used to be built from two literals - 1080 tall out of a 1920x1080 frame -
    and that is the branch that runs on every head clip with no authored
    head_crop, 8 of 28 in the archive. A 1280x720 master asked for a crop 1080
    pixels tall and the render died a hundred seconds in, inside the filtergraph.
    """
    t = f"head_box@{fps}"
    real = q.src_size
    for sw, sh in ((1920, 1080), (1280, 720), (3840, 2160), (1080, 1920),
                   (640, 480), (1440, 1080), (720, 1280)):
        q.src_size = lambda _s=(sw, sh): _s
        try:
            cw, ch, cx, cy = q.head_box()
        except Exception as e:
            ok(False, f"{t}: {sw}x{sh} raised {type(e).__name__}: {e}")
            continue
        ok(cw > 0 and ch > 0, f"{t}: {sw}x{sh} gave a zero-area crop {(cw,ch,cx,cy)}")
        ok(cx >= 0 and cy >= 0, f"{t}: {sw}x{sh} gave a negative origin {(cx,cy)}")
        ok(cx + cw <= sw and cy + ch <= sh,
           f"{t}: {sw}x{sh} -> crop {(cw,ch,cx,cy)} runs past the frame")
        ok(abs(cw / ch - q.PANEL_W / q.PANEL_H) < 0.01,
           f"{t}: {sw}x{sh} -> aspect {cw/ch:.4f}, wanted {q.PANEL_W/q.PANEL_H:.4f}")
    # a wild face_crop_x must be clamped, not obeyed off the edge
    q.src_size = lambda: (1280, 720)
    for want in (-500, 0, 99999):
        q.CFG["face_crop_x"] = want
        cw, ch, cx, cy = q.head_box()
        ok(0 <= cx <= 1280 - cw, f"{t}: face_crop_x {want} escaped to cx {cx}")
    q.CFG.pop("face_crop_x", None)
    q.src_size = real


# ------------------------------------------------------------- the vocabulary --
def check_vocab() -> None:
    import broll
    ok(len(broll.EXPAND) > 8000, f"vocab: EXPAND is only {len(broll.EXPAND)} entries")
    both = set(broll.EXPAND) & set(broll.PEOPLE)
    ok(not both, f"vocab: {len(both)} key(s) are in BOTH EXPAND and PEOPLE: {sorted(both)[:5]}",
       "query_for checks PEOPLE first, so the EXPAND entry is unreachable and misleading")
    bad = [k for k, v in broll.EXPAND.items()
           if any(broll._word_rx(w).search(v.lower()) for w in broll.COMPLIANCE_WORDS)]
    ok(not bad, f"vocab: {len(bad)} value(s) name a term the compliance filter blocks: {bad[:4]}")
    dead = [k for k, v in broll.EXPAND.items() if not v.strip() or len(v.split()) > 6]
    ok(not dead, f"vocab: {len(dead)} value(s) are empty or over six words: {dead[:4]}")
    nofall = [k for k, v in broll.PEOPLE.items() if not v[1].strip()]
    ok(not nofall, f"vocab: {len(nofall)} PEOPLE entries have no fallback picture")


# ------------------------------------------------- the non-negotiables, on a file --
# THE DETECTORS ARE THEMSELVES CHECKED, and this is not belt and braces.
#
# blackdetect, freezedetect and silencedetect print their findings at ffmpeg's
# INFO level. These three calls passed `-v error`, which deletes exactly that
# output - so the regex found nothing, `ok(not ...)` was always true, and all
# three checks passed unconditionally on every clip ever run through them.
# Proved on a synthetic 3s clip that is black, frozen and silent all at once:
# under `-v error` it reports 0 black stretches, 0 freezes and 0 silent runs.
#
# A check that cannot fail is worse than no check, because the green tick is
# read as evidence. So the net now proves its own instrument first: it builds
# that same known-bad clip and requires all three detectors to FIRE on it. If
# anybody quiets these calls again, this fails and says so, instead of the
# whole file going quietly green.
def _card_seconds() -> float:
    """How long the end card runs, from the module that draws it."""
    try:
        import endcard
        return float(endcard.CARD_SECONDS)
    except Exception:                                        # noqa: BLE001
        return 4.0


def check_detectors() -> None:
    """Prove the black/freeze/silence detectors can still report anything."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "known-bad.mp4"
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "lavfi", "-i", "color=black:s=320x240:r=30:d=3",
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
             "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", str(bad)], capture_output=True, text=True)
        if r.returncode or not bad.exists():
            ok(False, "detector control: could not build the known-bad clip",
               r.stderr.strip()[:200])
            return
        probes = (
            ("blackdetect", ["-vf", "blackdetect=d=0.5:pic_th=0.98"], "black_start"),
            ("freezedetect", ["-vf", "freezedetect=n=0.001:d=2"], "freeze_start"),
            ("silencedetect", ["-af", "silencedetect=noise=-44dB:d=0.7"],
             "silence_duration"),
        )
        for name, args, token in probes:
            out = subprocess.run(
                ["ffmpeg", "-v", "info", "-nostats", "-i", str(bad)] + args
                + ["-f", "null", "-"], capture_output=True, text=True)
            ok(token in out.stderr,
               f"detector control: {name} reported NOTHING on a clip that is "
               f"black, frozen and silent - the check below it cannot fail",
               "it prints at INFO level; -v error deletes it")


    # AND THE FOURTH DETECTOR. check_stall counts the frames mpdecimate lets
    # through; it used to parse " drop " out of ffmpeg's log at -v info, where
    # mpdecimate prints nothing, so it reported 0.0% on every master ever
    # passed to it. Same defect as the three above, one function later. This
    # control builds a master where 9 of every 10 frames are literal repeats
    # and requires the probe to SEE them.
    try:
        import subprocess as _sp
        with tempfile.TemporaryDirectory() as _td:
            _bad = Path(_td) / "held.mp4"
            _sp.run(["ffmpeg", "-v", "error", "-f", "lavfi",
                     "-i", "testsrc=size=320x180:rate=3,fps=30", "-t", "4",
                     "-pix_fmt", "yuv420p", str(_bad), "-y"], capture_output=True)
            _out = _sp.run(
                ["ffprobe", "-v", "error", "-f", "lavfi",
                 f"movie={_bad},trim=duration=4,mpdecimate=hi=64:lo=32:frac=0.33",
                 "-show_entries", "stream=nb_read_frames", "-count_frames",
                 "-of", "default=nw=1:nk=1"],
                capture_output=True, text=True).stdout.strip()
            _kept = int(_out) if _out.isdigit() else 120
            _drops = 120 - _kept
            ok(_drops / 120.0 > 0.04,
               f"detectors: the repeat-frame probe SEES a held master "
               f"({_drops}/120 repeats) - if this fails the stall gate is blind")
    except Exception as e:                                       # noqa: BLE001
        ok(False, f"detectors: the repeat-frame control did not run ({e})")

def check_clip(path: Path) -> None:
    """The four rules, measured on a delivered mp4."""
    t = f"clip[{path.name[:34]}]"
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
                         "-show_entries", "format=duration", "-of", "json", str(path)],
                        capture_output=True, text=True)
    ok(pr.returncode == 0, f"{t}: will not probe")
    if pr.returncode:
        return
    d = json.loads(pr.stdout)
    st, fmt = d["streams"][0], d["format"]
    ok((st["width"], st["height"]) == (1080, 1920),
       f"{t}: is {st['width']}x{st['height']}, not 1080x1920")
    # FRAME RATE. It was probed and then never asserted on, so a judder clip
    # passed the gate that exists to stop judder shipping.
    ok(st.get("r_frame_rate") in ("25/1", "30/1", "24/1", "50/1", "60/1"),
       f"{t}: frame rate is {st.get('r_frame_rate')}, not a whole number")
    # THERE IS AN AUDIO STREAM AT ALL. silencedetect reports NOTHING on a file
    # with no audio stream, so the old check inferred sound from the absence of
    # silence - and a completely silent clip sailed through.
    ap = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                         "-show_entries", "stream=codec_name,sample_rate,channels",
                         "-of", "json", str(path)], capture_output=True, text=True)
    astreams = (json.loads(ap.stdout or "{}").get("streams") or []) if not ap.returncode else []
    ok(bool(astreams), f"{t}: NO AUDIO STREAM")
    if astreams:
        a0 = astreams[0]
        ok(int(a0.get("channels", 0)) == 2, f"{t}: {a0.get('channels')} audio channel(s), wanted 2")
        ok(int(a0.get("sample_rate", 0)) == 48000,
           f"{t}: audio is {a0.get('sample_rate')}Hz, wanted 48000")
    # NOT BLACK, AND NOT FROZEN. A 50-second black rectangle with a valid .srt
    # beside it passed everything else on this list.
    bd = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", str(path),
                         "-vf", "blackdetect=d=0.5:pic_th=0.98", "-f", "null", "-"],
                        capture_output=True, text=True)
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd.stderr)
    body_black = [(float(a), float(b)) for a, b in blacks
                  if float(a) < float(fmt["duration"]) - 5.0]
    ok(not body_black, f"{t}: {len(body_black)} black stretch(es) in the body: {body_black[:2]}",
       "the end card is near-black and is excluded; anything earlier is a hole")
    fz = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", str(path),
                         "-vf", "freezedetect=n=0.001:d=2", "-f", "null", "-"],
                        capture_output=True, text=True)
    frozen = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", fz.stderr)]
    body_frozen = [x for x in frozen if x < float(fmt["duration"]) - 5.0]
    ok(not body_frozen, f"{t}: the picture freezes for 2s+ at {body_frozen[:3]}")
    dur = float(fmt["duration"])
    # THE OWNER'S FLOOR, NOT A STALE ONE. This tested 45.0 while q.MIN_CLIP has
    # been 60.0 since the "minimum a minute to a minute thirty" instruction, so
    # the ONE gate that runs on the delivered file would have passed a 50-second
    # clip the rest of the pipeline refuses. Read the constant.
    # IMPORTED HERE. check_clip runs in FILE mode only, where `q` is a local in
    # main() and not a module global - so reading q.MIN_CLIP raised NameError
    # the first time this gate ran on a real mp4, and the 1167-check run never
    # touched it because that path needs a file argument.
    import qmclip as _q
    ok(dur >= _q.MIN_CLIP,
       f"{t}: {dur:.1f}s is under the {_q.MIN_CLIP:.0f}s floor")
    # audio present, and nobody is watching someone not talking
    sil = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", str(path),
                          "-af", "silencedetect=noise=-44dB:d=0.7", "-f", "null", "-"],
                         capture_output=True, text=True)
    # THE END CARD IS EXCLUDED, exactly as it is for blackdetect above. The card
    # plays a whoosh over its entrance and is then deliberately quiet for its
    # remaining ~3.5s, which is not somebody failing to talk. Judged on where the
    # run STARTS, so a silence that opens in the body and runs into the card
    # still fails. Measured on both nd-test clips: the only run either has starts
    # 1.23s from the end, inside the card.
    card = _card_seconds()
    runs = [(float(a), float(b)) for a, b in re.findall(
        r"silence_start: ([\d.]+)[\s\S]*?silence_duration: ([\d.]+)", sil.stderr)]
    body_silent = [(a, b) for a, b in runs if a < float(fmt["duration"]) - card]
    ok(not body_silent,
       f"{t}: {len(body_silent)} silent run(s) over 0.7s in the body: {body_silent[:3]}",
       "a viewer must never be watching somebody who is not talking")
    # a caption file, and it must match the burned-in words
    srt = path.parent.parent / "captions" / f"{path.stem}.srt"
    ok(srt.exists(), f"{t}: no .srt beside it at {srt}")
    if srt.exists():
        txt = srt.read_text()
        cues = len(re.findall(r"^\d+$", txt, re.M))
        ok(cues > 10, f"{t}: only {cues} caption cues")
        # EVERY CUE MUST LAST LONG ENOUGH TO BE SHOWN. A delivered clip shipped
        # cue 19 as 00:00:12,433 --> 00:00:12,433 - most players skip a
        # zero-duration cue, so the word was lost to anybody reading captions.
        def _sec(x: str) -> float:
            h, m, rest = x.split(":"); sec, ms = rest.split(",")
            return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
        short = []
        for n, a, b, _tx in re.findall(
                r"^(\d+)\n(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})\n(.*)$",
                txt, re.M):
            if _sec(b) - _sec(a) < 0.09:
                short.append(n)
        ok(not short, f"{t}: {len(short)} caption cue(s) under 90ms: {short[:5]}")
        last = re.findall(r"[.!?]\s*$", txt.strip())
        ok(bool(last), f"{t}: the caption file does not end on terminal punctuation",
           "a clip must not cut off mid-sentence")


def check_pick(q, fps: int) -> None:
    """
    THE PICKER'S HARD RULES, which are the ones a human should never have to
    re-check: what the compliance scan catches, and what may open a clip.
    """
    t = f"pick@{fps}"
    try:
        import pick
    except Exception as e:                                        # noqa: BLE001
        ok(False, f"{t}: pick.py will not import ({type(e).__name__})")
        return

    # THE SHAPES THIS DESK ACTUALLY SAYS. Every one of these is lifted from a
    # real transcript on this machine; they are the reason the scan exists.
    must_flag = [
        ("Steve, I'm averaging at 39.5 here now on Nike.", "position"),
        ("39.30 on Nike is where I'm at, 39.30.",          "level"),
        ("Oil, almost $81 a barrel here, pushing higher.",  "price"),
        ("You can buy the fund, WEAT, if you don't trade futures.", "advice"),
        ("And of course, my Nike thesis, I have purchased Nike.",  "position"),
    ]
    for txt, kind in must_flag:
        got = [f.split(":")[0] for f in pick.compliance_flags(txt)]
        ok(kind in got, f"{t}: {kind!r} not caught in {txt[:44]!r}", str(got))

    # AND WHAT IT MUST NOT DRAG IN. A wage is not a share price; a percentage
    # of an economy is not a return. Over-flagging is what makes a scan ignored.
    must_pass = [
        "I get rid of the $20 accountant and pay for the $10 robot.",
        "It is a $4 trillion economy and it is still growing.",
        "He wrote a 6,000 word warning about artificial intelligence.",
    ]
    for txt in must_pass:
        got = pick.compliance_flags(txt)
        ok(not got, f"{t}: false flag on {txt[:44]!r}", str(got))

    # AN OPENER HAS TO CARRY AN IDEA. These are real rejected in-points.
    for bad in ("Wow.", "They just do.", "Oh, it's called, sorry.", "Yeah.",
                "Right."):
        ok(not pick.opens_an_idea(bad), f"{t}: {bad!r} was allowed to open a clip")
    for good in ("Cruise ships are all going to Starlink.",
                 "The Fed should meet six times a year, not four.",
                 "AI is not a substitute for human intelligence."):
        ok(pick.opens_an_idea(good), f"{t}: {good[:38]!r} was refused as an opener")

    # A flag carries enough context to clear it at a glance - the whole reason
    # a 36% flag rate is workable.
    f = pick.compliance_flags(
        "typically be negative. Steve, I'm averaging at 39.5 here now on Nike.")
    ok(f and len(f[0]) > 30 and "averaging" in f[0],
       f"{t}: a flag came back without the words that let you clear it", str(f))

    # THE WAGE EXCEPTION, which is the one false positive worth suppressing:
    # a share price is attached to an INSTRUMENT and a wage to a PERSON, and
    # that is the only principle available without a company-name list.
    ok(not pick.compliance_flags("a $20 an hour worker in accounting"),
       f"{t}: an hourly wage flagged as a price")
    ok(pick.compliance_flags("Oil, almost $81 a barrel here"),
       f"{t}: a commodity price did NOT flag")


def check_speaker_tracks(q, fps: int) -> None:
    """
    PER-SPEAKER AUDIO IS THE ONE ROUTE THAT IS EXACT, so it gets a real test.

    Everything else that answers "who is talking" infers it from a mixed track
    and a picture, and measured against transcript ground truth on real footage
    that ceiling was 43% - at or below chance for two people. Given one file per
    person the same question is two levels compared.

    Synthesised here with -20 dB of mic bleed, which is what an open mic in the
    same room actually leaks, because the failure this must not have is picking
    the bleed. Boundaries are checked exactly, not approximately.
    """
    import tempfile
    import wave

    import numpy as np

    t = f"trk@{fps}"
    try:
        import turns as _t
    except Exception:                                            # noqa: BLE001
        ok(False, f"{t}: turns.py imports")
        return

    SR = 16000
    TRUTH = [(0, 12, "a"), (12, 26, "b"), (26, 31, "a"), (31, 48, "b"), (48, 60, "a")]
    DUR = 60.0
    rng = np.random.default_rng(7)
    voice = rng.normal(0, 0.08, int(DUR * SR))
    n = len(voice)
    gate = {"a": np.zeros(n), "b": np.zeros(n)}
    for x, y, who in TRUTH:
        gate[who][int(x * SR):int(y * SR)] = 1.0
    bleed = 10 ** (-20 / 20)

    with tempfile.TemporaryDirectory() as td:
        paths = {}
        for who in gate:
            other = "b" if who == "a" else "a"
            sig = voice * gate[who] + voice * gate[other] * bleed
            sig = sig + rng.normal(0, 0.0008, n)
            f = Path(td) / f"{who}.wav"
            with wave.open(str(f), "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(sig, -1, 1) * 32767).astype("<i2").tobytes())
            paths[who] = f
        sched = _t.track_turns(0.0, DUR, paths)

    ok(len(sched) == len(TRUTH),
       f"{t}: {len(TRUTH)} turns recovered, got {len(sched)}")
    if len(sched) != len(TRUTH):
        return
    hit = tot = 0.0
    for x, y, who in TRUTH:
        for s_ in sched:
            o = max(0.0, min(y, s_["end"]) - max(x, s_["start"]))
            if o > 0:
                tot += o
                if s_["who"] == who:
                    hit += o
    ok(hit / max(1e-9, tot) >= 0.99,
       f"{t}: agreement {hit / max(1e-9, tot) * 100:.1f}% (needs >=99)")
    for i, (x, y, who) in enumerate(TRUTH):
        ok(sched[i]["who"] == who, f"{t}: turn {i + 1} is {who}")
        ok(abs(sched[i]["start"] - x) <= 0.3,
           f"{t}: turn {i + 1} starts at {x}s (got {sched[i]['start']:.2f})")
        ok(sched[i]["confidence"] >= 0.95,
           f"{t}: turn {i + 1} is measured, not held")
    ok(all(s_.get("source") == "tracks" for s_ in sched),
       f"{t}: schedule is labelled as coming from tracks")
    # BLEED MUST NOT WIN. With one person silent the other's leaked signal is
    # all that is in their track, and TRACK_MARGIN is what stops it scoring.
    ok(_t.TRACK_MARGIN > 10 ** (-20 / 20) * 10,
       f"{t}: margin clears -20dB bleed with headroom")


def check_speaker_transcript(q, fps: int) -> None:
    """
    THE STREAM'S OWN TRANSCRIPT, and the trap in using it.

    The platform knows who spoke - each person is on their own feed. What it
    does NOT share is the master's clock: the stream has pre-roll, the download
    starts elsewhere, and a few seconds of offset puts every cut on the wrong
    face while looking entirely plausible. So the timestamps are discarded and
    the WORDS are aligned onto cues.json.

    This synthesises exactly that failure - a transcript whose clock is 37.5s
    out, from a different ASR that dropped words - and requires the alignment to
    put it back on the master's time regardless.
    """
    import tempfile

    t = f"spk@{fps}"
    try:
        import speakers as _s
    except Exception:                                            # noqa: BLE001
        ok(False, f"{t}: speakers.py imports")
        return

    ok(_s.MIN_MATCH > 0.0, f"{t}: an unmatched turn is dropped, not placed")

    body = [("Steven E. Orr", "the federal reserve is not going to move on this"),
            ("Stephen Flanagan", "and that is exactly the point i keep making here"),
            ("Steven E. Orr", "so why is that narrative being pushed so hard")]
    cues, tsec = [], 100.0
    for _who, txt in body:
        cues.append([tsec, tsec + 6.0, txt])
        tsec += 6.0

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        (work / "cues.json").write_text(json.dumps(cues))
        (work / "project.json").write_text(json.dumps(
            {"follow_tiles": {"steve": [1, 1, 0, 0], "flanagan": [1, 1, 1, 0]}}))
        OFF = 37.5
        lines = ["WEBVTT", ""]
        at = OFF + 100.0
        for who, txt in body:
            drop = " ".join(w for i, w in enumerate(txt.split()) if i % 11 != 3)
            lines += [f"00:00:{at:06.3f} --> 00:00:{at + 6:06.3f}",
                      f"<v {who}>{drop}</v>", ""]
            at += 6.0
        (work / "p.vtt").write_text("\n".join(lines))

        old = _s.WORK
        try:
            _s.WORK = work
            sched = _s.timeline(100.0, 118.0, ["steve", "flanagan"], work / "p.vtt")
        finally:
            _s.WORK = old

    ok(bool(sched), f"{t}: a labelled transcript produces a schedule")
    if not sched:
        return
    # THE CLOCK MUST HAVE BEEN IGNORED. If the platform's timestamps leaked in,
    # everything lands ~37.5s late and off the end of the window.
    ok(sched[0]["start"] >= 99.9 and sched[-1]["end"] <= 118.1,
       f"{t}: placed on the MASTER's clock, not the platform's "
       f"({sched[0]['start']:.1f}-{sched[-1]['end']:.1f})")
    ok([x["who"] for x in sched] == ["steve", "flanagan", "steve"],
       f"{t}: recovers steve/flanagan/steve, got {[x['who'] for x in sched]}")
    ok(all(x.get("source") == "transcript" for x in sched),
       f"{t}: schedule is labelled as coming from the transcript")
    # TWO DIFFERENT PROPERTIES, and they used to be conflated. The SCHEDULE
    # must span the clip end to end (there is always a face on screen), while
    # coverage() reports how much of it the transcript actually MATCHED - which
    # is necessarily less, and was previously summed after gap-closure so it
    # could only ever return ~1.0.
    ok(abs(sched[0]["start"] - 100.0) < 0.01 and abs(sched[-1]["end"] - 118.0) < 0.01,
       f"{t}: the schedule spans the clip end to end")
    _cov = _s.coverage(100.0, 118.0, sched)
    ok(0.3 < _cov <= 1.0,
       f"{t}: coverage reports the ALIGNED share, not the schedule span ({_cov:.2f})")
    ok(all(x.get("aligned") is not None for x in sched),
       f"{t}: every turn records how much of it was aligned")
    # "steve" must not claim "Stephen Flanagan"
    m = _s.name_map(["Steven E. Orr", "Stephen Flanagan"], ["steve", "flanagan"])
    ok(m.get("Stephen Flanagan") == "flanagan",
       f"{t}: 'Stephen Flanagan' maps to flanagan, not steve")
    ok(m.get("Steven E. Orr") == "steve", f"{t}: 'Steven E. Orr' maps to steve")


def check_second_plate(q, fps: int) -> None:
    """
    THE SECOND SPEAKER GETS NAMED TOO.

    Until 2026-08-28 a conversation clip named one person and the other could
    hold the screen for forty seconds unidentified. The owner's rule is that
    every clip carries the white box with the name on it, and the spirit of that
    is that people ON SCREEN get named - so the second speaker is plated at
    their first appearance, once, which is where broadcast does it.

    What must not happen: two bone cards up at once, a card fading through a
    cutaway's dissolve, or a card still on screen when the outro wipe starts.
    """
    t = f"plate2@{fps}"
    ok(hasattr(q, "ATTR2") and isinstance(q.ATTR2, list),
       f"{t}: ATTR2 exists and is a list")
    ok(q.ATTR2_SETTLE > 0, f"{t}: the card waits for the cut to land")

    saved = list(q.ATTR2)
    try:
        q.ATTR2.clear()
        ok(q.attr_window2() is None, f"{t}: no second plate by default")
        ok(q.attr_band_state2(5.0) == 0.0, f"{t}: draws nothing when unset")

        q.ATTR2.append((20.0, 24.2, "Stephen Flanagan", "Markets"))
        ok(q.attr_window2() == (20.0, 24.2), f"{t}: window reported")
        # THE SAME CROSS-FADE AS THE FIRST PLATE, or the clip has two registers.
        ok(q.attr_band_state2(19.9) == 0.0, f"{t}: nothing before it arrives")
        ok(q.attr_band_state2(24.3) == 0.0, f"{t}: nothing after it leaves")
        mid = q.attr_band_state2(22.0)
        ok(abs(mid - 1.0) < 1e-6, f"{t}: fully up in the middle")
        rise = [q.attr_band_state2(20.0 + k * 0.01)
                for k in range(int(q.ATTR_BAND_IN * 100) + 1)]
        ok(all(b >= a - 1e-9 for a, b in zip(rise, rise[1:])),
           f"{t}: the entrance only ever rises")
        fall = [q.attr_band_state2(24.2 - q.ATTR_BAND_OUT + k * 0.01)
                for k in range(int(q.ATTR_BAND_OUT * 100))]
        ok(all(b <= a + 1e-9 for a, b in zip(fall, fall[1:])),
           f"{t}: the exit only ever falls")

        # NEVER TWO CARDS AT ONCE. The first plate lives at attr_at() and the
        # second is placed after it; if they can overlap the strip has two
        # tenants and the layout was built for one.
        w1 = q.attr_window(60.0)
        if w1:
            ok(20.0 >= w1[1], f"{t}: the second card starts after the first ends")
            over = [k / 60.0 for k in range(int(60 * 60))
                    if q.attr_band_state(k / 60.0, 60.0, True) > 0.004
                    and q.attr_band_state2(k / 60.0) > 0.004]
            ok(not over, f"{t}: the two cards are never both on screen "
                         f"({len(over)} frame(s) overlap)")
    finally:
        q.ATTR2.clear()
        q.ATTR2.extend(saved)


def check_caption_floor(q, fps: int) -> None:
    """
    NO CAPTION CARD MAY FLASH. See CAP_MIN_ON.

    Measured on a delivered clip: 12 of 71 cards under 0.45s and two at 0.13s -
    four frames. "Even though" appeared and vanished between two other cards.
    The eye catches the flicker and reads nothing, which is worse than the words
    never being there.

    The cost term for this existed and was OUTBID, so the check is on the floor
    that replaced it, and it is built from times a real word alignment produced:
    a two-word card whose whisper timings are 0.13s apart.
    """
    from PIL import ImageFont

    t = f"capfloor@{fps}"
    ok(q.CAP_MIN_ON >= 0.3, f"{t}: the floor is long enough to read a short card")
    ok(q.CAP_MIN_ON * fps >= 9, f"{t}: at least 9 frames on screen "
                                f"({q.CAP_MIN_ON * fps:.0f})")
    font = ImageFont.truetype(str(q.F_CAP), q.CAP_SIZE)
    # A CARD THAT CANNOT BORROW A WORD BORROWS TIME. See CAP_LATE_MAX.
    ok(0.0 < q.CAP_LATE_MAX <= 0.30,
       f"{t}: a card may slip at most {q.CAP_LATE_MAX:.2f}s behind its word")
    ok(q.CAP_LATE_MAX < q.CAP_MIN_ON,
       f"{t}: the slip is smaller than the floor it serves")
    # width-bound: three words that already fill the line, timed impossibly fast
    long3 = [(0.00, 0.10, "Extraordinarily"), (0.10, 0.20, "interconnected"),
             (0.20, 0.31, "infrastructure"), (0.31, 1.90, "matters.")]
    lw = [q.Word(text=x, start=a, end=b) for a, b, x in long3]
    lc = q.group_words(lw, font, max_w=q.CAP_MEASURE)
    starts = [c[0].start for c in lc]
    ok(all(b >= a for a, b in zip(starts, starts[1:])),
       f"{t}: cards still start in order after the slip")
    for c, nxt in zip(lc, lc[1:]):
        ok(nxt[0].start <= c[0].start + 5.0, f"{t}: no card is pushed off the clip")
    # THE SLIP MAY NEVER OUTRUN THE WORD IT LABELS.
    orig = {id(w): w for w in lw}
    for c in lc:
        w0 = c[0]
        src = next((o for o in long3 if o[2] == w0.text), None)
        if src:
            ok(w0.start <= src[1] + 1e-9,
               f"{t}: {w0.text!r} card arrives before its word ends")

    # A REAL STEPHEN IS NOT RENAMED. fix_spelling corrected the host's name and
    # was rewriting the CO-HOST'S: "Stephen Flanagan" -> "Steven Flanagan",
    # burned into every caption naming him.
    _saved = dict(q.CFG)
    try:
        q.CFG.pop("speakers", None)
        q.CFG["host"] = {"name": "Steven E. Orr"}
        # THE DEFAULT IS TO LEAVE A NAME ALONE. The guard used to run whenever
        # no Stephen was configured, and _real_stephens reads a per-clip key
        # that never appears in project.json - so it was always empty and the
        # correction ALWAYS ran, including on the co-host's real name. It is
        # opt-in now, so the default must be no-op and the opt-in must work.
        _saved_fix = q.FIX_STEPHEN
        try:
            q.FIX_STEPHEN = False
            ok(q.fix_spelling("Thanks Stephen") == "Thanks Stephen",
               f"{t}: by default no name is rewritten")
            q.FIX_STEPHEN = True
            ok(q.fix_spelling("Thanks Stephen") == "Thanks Steven",
               f"{t}: opting in still corrects the host when he is the only one")
        finally:
            q.FIX_STEPHEN = _saved_fix
        q.CFG["speakers"] = {"flanagan": {"name": "Stephen Flanagan"}}
        _saved_fix = q.FIX_STEPHEN
        q.FIX_STEPHEN = True          # even opted IN, a real Stephen is safe
        ok(q.fix_spelling("Stephen Flanagan makes a point")
           == "Stephen Flanagan makes a point",
           f"{t}: a configured Stephen keeps his own name")
        ok(q.fix_spelling("You know, Stephen, I agree")
           == "You know, Stephen, I agree",
           f"{t}: a bare Stephen is left alone when one is on the show")
        q.FIX_STEPHEN = _saved_fix
    finally:
        q.CFG.clear()
        q.CFG.update(_saved)


    # "Even though | the Democrats are asking" - the real shape of the defect.
    times = [(0.00, 0.07, "Even"), (0.07, 0.13, "though"),
             (0.13, 0.60, "the"), (0.60, 1.10, "Democrats"),
             (1.10, 1.60, "are"), (1.60, 2.20, "asking.")]
    words = [q.Word(text=x, start=a, end=b) for a, b, x in times]
    chunks = q.group_words(words, font, max_w=q.CAP_MEASURE)
    ok(bool(chunks), f"{t}: produces cards")
    short = [c for c in chunks
             if (c[-1].end - c[0].start) < q.CAP_MIN_ON - 1e-9]
    ok(not short,
       f"{t}: no card under the floor "
       f"({[' '.join(w.text for w in c) for c in short]})")
    # AND THE WORDS SURVIVE. A merge that drops text is worse than a flicker.
    ok(" ".join(w.text for c in chunks for w in c)
       == " ".join(x for _a, _b, x in times),
       f"{t}: every word still on a card, in order")
    # The merge may exceed max_words - width is the only hard constraint.
    for c in chunks:
        txt = " ".join(w.text for w in c)
        ok(len(c) == 1 or font.getbbox(txt)[2] <= q.CAP_MEASURE,
           f"{t}: {txt!r} still fits one line")


def check_centring(q, fps: int) -> None:
    """
    WHOEVER IS TALKING IS CENTRED. The owner's rule, 2026-08-28: "whoever's
    talking, their face needs to be centred, a lot of times they're shifted to
    the side, everybody has to be centred."

    Two separate faults produced that, and both are checked here.

    analyze.py wrote "face_crop_x" into every project as the GEOMETRIC CENTRE OF
    THE FRAME, without ever looking for a face - and because a configured value
    beat a measured one, that number was the reason speakers came out off
    centre. On the 08.28 head clip the face centre is 866 of 1920 in the source,
    and the frame-centred window at x=656 put it 167px LEFT of the panel centre.

    And the authored two-up crops pointed where somebody typed, not where the
    speaker is: the left crop was +189px out once blown up to the panel, while
    the right one happened to be correct - which is why looking at one speaker
    never revealed it.
    """
    t = f"centre@{fps}"
    ok(hasattr(q, "centre_on_face"), f"{t}: centre_on_face exists")
    ok(hasattr(q, "face_centre"), f"{t}: face_centre exists")

    # THE SIZE IS AUTHORED AND MUST SURVIVE. Only the x may move.
    saved = dict(q._FACEC)
    try:
        q._FACEC[(0, 960, 10.0, 5.0)] = 326.0        # face right of the crop
        box = (516, 917, 0, 0)
        out = q.centre_on_face(box, (0, 960), 10.0, 5.0)
        ok(out[0] == box[0] and out[1] == box[1],
           f"{t}: the crop keeps its authored SIZE ({out[0]}x{out[1]})")
        ok(out[3] == box[3], f"{t}: y is untouched")
        ok(abs((out[2] + out[0] / 2) - 326.0) < 1.0,
           f"{t}: the window centres on the face ({out[2] + out[0] / 2:.0f})")

        # CLAMPED TO ITS OWN TILE, or a crop slides far enough to show the
        # other person's shoulder.
        q._FACEC[(0, 960, 11.0, 5.0)] = 950.0        # face at the tile's edge
        out = q.centre_on_face(box, (0, 960), 11.0, 5.0)
        ok(0 <= out[2] <= 960 - box[0],
           f"{t}: stays inside the tile (x={out[2]})")
        q._FACEC[(0, 960, 12.0, 5.0)] = 5.0
        out = q.centre_on_face(box, (0, 960), 12.0, 5.0)
        ok(out[2] >= 0, f"{t}: never runs off the left edge (x={out[2]})")

        # NO FACE IS NOT A GUESS. The authored box is returned unchanged.
        q._FACEC[(0, 960, 13.0, 5.0)] = None
        ok(q.centre_on_face(box, (0, 960), 13.0, 5.0) == box,
           f"{t}: an unreadable tile keeps its authored crop")
    finally:
        q._FACEC.clear()
        q._FACEC.update(saved)

    # A face_crop_x THAT IS THE GEOMETRIC CENTRE IS THE AUTO-WRITTEN DEFAULT,
    # not a decision, and must not beat the measurement.
    cfg = dict(q.CFG)
    try:
        sw, sh = q.src_size() or (1920, 1080)
        cw = min(sw, int(round(sh * q.PANEL_W / q.PANEL_H)))
        q.CFG["face_crop_x"] = (sw - cw) // 2
        # DETERMINISTIC, so the assertion always RUNS. This read the real
        # detector and then skipped its own central check with
        # `if auto is not None`, so on any machine or span where no face was
        # found - no opencv, an undecodable time, a profile shot - the bug this
        # test exists for passed green and said nothing.
        _fc = dict(q._FACEC)
        q._AUTOX.clear()
        try:
            q._FACEC[(0, sw, 10.0, 5.0)] = float(sw) / 2 + 90.0
            auto = q.auto_crop_x(cw, 10.0, 5.0)
            ok(auto is not None,
               f"{t}: the measurement runs when a face IS present")
            got = q.head_box(None, None, at=10.0, dur=5.0)
            ok(got[2] == auto,
               f"{t}: the stale default steps aside for the measurement")
        finally:
            q._FACEC.clear(); q._FACEC.update(_fc); q._AUTOX.clear()
        q.CFG["face_crop_x"] = (sw - cw) // 2 + 37     # a hand-tuned value
        got = q.head_box(None, None, at=10.0, dur=5.0)
        ok(got[2] == (sw - cw) // 2 + 37,
           f"{t}: a deliberate face_crop_x still wins")
    finally:
        q.CFG.clear()
        q.CFG.update(cfg)


def check_broll_length(q, fps: int) -> None:
    """
    A SHORT INSERT IS A PICTURE, NOT A GHOST - and a long one is unchanged.

    The defect this exists to catch is the one that made the owner's "boom, cut
    to Elon, half a second" unrenderable for as long as it was asked for. The
    two `fade ... alpha=1` filters broll_chain emits are CHAINED, so they scale
    the same alpha plane and MULTIPLY wherever they overlap - which is any
    insert shorter than BROLL_IN + BROLL_OUT. Measured on delivered pixels
    before the fix, peak composite alpha:

        hold 0.40 -> 0.275    0.50 -> 0.498    0.60 -> 0.675    0.70+ -> 0.996

    So a half-second cutaway rendered as a permanent 50% double exposure of the
    picture over the speaker. Nothing could see it: preflight scored the hold,
    not the alpha, and the only reason it never shipped is that a separate
    guard refused anything under 0.8s.

    THE INVARIANT: the two ramps together never take more than half the window,
    so the picture is fully itself for the middle of EVERY legal insert - which
    is what the comment above BROLL_IN always claimed and only accidentally had.
    """
    IN, OUT = q.BROLL_IN, q.BROLL_OUT
    for k in (q.SPEED_MIN, 1.0, 1.06, q.SPEED_MAX):
        for hold in (0.55, 0.7, 0.9, 1.2, 1.39, 1.4, 1.8, 2.2, 3.0, 3.2, 3.6, 4.2):
            din, dout = q.broll_ramp(hold, k)
            ok(din + dout <= hold / 2.0 + 1e-9 or din + dout <= 6.0 / q.FPS + 1e-9,
               f"broll_ramp {hold}s @{k} travel {din+dout:.3f} exceeds half the window",
               "two chained alpha fades multiply where they overlap")
            ok(din >= 3.0 / q.FPS - 1e-9 and dout >= 3.0 / q.FPS - 1e-9,
               f"broll_ramp {hold}s @{k} ramp under 3 frames - that is a cut, not a blend")
            # IDENTITY where the archive lives. 217 authored holds across every
            # slate on this machine, minimum 1.8s, none below 1.4 - so every
            # clip ever shipped re-renders byte-identically.
            if hold >= 2.0 * (IN + OUT) * k:
                ok(abs(din - IN * k) < 1e-9 and abs(dout - OUT * k) < 1e-9,
                   f"broll_ramp {hold}s @{k} is not today's {IN}/{OUT} - the archive moves")

    # THE BANDS ARE DISCONTINUOUS ON PURPOSE. An insert at 2.0s is the length
    # the owner rejected by name ("the broll + signup feels very rushed"), and
    # it was the BUTTON that made it rushed. So a carrier clears the button's
    # five beats and a flash has no button to fit; nothing lands between.
    need = q.cta_insert_min()
    ok(need <= q.BROLL_HOLD_MIN + q.BROLL_IN + q.BROLL_OUT + 1e-9,
       f"the carrier floor {q.BROLL_HOLD_MIN + q.BROLL_IN + q.BROLL_OUT:.2f}s no longer "
       f"covers the invitation's {need:.2f}s - the sign-up would not fit its own insert")
    ok(q.BROLL_FLASH_MAX < need,
       f"the flash ceiling {q.BROLL_FLASH_MAX}s reaches into the carrier band "
       f"({need:.2f}s) - an insert could be long enough to look like it carries "
       f"the button and too short to hold it")
    # A FLASH NEVER DRIFTS. Below BROLL_DRIFT_MIN_HOLD the entrance drift has
    # not landed before the exit drift starts; on a same-sign pair the two ADD
    # and the insert slides off its own over-scale, uncovering a hard edge of
    # the speaker at the frame border.
    # The property is NOT "a flash never drifts" - an insert of 1.1 to 1.6s is
    # longer than the drift's own 1.05s of travel, so it lands and holds like
    # any other. The property is that NOTHING SHORTER THAN THE TRAVEL is
    # allowed to move: below that the entrance is still running when the exit
    # begins, the two ADD on a same-sign pair, and the insert slides off its
    # own over-scale. Swept over all 25 BROLL_MOVES pairs the margin against
    # BROLL_BLEED goes +10px at 0.90s, +2px at 0.55s, -96px at 0.50s.
    ok(q.BROLL_DRIFT_MIN_HOLD >= q.BROLL_FLASH_MIN - 1e-9,
       f"the drift threshold {q.BROLL_DRIFT_MIN_HOLD}s is below the flash floor "
       f"{q.BROLL_FLASH_MIN}s, so the shortest legal insert would be allowed to "
       f"move and can uncover the speaker at the frame edge")
    ok(q.BROLL_DRIFT_MIN_HOLD >= q.BROLL_DRIFT_IN + q.BROLL_DRIFT_OUT - 1e-9,
       "the drift threshold no longer covers the drift's own travel - an insert "
       "can be taken off screen while it is still moving")
    # AND THE PAN MUST NOT FOLLOW THE FLASH FLOOR DOWN. PAN_DONE is baked into
    # 1,795 assets already on disk and there is no migration path.
    ok(abs(q.BROLL_PAN_DONE
           - (q.BROLL_HOLD_MIN + q.BROLL_IN + q.BROLL_OUT) * q.SPEED_MIN) < 1e-6,
       "BROLL_PAN_DONE no longer matches what the library was baked at")

    # THE DISSOLVE'S SHAPE. `fade` writes a LINEAR alpha ramp and the linear
    # middle is where a cross-dissolve turns to mush - both of our frames are
    # busy, so at alpha 0.5 the viewer sees neither picture. BROLL_ALPHA_LUT is
    # a 256-entry table applied after the fades that re-maps the ramp onto an
    # S-curve, halving the frames that sit in the ambiguous middle (measured on
    # the delivered clip's own frames: 8 -> 4 at the shipped 0.35s ramp).
    #
    # Evaluate the REAL expression the filter graph carries, not a Python copy of
    # it - a second implementation here would drift from the string that ships.
    def _lut(v: int) -> float:
        return eval(q.BROLL_ALPHA_LUT.replace("val", str(float(v))))  # noqa: S307
    ok(abs(_lut(0)) < 1e-6, "the alpha LUT does not map 0 to 0 - a cutaway "
                            "would never be fully transparent at its edges")
    ok(abs(_lut(255) - 255.0) < 0.5,
       "the alpha LUT does not map 255 to 255 - the picture would never reach "
       "full opacity, which is the defect broll_ramp exists to prevent")
    vals = [_lut(v) for v in range(256)]
    ok(all(b >= a - 1e-9 for a, b in zip(vals, vals[1:])),
       "the alpha LUT is not monotone - the dissolve would go backwards")
    # ...and it must actually SPEND LESS TIME in the middle than the linear ramp
    # it replaces, or it is decoration. Count the input levels whose OUTPUT lands
    # in the ambiguous band.
    mid_lin = sum(1 for v in range(256) if 0.25 <= v / 255.0 <= 0.75)
    mid_lut = sum(1 for v in range(256) if 0.25 <= vals[v] / 255.0 <= 0.75)
    ok(mid_lut < mid_lin * 0.75,
       f"the alpha LUT leaves {mid_lut} of 256 levels in the ambiguous band "
       f"against {mid_lin} linear - it is not easing the middle")

    # THE GAP CEILING IS DERIVED FROM THE CUT RATE, so changing how often we cut
    # moves how long the picture may stay still. A typed constant would drift.
    ok(abs(q.BROLL_GAP_MAX - round(q.BROLL_EVERY * 1.65 / 0.98, 1)) < 1e-6,
       "BROLL_GAP_MAX is no longer derived from BROLL_EVERY")
    ok(q.BROLL_GAP_MAX > q.BROLL_MIN_FACE,
       "the gap ceiling is under the gap floor - no layout could satisfy both")


def check_picture_index(q, fps: int) -> None:
    """
    THE SECOND DOOR INTO THE LIBRARY, and the ways it can quietly stop working.

    `search_library` reaches an asset only if the caption shares words with its
    stored title. Measured over 135 real caption contexts against all 1,783 live
    rows, that leaves 291 of them (16.3%) ever reachable - so 84% of the library
    could not be retrieved at all. visual.py asks the PICTURE instead.

    Everything here runs on a synthetic index, so the suite stays offline and
    fast: loading CLIP would add about 90 seconds and a 590MB download to a run
    that takes 47.
    """
    import importlib
    import numpy as np
    visual = importlib.import_module("visual")

    # THE TWO TOWERS MUST BE THE SAME MODEL. They are compared by dot product,
    # so a mismatched pair does not raise - it returns confident nonsense, which
    # is the worst failure mode available here.
    ok(visual.MODEL_VISION.rsplit("-", 1)[0] == visual.MODEL_TEXT.rsplit("-", 1)[0],
       f"the CLIP towers are from different models ({visual.MODEL_VISION} / "
       f"{visual.MODEL_TEXT}) - their vectors are not comparable")

    # THE FLOOR IS ON THE CLIP SCALE, NOT THE TEXT SCALE. semantic.FLOOR is 0.55
    # on a sentence-embedding cosine; CLIP text-image cosines on this library run
    # about 0.18 to 0.32, so copying the other number across would return
    # nothing, for ever, silently.
    ok(0.10 < visual.FLOOR < 0.40,
       f"visual.FLOOR is {visual.FLOOR} - that is not on the CLIP scale "
       f"(0.18..0.32 measured); a text-model floor here returns nothing at all")
    ok(visual.FRAMES_PER >= 2,
       "FRAMES_PER below 2 gives one moment per asset, which is the single-title "
       "limitation this index exists to remove")

    # ROUND TRIP on a synthetic index: build the npz by hand, then prove load()
    # and search() agree about which asset a vector belongs to.
    d = Path(tempfile.mkdtemp(prefix="qmpic-st"))
    dim = 8
    keys = np.array(["a.mp4", "a.mp4", "b.mp4", "b.mp4"])
    vecs = np.zeros((4, dim), dtype="float32")
    vecs[0, 0] = 1.0          # a: frame 0 points at axis 0
    vecs[1, 1] = 1.0          # a: frame 1 points at axis 1
    vecs[2, 2] = 1.0          # b
    vecs[3, 3] = 1.0
    hub = np.zeros(4, dtype="float32")
    np.savez_compressed(visual.index_path(d), keys=keys, vecs=vecs, hub=hub)
    visual._CACHE = None
    got = visual.load(d)
    ok(got is not None and len(got) == 3, "the picture index does not round-trip")
    if got:
        k, v, h = got
        ok(list(k) == list(keys) and v.shape == (4, dim),
           "the picture index came back a different shape than it went in")
        ok(h is not None and len(h) == 4,
           "the hub array did not survive the round trip - the correction would "
           "silently become a no-op")

    # AN ASSET SCORES ITS BEST FRAME. This is what multi-frame indexing buys, and
    # it is the one behaviour a refactor is most likely to average away.
    class _FakeText:
        def embed(self, xs):
            v = np.zeros(dim, dtype="float32")
            v[1] = 1.0        # matches a's SECOND frame only
            return [v]
    visual._TXT, visual._TRIED_TXT = _FakeText(), True
    visual._CACHE = None
    hits = visual.search(d, "anything", n=4, floor=0.5)
    ok([x[0] for x in hits] == ["a.mp4"],
       f"an asset is not scored by its best frame - got {hits}. A clip that is "
       f"on subject for one second of four is exactly what this index is for.")
    visual._TXT, visual._TRIED_TXT = None, False

    # A NAMED REBUILD MUST NOT DISCARD THE REST OF THE INDEX. `build(names=[x],
    # rebuild=True)` used to write an index containing exactly x and drop
    # everything else - "re-do this one" meaning "delete the other 1,774". It
    # cost a thirty-minute rebuild to discover, from a one-line test that had
    # nothing to do with indexing, because the failure is completely silent: the
    # only symptom is that search starts answering every query with the same two
    # pictures. Proved here on a synthetic index, so it needs no model.
    d2 = Path(tempfile.mkdtemp(prefix="qmpic-rb"))
    (d2 / "index.json").write_text(json.dumps(
        {f"{n}.mp4": {"term": n, "title": n, "src": f"{n}.src"} for n in "abcd"}))
    for n in "abcd":
        (d2 / f"{n}.mp4").write_bytes(b"")
    np.savez_compressed(
        visual.index_path(d2),
        keys=np.array([f"{n}.mp4" for n in "abcd"]),
        vecs=np.eye(4, dtype="float32"), hub=np.zeros(4, dtype="float32"))
    # A build that names ONE asset: it cannot embed (no real video, no model),
    # but it must still leave the other three rows alone.
    visual._VIS, visual._TRIED_VIS = None, True      # force "no model"
    visual.build(d2, names=["a.mp4"], rebuild=True)
    visual._TRIED_VIS = False
    z2 = np.load(visual.index_path(d2), allow_pickle=False)
    ok(len(set(str(x) for x in z2["keys"])) == 4,
       f"a named rebuild left {len(set(str(x) for x in z2['keys']))} of 4 assets "
       f"- naming an asset must mean 'this row, in place', never 'discard the rest'")
    shutil_ = __import__("shutil"); shutil_.rmtree(d2, ignore_errors=True)
    visual._CACHE = None

    # AND IT DEGRADES TO NOTHING. If the index is missing, search returns [] and
    # broll.search must behave exactly as it did before this existed.
    visual._CACHE = None
    empty = Path(tempfile.mkdtemp(prefix="qmpic-none"))
    ok(visual.search(empty, "x") == [],
       "picture search does not degrade to empty when there is no index - "
       "a machine without the model would break instead of losing a feature")
    visual._CACHE = None
    # CLEAN UP AFTER THE SUITE. Both of these hold a file, so they survive an
    # "empty dir" sweep - and the suite is run many times a day. Left alone they
    # accumulate two directories per run for ever, which is the same fault
    # _sweep() was just added to visual.py to fix.
    import shutil
    for _d in (d, empty):
        shutil.rmtree(_d, ignore_errors=True)


def check_shipped_ledger(q, fps: int) -> None:
    """
    WHAT ACTUALLY SHIPPED, and the two ways this signal goes wrong.

    Before this existed, 11 of 1,807 library rows carried any usage count, and
    nothing read one to choose between two pictures that both match. The ledger
    records (picture, term) pairs that reached a DELIVERED clip.

    Runs against a throwaway ledger file so the suite never touches the real one.
    """
    import importlib
    import semantic
    broll = importlib.import_module("broll")

    # APPROVAL IS NOT DELIVERY. An insert can be approved and then dropped - four
    # were on the 08.26 clip - so anything counted before the mp4 exists records
    # rejected pictures as good ones. And an unapproved row must never count.
    d = Path(tempfile.mkdtemp(prefix="qmship"))
    real = broll.SHIPPED
    try:
        broll.SHIPPED = d / "shipped.json"
        n = broll.record_shipped("a-clip", [
            {"asset": "x.mp4", "term": "gold bullion bars", "approved": True},
            {"asset": "y.mp4", "term": "gold bullion bars", "approved": False},
            {"asset": "z.mp4", "term": "", "approved": True},
            {"asset": None, "term": "something", "approved": True},
        ])
        ok(n == 1, f"record_shipped counted {n} of 4 rows - only the approved one "
                   f"with both an asset and a term may count")
        led = broll._shipped()["assets"]
        ok(list(led) == ["x.mp4"],
           f"the ledger holds {list(led)} - an unapproved or term-less row got in")
        # TERM-CONDITIONAL, never a bare popularity count. A global counter is the
        # hub problem again: the most-used asset would start winning queries it
        # has nothing to do with, which is what the picture index exists to stop.
        ok(led["x.mp4"]["terms"].get("gold bullion bars") == 1,
           "the ledger is not recording WHICH TERM the picture shipped for")
        broll.record_shipped("b-clip", [{"asset": "x.mp4",
                                         "term": "GOLD BULLION BARS",
                                         "approved": True}])
        led = broll._shipped()["assets"]
        ok(led["x.mp4"]["terms"].get("gold bullion bars") == 2,
           "the term key is case-sensitive - the same words would split into two "
           "counters and neither would ever reach the threshold")
        ok(sorted(led["x.mp4"]["clips"]) == ["a-clip", "b-clip"],
           "the ledger is not recording which clips a picture shipped in, so a "
           "wrong pairing cannot be traced back")
    finally:
        broll.SHIPPED = real
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # THE SIGNAL HAS TO REACH THE FLOOR, which is where all of its value is.
    # Measured leave-one-out over 180 approved inserts, a last-position tie-break
    # changed NOTHING (91/180 either way); rescuing over the floor is what moved
    # it. If somebody demotes this back to a tie-break, that is a silent revert.
    hit = {"title": "a picture", "url": "/lib/src/a.mp4", "page": "",
           "score": 0.0, "picture_score": 0.0}
    kept, _ = semantic.rerank("a sentence about something else entirely",
                              [dict(hit)], term="x",
                              preferred={"/lib/src/a.mp4"})
    ok(len(kept) == 1 and kept[0].get("shipped_before"),
       "a picture that already shipped for this term is being dropped by the "
       "floor - the ledger is then decoration")
    kept2, _ = semantic.rerank("a sentence about something else entirely",
                               [dict(hit)], term="x", preferred=set())
    ok(kept2 == [] or not kept2[0].get("shipped_before"),
       "a picture with no shipping history is being treated as if it had one")
    # ...but the bonus must stay SMALL, or it stops being a preference and starts
    # overruling meaning.
    ok(0.0 < semantic.SHIPPED_BONUS <= 0.25,
       f"SHIPPED_BONUS is {semantic.SHIPPED_BONUS} - above a quarter of a score "
       f"bucket it outranks a clearly better match on what the sentence is about")


def check_people_reachable(q, fps: int) -> None:
    """
    A NAMED PERSON MUST BE PICTURABLE, and for 1,683 of them they were not.

    `_is_concrete` is the gate that decides whether the candidate walk even
    offers a word to the ranker. It tested EXPAND, the learned vocabulary and a
    hint list - and PEOPLE was in none of them. Measured when this was found:
    1,683 of 1,688 PEOPLE rows failed it, so the entire portrait tier, with its
    curated names and its public-domain licence handling, was unreachable from
    ordinary speech for 100% of the people in it. Donald Trump shipped in a
    delivered clip only because "trump" happens also to be an English word with
    an EXPAND row.

    This is the check that would have caught it on the day the tier was built.
    """
    import importlib
    broll = importlib.import_module("broll")
    bad = [k for k in broll.PEOPLE if " " not in k and not broll._is_concrete(k)]
    ok(len(bad) <= 1,
       f"{len(bad)} of {len(broll.PEOPLE)} PEOPLE keys are invisible to the "
       f"candidate walk (e.g. {bad[:4]}) - the portrait tier cannot be reached "
       f"from speech for them")
    for who in ("elon", "musk"):
        if who in broll.PEOPLE:
            ok(broll._is_concrete(who),
               f"{who!r} is in PEOPLE and resolves to {broll.query_for(who)!r}, "
               f"but the walk will not offer it")

    # ONE CLEARANCE, READ ONCE. A flash may sit inside the tail clearance so a
    # name spoken near the end can still be shown - but the hold was then
    # clamped against the FULL clearance three lines later, driving it negative.
    # "Elon" passed the test that was changed for it and was dropped by the one
    # that was not. Both now read the same value.
    import inspect
    src = inspect.getsource(broll.candidates)
    ok("body - tail_clear - t" not in src,
       "candidates() still clamps a hold against the full tail clearance while "
       "the window test uses the flash exemption - two readings of one number")
    ok(q.BROLL_TAIL_FACE < q.BROLL_TAIL_CLEAR,
       "BROLL_TAIL_FACE is not below BROLL_TAIL_CLEAR, so the flash exemption "
       "grants nothing")


def check_carried_subject(q, fps: int) -> None:
    """
    WHO THE CLIP IS ABOUT WHEN IT NEVER SAYS THE NAME.

    A clip cut from the middle of a segment inherits its subject: the show says
    "Bill Gates' 6,000 word warning" and then discusses him for two minutes as
    "he". The pipeline had no way to know, and shipped a clip about one of the
    most recognisable faces in technology without ever showing him.

    Synthetic cues, so this is fast and needs no work directory.
    """
    import importlib
    context = importlib.import_module("context")
    PEOPLE = {"bill gates": ("Bill Gates", "microsoft campus"),
              "elon musk": ("Elon Musk", "rocket launch"),
              "lindsay ellis": ("Lindsay Ellis", "newsroom")}

    # THE CASE IT WAS BUILT FOR: named once before the span, possessively, then
    # only pronouns inside.
    cues = [(100.0, 110.0, "Lindsay Ellis has put this out about the three "
                           "takeaways from Bill Gates' warning on AI."),
            (140.0, 150.0, "He's saying that AI will hit blue collar jobs."),
            (150.0, 160.0, "And he says his view is that it takes a decade.")]
    got = context.carried_subject(cues, 140.0, 160.0, PEOPLE)
    ok(got is not None and got[0] == "Bill Gates",
       f"the carried subject came back {got!r} - a passage named possessively "
       f"before the span and continued with pronouns is the case this exists for")

    # ...AND THE POSSESSIVE IS WHAT BREAKS THE TIE. Both are named once, in one
    # sentence; only one of them owns the subject.
    flat = [(100.0, 110.0, "Lindsay Ellis spoke and Bill Gates spoke."),
            (140.0, 150.0, "He's saying that AI will hit blue collar jobs."),
            (150.0, 160.0, "And he says his view is that it takes a decade.")]
    ok(context.carried_subject(flat, 140.0, 160.0, PEOPLE) is None,
       "two people named equally should be refused - 'he' is genuinely "
       "ambiguous there and a wrong face is worse than no face")

    # A COMPANY IS "THEY". Admitting they/their made a clip about a shoe company
    # resolve to a person named in an unrelated segment.
    corp = [(100.0, 110.0, "Bill Gates' warning on AI."),
            (140.0, 150.0, "Nike still sells shoes and they are an elite brand."),
            (150.0, 160.0, "Their numbers are coming down but they can turn it.")]
    ok(context.carried_subject(corp, 140.0, 160.0, PEOPLE) is None,
       "a span whose only pronouns are 'they/their' resolved to a person - "
       "on this material that is almost always a company")

    # THE TITLE IS THE CHEAPER HALF OF THE SAME FIX, and the sheet and preflight
    # must agree about it. A viewer who reads "Bill Gates" in the headline
    # already knows who "he" is - which is most of what the portrait was for,
    # and it reaches the far larger number of people who never press play.
    import importlib
    ms = importlib.import_module("make_sheet")
    silent = {"about": "Bill Gates", "rank": 1, "hook": "Not just white collar",
              "titles": ["Not just white collar"], "platform_caption": "",
              "linkedin_caption": ""}
    named = dict(silent, titles=["Bill Gates: not just white collar"])
    ok("warn" in ms.about_block(silent),
       "the sheet does not flag a clip that is about a named person no title "
       "mentions - the operator types the headline with no idea")
    ok("warn" not in ms.about_block(named) and ms.about_block(named),
       "the sheet still warns once a title names him")
    ok(ms.about_block({"rank": 1}) == "",
       "the sheet prints an about note on a clip with no carried subject")

    # AND "He's" MUST COUNT. Apostrophes are removed, not stripped from the ends:
    # "He's" -> "he's" is not "hes", and that scored the founding case 1 pronoun.
    ok(context._norm("He's") == "hes",
       f"_norm('He's') is {context._norm(chr(39).join(['He','s']))!r} - the "
       f"commonest third-person pronoun in speech would match nothing")


def check_drift(q, fps: int) -> None:
    """
    THE FRAME IS NEVER DEAD, AND THE DRIFT DOES NOT JUDDER.

    `punch` is a two-state toggle, so between flips the camera does not move at
    all - measured on the 08.28 clip, a LONGEST UNCHANGED HOLD OF 9.1 SECONDS
    while the cutaways around it drifted the whole time. face_chain lays a slow
    continuous move under the punch so the toggle is the accent rather than the
    only motion.

    Both shapes here were arrived at by measurement, and the first one was wrong:

      sine + 2px grid   stalls of 44 and 54 frames (1.5-1.8s), then a 2px jump
      triangle + 1px    moves on some axis every 2 frames, worst gap 4

    A sine spends its time near a turning point where velocity goes to zero, and
    a pixel grid turns "very slow" into "stopped". A triangle holds constant
    speed and only turns twice per period.
    """
    t = f"drift@{fps}"
    ok(hasattr(q, "face_chain"), f"{t}: face_chain exists")
    ch = q.face_chain()

    if not q.DRIFT_ON:
        ok("crop=" not in ch.split("scale=")[-1], f"{t}: drift off means no moving crop")
        return

    # THE OUTPUT IS STILL THE PANEL. An over-scale that forgets to crop back
    # ships a 1124x1996 picture into a 1080x1920 panel.
    ok(f"crop={q.PANEL_W}:{q.PANEL_H}:" in ch,
       f"{t}: crops back to the panel exactly")
    ok(ch.startswith(f"scale={q._even(q.PANEL_W * (1 + q.DRIFT_OVERSCALE))}:"),
       f"{t}: over-scales before cropping")
    # THE COMMA INSIDE mod() MUST BE ESCAPED or it ends the filter early.
    ok(chr(92) + "," in ch, f"{t}: the mod() comma is escaped for ffmpeg")

    # EVALUATE THE EXPRESSION face_chain ACTUALLY EMITS, do not re-implement it.
    # This block used to define its own Python triangle and test THAT, so the
    # checks below passed no matter what the filter string said - a sine on a
    # 2px grid, the exact shape that juddered, would have gone green. Parse the
    # real crop expression out of the chain and evaluate it with ffmpeg's own
    # operator set, so the thing under test is the thing that ships.
    import math
    import re as _re

    _m = _re.search(r"crop=\d+:\d+:([^:]+):(.+?)(?:,eq=|$)", ch)
    ok(bool(_m), f"{t}: the chain carries a crop with two expressions")
    if not _m:
        return

    def _ff(expr: str, x: float) -> float:
        """Evaluate one ffmpeg crop expression at time x."""
        e = expr.replace(chr(92) + ",", ",")          # un-escape the mod() comma
        return eval(e, {"__builtins__": {}},          # noqa: S307 - our own string
                    {"t": x, "PI": math.pi, "abs": abs, "round": round,
                     "sin": math.sin, "cos": math.cos,
                     "mod": lambda a, b: a % b})

    _xe, _ye = _m.group(1), _m.group(2)

    def tri(a, per, x):
        return a * (4 * abs((x / per + 0.25) % 1 - 0.5) - 1)

    sw, sh = (q._even(q.PANEL_W * (1 + q.DRIFT_OVERSCALE)),
              q._even(q.PANEL_H * (1 + q.DRIFT_OVERSCALE)))
    mx, my = sw - q.PANEL_W, sh - q.PANEL_H
    cxm, cym = mx / 2.0, my / 2.0 + q.DRIFT_BIAS_Y
    ax = min(q.DRIFT_AMP_X, max(0.0, cxm - 2))
    ay = min(q.DRIFT_AMP_Y, max(0.0, min(cym, my - cym) - 2))

    # IT STARTS CENTRED. The clip must open on the framing preflight measured,
    # not on an extreme of the travel.
    ok(abs(tri(ax, q.DRIFT_PERIOD_X, 0.0)) < 1e-9,
       f"{t}: x starts at the middle of its travel")
    ok(abs(tri(ay, q.DRIFT_PERIOD_Y, 0.0)) < 1e-9,
       f"{t}: y starts at the middle of its travel")

    # FFMPEG FLOORS crop x/y TO EVEN ON yuv420p - measured, crop x=10 and x=11
    # render byte-identical - so the expression's own rounding is not what
    # ships. Model the floor here or this test grades a grid the viewer never
    # sees, which is exactly how the first version of this drift was declared
    # judder-free while delivering 2px steps.
    _even = lambda v: int(v) // 2 * 2
    xs = [_even(_ff(_xe, i / fps)) for i in range(fps * 30)]
    ys = [_even(_ff(_ye, i / fps)) for i in range(fps * 30)]
    # the emitted expression must agree with the shape this test reasons about
    ok(abs(xs[0] - round(cxm)) <= 1 and abs(ys[0] - round(cym)) <= 1,
       f"{t}: the emitted crop starts at the middle of its travel "
       f"({xs[0]},{ys[0]}) vs ({round(cxm)},{round(cym)})")
    # NEVER OFF ITS OWN MARGIN - a clamped drift stops dead, which is worse
    # than not drifting.
    ok(min(xs) >= 0 and max(xs) <= mx, f"{t}: x stays inside the margin")
    ok(min(ys) >= 0 and max(ys) <= my, f"{t}: y stays inside the margin")

    # NO STALL. This is the check that would have caught the sine.
    worst = 0
    run = 1
    for i in range(1, len(xs)):
        if xs[i] == xs[i - 1] and ys[i] == ys[i - 1]:
            run += 1
            worst = max(worst, run)
        else:
            run = 1
    # On the delivered 2px grid the achievable bar is a step every ~4 frames
    # per axis; the two axes are on different periods so the FRAME moves about
    # every 2. Measured on real delivered pixels: median 2 frames, worst 27 at
    # a turning point where both axes reverse together.
    ok(worst <= fps,
       f"{t}: never still for more than {fps} frames (worst {worst})")
    # AND IT ACTUALLY MOVES.
    ok(max(xs) - min(xs) >= 8 and max(ys) - min(ys) >= 8,
       f"{t}: travels a visible distance (x {max(xs)-min(xs)}px, y {max(ys)-min(ys)}px)")

    # THE GRADE IS LIGHT. A look, not a LUT.
    if q.GRADE_ON:
        ok(1.0 < q.GRADE_CONTRAST <= 1.10, f"{t}: contrast lift stays subtle")
        ok(1.0 < q.GRADE_SATURATION <= 1.15, f"{t}: saturation lift stays subtle")
        ok("eq=" in ch, f"{t}: the grade is in the chain the colour probe samples")


def check_caption_colours(q, fps: int) -> None:
    """
    THE FUNCTION THAT DECIDES WHETHER A VIEWER CAN READ THE WORDS had no test.

    choose_caption_colours picks the base, stroke and keyword colour for a clip
    from its measured background, and its own docstring records a defect it was
    written to prevent: cyan on navy clears a contrast bar on paper and still
    disappears, because the eye reads HUE before luminance. Nothing exercised
    either axis.
    """
    t = f"capcol@{fps}"
    ok(hasattr(q, "choose_caption_colours"), f"{t}: exists")

    def pick(lum, hue=210.0, split=False):
        return q.choose_caption_colours({"lum": lum, "hue": hue, "split": split})

    dark_bg, light_bg = pick(0.05), pick(0.85)
    for name, got in (("dark", dark_bg), ("light", light_bg)):
        ok(isinstance(got, dict) and {"base", "stroke", "key"} <= set(got),
           f"{t}: {name} background returns base/stroke/key")

    # THE INK MUST SEPARATE FROM THE BACKGROUND IT WAS CHOSEN FOR. Same axis the
    # function scores, checked end to end rather than trusted.
    for lum, label in ((0.03, "near-black"), (0.35, "mid"), (0.92, "near-white")):
        got = pick(lum)
        c = abs(q.rel_lum(got["base"]) - lum)
        ok(c > 0.25, f"{t}: base separates from a {label} background "
                     f"(contrast {c:.2f})")
        cs = abs(q.rel_lum(got["stroke"]) - q.rel_lum(got["base"]))
        ok(cs > 0.25, f"{t}: the stroke separates from the base on {label} "
                      f"(contrast {cs:.2f})")

    # A CLIP THAT SWINGS ACROSS THE FLIP POINT TAKES THE SAFE SET. Ink type over
    # a dark half is unreadable; bone with a heavy stroke survives both.
    swung = q.choose_caption_colours({"lum": 0.9, "hue": 210.0, "split": True})
    steady = q.choose_caption_colours({"lum": 0.9, "hue": 210.0, "split": False})
    ok(swung != steady or q.rel_lum(swung["base"]) > 0.5,
       f"{t}: a split background does not take the dark set")

    # AND THE KEYWORD IS NOT THE SAME COLOUR AS THE BASE, or the highlight
    # this show uses to carry the noun does nothing at all.
    for lum in (0.05, 0.5, 0.9):
        got = pick(lum)
        ok(got["key"] != got["base"],
           f"{t}: the keyword colour differs from the base at lum {lum}")


def check_templates(q, fps: int) -> None:
    """
    THREE TEMPLATES, AND TWO PEOPLE ARE NEVER ON SCREEN AT ONCE.

    The owner's rule, 2026-08-28: "it should always be one person talking at one
    time... they'll never be cut side by side." That is enforceable and worth
    enforcing, because the two modes that break it - duo and duo_share - are
    still in the file for archived re-cuts and a slate can still name them.
    """
    t = f"tpl@{fps}"
    # THE PICTURE LEADS THE VOICE. See FOLLOW_LEAD.
    ok(0.03 <= q.FOLLOW_LEAD <= 0.25,
       f"tpl@{fps}: follow cuts lead the voice by 1-7 frames "
       f"({q.FOLLOW_LEAD * fps:.1f} frames)")
    ok(q.FOLLOW_LEAD < q.BROLL_IN if hasattr(q, "BROLL_IN") else True,
       f"tpl@{fps}: the lead is shorter than a cutaway's dissolve")

    ok(set(q.TEMPLATES) == {"head", "conversation", "conversation_share"},
       f"{t}: the three templates changed", str(q.TEMPLATES))
    for m in q.TEMPLATES:
        ok(m in q.MODE_NEEDS, f"{t}: template {m!r} has no MODE_NEEDS entry")
        try:
            q.split_labels(m)
        except Exception as e:                                    # noqa: BLE001
            ok(False, f"{t}: split_labels({m!r}) raised {type(e).__name__}")
    ok(q.canonical_mode("head_follow") == "conversation",
       f"{t}: the head_follow alias no longer resolves")
    for m in ("duo", "duo_share"):
        try:
            q.canonical_mode(m)
            ok(False, f"{t}: {m!r} was accepted - it puts two people on screen")
        except SystemExit:
            ok(True, "")
        ok(q.canonical_mode(m, allow_legacy=True) == m,
           f"{t}: the legacy escape for {m!r} does not work")

    # THE CONVERSATION MODES REFUSE TO GUESS. Both need a measured turn
    # schedule; without one they would hold a single speaker for the whole clip,
    # which is the defect the templates exist to remove.
    for m, kw in (("conversation", dict(follow_crops=[[516,917,150,0],[516,917,1392,0]])),
                  ("conversation_share", dict(follow_pips=[[348,276,8,260],[348,264,8,544]],
                                              share_crop=[1448,1064,364,8]))):
        try:
            q.reframe_chain(m, 60.0, slug="t", start=0.0, end=60.0, **kw)
            ok(False, f"{t}: {m!r} built a chain with NO turn schedule")
        except SystemExit:
            ok(True, "")
        g = q.reframe_chain(m, 60.0, slug="t", start=0.0, end=60.0,
                            follow_windows=[(5.0, 15.0)], **kw)
        ok("overlay=0:0:enable=" in g,
           f"{t}: {m!r} does not switch between the two speakers")
        # exactly two people's crops, and they meet at an ENABLE-gated overlay -
        # i.e. one at a time - never at a stack.
        #
        # The test names the FACE labels rather than looking for "vstack"
        # anywhere in the graph: fit_chain uses a vstack to extend the app's
        # bottom edge, which has nothing to do with people, and the first
        # version of this check failed on it.
        ok(g.count("crop=") >= 2, f"{t}: {m!r} does not crop two tiles")
        import re as _re
        pair = _re.search(r"\[(\w+)\]\[(\w+)\]overlay=0:0:enable=", g)
        ok(bool(pair), f"{t}: {m!r} does not switch its two tiles on an enable gate")
        if pair:
            a, b = pair.groups()
            ok(f"[{a}]" in g.split("overlay=0:0:enable=")[0]
               and f"[{b}]" in g.split("overlay=0:0:enable=")[0],
               f"{t}: {m!r} switch inputs are not the two cropped tiles")
            for st in ("vstack", "hstack"):
                seg = g[:g.index("overlay=0:0:enable=")]
                ok(st not in seg,
                   f"{t}: {m!r} {st}s the two people before switching them")

    # Neither conversation mode may fall back to the show's host for the
    # nameplate: the frame changes person part way through.
    for m in ("conversation", "conversation_share"):
        n, _r = q.speaker_label(None, m)
        ok(n == "", f"{t}: {m!r} fell back to the host for the nameplate")


def check_cut(q, fps: int) -> None:
    """
    THE BODY IS ACTUALLY CUT, and it is cut the same way by both modes.

    cut_graph had NO automated coverage until 2026-08-28, and it is the function
    whose silent failure this file's history records most expensively: a
    head-anchored removal that was the only removal produced one kept span, the
    old `len(keep) < 2` test returned the PASSTHROUGH graph, and the body shipped
    its full length while out_dur, the captions, the hook, the CTA, the .srt and
    the out-fade were all authored shorter. Nothing warned. preflight cannot
    catch it - it never calls cut_graph.
    """
    t = f"cut@{fps}"
    cases = [
        ("none",     [],                                   30.0),
        ("mid",      [(10.0, 11.0)],                       30.0),
        ("head",     [(0.0, 2.0)],                         30.0),
        ("tail",     [(28.0, 30.0)],                       30.0),
        ("many",     [(5.0,5.4),(12.0,12.6),(20.0,20.3)],  30.0),
        ("adjacent", [(5.0,5.4),(5.4,6.0)],                30.0),
    ]
    for name, rem, dur in cases:
        keep = q.keep_spans(rem, dur)
        kept = sum(e - s for s, e in keep)
        want = dur - sum(e - s for s, e in rem)
        ok(abs(kept - want) < 1e-9, f"{t}/{name}: kept {kept:.3f}s, arithmetic says {want:.3f}s")
        ok(all(a < b for a, b in keep), f"{t}/{name}: a kept span is empty or inverted", str(keep))
        ok(all(keep[i][1] <= keep[i+1][0] for i in range(len(keep)-1)),
           f"{t}/{name}: kept spans overlap", str(keep))

    # ONE OWNER FOR THE SPANS. The two modes are two implementations of one
    # transformation; the moment they disagree about WHAT to keep they are two
    # definitions of one quantity, which is the trap this file keeps recording.
    for name, rem, dur in cases:
        old, q.CUT_MODE = q.CUT_MODE, "select"
        sel = q.cut_graph(rem, dur, None)
        q.CUT_MODE = "trim"
        trm = q.cut_graph(rem, dur, None)
        q.CUT_MODE = old
        ok(bool(sel[0]) == bool(trm[0]) or not rem,
           f"{t}/{name}: one mode cuts and the other passes through")

    # A SINGLE KEPT SPAN MUST STILL CUT. This is the shipped bug, in one line.
    pre, v, a = q.cut_graph([(0.0, 2.0)], 30.0, None)
    ok(pre != "" and v != "0:v",
       f"{t}: a head-anchored removal returned the passthrough graph - "
       f"the body would ship its FULL length")

    # HALF-OPEN, NOT `between`. between() is inclusive at both ends, so it keeps
    # the frame sitting exactly on a span's end that trim excludes - one frame
    # per span, up to 40 on a real clip.
    old, q.CUT_MODE = q.CUT_MODE, "select"
    pre, _v, _a = q.cut_graph([(10.0, 11.0)], 30.0, None)
    q.CUT_MODE = old
    ok("gte(t," in pre and "lt(t," in pre,
       f"{t}: the select expression is not half-open")
    ok("between(t," not in pre.split("aselect")[0],
       f"{t}: the video select uses between(), which double-counts a boundary frame")

    # THE MUTE RUNS BEFORE THE SELECT. Mute windows are authored in SPAN time;
    # after the select `t` is OUTPUT time and they would land somewhere else.
    old, q.CUT_MODE = q.CUT_MODE, "select"
    pre, _v, _a = q.cut_graph([(10.0, 11.0)], 30.0, [(2.0, 3.0)])
    q.CUT_MODE = old
    ok(pre.index("volume=0") < pre.index("aselect"),
       f"{t}: the mute is applied AFTER the select, so its windows are in the "
       f"wrong clock")

    # The passthrough must hand back INPUT labels, which may be consumed more
    # than once - an output label may not, and that is the asplit footgun.
    pre, v, a = q.cut_graph([], 30.0, None)
    ok(v == "0:v" and a == "0:a" and pre == "",
       f"{t}: no removals should be a true passthrough")


def main() -> None:
    for fps in (25, 30):
        q = _load(fps)
        check_pill(q, fps)
        check_nameplate(q, fps)
        check_cutaway(q, fps)
        check_bands(q, fps)
        check_head_box(q, fps)
        check_cut(q, fps)
        check_templates(q, fps)
        check_speaker_tracks(q, fps)
        check_speaker_transcript(q, fps)
        check_second_plate(q, fps)
        check_caption_floor(q, fps)
        check_centring(q, fps)
        check_drift(q, fps)
        check_broll_length(q, fps)
        check_picture_index(q, fps)
        check_shipped_ledger(q, fps)
        check_people_reachable(q, fps)
        check_carried_subject(q, fps)
        check_caption_colours(q, fps)
        check_pick(q, fps)
    check_vocab()
    # the instrument before the measurement: prove the file-level detectors can
    # still report anything at all before trusting them on a real clip
    if any(Path(a).exists() for a in sys.argv[1:]):
        check_detectors()
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_dir():
            for f in sorted(p.glob("*.mp4")):
                check_clip(f)
        elif p.exists():
            check_clip(p)

    print(f"\n{CHECKS[0]} checks")
    if FAILS:
        print(f"\n{len(FAILS)} FAILED\n")
        for f in FAILS:
            print(f"  x {f}")
        raise SystemExit(1)
    print("all clear\n")


if __name__ == "__main__":
    main()
