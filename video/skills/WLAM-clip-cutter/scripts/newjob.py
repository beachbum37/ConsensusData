#!/usr/bin/env python3
"""
End the current job: archive this show's state into its own folder, then clear it.

    python3 newjob.py            # report what would move and what would go
    python3 newjob.py --apply    # do it

WHY THIS EXISTS. SKILL.md's first rule is that a new video is a NEW JOB and
delivered clips are never touched. That rule was being enforced by discipline
against a working directory that disagreed with it: project.json, slate.json,
cues.json, the transcripts and a 45MB audio16k.wav all defaulted into the scripts
directory and stayed there until the next show overwrote them. Which is also why
eight `slate.json.*-bak` files accumulated next to the live one - each is somebody
protecting themselves from exactly this.

There are two ways out and they are complementary. `QM_WORK` points the whole set
at the show's own folder, so two jobs never share a directory in the first place;
this is the other one, for a job that ran in the default place and is finished.

WHAT IT DOES NOT DO. It never touches `broll-library` (shared across every show by
design), never touches the delivered `clips/`, and never removes the `.pre-*`
source backups - those are the house convention for code edits, not job state.
Everything it clears is either archived first or regenerable.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
import os
WORK = Path(os.environ.get("WLAM_WORK") or os.environ.get("QM_WORK") or HERE)

# The state that belongs to ONE video. Anything not on this list stays put.
STATE = ("project.json", "slate.json", "sections.json", "cues.json",
         "transcript.srt", "transcript.txt", "transcript_compact.txt",
         "audio16k.wav")
# Regenerable scratch. Archived nowhere, cleared on --apply.
SCRATCH = ("tmp", "captions")


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    cfg_path = WORK / "project.json"
    if not cfg_path.exists():
        raise SystemExit(
            f"No project.json in {WORK}.\n"
            f"Nothing to end - this working directory has no job in it.")
    cfg = json.loads(cfg_path.read_text())
    out = Path(cfg.get("out_dir") or "")
    src = Path(cfg.get("source") or "")
    if not out:
        raise SystemExit("project.json has no out_dir, so there is nowhere to "
                         "archive this job's state to.")
    dest = out / "_project"

    # What would move
    keep = [WORK / n for n in STATE] + sorted(WORK.glob("slate.json.*"))
    keep = [p for p in keep if p.exists()]
    scratch = [WORK / n for n in SCRATCH if (WORK / n).exists()]
    kb = sum(_size(p) for p in keep)
    sb = sum(_size(p) for p in scratch)

    print(f"job in   {WORK}")
    print(f"source   {src.name or '?'}")
    print(f"archive  {dest}\n")
    print(f"{len(keep)} state file(s), {kb/1e6:.1f} MB - archived then cleared:")
    for p in keep:
        print(f"   {_size(p)/1e6:8.1f} MB  {p.name}")
    if scratch:
        print(f"\n{len(scratch)} scratch dir(s), {sb/1e6:.0f} MB - cleared, not "
              f"archived (regenerable):")
        for p in scratch:
            n = sum(1 for _ in p.rglob('*'))
            print(f"   {_size(p)/1e6:8.0f} MB  {p.name}/  ({n} entries)")

    baks = sorted(WORK.glob("*.pre-*")) + sorted(WORK.glob("*.bak"))
    if baks:
        print(f"\n{len(baks)} source backup(s), {sum(_size(p) for p in baks)/1e6:.1f} MB "
              f"- LEFT ALONE. These are code history, not job state.")

    if not apply:
        print(f"\nNothing changed. Re-run with --apply to archive and clear "
              f"{(kb + sb)/1e6:.0f} MB.")
        return

    dest.mkdir(parents=True, exist_ok=True)
    for p in keep:
        # COPY then remove, never move: if the archive lands on a different
        # volume or the destination is unwritable, a move can leave the job state
        # neither here nor there.
        shutil.copy2(p, dest / p.name)
    for p in keep:
        if (dest / p.name).exists() and (dest / p.name).stat().st_size == p.stat().st_size:
            p.unlink()
        else:
            print(f"   !! {p.name} did not archive cleanly - left in place")
    for p in scratch:
        shutil.rmtree(p, ignore_errors=True)
    print(f"\nArchived to {dest}, cleared {(kb + sb)/1e6:.0f} MB.")
    print("The working directory is empty of job state. `analyze.py` starts clean.")


if __name__ == "__main__":
    main()
