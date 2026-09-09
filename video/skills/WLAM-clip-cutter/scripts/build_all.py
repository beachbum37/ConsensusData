#!/usr/bin/env python3
"""Render every clip in the slate, then write the posting sheet."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# THE RENDERER NEEDS PYTHON 3.12+, AND SAYS SO HERE RATHER THAN AS A SyntaxError.
# qmclip.py uses backslashes inside f-string expressions, which is legal only from
# 3.12. Under 3.11 every earlier step - analyze, pick, preflight - imports and runs
# clean, and the job dies at `import qmclip` with a bare SyntaxError naming a line
# 5,000 deep in a file the operator did not open. SKILL.md warns about numpy and
# Pillow and says "do not assume python3 is it", which is the right hazard and the
# wrong cause: on a machine carrying both 3.11 and 3.13 the version is what picks
# the failure. Fail here, with the fix in the message.
if sys.version_info < (3, 12):
    raise SystemExit(
        f"\nThis renderer needs Python 3.12 or newer; you are on "
        f"{sys.version_info.major}.{sys.version_info.minor} "
        f"({sys.executable}).\n"
        f"Everything up to the render works on 3.11, so a job can get this far\n"
        f"and then fail on the import. Re-run with a 3.12+ interpreter that has\n"
        f"numpy and Pillow:\n"
        f"    python3.13 build_all.py\n"
        f"Check with: python3.13 -c \"import numpy, PIL\"\n")


import qmclip

# The slate is PER-SHOW state, so it follows WLAM_WORK like everything else. This
# script was the one missed when the rest moved, and the failure was quiet in the
# worst way: with WLAM_WORK set it read the DEFAULT directory's slate and started
# re-rendering a DELIVERED clip, which is the one thing SKILL.md's first rule
# forbids. qmclip already resolves it, so take it from there rather than keeping
# a fourth copy of the same decision.
SLATE = qmclip.WORK / "slate.json"
# Where poster() took each cover frame from. A sidecar so the build never has to
# write back to the hand-edited slate - see the note where it is populated.
POSTERS = qmclip.WORK / "posters.json"
DELIVER = qmclip.DELIVER


def _preflight(slugs: list[str] | None) -> None:
    """
    RENDERING REQUIRES A CLEAN PREFLIGHT. Nothing used to make you run it.

    preflight.py has always existed, has always exited non-zero on a failure, and
    SKILL.md has always said "Run preflight BEFORE you render. Always." - and
    build_all.py never mentioned it. So the whole guard was a habit: every rule
    it enforces was enforced only for as long as somebody remembered to type a
    second command. That is not what the owner means by "we want to be able to
    make a clip and not even have to think about problems."

    A subprocess rather than an import, because preflight's main() calls
    sys.exit() and owns its own output formatting; running it as the operator
    would run it means what you see here is exactly what you would have seen.

    --force renders anyway, and says loudly that it did. There are real reasons
    to use it - a GRAPHIC warning on a busy master, a set-wide b-roll repeat you
    have decided to accept - and none of them should be silent.
    """
    if "--force" in sys.argv:
        print("!! --force: rendering WITHOUT a clean preflight. Whatever it would "
              "have refused is going out in this set.\n", flush=True)
        return
    cmd = [sys.executable, str(Path(__file__).with_name("preflight.py"))] + (slugs or [])
    print("preflight...", flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(
            "\nNOT RENDERED. preflight refused the slate above - fix it and run "
            "again.\nIf you have read every line and want it anyway: "
            "build_all.py --force\n")

    # THE SET GATE'S MISSING HALF, run here for the same reason preflight is:
    # a check nobody is made to type is a habit, not a guard. check_broll already
    # refuses the same PICTURE in two clips of one set; nothing looked at the
    # WORDS, so two clips of a host restating a point both pass every measure and
    # only read as a duplicate to a viewer meeting them back to back.
    #
    # Whole-slate only. Scoring a subset would compare the named clip against
    # nothing and print ALL CLEAR, which is the false green build_all already
    # learned to refuse for a mistyped slug.
    if not slugs:
        print("set content...", flush=True)
        r = subprocess.run([sys.executable,
                            str(Path(__file__).with_name("checkdupes.py"))])
        if r.returncode != 0:
            raise SystemExit(
                "\nNOT RENDERED. Two clips in this set carry the same speech - see\n"
                "above. Drop one, move a span, or set \"dupe_ok\": true on a clip.\n"
                "If you have read the shared runs and want it anyway: "
                "build_all.py --force\n")


def main() -> None:
    slate = json.loads(SLATE.read_text())
    clips = sorted(slate["clips"], key=lambda c: c["rank"])
    only = [a for a in sys.argv[1:] if not a.startswith("-")] or None
    # A MISTYPED SLUG IS NOT AN EMPTY RUN. Both files filter the slate by name and
    # neither checked that the name matched anything, so `preflight.py
    # tarifs-timed-to-early-voting` skipped every clip, checked nothing, printed
    # ALL CLEAR and exited 0 - and build_all did the same and rendered nothing,
    # also exiting 0. Two green runs and no work done, which is the worst kind of
    # pass because it looks exactly like success.
    _known = {c["slug"] for c in clips}
    _unknown = sorted(set(only or []) - _known)
    if _unknown:
        raise SystemExit(
            f"\nNo clip named {', '.join(repr(u) for u in _unknown)} in this "
            f"slate.\nThe slugs are:\n"
            + "".join(f"  {s}\n" for s in sorted(_known)))
    _preflight(only)

    posters = {}
    if POSTERS.exists():
        try:
            posters = json.loads(POSTERS.read_text())
        except ValueError:
            posters = {}

    DELIVER.mkdir(parents=True, exist_ok=True)
    (DELIVER / "clips").mkdir(exist_ok=True)
    (DELIVER / "captions").mkdir(exist_ok=True)

    for c in clips:
        name = f"{c['rank']:02d}-{c['slug']}"
        if only and c["slug"] not in only:
            continue
        t0 = time.time()
        # A WELDED CLIP IS NOT AS LONG AS ITS SPAN. Printing end-start on a
        # two-moment clip announces "241.0s" for a 78-second clip, which reads
        # as a slate error every time you see it.
        _gone = sum(float(b) - float(a) for a, b in (c.get("drop") or []))
        print(f"[{name}] {c['start']:.1f}s -> {c['end']:.1f}s "
              f"({c['end']-c['start']-_gone:.1f}s"
              + (f", {_gone:.0f}s welded out" if _gone else "")
              + f")  {c['hook']!r}", flush=True)
        qmclip.render(name, c["start"], c["end"], c["hook"],
                      mode=c.get("mode", "head"), crop_x=c.get("crop_x"),
                      head_crop=c.get("head_crop"),
                      pip_crop=c.get("pip_crop"),
                      share_crop=c.get("share_crop"),
                      face_h=c.get("face_h"),
                      duo_crops=c.get("duo_crops"),
                      mute=c.get("mute"),
                      drop=c.get("drop"),
                      hard_out=c.get("hard_out"),
                      cap_colour=c.get("cap_colour"),
                      broll=c.get("broll"),
                      speed=c.get("speed"),
                      allow_ragged_end=c.get("allow_ragged_end", False),
                      layout_ok=c.get("layout_ok", False),
                      follow_crops=c.get("follow_crops"),
                      follow_pips=c.get("follow_pips"),
                      follow_tiles=c.get("follow_tiles"),
                      allow_legacy_duo=c.get("allow_legacy_duo", False),
                      speakers=c.get("speakers"),
                      speaker_verified=c.get("speaker_verified", False),
                      speaker=c.get("speaker"))
        src = DELIVER / "clips" / f"{name}.mp4"
        print(f"   done in {time.time()-t0:.0f}s  "
              f"{src.stat().st_size/1e6:.1f}MB", flush=True)
        # THE PICTURES THAT ACTUALLY SHIPPED. Recorded HERE, after the mp4
        # exists, and not at fetch: approval is not delivery. Four inserts were
        # approved and then dropped on the 08.26 clip alone - one for colliding
        # with the nameplate, two as duplicates - and counting them at fetch
        # would have filed four rejected pictures as good ones.
        try:
            import broll
            _n = broll.record_shipped(c["slug"], c.get("broll"))
            if _n:
                print(f"   learned: {_n} picture(s) shipped for their terms",
                      flush=True)
        except Exception as e:      # never let bookkeeping fail a delivered clip
            print(f"   note: could not record shipped pictures "
                  f"({type(e).__name__})", flush=True)
        srt = qmclip.CAPDIR / f"{name}.srt"
        dst = DELIVER / "captions" / f"{name}.srt"
        # WLAM_WORK pointed at the show's own folder - the documented per-show
        # setup - makes CAPDIR and DELIVER the same directory, and shutil.copy
        # raises SameFileError on a file onto itself. The caption is already
        # where it belongs in that case.
        if srt.exists() and srt.resolve() != dst.resolve():
            shutil.copy(srt, dst)

        # Record where poster() took the cover frame from, so make_sheet.py can
        # print it beside the thumbnail. It has to be PERSISTED and not left in
        # qmclip.POSTER_AT, because the sheet is regularly re-run in a fresh
        # process - days later, over an archived show - where that dict is empty.
        #
        # A SIDECAR, NOT THE SLATE. Writing the whole slate document back after
        # every clip republishes a copy read at t=0, across a 15-30 minute build:
        # anything a human typed into slate.json in the meantime - a caption, a
        # hashtag, a ticker - is silently reverted, and re-running build_all with
        # WLAM_WORK pointed at a delivered _project/ would mutate an archived show's
        # slate. The rest of this pipeline treats slate.json as a hand-edited
        # document that only the operator and broll.py's own CLI write to. Keep
        # it that way.
        at = qmclip.POSTER_AT.get(name)
        if at is not None:
            posters[name] = round(at, 2)
            POSTERS.write_text(json.dumps(posters, indent=1))

    # The caption colour is chosen per clip from what is behind it, so it is the
    # one thing in this look that can differ between two clips in the same set.
    # Print the picks together: a single clip's choice is visible in its own log
    # line, but whether the SET still reads as a set is only visible here.
    # Anything shipped with a ragged ending is named HERE, at the end, not left
    # in a stderr line six clips back. The whole reason the ending rule became a
    # refusal is that a warning mid-run scrolls past and the clip ships.
    if qmclip.RAGGED_ENDS:
        print("\nENDS MID-SENTENCE (shipped on \"allow_ragged_end\")")
        for name in qmclip.RAGGED_ENDS:
            print(f"  {name}")
        print("  Listen to the tail of each before handing these over.")

    # The loudness SPREAD, which is the thing that matters and which a per-clip
    # line cannot show. One clip at -15.9 LUFS is fine on its own; it is only
    # wrong next to a sibling at -14.0, and a viewer meets them back to back in a
    # feed. Measured across 16 delivered clips before this existed: sd 0.48 LU,
    # 1.92 LU end to end.
    loud = qmclip.LOUDNESS
    if len(loud) > 1:
        vals = [i for i, _tp in loud.values()]
        spread = max(vals) - min(vals)
        print("\nLOUDNESS")
        for name, (I, TP) in loud.items():
            print(f"  {name:<46} I={I:7.2f} LUFS   TP={TP:6.2f} dBTP")
        print(f"  {'spread across the set':<46} {spread:7.2f} LU")
        tb = qmclip.TIMBRE
        if len(tb) > 1:
            tv = list(tb.values())
            tspread = max(tv) - min(tv)
            print(f"  {'4-6kHz spread across the set':<46} {tspread:7.2f} dB")
            if tspread > 4.0:
                print("  NOTE: over 4 dB of brightness between clips. That is two")
                print("  different microphones, not two different rooms. Worth")
                print("  fixing at the source rather than in the render.")
        if spread > 1.0:
            print("  NOTE: over a dB between the quietest and loudest clip in this")
            print("  set. Played back to back in a feed that is audible. Check the")
            print("  source levels for the outlier before handing these over.")

    picked = qmclip.CHOSEN_COLOURS
    if picked:
        print("\nCAPTION COLOURS")
        for name, col in picked.items():
            print(f"  {name:<46} {col['set']}/{col['key_name']}")
        keys = {c["key_name"] for c in picked.values()}
        if len(keys) > 1:
            print(f"  NOTE: {len(keys)} different accents in this set "
                  f"({', '.join(sorted(keys))}).")
            print("  Look at the clips side by side before handing them over.")
            print("  Pin one with \"cap_colour\": {\"key\": \"cyan\"} on a clip, or")
            print("  \"adaptive_captions\": false in project.json for the whole set.")


if __name__ == "__main__":
    main()
