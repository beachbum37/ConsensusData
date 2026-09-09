#!/usr/bin/env python3
"""What the clean decode deleted before you saw it. REPORT ONLY - cuts nothing.

SKILL.md refuses "remove filler from the AUDIO as well as the captions" on a
measurement - "pure filler is 0.71% of body, mean 0.35s a clip" - and in the same
breath names the precondition for ever revisiting it: "it needs two whisper
decodes to agree, since one flag swings the token count 4.7x."

That 4.7x is the whole problem with the 0.71%. Whisper is trained to emit clean
prose and normalises disfluencies out before anything downstream sees them, so a
filler count taken off the clean decode is the undercount, not the measurement.
The refusal does not say which decode produced 0.71%. If it was the clean one,
the real figure is nearer 3.3% - still possibly not worth cutting, but a
different number to decide on.

So this runs the second decode and prints what it finds. It does not cut, does
not write an EDL, and does not touch the slate: the refusal also demands that
"preflight must print the exact tokens and timecodes removed: this is a finance
brand editing its CEO's recorded speech", and the honest version of that is to
print them and let a person decide.

    python3 fillercheck.py                  # the show's source, from project.json
    python3 fillercheck.py --media path.mp4

NEVER CAPTION FROM THIS. Prompting the decoder costs accuracy - in the studio's
own sample it turned "kick off our build today" into "our bill today". The clean
decode analyze.py already wrote is what the captions come from. This decode is
for filler timestamps and for the count, and for nothing else.

Needs the studio's filler_pass.py, ffmpeg and whisper-cli. Point WLAM_STUDIO_TOOLS
at the studio's video/tools directory if it is not in the default place.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("WLAM_WORK") or HERE)

# Default assumes the skill lives inside the studio repo at
# video/skills/WLAM-clip-cutter/scripts, which puts video/tools three levels up.
_DEFAULT_TOOLS = HERE.parent.parent.parent / "tools"
TOOLS = Path(os.environ.get("WLAM_STUDIO_TOOLS") or _DEFAULT_TOOLS)


def main() -> None:
    args = sys.argv[1:]
    media = None
    if "--media" in args:
        media = Path(args[args.index("--media") + 1])
    else:
        cfg_p = WORK / "project.json"
        if not cfg_p.exists():
            raise SystemExit(
                f"no project.json in {WORK} and no --media given.\n"
                f"Run analyze.py first, or name the file: "
                f"fillercheck.py --media /path/to/show.mp4")
        media = Path(json.loads(cfg_p.read_text())["source"])

    if not media.exists():
        raise SystemExit(f"source not found: {media}")

    tool = TOOLS / "filler_pass.py"
    if not tool.exists():
        raise SystemExit(
            f"filler_pass.py not found at {tool}\n"
            f"It ships with the video studio, in video/tools/. Point\n"
            f"WLAM_STUDIO_TOOLS at that directory:\n"
            f"    export WLAM_STUDIO_TOOLS=/path/to/ConsensusData/video/tools")

    # The clean decode analyze.py already wrote, so the report can show each
    # filler in its surrounding words rather than as a bare timecode. Optional:
    # without it filler_pass still reports, just with less context.
    cmd = [sys.executable, str(tool), str(media)]
    ctx = WORK / "transcript.json"
    if ctx.exists():
        cmd += ["--context", str(ctx)]

    print(f"second decode over {media.name} - this is NOT the caption transcript\n",
          flush=True)
    r = subprocess.run(cmd)
    print("\nREPORT ONLY. Nothing was cut and no file was written.\n"
          "An 'uh' mid-phrase is sometimes load-bearing; a filler between two\n"
          "sentences usually is not. If this set changes your view of the 0.71%\n"
          "in SKILL.md, record the new number and which decode produced it.",
          flush=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
