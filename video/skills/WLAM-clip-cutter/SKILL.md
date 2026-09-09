\---

name: WLAM-clip-cutter
description: Turn a long-form video (webinar, podcast, interview, keynote, panel, AMA, earnings call, livestream replay, Zoom recording) into short branded vertical clips for TikTok, Reels, Shorts and LinkedIn - finding the moments worth cutting, then rendering them 1080x1920 with burned-in captions, a hook headline, retention jump cuts and the Subscribe CTA. Use this ANY time the user drops a long video and asks for "viral clips", "shorts", "reels", "social cuts", "clip this up", "best moments", "highlights", "make clips from this", "cut this down for social", or asks to repurpose a recording for social. Trigger even when they only hand over the file and say "make clips" without naming a platform or a style, and when they ask for one specific moment rather than a set. This is the Work Less Ai More house clip look, so also use it for any WLAM or Kimberly footage.
---

# WLAM clip cutter

Long video in, posting-ready vertical clips out. Two halves that fail
differently: **picking the moments** is judgment, **rendering them** is a
pipeline. Do them in that order and do not blur them.

The look is not invented — it is lifted from the Quasar Markets landing page.
The cut mechanic is not invented either — it was measured off a reference reel.
Both are recorded in `references/` with the reasoning, because the failure mode
here is someone "improving" a decision that was made from evidence.

## A new video is a NEW job. Never touch a delivered clip.

Clips that have already been handed over are **posted**. They are finished. When a
new video arrives:

* Do not re-render, re-cut, re-caption or "improve" any previous clip.
* Do not rebuild a previous show's posting sheet or ticker file.
* Do not go looking through past output folders for anything except a `\_project/`
archive you need in order to read a setting.
* Skill fixes apply from now on. They are NOT a reason to revisit old work, however
wrong the old work turns out to have been.

If a past clip has a real defect, SAY SO in one line and move on. Only re-cut it if
the user explicitly asks.

Each show gets one folder on the Desktop, named **`WLAM Podcast Live MM.DD.YY`**.

**And the working directory now agrees with that rule instead of fighting it.**
`project.json`, `slate.json`, `cues.json`, the transcripts and a 45MB
`audio16k.wav` all defaulted into `scripts/` and stayed there until the next show
overwrote them - so the rule above was being enforced by discipline against a
directory that carried the last job's state into the next one. That is also why
eight `slate.json.\*-bak` files piled up next to the live one: each is somebody
protecting themselves from exactly this.

Two ways out, and they are complementary:

* **`WLAM\_WORK=<dir>`** points the whole per-show set at the show's own folder, so
two jobs never share a directory in the first place. Unset, everything behaves
exactly as before, so it cannot break a job in flight - it is opt-in per show.
* **`python3 newjob.py \[--apply]`** is for a job that ran in the default place and
is finished: it archives the state into `<out\_dir>/\_project/` and clears the
working directory, so the next `analyze.py` starts clean. It reports first and
changes nothing without `--apply`.

`newjob.py` never touches `broll-library` (shared across every show by design),
never touches delivered `clips/`, and never removes the `.pre-\*` source backups -
those are code history, not job state.

**GIT IS THE CODE HISTORY NOW, SO DO NOT LEAVE `.pre-\*` FILES BEHIND.** The habit
of copying a script to `<name>.pre-<thing>-bak` before editing it had grown to
**103 files and 11 MB** in `scripts/` by 2026-08-24, thirteen of broll.py alone,
and it makes the directory unreadable: `ls scripts/` returned nine screens of
near-identical names for fifteen live files. This is a git repo. Make the edit,
and if you want a safety net before a big change, commit first - `git checkout scripts/ SKILL.md` restores a complete, coherent state, which a scatter of
per-file backups from different afternoons does not. They were all deleted on
2026-08-24 after verifying HEAD restores a working tree. On the 08.22 job it accounted for 306 MB:
46 MB of state to archive and 260 MB of regenerable scratch.

## HOW TO KNOW A CLIP IS RIGHT

**Set on 2026-08-28, after a defect the owner caught by watching that every
automated check had passed.** This is the standard for verifying any change to
this pipeline, and it is written near the top because it is the part most easily
skipped.

### 1\. Look at the frames. They are the evidence.

A clip is a picture. The question "is the right person on screen", "is that
really Bill Gates", "does the crop cut the logo in half" is answered by
extracting a frame and looking at it — not by a check that returns OK.

Two defects this file records were found ONLY this way, both after a full green
preflight: a clip that cut to a **$100 bill** where the show said a man's name,
and a clip that showed the **listener with his mouth closed** for the first
twenty-nine seconds. Every gate passed on both.

```bash
ffmpeg -v error -ss <t> -i clip.mp4 -frames:v 1 -vf scale=270:480 f.png
```

Pull three: one early, one mid, one late. On a conversation clip pull one inside
each turn and check **whose mouth is open**.

**On a follow clip this is now mechanical and MANDATORY.** `verify\_turns.py`
builds the whole sheet — both faces at the middle of every turn, the schedule's
pick framed — and `render()` refuses the clip until `"speaker\_verified": true`
says somebody read it:

```bash
python3 verify\_turns.py <slug>
```

Do not substitute the schedule's confidence for this. Measured on 08.26 it ran
**69% confident at 43% correct**, and the most confident variant of four was the
second worst. See "THE CONFIDENCE NUMBER DOES NOT MEAN THE SCHEDULE IS RIGHT".

### 2\. A proxy that disagrees with the frames is WRONG — fix the proxy

This is the expensive lesson. A "does the face on screen match the voice" ratio
was built, quoted in five commits, and used to justify two guards. It measured a
**fixed box** in the delivered frame — and because two speakers' faces land in
different places after the crop, it measured one man's mouth and the other man's
cheek. It scored whichever schedule happened to align better, not whichever was
correct, and it said a clip was fine that the owner could see was not.

**When a measurement and a frame disagree, the frame wins and the measurement is
the bug.** Every figure that metric produced was retracted. If a number is worth
quoting in a commit, it is worth checking that it measures what its name says.

### 3\. A/B against the thing you changed, not against nothing

"It looks fine" is not a result. Render the same span both ways and compare:
the cut-mode rewrite was accepted on **840 of 840 identical frames** at aligned
spans; the panel rewrite on the seam landing at **exactly (887, 921) in both**
and the same file size to within 2 KB. Keep the old file until the new one is
proved — never delete a delivered clip before its replacement renders.

### 4\. Measure the failure, not the fix

A hang is not "slow". Sample `ps -o time= -p <ffmpeg>` twice 60s apart: real work
advances CPU by **minutes**, a stall by fractions of a second. Do not trust file
size (the muxer writes in bursts — an output sat at the same byte count across
three runs and was working), and do not trust your own timeout (two runs were
killed at ten minutes and written down as hangs when they were merely slow).

### 5\. When you are wrong, say so in the file

Three hypotheses about the 72 GB render were measured and refuted before the real
cause was found; all three are written down. A wrong answer that looked right is
worth more to the next person than a tidy account of the right one — it is the
only thing that stops them spending the same afternoon.

## Rendering REQUIRES a clean preflight (build\_all runs it for you)

**As of 2026-08-25 this is mechanical, not a habit.** `build\_all.py` runs
preflight over the clips it is about to render and **refuses to render if it
fails**. Nothing used to make you run it: preflight has always existed, has
always exited non-zero, and this section has always said "always" — and
`build\_all.py` never mentioned it. Every rule it enforces was enforced only for
as long as somebody remembered to type a second command.

&#x20;   python3 build\_all.py                 # preflight, then render
    python3 build\_all.py <slug>          # just that clip
    python3 build\_all.py --force         # render anyway, and say so loudly


`--force` exists because there are real reasons to use it — a GRAPHIC warning on
a busy master, a set-wide b-roll repeat you have decided to accept — and none of
them should be silent. It prints a banner naming what it is doing.

**And there is now a regression net.** `python3 selftest.py` runs 763 checks in
about a second, at BOTH frame rates, over every invariant this file records being
broken once: the invitation's two seams and its ink against the chrome line at
its peak, the nameplate's rows and its pure cross-fade and its arrival after the
title card, all 25 cutaway move pairs, the feasibility gates at every hold, and
the vocabulary's own rules. Given a clip or a directory it also measures the
non-negotiables on the delivered file. Run it before you commit anything.

```bash
python3 preflight.py            # the whole slate
```

A render costs 80 to 170 seconds. `preflight.py` answers, in a few seconds and
without touching ffmpeg, every question a failed render was going to tell you:

|check|catches|
|-|-|
|MODE|a layout name (`two\_up`, `gallery`) used as a render mode|
|LAYOUT|a span crossing a run boundary or unmapped video|
|RAIL|the cropped camera tile moving mid-clip|
|SPEAKER|the authored tile not being the one talking|
|CROPS|a crop authored for an older panel, which the renderer silently re-cuts|
|GRAPHIC|a crop edge slicing the show's own burned-in logo in half|
|NAMED|who this clip names on screen, printed in full to be read back against the face|
|PACK|how a share panel splits, and what the split costs the chart|
|SAFE|anything readable sitting under the platform chrome|
|BURNED|captions already burned into the source, fighting ours|
|TEXT|the reference being FLAT over the span, so captions would render lowercase|
|EDGES|the exact first and last whole words, so in/out land on speech|
|OPENER|the opening CLAUSE, and a warn when the clip lands the viewer mid-conversation|
|ENDING|WHERE the out-point will land — which full stop, and whether the move is available at all. A `stuck` span is a FAIL: `render()` refuses it|
|LENGTH|the post-silence duration against the floor, before it is too late|
|BROLL|the insert count against the target this body's length asks for, a repeated PICTURE, too little face between two cutaways, each hold against ITS OWN kind's band, a flat spread (they all fell to one floor), too FEW seconds of picture, and no insert long enough to carry the sign-up|
|HEADROOM|WHERE THE FACE LANDS in the delivered panel, in every mode — chin under the caption band or the platform chrome, crown sliced, a small or off-centre head|
|PICTURE|what the inserts look like (luma / motion), and any that never went through the exposure pass|
|CADENCE|how long the picture goes without changing, and whether b-roll breaks it|
|SET|the same PICTURE reused by two clips of one set - scored across the whole slate, not inside one clip|

The b-roll commands, in the order they are used:

```bash
python3 broll.py propose            # candidates -> slate, nothing downloaded
python3 broll.py preview <terms>    # a contact sheet for bare terms
python3 broll.py fetch              # download + bake what you approved
python3 broll.py vocab              # what the library has taught the tool
python3 broll.py retire <fragment>  # unlearn a pairing, delete the bake
python3 broll.py learn <slate.json> # backfill anchors from a shipped show
python3 broll.py sweep \[--apply]    # re-bake anything short of BAKE\_HOLD
python3 broll.py pictures           # index the library by what each frame SHOWS
python3 broll.py picture-search "x" # what the library has a picture of
python3 broll.py shipped \[term]     # pictures that reached a delivered clip
```

Every timing check (EDGES, ENDING, LENGTH, TEMPO, CADENCE, BROLL) now runs off ONE decode
per clip, with `drop\_unspoken` applied and the adaptive tempo included - so
LENGTH and BROLL score the same body, which they did not before 2026-08-22. A
span that cannot be decoded prints a DECODE warning and those lines say "not
measured" rather than scoring the raw span. SPEAKER likewise prints "NOT
measured" when the project has no `tiles` map, instead of a pass off no evidence.

It was written after a single clip was rendered SIX times, where every failure was
answerable up front. Fix the slate until preflight is ALL CLEAR, then render each
clip once. Do not use the renderer as a diagnostic.

## What the 2026-08-25 audit changed, and what will now REFUSE

**Read this the first time preflight stops you on a slate that used to pass.**
A 63-agent audit was run against the whole pipeline on 2026-08-25 and returned
39 confirmed findings. 35 were fixed, 2 were REFUTED with measurements (see the
bottom of this section — do not "fix" them), and 2 are open. Several of the
fixes turned a warning into a refusal, so a slate authored before that date can
be refused today for something real that nobody was told about before.

### The checks that could never fail

Three of selftest's file-level checks — **blackdetect, freezedetect and
silencedetect** — passed `-v error` to ffmpeg. Those filters print their
findings at INFO level, so `-v error` deleted exactly the output the regexes
read: the matches were always empty, `ok(not ...)` was always true, and all
three passed unconditionally on every clip ever run through them. Proved on a
synthetic clip that is black, frozen and silent at once — 0 reports under
`-v error`, 1 of each under `-v info`.

`selftest.check\_detectors()` now builds that known-bad clip and requires all
three to FIRE before the checks below them are trusted. **If it ever fails,
somebody has quieted those calls again — do not "fix" it by lowering a
threshold.**

This is a shape, not a one-off, and it turned out to be a family:

* `check\_speaker` had SEVEN bail-outs (no tiles map, whospeaks missing, fewer
than two moving tiles, under eight samples, not enough loud/quiet frames, the
crop in no named tile, any exception) and communicated only through stderr,
which it writes only on a mismatch. Every bail-out was indistinguishable from
a clean pass, and preflight printed "authored tile matches the voice" over all
of them. It returns a REASON now.
* `place\_hook`'s fallback printed "OVERLAPS a face" and returned False without
ever comparing the position it had chosen against a face rectangle. It
measures now and prints the pixels.
* The GRAPHIC check gave up whenever it found more than `GFX\_MAX\_BOXES` static
coloured regions, which is **4 of 4 real masters** (7 regions on the Nathan
Dean master) — so the check that exists to stop a crop slicing the WLAM logo had
never run on a master that has one.
* `check\_burned\_in` required 90% of the ENTIRE row width to be plate-or-glyph,
which only a full-bleed caption bar satisfies. A centred caption box — what
every burned-in social caption uses — scored 0.60 and read as clean.

**The lesson to keep:** a check that cannot fail is worse than no check, because
the green tick gets read as evidence.

### New REFUSALS — what will stop you tomorrow

|It refuses when|Why|What to do|
|-|-|-|
|**Nobody is named** on a clip|The owner's non-negotiable: "every clip needs to have the white box, and then their name comes on there". All four exits of that check returned True, so it was unenforceable.|Set `speaker` on the clip or `host` in project.json. For a montage or cold open that genuinely has nobody, set `"allow\_unnamed": true` on the clip.|
|**The clip opens MID-CLAUSE**|The other half of "the way it starts, the way it finishes". Only the ending was ever checked.|Move `start` back onto the boundary, or set `"allow\_ragged\_start": true` if the fragment stands up alone.|
|`"broll\_style": "cut"`|It sets BROLL\_IN and BROLL\_OUT to 0.0 and strips the transition off EVERY cutaway in the show. "There's animations for every b roll cut."|Use `dissolve` (the default) or `slide`.|
|**A cutaway is cut below the 3.0s settled floor** by the tail clearance|preflight certified the authored hold and the renderer then shortened it silently.|Move the insert earlier.|
|**Two cutaways closer than BROLL\_MIN\_FACE after the re-snap**|preflight scored the AUTHORED anchor; the renderer snaps it onto the named word by up to ±2.5s, which is wider than the floor is deep.|Move one insert.|
|**The master repeats more than 4% of frames** over the span|A stalling stream repeats frames rather than skipping time, so the file plays at the right length with the picture frozen inside it. Nothing counted this.|Pick the span from a clean stretch, or re-pull the master.|
|**The clip is over `MAX\_CLIP`** (180s)|There was a floor and nothing above it, so a mis-typed `end` rendered a six-minute file.|Check `end`. Raise `max\_clip` in project.json if it really is a long one.|
|**The delivered audio measures silent**|`report\_loudness` used to `return` on -inf, so the one measurement that can see a dead clip stayed quiet about the only case it should shout at.|Check the master's audio and the mute windows.|
|**A mute window falls outside the span, or covers >50% of it**|They are authored in SOURCE seconds and the easy mistake is clip-relative, which silently keeps the word you were muting.|Rewrite them on the same clock as `start`/`end`.|
|**A hook the title font cannot draw**|PIL draws `.notdef` — a black brick — for an emoji or a pasted invisible U+2060, and says nothing.|Retype it. Emoji do not belong in a title card.|
|**A hook that will not fit at any size**|The 84px floor was documentation; the loop's real floor was 42px, so a long hook set at half the documented minimum in silence.|Cut it to 3–8 words.|

### Re-cutting an OLD show: expect BROLL and NAMED to stop you

**Superseded on 2026-08-30 — the numbers below are history.** The floor moved
from 3.0 to 2.5 and the ceiling from 4.2 to 3.6 (see "FASTER B-ROLL"), so
`propose` now writes around `hold: 3.2` and the legal band is 3.2–3.6. The
archive's `hold: 3.0` inserts, which used to be refused for being too SHORT,
now sit under the ceiling; what will stop an old slate today is a hold of 4.2
being too LONG. Raise or lower them into 3.2–3.6 either way.

**And superseded again the same day, in the direction that makes old slates
EASIER.** There is no single legal band any more — see "A HOLD IS A BAND NOW".
An insert carrying a `kind` is scored against that kind's band; an insert
WITHOUT one (which is every slate written before 2026-08-30) is scored exactly
as it was, so nothing in the archive re-scores differently. What an old slate
will now collect is the SPREAD warning, telling you its holds all fell to one
floor — which they did.

A fresh job is fine — `propose` writes a hold the current band accepts. But
**49 of the archive's inserts were authored at `hold: 3.0`**, from before the
floor and the travel were set. Old slates also predate the nameplate being enforced, so `NAMED` will
stop any clip whose `speaker` was never set.

Neither is a regression. Re-cutting a show from before 2026-08-25 means bringing
its slate up to the current standard: move the holds into the 3.2–3.6 band and
name the speakers. `--force` is there if you have read every line and want it anyway.

`allow\_ragged\_end` is now honoured by preflight too. It was a documented escape
that only `--force` could actually take, and `--force` disarms every other check
on every other clip in the set.

### New WARNINGS worth reading

* **`hard\_out` leaves under END\_PAD\_MIN after the last word.** It is your
never-cross line and the pipeline will not overrule it, but it silently
defeated the tail guarantee — measured, a 0.30s tail delivered as 0.07s. It
now prints the exact number to move it to.
* **An authored `face\_h` blows the PAD\_MAX\_FRAC budget.** The whole budget sits
inside `if fh is None`, so an authored value skips it. Measured on the Alan
Ellman clip: 484px of a 1092px app band is flat fill, 44% against a 30%
budget. Deliberate override, but worth knowing you chose it.
* **PIPFACE**: no face detected in the camera tile. Either the tile has no
camera in it — a screen recording with the camera off renders a blown-up slab
of app pixels in the face band — or the cascade lost it. Advisory.
* **HOOK**: how many of the hook's content words are actually spoken. **This is
deliberately NOT a gate** — see below.
* **Title lengths on the posting sheet** now read `77/70` and go red. The counts
were always printed with no limit beside them, which made them decoration.

### Two findings REFUTED — do not "fix" these

1. **pc-range b-roll does NOT re-grade the clip.** The audit reported that one
full-range asset re-grades the whole delivered clip, across 278 of the
library's assets. Checked against ground truth — the asset decoded on its own
at the insert's size — on three pc assets: as-is tracks the source to within
0.1 mean RGB (113.04/113.21, 119.83/119.91, 165.81/165.90) and adding an
explicit `in\_range`/`out\_range` conversion moves every one 1.4 FURTHER AWAY
and raises the per-pixel residual. It would darken a quarter of the library
for nothing. The measurements are recorded at the scale line in
`broll\_chain`.
2. **The share softness guard is NOT dead.** `blow > 4.5` fires on 17% of real
clips. Measured across every share clip on this machine (24, 08.05–08.25) the
blow-up factor is bimodal: 20 sit at 3.13–3.55 on a 320–355px tile, 4 sit at
4.62–4.91 on a 220–234px one. 4.5 falls in the empty gap between the two
populations, which is where a threshold belongs. Do not lower it.

### Why there is no hard floor on the hook check

The rule is that every clip refers to its title, and the honest limit without a
language model is word overlap. Across all 130 archived clips with a hook and a
quote the median overlap is 100% and the mean 79% — but the tail is full of
hooks that are editorially RIGHT and lexically empty:

&#x20;   0%   'Oil is heading lower'            a-glut-coming-back-on-the-market
    0%   'HE COULD NOT NAME \*$18.8T\*'      vought-household-debt
    0%   'FIATO: ASKED 3X, NO PAY FIGURE'  fiato-wont-say-his-pay
    7%   'Banks waived hundreds of millions of dollars'


Every one is a paraphrase, a negation, or a description of what did NOT happen —
the three shapes a good hook most often takes on this material, and the three a
word-overlap test cannot see. A 60% floor flags 29 of 130. Even 25% flags 5, and
all five are good. **A gate that refuses good clips gets ignored, and an ignored
gate is worse than no gate.** It reports and a human decides.

### Still open

* **In share mode the nameplate raise can drive the captions onto the slide's
own bullet text.** Real, and the fix is a layout decision — raise into the
flat-fill pad, or move the invitation instead — so it is not taken unilaterally.
* **An authored speaker name is checked on a CONVERSATION clip and not on a
`head` or `share` one.** Solved where it could be: on `conversation` and
`conversation\_share` the turn schedule names the tile holding the frame while
the nameplate is up, so `render()` compares the two and warns — over the
plate's whole life, not its arrival, since a turn boundary can fall inside that
window. On a single-crop clip there is nothing to compare against, and true
identity would need voice embeddings (pyannote/WhisperX): torch is not
installed and the models are gated.

### Known issues in the delivered 08.25.26 Nathan Dean set

Both were found by the new gates, and both are SLATE issues, not code:

* `02-no-good-answers-on-hormuz` has **5.4s of speaker between its last two
inserts** after the re-snap, against a 6s floor. preflight refuses it now.
* One clip ships a **77-character YouTube title** against the \~70 that Shorts
shows before truncating in search and the sidebar.

### The library's real footprint

`python3 broll.py size` reports it, split by what is needed to RENDER:

&#x20;   baked clips     1482     7.11 GB   <- needed to render
    index + misc               16 MB   <- needed to render
    previews         690      853 MB   rebuildable
    src originals   1455    45.68 GB   re-bake cache only
    TOTAL           3627    53.66 GB


`src/` is a re-bake cache — render only ever opens the baked `.mp4` beside the
index. **A distribution copy is 7.12 GB, not 53.66.** `python3 broll.py prune-src` drops the originals after asking, and refuses if any indexed asset
has no baked file (because then src/ is its only copy).

## Setup, once per video

```bash
cd \~/.claude/skills/WLAM-clip-cutter/scripts
python3 analyze.py "/path/to/the-video.mp4" --out \~/Desktop/"Name Of Clips"
```

That transcribes it, writes `transcript\_compact.txt` (a `\[MM:SS]` line per cue
— this is what you read), and classifies every stretch as `two\_up`, `share` or
`head` into `sections.json`. It also writes `project.json`, which holds every
source-specific number so nothing is hardcoded — including, on a two-up, the
measured divider position and a ready-made crop for each speaker's half.

Needs `ffmpeg`, `whisper-cli`, python with `pillow` and `numpy`, and a whisper
model. Run from a directory whose path has **no spaces** — this ffmpeg has no
libass and no drawtext, so all text is rasterised with Pillow, and the filter
graph uses short relative paths.

`sections.json` now carries four layouts: `two\_up`, `share`, **`gallery`** (a wall
of faces, no shared screen) and `head`. Only `head` can use a gallery stretch, and
only with an explicit `head\_crop` picking one face out of the wall.

**Check the layout map against a real frame before rendering.** `two\_up` is found
from the dark divider at frame centre and is reliable. `share` is found from a
bright strip along the top, and that test **misfires on a bright background** — a
guest sitting in front of a sunlit window comes back labelled `share`. On the AI
Matters master every solo shot did. If a two-up is present, distrust every `share`
run until you have looked at one.

**On a two-up, put the speaking half on each clip** as `head\_crop` in the slate;
`analyze.py` prints a ready-made crop for each side. Render it as `mode="head"` —
do not reach for `mode="share"`, which stacks a camera tile over a shared screen
and is a different problem.

**Two guards now run automatically on every share and duo\_share clip**, so you no
longer have to remember them:

* `check\_rail` REFUSES a span whose camera rail re-flows part way through, because
a fixed crop through a re-flow shows a black gap for part of the clip.
* `check\_speaker` measures which tile is actually talking and WARNS if the authored
`pip\_crop` is a different person. Advisory, not a refusal - the measure is
rig-dependent and has named the wrong person on a master where a guest sat far
from his camera. Treat a warning as "go and look at a frame", not as proof.

**You can still run either by hand, and should when picking:**

```bash
python3 pick.py                                 # candidate spans that already pass
python3 turns.py <start> <end>                  # who holds the floor, second by second
python3 railcheck.py <start> <end>              # is this span safe?
python3 railcheck.py <run\_start> <run\_end> --windows   # find one that is
python3 railcheck.py <run\_start> <run\_end> --map       # what does the rail DO?
```

A share clip crops a fixed rectangle out of the rail, and the compositor RE-FLOWS:
when someone stops talking their tile is dropped and the remaining tile moves and
resizes. On one master the rail was two tiles at y278-801, then for twenty seconds
mid-clip it became a single tile at y410-669, then switched back. A fixed crop
through that renders the speaker for part of the clip and a **black gap** for the
rest. The layout is still "share" the whole way, so `check\_layout` sees nothing
wrong - only the furniture inside it moved. On that master only two windows in a
fifteen-minute share run held still long enough to cut from.

**On a rail of three or more guests it will refuse a span that is perfectly
still, and the reason is worth knowing.** `railcheck.tiles()` finds tiles by
brightness and MERGES adjacent ones when the separator between them is only a
few pixels. A three-guest rail came back as ONE band, (144, 904), for tiles
whose tops measure 146 / 410 / 675 - so the edge the persistence test was
watching belonged to the bottom guest, not to the crop. That guest was the
darkest person on the call, his lower rows drift in and out of threshold, and a
span whose three tops were byte-identical in all 52 sampled frames was refused
for "the cropped tile moves".

So when the discovered band is more than 1.6x the height of the crop, the check
measures the AUTHORED RECTANGLE instead: the separator directly above the crop
must stay within 8px of where it was authored, and the crop's own rows must
never go dark. Both of those break on a real re-flow (the tile moves and leaves
black) and neither breaks on a brightness dropout. It prints what it measured
rather than passing silently:

```
note: rail band (144, 904) is 760px for a 259px crop - the tile finder merged
neighbours, so the authored rectangle was measured instead: top holds at y410
(authored 409), crop brightness 120-122.
```

If you see that note, the span was checked harder, not waved through. A genuine
re-flow still refuses, now naming the crop's own top edge.

**The bare two-argument call is the one to run when a span has just been
refused.** With no flag `railcheck.py` prints every stable stretch it found across
the span, one line each, with the start, the end, the length and the
tile geometry that held for it, then says STABLE or RE-FLOWS N times. That is what
tells you WHERE the re-flow is, so you can pull the in-point past it instead of
guessing. `--windows` is the same measurement swept over a whole run and filtered
to stretches long enough to cut from, `--min` seconds (default 46, one clip's
length), sampling every `--every` seconds (default 1.0). `--map` is the third
mode, and the one to reach for when `--windows` comes back empty: it classifies
every sampled frame by the SET of tile bands in it, collapses identical
neighbours into runs, and prints the rail's states plus the stretches each state
holds for, longest first. On the 08.21.26 McGlone master `--windows` printed
"NONE. Every stretch re-flows inside a clip's length." and stopped, while `--map`
over the same range (55 to 1324) printed held-still stretches of 197s, 94s, 74s,
73s, 62s, 55s, 54s, 53s, 51s and 51s: the rail was alternating between two
states and both were long enough to author a clip inside.

**`--map` carries a tolerance and the other two modes do not, deliberately.**
`MAP\_TOL` is 64px. Inside ONE state the discovered band's top edge wandered 40px
on that master (416, 448, 456 on consecutive samples), because the speaker's
backdrop is a dark Bloomberg wall whose upper rows drift in and out of the
brightness threshold, while a genuine re-flow moved the same edge 130px. Without
the tolerance every wobble started a new state and `--map` answered "the longest
the rail holds one state is 41s" over a run that holds still for three minutes,
which is the same right-and-useless answer `--windows` gives and the whole reason
`--map` exists. `--windows` and the bare per-span report keep exact equality,
because they are what `check\_rail` is built on and loosening them would let a
real re-flow through.

**And `--map` is COARSER than preflight, so never use it to rule a span out.**
It measures the whole merged band; `check\_rail` measures the authored rectangle
whenever the discovered band is more than 1.6x the crop's height, and it is the
only thing that knows your `pip\_crop`. On this master the delivered span
523.6-617.11 passed preflight as "cropped tile holds still" while a bare
`railcheck.py 523.6 617.11` on the same span reported it re-flowing 28 times.
Both are honest about what they measure. Use the map to find where to look.

**Check whether the SOURCE already has captions burned into it.** The 08.18.26
master streamed with live captions on for the first six minutes - a dark plate
with white text across the lower third of the stage - and nothing in the pipeline
objected. It is not a layout, `check\_crops` is happy, and the render succeeds; it
just ships with the show's captions arguing with ours, one sentence behind and cut
off at both ends by the crop. It was caught on a contact sheet, which is not a
check, so `check\_burned\_in` now runs in preflight over every rectangle the clip
actually puts on screen.

Two things about that detector are worth knowing if you touch it:

* **A caption row is BIMODAL, not dark.** The first version tested "at least 80% of
the row is below 70 luma" and "at least 2% is above 185" as separate conditions,
and scored ZERO on a span that plainly had captions burned into it - because the
glyphs are 45% of a text row, so the same row fails the dark test. It asks
instead that 90% of the row is plate OR glyph with almost nothing between, which
measured 16.5% of frames on the bad span and 0% on all six good crops of the same
master, including a guest against a black studio wall.
* **The fix is usually the SPAN, not the crop.** On that master the plate sat at
y873-1055 and the head crop needed all 1080 rows to frame a face at y516;
cropping above the plate forced a 486x864 window that put his mouth under our own
captions. The plate was intermittent - up over 0-124, 260-267, 330-360 and
570-600 - so moving the in-point from 348.5 to 364.09 solved it completely, at a
cost of eleven seconds of setup. Map the plate across the whole master before
re-framing anything.

**If the video really does have screen-share stretches**, check `share\_crop` and
`pip\_crop` against a real frame. Those numbers change per recording setup, and
getting them wrong is what makes a clip read as a screen recording instead of a
post. Two things they now also decide, because the app is fitted rather than
trimmed: `share\_crop`'s ASPECT sets how tall the app lands (a 16:9 slide is 608px
of 1920 and no packing changes that), and `pip\_crop`'s aspect sets the face band.
Run `preflight.py` — its PACK line prints the split, how much of the band is flat
fill, and how much of the camera tile the band costs:

```bash
ffmpeg -ss 600 -i "video.mp4" -frames:v 1 -vf "crop=1600:972:8:104" check.png
```

## Length: 60 seconds minimum, 60 to 90 the house band

**Every delivered clip finishes at 60 seconds or longer, end card included.**
Raised from 45 on 2026-08-28 by the owner: *"every clip has to be minimum a minute
to a minute thirty."* That is a floor AND a target band, and they are different
kinds of thing — `MIN\_CLIP` **refuses**, `CLIP\_BAND` **reports**. It applies to all
five modes and to a one-off single clip as much as to a set.

What that means when you are picking:

|||
|-|-|
|finished clip|**60s minimum, 90s the top of the band**|
|end card|4s, appended automatically|
|so the span needs|**56s minimum of speech**|
|and in practice|**pick 75s or more** — the silence pass takes \~19% before anyone sees it|

A clip over 90s is a **WARN, not a refusal**: the 08.21 McGlone clip the owner
called "literal perfect" ran 1:35, and `MAX\_CLIP` (180s) is the actual ceiling. The
warning asks one question worth answering — is there a second idea in here that
wants its own clip?

**WHAT THE RAISE COSTS, stated exactly.** Measured over the 96 delivered clips, 71
are under 60s and would be refused today. They are posted and finished and are
never re-run, but it means **a re-cut of any show before 2026-08-28 will stop on
LENGTH**, and the fix is to widen the span rather than to lower the number.

It also genuinely constrains what can be cut. On the 08.26 master the raise left
exactly one two-up stretch long enough AND clean enough (no price, no position, no
advice) to make a 60-second clip. That is the floor doing its job, and the honest
response is to say a slot is empty rather than to pad it.

Pick with margin. A span is only as long as the speech inside it: the silence pass
collapses every pause, so a 43s span with three seconds of dead air in it lands
under the floor. `render()` refuses a short clip twice - once on the requested span
before it spends a render, and again after the silence pass - and the second refusal
is the one that catches you.

A clip can be asked to run LONGER than the floor - if the ask is "make the
prediction one a minute", that is a per-clip floor on top of this one, not a
suggestion.

If the best version of a moment is genuinely shorter than this, **widen it or pick
something else**. Do not ship it short. If a required slot has no moment that can
reach 60 seconds cleanly, say so plainly rather than padding with dead air or
running past a compliance boundary to make up the seconds - both are worse than
telling the user the slot is empty.

## How many clips, and which framings

Unless the user names a number, scale the set to the source and **cover every
layout the source actually contains**:

|master length|clips|
|-|-|
|under 20 min|1 to 2|
|20 to 60 min|2 to 4|
|**over 60 min**|**4 to 5 minimum**|

**A set must not be all one framing.** A morning show that ran an hour has a solo
camera, a two-up and a screen share in it, and shipping five identical talking
heads throws away most of what the show looked like. Read `sections.json` and make
the slate cover it:

* a `share` run exists → **at least one screen-share clip.** This is not optional.
A screen share is the only framing that shows the work — the chart, the terminal,
the thing being pointed at — and a set without one looks like a podcast. Use
`mode: share` when one person is presenting, `mode: duo\_share` when both are in
the camera rail and talking over the screen.
* a `two\_up` run exists → at least one clip from it. Use **`mode: duo`** where they
are genuinely talking to each other, and `mode: head` with a `head\_crop` where one
of them holds the floor.
* a solo full-frame run exists → at least one `mode: head`.

Then pick the best moment *within* each framing rather than picking the best five
moments and accepting whatever framing they land in. If a required framing has no
moment worth cutting, say so plainly instead of shipping a weak clip to fill the
slot.

## Picking the moments

**Sweep the constraints first, then read.** This is the half that decides whether
the clips work, and it was the weakest half of the pipeline for a structural
reason rather than a lack of care: everything that makes a span ILLEGAL is cheap
to compute and was being discovered by hand, one preflight run at a time. A span
was read out of the transcript, authored into a slate, and only then told it
crosses a layout change, opens mid-clause, delivers 51 seconds, or has a price in
it. Each of those is a minute of reading and a re-author, so fewer candidates got
considered — which is exactly what makes a boring set.

```bash
python3 pick.py                      # ranked candidates that already pass
python3 pick.py --mode conversation  # only where the floor actually moves
python3 pick.py --top 25 --full      # the whole opening and closing sentence
python3 pick.py --dirty              # include the compliance-flagged ones
```

`pick.py` walks every sentence in the transcript as a possible in-point and
extends it sentence by sentence until the DELIVERED length (span minus the
silence the pass will remove, plus the card) lands inside the band. It keeps only
spans that **start and end on a sentence**, **stay inside one layout run**, and
**open on something that carries an idea** — the same shape as `broll.py propose`: the machine shortlists, the person decides.

**IT WILL NOT RANK THE IDEA, deliberately.** There is no lexical statistic on
this material that separates a clip that lands from one that trails off; SKILL.md
records the measurements and the reason a gate like that gets ignored. It ranks
on what is measurable — does it fill the band, is it clean, does it have pictures,
does the floor move — and prints the opening and closing sentence. **The last step
is reading.** Ask whether one thought starts and finishes between them.

**Validated against the hand-picked set:** all four spans chosen by hand for the
08.26 master — an hour of reading — were surfaced by the sweep within 25 seconds
of the chosen in-point, alongside 90 more candidates.

### The opener has to carry an idea

The first version offered `"Wow."`, `"They just do."` and `"Oh, it's called, sorry."` as in-points. Each is a legal sentence boundary and none of them opens a
clip: the non-negotiable is that a clip is ONE COMPLETE IDEA, and it cannot be if
the first thing a viewer hears is a reaction to something they did not.

`OPENER\_MIN\_WORDS` is 7, and a discourse marker is only fatal when the sentence
LEANS on it — *"So the Fed should meet six times a year"* is a fine opener and
*"So they just do"* is not, and the difference is whether anything substantial
follows.

### The compliance scan is the highest-value part, and the one to trust least

It flags prices, levels, positions and advice by pattern, and it catches the
shapes this desk actually says — `"I'm averaging at 39.5 here now on Nike"` trips
all three of level, position and price. That is a span that must not ship, and by
hand it takes careful reading to notice.

**A flag is a reason to READ THE SPAN, never a verdict.** Measured over one
master, 34 of 94 candidates carry one — plausible on a show that discusses prices
for a living, and unworkable if each costs a minute. So **every flag carries its
own context**: `$20` is a coin flip, `"I get rid of the $20 accountant"` is
resolved the instant you see it. Showing the words beats widening the patterns,
which is a losing game against English.

One exception IS worth suppressing, because it has a principle behind it: **a
share price is attached to an INSTRUMENT and a wage to a PERSON.** `"$20 an hour"`
and `"the $10 robot"` are labour costs in a jobs argument; `"$81 a barrel"` and
`"$39.30 on Nike"` still flag.

**A clean scan does NOT mean the span is clean.** The rule that compliance applies
to what is ON SCREEN is unchanged, and no text scan can see a chart.

### Then read, with real effort

A perfectly rendered clip of a boring moment is a boring clip.

Sweep the transcript through **several distinct lenses** rather than looking for
"good bits" once. Different lenses surface genuinely different moments, and a
single pass collapses onto whatever the opening minutes established:

* the cold open — a blunt declarative that works with zero runway
* the contrarian take — something people will argue with in the comments
* credibility and origin story — the concrete detail, not the summary
* the product aha — the moment the thing clicks
* numbers and stakes — a precise figure is inherently shareable
* mission and emotion — the line they would put on a wall

Then **verify every candidate against the transcript before it survives**, and
default to killing it. In practice most candidates die, and they die for
predictable reasons: the quote was paraphrased rather than copied; the clip
needs context it does not contain; it opens on filler ("so", "and", a half
sentence); it is a platitude any founder could say; it rambles with no payoff.
Cut dead runway off the front and end on a landed sentence, never mid-thought.

**A clip must end when the speaker stops talking.** That is the owner's rule and
it has three parts, in order: the speaker finishes the sentence, the sentence
lands, there is a beat of air, and THEN the card takes the frame. All three are
enforced now. Two of them were not, and the second failure is the one that shipped
because nothing that reads text could see it.

`q.plan\_ending()` is the one owner. It decodes `END\_LOOKAHEAD` (5s) past the span
and answers one of five things — `landed`, `back`, `forward`, `flat`, `stuck` —
and both `render()` and `preflight.py` call it. They used to have separate tests
and preflight's was the weaker one; see "Two definitions" below.

**Which direction, and this was BACKWARDS until 2026-08-24.** The old rule took
the nearest full stop in either direction, whichever move was *smaller*. But the
two directions are not symmetrical when the speaker is mid-sentence at the
out-point: running ON lets them finish the sentence they are saying, and pulling
BACK deletes it. A back of 1.0s against a forward of 2.0s took the back and threw
away a second of a sentence in progress — which is the "he gets cut off" defect
wearing the fix's clothes. So:

|||
|-|-|
|back within `END\_BACK\_FREE` (0.60s)|**take it.** The out-point is already on the sentence and a stray word of the next one hangs off it. Nothing is lost.|
|otherwise, forward within the run-on cap|**take it.** Let them finish.|
|otherwise, back within a third of the clip|take it — running on was not available|
|otherwise|**REFUSE**|

The run-on cap scales with the clip: `max(4.0, min(6.0, dur \* 0.08))`. A flat 4s
was that judgement made for a 45s clip and then applied unchanged to a 95s one.

**And `stuck` is now a REFUSAL, not a warning.** It can fail four ways — past the
run-on cap, across `hard\_out`, across a layout change, or more than a third of the
clip back — and every one of them used to print a stderr line and render anyway.
In a `build\_all` run that line scrolls past six other clips and the clip ships.
It raises now, in the same place and the same shape as the 60s floor, naming the
word the viewer hears cut off and the nearest full stop with its timestamp. Set
`"allow\_ragged\_end": true` on a clip to ship it anyway; `build\_all` then names
every clip that took the escape in a block at the END of the run, not in a line
six clips back.

**What counts as a sentence end** (`finished\_sentence` in `WLAMclip.py`): a trailing
period is not enough. An **ellipsis** ends with one, which shipped a clip ending on
"now that's a different…", and so does an **abbreviation** — the fix for that then
shipped "Now, how Mr." Both are excluded, along with initials. And the stop can be
**wrapped**: whisper writes the closing quote outside the period (`market."`), and
a bare `endswith(".")` scores that as unfinished, so the rule would either run past
a perfectly good ending or pull back and delete it. Trailing quotes and brackets
come off before the test.

**Two definitions of one quantity, again.** preflight had its own copy of this test
— a bare `endswith((".","!","?"))` — which passes all three false positives above,
and which said only "the out-point will move" without ever saying whether the move
would work. So EDGES printed OK on spans the renderer then had to rescue, and
printed nothing at all about the four ways the rescue fails. There is one function
now and preflight's `ENDING` line reports the actual outcome: which word it lands
on, at what timestamp, and whether it lands at all. Preflight's decode lookahead
was also 3.0s against render's 5.0s, so it could call a span stuck that render
finished cleanly; both read `END\_LOOKAHEAD`.

**THE OTHER HALF, AND THE ONE THAT WAS ACTUALLY SHIPPING: the last word was being
faded out while it was still being said.** The words were complete and every text
check passed; the clip still ended like someone pulled the plug. The out-fade sat
at a fixed `out\_dur - 0.25`, and the tail floor past the last word was `0.06s` —
so whenever the speaker ran straight on from the closing sentence (which is most
of the time, because that is exactly the case the sentence rule has just rescued)
the fade began **0.19s before the last word finished** and took it to about -13 dB
while it was still sounding.

Measured on 2026-08-24 across the 83 delivered clips under `COMPLETED WLAM PROJS`:

* **55 of 83** carried under 0.25s of air between the last speech and the end of
the body, against a 0.25s fade. Two thirds of the archive.
* **Fifteen** finished at or ABOVE the clip's own median speech level, worst
**+6.7 dB**. That is a butt cut at full voice straight into the swipe.
* All three of the 08.24.26 clips: **+3.9**, **-0.5** and **-7.4 dB**, with 0.17
to 0.20s of air.

Two numbers fix it, and they are in `WLAMclip.py` with everything else:

|||
|-|-|
|`END\_PAD\_MIN`|**0.30** — the tail floor when the speaker runs straight on. Was 0.06.|
|`END\_PAD`|0.42 — the tail when there is a natural pause to take it from|
|`END\_FADE`|0.25 — and it is placed off the LAST WORD, not off the end of the file|

The fade takes the LATER of `out\_dur - END\_FADE` and the last word's delivered
end, so the ordinary case (a real pause before the out-point) is byte-identical to
before and the fade only moves when it would otherwise bite. `END\_PAD\_MIN` being
larger than `END\_FADE` is what makes that never happen in practice; the `max()` is
there for any other path that leaves a short tail.

Do not "fix" this by lengthening the pad alone. A flat long tail is right after a
pause and wrong in continuous speech, where it drags the first phoneme of the NEXT
sentence in under the end card — ending on a finished sentence and then playing
0.4s of the following one is the same defect in a hat. The pad takes only the gap
that is actually there, floored; the fade covers the rest.

**Verified by re-rendering a delivered clip into a scratch directory** (never over
the delivered file): `03-that-bar-money-is-buying-stock`, whose shipped version
ends **+3.9 dB above** its own median speech level, re-renders at **-17.3 dB**.
The last 200ms went from `########++` (eight hundredths of a second at full speech
level, then a partial drop) to `.......` — the word releases, the tail decays, the
card takes it. A 21 dB improvement in how the clip ends.

**A sentence can be finished and still not LAND**, and that is the third part of
the rule — the ending has to connect to the main idea. Read off the delivered
archive, clips end on "go.", "that.", "this.", "about.", "good.", "way." and
"through.": grammatical full stops on sentences whose meaning lives in something
already said, so the clip stops on a pronoun and the payoff is a sentence away in
one direction or the other. `TRAIL\_OFF` in `WLAMclip.py` holds the words and
preflight WARNs on them, naming the word. It is a WARN and must stay one — whether
"That's it." is a landing or a trail-off is an editorial call about the moment,
and that is not decidable from a word list. **When you see it, go and read the
transcript either side of the out-point** rather than shipping on the fact that
the check was only yellow.

Then dedupe hard — lenses find the same moment — and spread the final set across
the whole video rather than clustering in the first five minutes.

**If subagents are available, this parallelises well**: one agent per lens, then
one verifier per candidate that is told to refute it, then one pass to dedupe
and rank. That structure is what produced the WLAM slate: 60 candidates found, 16
killed, ranked into 10.

Write the result to `scripts/slate.json`:

```json
{"clips": \[{
  "rank": 1, "slug": "never-tell-you-what-to-buy",
  "start": 1946.6, "end": 1983.7, "mode": "head",
  "head\_crop": \[830, 922, 990, 158],
  "hook": "I'll never tell you what to buy",
  "quote": "verbatim spoken words",
  "why": "one sentence on why it performs",
  "angle": "no-advice-stance",
  "platform\_caption": "...", "linkedin\_caption": "...", "hashtags": "..."
}]}
```

## The panel was built on a generated source, and it cost 72 GB

**Fixed 2026-08-28.** For a while `duo` simply would not render at 60-90 seconds
on this machine: 19 GB resident, swap driven from its 6 GB base to 97 GB, and
0.21 seconds of CPU in 29 seconds of wall clock. It failed as a **hang**, not an
error. A whole-set `build\_all` stalled on its third clip.

**THE CAUSE WAS THE PANEL, NOT THE LENGTH AND NOT THE CUTS.** All three packed
modes — `share`, `duo`, `duo\_share` — built their panel from a generated source:

&#x20;   color=c=...:s=1080x1920:r=30:d=58.4\[stack];\[stack]\[first]overlay=0:0\[s1]


A `color` source is infinitely fast and unbounded, so ffmpeg's scheduler pulls
frames from it as quickly as the overlay will take them — while the band feeding
the OVERLAY input arrives slowly, through select → split → crop → lanczos scale →
unsharp → punch overlay. `framesync` holds the fast side waiting for the slow
one, and the queue becomes the whole clip.

Measured on the duo clip that would not render, **with the output discarded** so
the encoder could not be blamed:

|||
|-|-|
|`color` + two overlays|**72.27 GB**, killed by the OS at 590s|
|`pad` + one overlay|**2.49 GB**, exit 0 in 53s|

And on the real render, end to end, of the clip that could not be made:

|||
|-|-|
|before|19 GB resident, 0.21s of CPU in 29s, never finished|
|after|**1.67 GB peak, done in 143s**, 61.1s delivered|

A re-render of a delivered `share` clip through the new path came out at 2.50 GB
and **the same 35.1 MB**, with the panel seam at **exactly (887, 921) in both**
and frames differing by 0.44 mean gray - crf-19 encoder noise, not geometry.

Padding the first band to the panel is **exactly the same composite** — `pad`
places it at (0,0) on a panel-coloured canvas of the panel's own size — and it
drops an overlay stage as well, because the first band no longer has to be
overlaid at all. `panel\_base()` is the one owner.

`head` and `head\_follow` were never affected: they composite onto a real,
decode-limited stream, which is what this now makes the packed modes do too.
`duo` hit it first because it is the heaviest of the three; `share` and
`duo\_share` were on the same road.

### What I got wrong first, and why it was plausible

Recorded because the wrong answer was measured, argued, and written down before
it was tested properly. Three separate hypotheses failed:

|hypothesis|measured|
|-|-|
|the N trims in `cut\_graph` force a split, and a split buffers|isolated, the cut stage is **0.18 GB in EITHER mode**|
|the three caption/hook/CTA PNG sequences (1753 frames each, 8.3 MB decoded)|adding all three: **0.43 GB**|
|the b-roll overlays with shifted PTS|adding those too: **0.58 GB**|
|the tempo `setpts`|bisected out: still runaway at 14.11 GB|
|the punch's extra per-band split|bisected out: still runaway at 13.11 GB|

Only replacing `color` fixed it. **The lesson is the method, not the answer:
bisect the ACTUAL captured command with the output sent to `null`.** Reasoning
about which filter "must" be buffering produced three confident wrong answers in
a row, each of which survived until it was measured.

### And two false readings of progress, which cost more than the bug

Both come from trusting the wrong signal. Sample `ps -o time= -p <ffmpeg>` twice,
60s apart: real work advances CPU time by **minutes**, a stall by fractions of a
second.

* **file size** — the muxer writes in bursts. The output sat at 48,758,832 bytes
across three separate runs, which reads like a deterministic freeze and is not.
A run that looked frozen by that measure was doing 3m50s of CPU per 60s.
* **your own timeout** — two runs were killed at ten minutes and written down as
hangs when they were merely slow.

### `cut\_graph` is one `select` now, and that is a separate improvement

The trims were not the memory bug, but they were still worth replacing. One
`select` has a single consumer of the input, so no split is inserted at all.

`gte(t,s)\*lt(t,e)`, **not** `between(t,s,e)` — `between` is inclusive at both
ends, keeps the frame sitting exactly on a span's end that `trim` excludes, and
that is one frame per span, up to 40 on a real clip. Verified on a synthetic
source: on frame-aligned spans the two modes produce **840 of 840 identical
frames, worst diff 0.000**. On unaligned spans they differ by one frame and
`select` is the arithmetically correct one (823 against an ideal 823.5, where
`trim` gave 824), and its audio and video durations match exactly (27.456 /
27.456) where `trim`'s differed by 16.7ms.

The mute gets simpler with it: one audio branch means no `asplit`, which retires
the documented trap that a filter OUTPUT label may only be consumed once — one
`\[amuted]` fed into every `atrim` looked right and silently muted only the first
kept span.

`"cut\_mode": "trim"` in project.json restores the old path for rollback. The
kept-span list has ONE owner (`keep\_spans`) and both modes read it, so they can
never disagree about what to keep.

## THE THREE TEMPLATES

**Every clip is one of exactly three.** The owner set this on 2026-08-28 and it
replaces the five-mode vocabulary that came before it:

> \*"There's only going to be three templates. First is a single person just
> talking, plus b-roll. Second is a conversation between two people, and it
> switches based on who's talking — the whole screen switches. Third is that
> same idea but with the screen share at the bottom. And there's no other way to
> do it."\*

|#|mode|what is on screen|needs|
|-|-|-|-|
|1|`head`|**one person, full frame**|`head\_crop` on a two-up|
|2|`conversation`|**one person full frame, CUTTING to whoever is talking**|`follow\_crops`, `follow\_tiles`, `speaker`|
|3|`conversation\_share`|**whoever is talking on top, the shared screen below**|`follow\_pips`, `share\_crop`, `speaker`|

**ALL THREE ALWAYS CARRY B-ROLL.** *"All of them will always have b-roll. It'll
never not be a video without b-roll."* `check\_broll` already refuses a clip with
no approved insert, in every mode — not new, but now a property of the templates
rather than a rule sitting beside them.

### Two people are NEVER on screen at once

The whole point of the change, and an editorial judgement:

> \*"When you have two people on the same clip it makes it not seem very
> professional, because then people are just sitting there waiting. It should
> always be one person talking at one time. You're losing real estate on the
> phone."\*

He is right about the real estate, and the pipeline had the rest in front of it
without drawing the conclusion:

* a fixed crop on a two-up shows the **listener** for every second the other
person holds the floor — visible in any frame pulled from one, and the defect
the owner named on the first delivered pair;
* `duo`'s lower band structurally **cannot** keep a mouth clear of the platform
chrome: only 463px of its 953px band sits above the line, and the crop that
would fix it needs `cy >= 378` where the source allows `cy <= 233`.

*(An earlier version of this passage quoted a 0.90x-against-1.32x sync ratio. That
measurement was flawed and has been retracted — see "A MEASUREMENT THAT WAS
WRONG". The argument does not need it: the frames show it.)*

`duo` and `duo\_share` are **RETIRED** — refused rather than deleted, so a re-cut
of an archived show fails loudly with a pointer instead of a KeyError.
`"allow\_legacy\_duo": true` on the clip re-opens them for that one purpose.

`share` survives as **template 3 with one speaker** — the degenerate case rather
than a fourth template, because a solo presenter has nobody to cut to.
`head\_follow` is an alias of `conversation`. `canonical\_mode()` is the single
resolution point, and both `render()` and `preflight` call it before anything
branches on the name.

### What template 3 actually is

`share` with a **following face band** — not a new kind of panel. The packing,
the fill-the-face / fit-the-app split and the app's edge extension are all
`pack\_share`'s, unchanged. What moves is which camera tile is scaled into the
face band, on the same turn schedule `conversation` uses. It replaces
`duo\_share`, which put both tiles **side by side** and halved each face on the
smaller half of the panel.

**THE MEASUREMENT TILES MOVE WITH THE LAYOUT, and that is a real trap.** On a
two-up the faces are the halves of the frame; in a screen share they are the
camera **rail**, somewhere else entirely. `project.json` holds only one
`follow\_tiles`, so a `conversation\_share` clip using the two-up halves would
score motion in two rectangles containing the shared app — and `turns.plan`
would decide nothing, or decide wrong. In share the **pips ARE the faces**, so
`render()` derives the measurement tiles from `follow\_pips` and takes the names
from `follow\_tiles`.

### Who is talking: boundaries from the AUDIO, identity over a whole turn

The owner, watching the first delivered pair: *"Stephen Flanagan is on the screen
but BigBeat is talking for the first three seconds... whoever is speaking, that's
who you need to cut to. Never the opposite."*

He was right and the per-window pass had it wrong across **twenty-nine seconds**.
Three things were broken, and the two obvious repairs fixed none of them —
sweeping the window 1.0→3.0s and the tile sampling 96→320px moved the numbers a
few points and the answer not at all.

**1. The decision was made one second at a time.** Ten samples, split into loud
and quiet, is noise. **The sound says WHEN the speaker changes; the picture says
WHO.** tinydiarize (`whisper-cli -tdrz`) gives the boundaries and each segment is
scored as a WHOLE — three hundred samples instead of ten.

**2. The mouth ROI was a fixed fraction of the tile** — rows 45–92%, cols 22–78%,
which assumes a centred face. Measured on this rig, one speaker's face sits at
x0.04–0.67 of his half and the other's at x0.48–0.89, so the fixed box put the
second speaker's **animated video wall** inside his "mouth" region. A moving
background scores exactly like a moving mouth. The mouth now comes from the face
the cascade actually finds.

**3. HOLDING IS ALSO A DECISION, and it was the one that shipped the defect.**
Three consecutive segments scored the same speaker at 1.16x, 1.13x and 1.12x —
each under the 1.25x CLEAR bar, so all three were discarded and inherited the
PREVIOUS speaker, putting the wrong man on screen for 47 seconds. Three weak
readings that agree are evidence; throwing them away is not caution, it is a
different guess with no measurement behind it. `MARGIN\_DECIDE` 1.08 acts on them;
only a CLEAR reading resets the running answer, so weak agreement cannot drag the
schedule off a confident call.

Also: the marked speaker CHANGES alone are too sparse to cut on — five on a 109s
span, leaving a 47.7s stretch containing both speakers that scores 1.01x and is
undecidable. **Every utterance boundary is a candidate**, and the merge collapses
the runs back down, so a boundary that was not a real change costs nothing.

Verified the way the owner verified it — by looking. At +1s, +3s and +5s the old
clip shows the listener with his mouth closed under the words "for a fact / that
members / are watching us", and a nameplate naming him. The new clip shows the
speaker, mouth open, saying them, correctly named.

### THE CONFIDENCE NUMBER DOES NOT MEAN THE SCHEDULE IS RIGHT

**08.28.26. This is the most important thing on this page about follow clips.**

The owner watched a `conversation` clip and said: *"Steven Flanagan again is
talking, and it's showing a picture of BigBeat. The first twenty five, thirty
seconds is great, but then towards the end it fucks up. Thirty seconds in on
this clip, it's fucked."* He was right, to the second — at +30s the words are
"AI is not a substitute for human intelligence", Flanagan is saying them, and
BigBeat is on screen.

That clip's schedule reported **69% measured**. So the number was checked against
ground truth taken from the transcript (direct address — "You know, Steve, I did
want to make an AI" — plus the question-and-answer structure, both confirmed by
pulling frames):

|boundary set|confidence it reported|how much it got RIGHT|
|-|-|-|
|tdrz marks only|69%|**43%**|
|+ transcript cue edges|59%|**39%**|
|+ 5s minimum spacing|68%|**34%**|
|+ 8s minimum spacing|74%|**36%**|

Every variant is **at or below chance** for a two-person problem, and the most
confident of the four was the second worst. `FOLLOW\_MIN\_CONF` was gating on a
number that carries no information about correctness — it was passing this clip
at 48% and 59% while the largest turn in it was wrong.

**So the gate is no longer a number. It is the frames.**

&#x20;   python3 verify\_turns.py <slug>


That writes a sheet: both faces at the **middle** of every turn, side by side,
with the schedule's choice framed in green. Read down it — if the framed face is
the one with the open mouth on every row, the schedule is right. `render()` now
REFUSES a `conversation` or `conversation\_share` clip unless the clip carries
`"speaker\_verified": true`, because the whole failure is that a wrong schedule is
indistinguishable from a right one from inside the code.

**It samples the MIDDLE on purpose.** Twice, edges were checked, looked right,
and the turn was wrong: a handover is where both mouths move, so whichever face
you pull near a boundary agrees with you. The error lives in the middle of a long
held turn. `EDGE\_GUARD` keeps every sample 1.0s clear of both ends.

### What was fixed, and what is still broken

**Fixed, and measured.** The speech-gated ratio asks "does this mouth move more
on loud frames than quiet ones", which needs the tile to fall quiet *inside* the
segment. A speaker who never pauses has no quiet baseline, so:

&#x20;   steve     loud 0.846   quiet 2.316   ratio 0.37
    flanagan  loud 9.546   quiet 9.723   ratio 0.98


Flanagan has **eleven times** the mouth motion and is plainly talking — the
frames confirm it — but the still man wins on ratio. The primary score is now
**LIFT**: the segment's motion against *that same tile's own median over the
whole span*, which makes two differently-lit, differently-framed tiles
comparable. The ratio is kept but may only **veto** into uncertainty, never flip
the answer, because it still guards the case lift cannot see — a listener who
nods or laughs hard. On whole segments lift scored 4/4 where the ratio scored
2/4.

**Also fixed:** a tile where the cascade finds **no face** falls back to a
centred box and used to report *0.95 confidence across twelve turns* — a number
computed entirely from background pixels. That now zeroes the confidence and
marks the schedule `degraded`.

**Tried and REVERTED:** splitting on transcript cue edges as well as tdrz marks.
Right in principle — a handover lands on a full stop — but it fragments the span
into segments too short to score, and it measured worse (39% against 43%). Do
not re-add it without a better scorer underneath.

**The limit of inferring it.** Mouth motion cannot reliably say *which of two
faces* is speaking on this material. Pitch clustering was tried as a replacement
(autocorrelation F0 on a 0.4s grid, 2-means over the span) and reached 60% —
better than the picture, still not usable, and it octave-errored badly enough to
report a 192 Hz "male" voice.

### THE ROUTE THAT IS EXACT — and the easiest one is the stream's own transcript

**Stop inferring. The platform already knows.** It has each participant on a
separate feed, so its transcript says WHO said each line. That is not a better
guess, it is a record. Measured on the 08.26 span the picture got wrong — the
41-second Flanagan monologue plus Steve's question inside it — the transcript
route returns **100% correct at 100% coverage**, against the picture's 43%.

&#x20;   "speaker\_transcript": "WLAM Live 08\_26\_26 transcript.vtt"


in `project.json`, and `plan()` uses it ahead of everything else. Inspect one
before trusting it:

&#x20;   python3 speakers.py <transcript>


**It must NAME the speakers.** `<v Stephen Flanagan>`, or `Stephen Flanagan:` at
the head of the line. YouTube's auto-captions carry no names and are useless for
this; StreamYard, Restream, Riverside and Zoom all label them. `speakers.py`
sniffs the shape — VTT voice tags, `Name:` cue bodies, Zoom's .txt, plain text,
JSON — so hand it whatever the download gives you.

**ITS TIMESTAMPS ARE DISCARDED, AND THAT IS THE WHOLE TRICK.** The download and
the stream do not share a clock: there is pre-roll, the capture starts
elsewhere, and a few seconds of offset puts every cut on the wrong face *while
looking entirely plausible* — the worst failure available here, because nothing
downstream can see it. So only the WORDS and the NAMES are taken. `difflib`
aligns them against `cues.json`, which whisper made from the master itself and
is therefore right by construction, and each labelled turn is placed at the
master's time for the words it matched. A turn matching less than `MIN\_MATCH` of
its words is DROPPED rather than placed by guesswork.

Proved with a synthetic transcript **37.5s out of clock** from a different ASR
that dropped 8% of its words: every turn landed on its true master time.
`selftest` reproduces that offset on every run so the discipline cannot rot.

Names map to tiles automatically — longest tile name first, so `steve` cannot
claim "**Steve**n Flanagan" ahead of `flanagan`. Override with
`"speaker\_names": {"Stephen Flanagan": "flanagan"}` when the platform uses
handles rather than names.

### The other exact route: one audio file per person

**Stop inferring. Record it.** Given one track per speaker, "who is talking" is
two levels compared — no model, nothing to tune, and it is *right*, not 90-odd
percent right. Synthesised at −20 dB of mic bleed (what an open mic in a room
actually leaks) `track\_turns` recovers every turn with exact boundaries:
**100.0% against 43% for the picture**, and `selftest.py` asserts it on every
run so it cannot rot.

This is a recording SETTING, not a purchase. Every live rig has it:

|rig|where|
|-|-|
|Zoom|Settings → Recording → **"Record a separate audio file for each participant"**|
|OBS|Settings → Output → Recording → Audio Track (tick 1–6), then assign one source per track in Advanced Audio Properties|
|Ecamm Live|Recording → **Multi-track audio**|
|Riverside / StreamYard / Restream|per-participant tracks are standard on the download page — take the **WAVs**, not the mixed mp4|

Then name them in `project.json`, keyed by the **same names as `follow\_tiles`**:

```json
"speaker\_tracks": {
  "steve":    "tracks/steve.wav",
  "flanagan": "tracks/flanagan.wav"
}
```

`plan()` short-circuits to them the moment they are there. Paths are relative to
the work directory or absolute.

**They must come from the same recording as the master.** A separately-started
file is offset, and an offset track is confidently wrong — the worst failure
mode there is. `check\_tracks()` cross-correlates each track's envelope against
the master's and **refuses** anything more than 0.3s out rather than trusting
it. The published YouTube file is a re-encode (`encoder=Lavf61.7.100` on the
08.26 master) and its stereo pair is dual mono — correlation +1.0000, both
channels identical — so nothing can be recovered from the download. The tracks
have to come off the rig.

**What still needs one look per show:** which track is which person, and which
tile is which person. Both are show-level facts, so `"speaker\_verified": true`
may now sit in `project.json` rather than on every clip. `verify\_turns.py`
answers it in one sheet.

**The order of preference, and it is not close:**

|route|correct|what it costs|
|-|-|-|
|the stream's labelled transcript|**100%**|a download you already have|
|per-speaker audio tracks|**100%**|a recording setting|
|hosted diarizing ASR (Deepgram, AssemblyAI)|high|an API key, audio leaves the machine|
|pyannote/WhisperX locally|high|torch, a HF token, gated model terms|
|the picture (mouth motion)|**43%**|nothing, and it is worth what it costs|

Failing all of them, `head` is the template that cannot get this wrong, and a
follow clip ships only after somebody has read the sheet.

### THE MASSIVE VOCABULARY RUN — 2026-08-28

The owner: *"we almost wanna have a clip or a trigger for every single word...
tens of thousands of words that they would say. If a noun comes up, like a city
or a person or a thing, those definitely should be prioritized... any noun that
comes up should be the one that has the b-roll."* Backend only, explicitly:
*"we're not making a new clip... we're just massively updating the back end of
all our terms."*

**Measured the gap before generating anything.** Every `cues.json` and `.srt`
across the working folders and Desktop — 343 files, 541,796 sentences, \~9.8M
words — was tokenised and checked against the existing vocabulary. **9,895**
distinct words appeared 3+ times and had no entry at all.

**Two fan-outs, not one.** A 35-agent wave classified the actual gap words
found in the corpus, each with a real sentence for context. A separate 45-agent
wave covered systematic NOUN DOMAINS the corpus doesn't fully exercise yet -
world cities, countries, US agencies, commodities, sports, occupations, and 37
more - because the goal is coverage of what COULD be said, not just what has
been so far.

**Results: EXPAND 11,901 → 31,135, PEOPLE 142 → 1,717, ABSTRACT 2,911 → 6,667,
NOT\_A\_PICTURE 63 → 3,084.**

**Nothing was trusted on the way in.** Every agent's output ran through a
merge step that re-checked the SAME rules against the SAME picture library,
independent of what the agents claimed:

* **Reuse first.** Of 19,239 new EXPAND entries, 15,375 point at one of the
2,191 pictures already in the library. Only 1,033 new pictures were needed.
* **Context beats a domain guess.** Where the corpus-reading wave and the
domain wave disagreed on a person's identity, the corpus-reading call was
checked against real transcript sentences by hand and was right or safely
cautious every time; the domain guess was wrong every time. Confirmed
cases: "cramer" is Senator Kevin Cramer in this show, never Jim Cramer.
"newton" is a unit ("newton-meter chip") on an Apple-keynote clip, not Isaac
Newton. "newsom" names a different person entirely in the sentence that
uses it. "zell" is the payment app Zelle mistranscribed, not Sam Zell.
"diamond" is ASR mangling "Dimon" in ALL-CAPS hearing captions - real, but
too risky to ship, since "diamond" is also an ordinary noun; kept as the
gemstone. Where a real person WAS confirmed but the bare surname collides
with something more common ("ford" the carmaker vs Ontario Premier Doug
Ford), the surname keeps the common sense and the person is filed under
their full name instead.
* **Two production bugs found by the merge script itself, both fixed at the
source:** `NAME\_TOKENS` (which blocks a person's name inside a search term)
was extracted from EVERY word of a compound `PEOPLE` key like "bill ackman"
or "chair powell", so it flagged "medical bill paperwork" and "oncology
chemotherapy treatment chair" as containing a person's name - the FIRST-name
or TITLE half, never the risky half. Fixed to use only the surname (last
token). And the sacred-picture check didn't know that reusing an EXISTING
picture (like Brazil's own Christ Redeemer photo, already shipped) is not a
new pairing to scrutinise for a new word like "reais" - fixed to skip the
check on exact reuse.
* **`\_lint\_vocabulary()` caught two real classes on its own**, both because
the write is verified by re-importing the module, not by trusting the
splice. 128 new EXPAND values used phrases the compliance filter blocks
outright - `chart`, `candlestick`, `ticker`, `forex` - because that is what
the stock libraries this pipeline searches return ZERO results for. All 128
collapsed to 16 distinct picture strings and were reworded (e.g.
`"candlestick chart trading screen"` → `"traders working stock exchange floor"`). And 27 genuinely religious words - amen, archbishop, baptist,
belfry, chaplain, deacon, muezzin, mullah, nave, transept, and more - had no
entry in `SACRED\_WORDS` even though their close synonyms (cathedral,
monastery, abbey) already did; filled the gap in two small, evidence-based
commits rather than relax the rule. `spire`/`spires` and three ambiguous
biblical-also-modern first names (isaac, isaiah, jacob) were deliberately
left unmapped - the same over-match risk `cross` was dropped for earlier.
* **The splice is by AST, not by regex**, on a file where EXPAND alone is now
31,135 entries: the exact line span of each literal comes from Python's own
parser, insertion happens bottom-up so earlier spans never shift, and the
result is re-parsed and re-imported before it is allowed to stand - a write
that fails either check is reverted automatically. It failed twice on the
real defects above and reverted cleanly both times.

**Measured the effect, not just the mechanics.** `vocabcheck.py save` took a
before-snapshot (80,130 group winners) before any of this started, specifically
so the after-effect would be a measurement and not an assertion. After:
87,931 groups, 10,276 winners displaced, 56,154 new, 48,353 lost. The new
top winners are overwhelmingly real named people and concrete nouns from the
corpus's own Senate Banking hearing content (Warren, Scott, Kennedy, Warnock,
Brown, Tillis, Rounds, Trump, Powell) and finance nouns (financial, committee,
inflation, consumers) that previously had no entry to win with - exactly the
"a noun should be the one that gets the b-roll" the owner asked for. A change
this large touches too many groups to hand-verify each one tonight; the real
verification is the next clip actually cut with it, watched the way this file
says to watch everything - by pulling frames.

1113 selftest checks, all clear.

### THE FRAME IS NEVER DEAD — the drift under the punch

**The cutaways breathed and the person talking did not.** `punch` is a two-state
A/B toggle at 1.06x with a 2.0s minimum dwell, so BETWEEN flips the camera does
not move at all — not subtly, mathematically zero. Measured on the 08.28
delivered clip: 10 framing changes, median 5.0s apart, and a **longest unchanged
hold of 9.1 seconds**. Meanwhile every cutaway drifts continuously
(`BROLL\_MOVES`). That is backwards, and it is most of the difference between a
clip that reads as edited and one that reads as exported.

`face\_chain()` now lays a slow continuous move UNDER the punch, so the toggle is
the accent rather than the only motion. One definition, used by every mode that
puts a face full-frame, so framings A and B drift together and the punch stays a
clean discrete step.

**By over-scale and a moving crop, not `zoompan`.** The picture is scaled
`DRIFT\_OVERSCALE` larger than the panel and a panel-sized window walks around
inside the margin — the same shape `broll\_drift` already uses. `zoompan`
recomputes an integer crop per frame, and at single pixels per second the
rounding IS the motion: it would sit still and then jump.

**Two shapes were tried and the first one was wrong.** Both measured:

&#x20;   sine       stalls of 44 and 54 frames (1.5-1.8s), then a jump
    triangle   moves every 2 frames median, worst 27 at a turning point


**AND THE "1px GRID" IN THE FIRST VERSION OF THIS SECTION WAS A FICTION.**
ffmpeg FLOORS crop x/y to even on yuv420p — measured directly, `crop=32:32:10`
and `crop=32:32:11` render byte-identical while `:11` and `:12` differ by 27.17
mean. The first build "fixed" the judder by rounding to whole pixels and
verified it by evaluating the EXPRESSION in Python, which is not what ships; the
delivered step was 2px the whole time. The fix is VELOCITY, not rounding — the
amplitudes and periods are set to \~14px/s so a 2px step lands every \~4 frames
per axis, and because the axes run on different periods the frame moves about
every 2. All of those numbers come from tracking a background patch in the
DELIVERED file at full resolution.

A sine spends most of its time near a turning point where velocity goes to zero,
and a pixel grid turns "very slow" into "stopped" — so it juddered exactly where
the eye had settled, twice per period. A triangle holds constant speed the whole
way and turns only twice per period. The even-grid `2\*round(../2)` that broll
uses is right for broll at \~133px/s and wrong here at \~8px/s, so this rounds to
whole pixels: half the step, twice as often.

Two details that are load-bearing: the `mod()` comma is **escaped**, or it ends
the filter early; and the triangle carries a **+0.25 phase** so `t=0` is the
MIDDLE of the travel — without it the clip opens 14px right and 18px low of the
framing `centre\_on\_face` computed and `HEADROOM` measured, so the composition
checked before the render is not the one in the first frame. The vertical centre
is also biased up (`DRIFT\_BIAS\_Y`), because a larger crop y puts the face HIGHER
in frame — the safe direction for the chin-under-chrome check.

### A light grade, because the clips are only as good as the cameras

The face crop got `unsharp` and nothing else, so a guest on a flat webcam and the
host on a good one shipped as two different-looking shows. `eq` now applies a
deliberately small lift — contrast 1.03, saturation 1.05, measured at +3.2%
contrast and a max per-pixel change of 13/255. Enough to make them siblings, not
enough to be a look of its own. No curves, no vignette.

It lives INSIDE `reframe\_chain` on purpose: the caption-colour probe samples that
same chain, so the words are coloured against the pixels that actually ship.

### THE PULSE WAS FINE AND THE MEASUREMENT WAS WRONG — again

Reported to the owner that the "Sign up free" pulse was "2px per edge on a phone,
below the perceptual floor", and recommended changing it. **That was wrong, and
the pulse was left alone.**

The error: quoting total DISPLACEMENT when whether slow motion is perceptible
depends on VELOCITY. Measured properly off `cta\_state` over the settled window,
excluding the arrival and exit ramps that are supposed to be fast:

&#x20;   edge displacement   0.00 .. 5.54 px (panel)   <- the number first quoted
    peak velocity       17.4 px/s panel = 6.3 px/s on a phone
    mean velocity        9.4 px/s panel = 3.4 px/s on a phone


The detection threshold for a slowly moving edge at phone viewing distance is
roughly 2-4 px/s. The pulse sits ABOVE it. `PILL\_PULSE\_AMP` stays at 0.024.

This is the third time in one session that a wrong measurement nearly drove a
change to working code — the retracted sync ratio, the face-offset direction
reported backwards off a cascade with a bad width filter, and now this. The
pattern each time: **a number that was easy to compute standing in for the
quantity that actually matters.** See "A MEASUREMENT THAT WAS WRONG"; the rule
there is the rule here.

### FASTER B-ROLL — measured against a reference, and it reverses two of my own floors

The owner sent a YouTube short and said the pace was what he wanted: *"I like the
fast changing of the clips ... talking about different nouns, the nouns come up
... can be quicker."* It was downloaded and MEASURED rather than described.

**What that reference actually is:** 20.7s, 20 cuts, **58 cuts per minute**,
median shot **1.03s**, and not one shot over 2.0s or under 0.5s. Face detection
reads 15%, and those are people inside the footage — **there is no presenter.**
It is a voiceover montage, and that single fact is why it can cut every second:
there is nobody to cut back to.

**Two things it does NOT have, both of which were assumed:**

* **No flashes.** Zero luma spikes that return, zero near-white frames, across
all 621 frames. The "subtle flash" impression comes from the CUT RATE.
* **No zoom punch on the cuts.** Motion after a cut measures 8.6–10.2 against a
mid-shot baseline of 8.09. Flat.

Do not build either of those on the strength of remembering them.

**The arithmetic that forced a decision.** At 4 inserts × 4.0s the old settings
were ALREADY at the 30% ceiling — so there was no way to add pictures without
opening a door. Both doors were ones the owner had closed himself:
`BROLL\_HOLD\_MIN 3.0` (*"twice now, unprompted, he has landed on three seconds"*,
so it doesn't feel rushed) and `BROLL\_MIN\_FACE 5.5` (*"NOT licence to drift
further"*). He was shown the trade and chose: *"I don't mind faster b-roll, but
then we need to be having more b-roll in each clip ... lower the floor to 2 1/2
seconds."*

&#x20;   BROLL\_HOLD\_MIN   3.0  -> 2.5     the settled floor; hold floor becomes 3.2
    BROLL\_HOLD       4.2  -> 3.6     also DIVIDES the ceiling in broll\_target
    BROLL\_EVERY     16.0  -> 10.0    6 inserts on a 59.3s body against 4
    BROLL\_MIN\_FACE   5.5  -> 4.5 -> 2.5   see "THE FACE GAP WAS THE BLOCKER"
    BROLL\_MAX\_FRAC  0.30  -> 0.38    or the new cadence is refused by construction


**Two of those lines were superseded a day later** — see "A HOLD IS A BAND NOW".
`BROLL\_EVERY` went 10.0 -> 6.0, `BROLL\_MIN\_FACE` 2.5 -> 1.5, and `BROLL\_HOLD`
**stopped dividing anything**: that division was the defect. `BROLL\_HOLD\_MIN`
did not move and must not — `PAN\_DONE` is baked into the library from it.

### THE FACE GAP WAS THE BLOCKER, and it was measured rather than argued

Raising the target to 6 did NOT produce 6 inserts. A delivered clip came back
with **three**, and the owner's response was the whole brief: *"the only problem
is the b-roll, there's not enough ... you need to have more b-roll incorporated
into all the clips going forward, almost double the amount."*

So the rejection paths in `candidates()` were instrumented on that real clip
rather than reasoned about, and they answered immediately:

&#x20;   6 dropped   too close to the previous insert     <- BROLL\_MIN\_FACE
    4 dropped   outside the placeable window         <- LEAD\_IN / TAIL\_CLEAR


The subjects were never missing — **33 of that body's 215 words carry a
picture.** They were being rejected for sitting near each other, which is
exactly what a dense stretch of speech looks like. `BROLL\_MIN\_FACE` 4.5 -> 2.5
took the same clip from 3 inserts to 5, 17% of the body to 28%.

2.5s still keeps two cutaways from touching, which is what the rule was written
for. **If clips start reading as a montage rather than a person talking, this is
the number that did it, and 4.5 is where it was.**

`BROLL\_HOLD` is not only the longest an insert may be: `broll\_target` divides
the ceiling BY it, so lowering the maximum is what buys the extra cutaway.
`int(0.38 \* 59.3 / 4.2)` is 5; `int(0.38 \* 59.3 / 3.6)` is 6.

`BROLL\_MIN\_FACE` was moved despite its own note because it became arithmetic:
six inserts averaging 3.6s leave 37.7s of face across seven gaps, 5.4s each, so
a 5.5s floor makes the requested cadence impossible to author on ANY span.

**Two bugs fell out of it.** `broll.MAX\_HOLD` was 4.6 while preflight's ceiling
was 4.2, so the tool that writes the slate could propose a hold the tool that
checks it would refuse — it is DERIVED from `q.BROLL\_HOLD` now and cannot
diverge again. And a selftest check was testing the button against a 2.5s
insert: it read `BROLL\_HOLD\_MIN`, which is the SETTLED floor, when the shortest
hold that can occur is that plus travel. It passed for years only because 3.0
happened to leave 1.95s against the button's 1.76s, and it failed the instant
the floor moved — on a length the pipeline cannot produce.

**What it delivers, measured on the 08.26 span:** holds fell from 4.0 to 3.2s.
It placed 4 inserts, not 6 — the binding limit there is SUBJECTS, not spacing
(gaps measured 6.3–10.6s against a 4.5s floor, so there was room it could not
fill). The cadence config now permits 6; the content decides. On a 91s body the
target is 9 against 6 before.

**If clips start reading as rushed, `BROLL\_HOLD\_MIN` is what did it, and 3.0 is
where it was.** If they read as a slideshow with a voiceover, that is
`BROLL\_MAX\_FRAC` at 0.38 against 0.30.

### A HOLD IS A BAND NOW, AND IT COMES FROM WHAT THE PICTURE IS — 2026-08-30

The owner, after the clip above: *"in a minute clip, there needs to be at least
ten ... a picture if it just says someone's name that I sent is, boom. Cut to
Elon. It's half a second, not even. You need to build it dynamically for the
b-roll that's what's being shown."* Reference: `youtube.com/shorts/mx9x5ni\_zAs`
— *"we don't want it exactly like it, but it's the feel."*

**The reference, measured.** 25.4s, 26 shots, **61 cuts a minute**, shot lengths
0.55 / 0.86 / 1.65 (min / median / max), stdev 0.32 on a mean of 0.98, longest
over shortest **3.0x**. Pulling frames from the three shortest and the three
longest shots settles the thing that matters: **the speaker is in both sets.**
He is in the rotation, not the bed under it — so the reference's *face gaps* are
themselves 0.55 to 1.65s. That is the measurement `BROLL\_MIN\_FACE` never had.

#### The blocker was in the renderer, and nothing could see it

`broll\_chain` emits two chained `fade ... alpha=1` filters. They SCALE the same
alpha plane, so they **MULTIPLY** wherever they overlap — which is any insert
shorter than `BROLL\_IN + BROLL\_OUT`. Rendered and measured on delivered pixels,
peak composite alpha:

&#x20;   hold 0.40 -> 0.275    0.60 -> 0.675    1.50 -> 0.996
    hold 0.50 -> 0.498    0.70 -> 0.996    3.60 -> 0.996


**A half-second cutaway was not a fast cut. It was a permanent 50% double
exposure of the picture over the speaker's face** — "a luma spike that jumps and
returns", the exact thing the first reference was measured NOT to do. The
owner's "boom, cut to Elon" was unrenderable for as long as it was asked for,
and no gate could see it: preflight scored the hold, never the alpha.

The undocumented `a1 - a0 < 0.8` guard turns out to be exactly this. 0.8 is
`BROLL\_IN + BROLL\_OUT` plus a frame — the shortest window where the old ramps
did not overlap. **It was the anti-ghost guard, spelled as a duration.**

`broll\_ramp(hold, k)` makes the travel a SHARE of the window, so the picture is
opaque for the middle at every length by construction. It returns today's
0.35/0.35 at and above 1.4s, and the archive's **217 authored holds bottom out
at 1.8** — so every clip ever shipped re-renders byte-identically at every legal
tempo. That was verified against the slates, not asserted.

#### Why a flash is legal without reversing "it feels rushed"

`BROLL\_HOLD\_MIN` was **two rules welded into one number**: how long a picture
needs to be read, and how long the SIGN-UP needs to arrive, settle and leave.
The one recorded rejection of fast b-roll names the second — *"cuz the broll +
signup feels very rushed"* — and the note under it already answered itself:
*"The reference does not carry an invitation button inside its cutaways. Ours
does, and that is the whole difference."*

`cta\_insert\_min()` is **2.81s** and it rides ONE insert per clip. So:

|kind|what it is|band|
|-|-|-|
|**flash**|a face — `\_person\_of` hit the portrait tier|0.55–1.10|
|**mark**|a named org, place or product|1.10–1.70|
|**object**|an ordinary mapped noun|1.30–2.20|
|**scene**|the query carries a scene head (skyline, crowd, refinery…)|2.00–3.20|
|**carrier**|a ROLE, not a kind: the one holding the sign-up|2.81–3.60|

**The gap between 1.60 and 3.20 is a WALL, not a hole.** An insert at 2.0s is
the length he rejected by name, and it was the button that made it rushed.

**`BROLL\_HOLD\_MIN` itself does not move**, and that is load-bearing: `PAN\_DONE`
derives from it and is baked into **1,795 assets with no migration path**.
Lowering it would give everything baked afterwards a half-second whip-pan while
the library ramps over three seconds.

`want` — the sentence-end rule — is untouched and still varies inside the band.
What it lacked was a cap that knows what it is looking at: `want` for "Bill
Gates" measured **8.93s** on the last delivered clip, so the sentence rule
clamped a PORTRAIT to the ceiling and made a name the LONGEST insert in the clip.

#### The count, and the placer

`broll\_target`'s ceiling converted a budget into a count by dividing by the
**maximum** hold — pricing a half-second flash at 3.6s. It was the binding term
at every body length and it bound **silently**, no warning, no preflight line:

&#x20;   body   raw  ceiling -> target     (asked for)
    60.0    10      6        6            10


The share becomes a budget in SECONDS (`broll\_budget`), spent where the holds
are actually chosen. `BROLL\_EVERY` 10.0 -> 6.0 is the owner's stated ten.

Placement was a greedy left-to-right walk, so it spent its face budget on
whichever anchors came first — and picturable words CLUSTER. Worse, once holds
could shrink it produced layouts that **violated `MIN\_FACE`**. `\_schedule()` is
a longest-chain DP at the band floors, then a growth pass that spends the room
the neighbours leave. Two questions, two answers: how many fit is decided at the
floors, how long each runs is decided after.

#### What he actually asked for: the picture matching the words

*"our problem is the connection to the caption to choosing the correct b-roll."*
Measured over 74 slates / 150 approved inserts:

* `hits = b.get("shortlist") or search(b\["term"])` was **the only fetch path
with no `semantic.rerank`** — 45% of approved inserts, shipped on raw lexical
order.
* **`\[] or search(term)` is falsy.** When propose found nothing on topic it
wrote `shortlist: \[]`, so fetch re-ran the raw search and shipped the top of
the very set the semantic floor had just rejected.
* The archive's wrong pictures are exactly this class: *server room network
cables* → a hospital heart monitor; *new york stock exchange* → a British flag.

**This was urgent at the new density, not merely untidy:** propose finds fewer
placeable subjects than a target of ten wants, the rest are authored BY HAND,
and hand-authored is precisely the no-shortlist path. Raising density without
this raises the wrong-picture rate mechanically.

The rerank now runs there too — and **persists the list and resets `pick`**,
because `pick` indexes what the operator was SHOWN and both listings print raw
order. Reranking without that re-creates "the picture you approved was not the
picture you got" under a new name.

A short insert also **seeks past a baked pan**. 275 stills are baked with a push
that lands ON the subject at 3.07s; played from zero a 1.3s flash showed 42% of
the travel and was gone before its own picture arrived — a corner of a building
and a cut. That is a wrong picture too.

#### The gates

preflight scored every insert against one 3.20–3.60 band built from constant
travel. **That single line is what made a sub-second insert impossible no matter
what the renderer could draw.** It now reads the per-insert ramp and the kind's
band, and an insert with no `kind` scores exactly as before, so all 74 slates
re-score byte-identically. Added:

* **a FLOOR on the share.** A count target is satisfiable by cutting to nothing:
ten 0.6s flashes hit ten cuts with 6.0s of picture, *less* b-roll than the
clip that prompted "you need more", while passing the gate that asks for more.
* **a refusal when nothing can carry the sign-up.** `CTA\_IN\_BODY` is False
whenever the end card is on, so a cutaway is the only in-body carrier. All
flashes = no sign-up anywhere, silently.
* **spread by RATIO, not equality.** `len(set(holds)) == 1` cannot see
3.5/3.6/3.6. Across 74 slates the max/min ratio has median **1.00** and p90
1.14 — this pipeline had never once produced variety.

**Measured on the 08.30 body:** 5 inserts / 5.1 cuts per minute / holds 1.1x
flat → **7 inserts / 7.1 cuts per minute / 1.10–3.60s / 3.3x spread.** selftest
1167 → 1423 checks.

**Ten a minute is NOT reached on that transcript, and the reason is not a
constant.** It carries an 18.7s stretch with no picturable word in it and caps
at 8 with every floor switched off. That is anchor SUPPLY, and it belongs to the
vocabulary — do not go looking for a number to lower.

**That is true of the 08.30 body and NOT true in general — corrected the same
day.** On the 08.26 Nike span `candidates()` proposed 18 subjects and
`\_schedule()` picked **14**, with a worst gap of 7.1s. The delivered clip had 10
and a 12.8s hole, and the difference was ATTRITION after propose: terms that
found no picture, an insert that collided with the nameplate, and two dropped as
duplicates. So when a clip comes out short, measure which of the two it is before
reaching for a constant — and note that `propose` OVERWRITES `c\["broll"]`, so it
cannot be re-run to repair a dropped row without destroying every approval in the
clip.

### B-ROLL CRAFT: why ten cutaways looked worse than three — 2026-08-30 (later)

The density change shipped and the owner watched it: *"it's coming across very,
very sloppy ... some of the pictures are not really coming across as clean and
sharp and professional. It's still coming across as kind of glitchy ... the
transitions and the way how they come up need to be more methodical ... the more
b-rolls the better, and that's very good. But now you need to really think about
the timing of the b-roll and the length of them ... the idea now is the b-roll
optimization of how long, when to use it, why it's used."*

**Every one of those had a specific, measurable cause. None of them was the
count.** More cutaways did not make the clip worse; they made four latent faults
visible at once, because each fault now happened ten times instead of three.

#### 1\. The dissolve was mush, and the fix is its SHAPE not its length

`fade` writes a **linear** alpha ramp. A cross-dissolve therefore spends its time
at alpha 0.5 — and at 0.5 the frame is neither picture. Both of ours are busy (a
face over a chart, against a full-bleed photograph), so the speaker ghosts
through the picture at every entrance and exit.

Measured on the delivered clip's own frames. A frame is **ambiguous** when it sits
more than 12 grey levels from BOTH source images:

&#x20;   ramp     linear   smoothstep   smoothstep²
    0.35s       8          6            4        <- 0.35 is the shipped length
    0.30s       7          5            3
    0.25s       6          4            4
    0.20s       6          4            2
    0.15s       4          2            2


**Shape buys as much as length.** That matters because the length is not ours to
shorten: 0.35 is the owner's own number (*"a little bit slower, a little bit
cleaner"*) and shortening it walks back toward the hard cut he has rejected three
times. Easing the ramp he approved gets the same result without touching it.

`BROLL\_ALPHA\_LUT` is a **256-entry table applied after the fades**. The fade still
writes a linear ramp; the table re-maps that ramp's *values* onto an S-curve. It
needs no notion of time, so it is a lookup rather than an evaluation:

&#x20;   two fades (today)          0.16s
    + alpha LUT smoothstep²    0.20s     <- ships
    geq smoothstep on alpha    2.10s     <- 13x, rejected


Applied **twice** because once is not enough on this material (6 ambiguous frames
against 4). Re-measured on the delivered file afterwards: the Trump flash crosses
in **3 ambiguous frames against 8** — it holds near the speaker, crosses fast,
settles. The plateau is untouched, so `broll\_ramp`'s full-opacity guarantee is
unaffected.

#### 2\. The opening hole had a cause, and it was the nameplate

`BROLL\_LEAD\_IN` is 5.0s and its comment says it clears "the hook card (opaque to
3.5s) and poster()". The bone nameplate runs **+3.3s to +7.5s**. So the window
5.0–7.5s let a cutaway be placed *under the clip's own nameplate*. `render()`
printed a note; nothing gated it and `candidates()` could not see it.

On the 08.26 clip that cost the **opening insert at +5.92s** — the name floated
over a shoe shop with the speaker nowhere on screen, so it was dropped — and
dropping it opened the **12.8s hole** the owner then called sloppy. One
collision, two complaints. The placeable window now derives from `attr\_window()`.

#### 3\. The payoff belongs on his face

The last sentence is the line the clip exists to deliver — on both recent clips
the slate's own `quote` IS that sentence — and `BROLL\_TAIL\_CLEAR` (3.0s) is not
long enough to cover it. The Nike pool duly offered *"one red apple among green
apples"* over *"this is a contrarian recovery trade on an iconic American
brand"*. Cutting away from the punchline to show a stock photo of an apple is the
most expensive thing this tool can do. Capped at `TAIL\_CLEAR + BROLL\_EVERY` so it
can never cost more than one cut.

#### 4\. An honest hole beats a generic picture

**Every wrong picture in that clip came from one mechanism.** `\_rank\_key`'s first
element is `query\_for(x) in used\_terms` — a hard demotion — so when the concrete
subject of a sentence has already been pictured earlier in the clip, the
**abstract runner-up wins the group by default**:

&#x20;   anchor        proposed                      wanted       why it lost
    excited    -> rollercoaster riders          turnaround   already used
    think      -> man looking out of a window   shoes        already used
    numbers    -> hands tallying a notebook     sporting     already used


All three were retyped by hand to *the ranker's own first choice* and all three
then passed the semantic floor. The pipeline knew the answer and threw it away —
and because filler still satisfies the count, nothing downstream could tell a
clip with ten subjects from a clip with seven subjects and three shrugs. It skips
now, and says which subject it was and why.

#### 5\. A portrait could not be fetched twice

A person's name may only be written over a hit whose `source` is `"people"` — the
rule that stops a photograph of a dollar bill being filed as "Bill Gates". But
the first successful fetch **bakes that portrait into the library**, so every
later search returns it with `source="library"` and the guard refused the very
picture it had just approved. Silent: the insert simply got no asset, and the
clip shipped without the one cutaway the owner had asked for by name.
`\_origin\_source()` reads the provenance back off the index row.

#### 6\. A ceiling on how long the picture may NOT change

`BROLL\_MIN\_FACE` is a floor on how CLOSE two cutaways may be and there has never
been anything on the other side, so a clip could satisfy every rule and still sit
on one shot for twelve seconds. `BROLL\_GAP\_MAX` is derived from the cut rate (the
reference's longest shot is 1.68x its mean, so 1.68 cut-intervals = 10.1s at
`BROLL\_EVERY` 6.0). **A WARN, never a refusal** — re-scored over every slate on
this machine, 19 of 19 clips carrying an approved insert exceed it, worst 36.1s.
A gate that refuses the entire archive gets `--force`d, and then it protects
nothing.

#### What was NOT shipped, and why it matters

A picture-legibility gate on the **"subject fraction"** (pixels more than 28 from
the frame median) separated the two mush pictures perfectly on the ten assets of
one clip — 0.14 and 0.17 against 0.37–0.90 — and **dissolved at scale**. Over 70
random library assets the distribution is continuous (p05 0.24, p25 0.41, median
0.55) with no gap anywhere, and the lowest scorers include an airport runway, a
boxing gym and a standing ovation. A 0.30 warn fires on 13% of the library,
mostly wrongly.

**It is still useful — as a TIE-BREAK, not a gate.** Among cells that have already
passed the semantic floor it picks the legible one, and that is how the two mush
pictures were replaced on this clip without changing a single term:

&#x20;   Sporting Goods   cell 0  tennis balls in a bag     luma  75  subj 0.35
                     cell 2  athlete with soccer cleats luma 133  subj 0.57  <- picked
    casino           cell 0  unlit machine bank        luma  38  subj 0.12
                     cell 4  people gambling           luma 132  subj 0.48  <- picked


**Set `pick` when the picture is dim or macro. The term is usually right and the
cell is usually wrong.** That is the single most useful manual move in this whole
pipeline, and it costs one integer.

#### A note on where these findings came from

Some of this was designed by subagents. **Two of them wrote their proposals
directly into the working tree**, and a later agent then read one of those
comments and cited it as pre-existing prior art. The tree was reverted to HEAD
and everything here was re-measured by hand before it shipped. If you run agents
over this repo, `git status` before you trust anything you read in it.

### THE LIBRARY WAS 84% UNREACHABLE — picture search, 2026-08-30 (later still)

Asked whether anything needed *building* to make caption-to-b-roll matching
better, given 1,783 assets and every caption on disk. The answer was yes, and
the reason is structural rather than a matter of tuning.

**`search\_library` matches on token overlap** against the stored term and title.
So an asset whose title happens to use different words is invisible however
right it is — a caption about *manufacturing* never reaches a clip titled
"workers on an assembly line", because no word is shared. Scoring 135 real
caption contexts from every slate on this machine against all 1,783 live rows:

> \*\*Only 291 assets (16.3%) can ever enter a top-5.\*\* And the reachable sixth is
> dominated by whatever sits nearest the centre of the embedding — a close-up of
> a "Need a Job" sign came top-5 for \*\*15.6% of all captions\*\*, a stock photo of
> coins for 11.1%, a portrait of Warren Buffett for 8.9%. Those are not answers,
> they are the shape of the space.

`visual.py` adds a **second door**. CLIP puts images and text in one vector
space, so every baked asset is decoded to four frames, each embedded once, and a
query phrase is compared to the frames directly. 1,776 assets / 7,104 frames,
about thirty minutes once; searches afterwards are instant and incremental.
**Reach 16.3% → 29.7%, worst hub 15.6% → 5.7%.**

It is an EXTRA tier, not a replacement. `search\_library` still runs first,
because a picture a human already approved *for these exact words* outranks one
that merely looks similar.

#### Feed it the TERM, not the sentence

The one thing to get right, and I got it wrong first. CLIP is trained on short
captions and returns noise on a spoken sentence. Same library, same model, the
only difference being what was embedded:

&#x20;   query                        fed the SENTENCE         fed the TERM
    people gambling in a casino  a graphics card          the 3 casino clips, 1-2-3
    a portrait of Donald Trump   Trump portrait 0.251     Trump portrait 0.298
    athletic shoes in a store    a forklift               the shoe assets, 1-2-3


`query\_for()` already produces exactly that phrase. So: **retrieval by picture,
judgement by meaning.** `semantic.py` keeps the sentence and keeps the final say.

#### Four frames per asset

One row per file meant one moment for a thirty-second clip, and a still baked
with a pan is a different picture at each end. An asset scores its **best**
frame, so the same file is now reachable from several different captions —
which multiplies the effective library without buying anything.

#### A picture that matches overrules a title that does not

`semantic.rerank` scores TITLES, so left alone it would have thrown away the
very assets this index exists to find. A hit above `PICTURE\_RESCUE` clears the
floor and then takes its ordinary place in the buckets — the same shape as the
existing `named` rescue. Proved on the insert the Nike clip had to DROP:

&#x20;   'empty retail store aisle shelves'   before: 21 found -> 0 kept
                                          after: 26 found -> 4 kept
    led by "Bare shelves at Sainsbury's", every one rescued by its PICTURE at a
    text score (0.44-0.49) below the 0.55 floor.


#### The hub correction ships at ZERO, and that is the measurement

It was specified from the text-space problem above, where it works (reach 16.3%
→ 23.7%, worst hub 15.6% → 6.7%). On the real picture index it does the
opposite:

&#x20;   weight   reach              worst hub
    0.0      528/1776  29.7%      5.7%
    0.5      233/1776  13.1%     48.7%
    1.0       39/1776   2.2%     96.8%


CLIP is far less hub-prone to begin with, and the offline asset-to-asset proxy
is not the quantity the text measurement used (they correlated at only r=0.72
even in the space it came from). Subtracting it does not suppress hubs, it
promotes ANTI-hubs — one isolated congressional portrait ended up winning 96.8%
of every query. **The mechanism and the stored array are kept; the weight stays
0.0 until somebody re-measures that table and it comes out the other way.**

#### What it buys, and where it does not

On the clip that prompted this, the two cells that had to be corrected BY HAND
are now the automatic first choice:

&#x20;   casino          "people gambling in a casino"      0.62   (was an unlit machine bank)
    Sporting Goods  "confident athlete with soccer cleats" 0.57 (was a macro of tennis balls)


And it stays honest where it should: `declining stock market chart red` still
returns nothing, because CLIP sees pictures and a falling red chart is a graphic
idea rather than a thing. **That is exactly why this is an extra tier and not a
replacement** — words win on abstractions, pictures win on people, places and
objects.

Degrades to today's behaviour with no model and no index, the same stance
`semantic.py` takes. Run `broll.py pictures` after a big `stock` run; it is
incremental, so a top-up costs only the assets baked that day.

### IT LEARNS FROM WHAT SHIPPED — 2026-08-30 (last)

The library recorded which TERMS a human corrected but not which PICTURES
survived to a delivered clip. **11 of 1,807 rows carried any usage count at
all**, and nothing read one to choose between two pictures that both match.

`shipped.json` records (picture, term) pairs that reached a rendered mp4.

* **At render, not at fetch.** Approval is not delivery: four inserts were
approved and then dropped on the 08.26 clip alone, so counting at fetch would
have filed four *rejected* pictures as good ones.
* **Term-conditional, never a bare popularity count.** A global counter is the
hub problem in different clothes — the most-used asset would start winning
queries it has nothing to do with, which is what the picture index exists to
stop.
* **Its own file**, beside `corrections.json`. The index is rewritten wholesale
by `fetch` and `stock`, and a long `stock` run has already clobbered rows a
`fetch` added that afternoon. A counter meant to be trusted must not live
where a background job can roll it back.

#### It had to RESCUE, and that is not where I first put it

The first version was a last-position tie-break. Measured **leave-one-out** over
180 approved inserts — the ledger built from every clip *except* the one under
test, so a picture never votes for itself — it changed **nothing**: 91/180
either way. A tie-break in last position only fires when meaning and naming are
both already tied, which on real candidate sets almost never happens.

&#x20;   placement                    rank 1   top 3
    none                          30.6%   37.2%
    tie-break, last in the key    30.6%   37.2%   <- did nothing
    +0.2 score bonus              33.3%   39.4%
    rescue over the floor         38.9%   48.3%
    bonus + rescue                42.2%   51.1%   <- ships


**The floor was exactly what it had to get past.** The floor judges the
SENTENCE; a picture a human chose for THESE WORDS and let through to a render is
evidence about the term that a sentence embedding cannot see.

Through the real pipeline, leave-one-out: **rank 1 50.6% → 53.9%, top 3 65.0% →
69.4%.** Modest today because only 30 pictures have shipped more than once and
leave-one-out removes a vote from each. It compounds with every render.

**If somebody demotes this back to a tie-break, that is a silent revert** — so
selftest asserts the signal reaches the floor.

#### How to read the accuracy number at all

`replay` is the honest test: for every insert a human approved, does the
pipeline return that same picture today? It is also what caught the stale cache
(the first run read 39.4% through cached pre-picture-index results). When
judging any change here, **build the evidence from clips other than the one you
are testing**, or the number is circular and always improves.

### THE PORTRAIT TIER WAS UNREACHABLE, AND A CLIP NEVER KNEW WHO "HE" WAS

The owner, on the clip cut from the Gates segment: *"he was talking about Bill
Gates ... and in that clip he mentioned Elon Musk ... we need to have another
agent or a skill or a Python machine that gets very good at context."*

Both faces were missing, for two different reasons.

#### 1\. 1,683 of 1,688 people could not be reached from speech

`\_is\_concrete` is the gate that decides whether the candidate walk offers a word
to the ranker at all. It tested `EXPAND`, the learned vocabulary and a hint list.
**`PEOPLE` was in none of them.** So a person was picturable only if their name
happened *also* to be an ordinary noun with a mapping:

> Measured: \*\*1,683 of 1,688 PEOPLE rows failed the test — 100% of them.\*\* The
> whole "Steve says Elon Musk, cut to Elon Musk" feature, with its curated names
> and its public-domain licence handling, was unreachable from ordinary speech.
> Donald Trump shipped in a delivered clip only because "trump" is one of five
> names that is also an English word.

`PEOPLE` is the FIRST test in that function now — which is what `\_rank\_key`, with
its explicit "a named human is the strongest subject a sentence can hold" tier,
had always assumed.

#### 2\. A name near the end was refused by a rule about an end-card wipe

The show says *"Or as **Elon** is now stressing"* 2.1s from the end.
`BROLL\_TAIL\_CLEAR` keeps the last three seconds free because `endcard.append`
freezes the final frame — a rule about ONE frame, applied as three seconds. A
**flash** may now sit inside it provided `BROLL\_TAIL\_FACE` (1.0s) of speaker
still follows, so the frame the wipe freezes is always his face.

**That fix needed making twice.** The window test was exempted and the hold was
then clamped against the FULL clearance three lines later, driving it negative:
"Elon" passed the test that was changed for it and was dropped by the one that
was not. selftest now refuses two readings of that number.

#### context.py — who "he" is

A clip cut from mid-segment inherits its subject. The show says *"Bill Gates'
6,000 word warning"* **33 seconds before the clip starts** and then discusses him
for two minutes as "he". `carried\_subject()` answers the one question the
transcript can support — which named person was the show on when this span
began, and is the span still on them — and **refuses whenever it is not sure**.

It is not a language model and it does not parse. It is recency, density, and
one piece of syntax:

|signal|why|
|-|-|
|**the possessive**|*"Lindsay Ellis has put this out about the three takeaways from **Bill Gates'** warning"* names the reporter and the subject; a plain count scores them equally. The apostrophe says which is which. Generalises: "Powell's comments", "Musk's plan".|
|**surname after the full name**|`gates` is deliberately not a PEOPLE key — it is an iron gate — so only the bigram was ever counted.|
|**not "they" / "their"**|on this material a company is "they". Admitting them made the Nike clip resolve to Kevin Warsh.|
|**apostrophes removed, not stripped**|`"He's"` strips to `"he's"`, which is not `"hes"` — the commonest third-person pronoun matched nothing and the founding case counted one pronoun instead of six.|

The portrait also had to be worth keeping: the scheduler maximised count, so Bill
Gates entered the pool at +15.0s and was **dropped for a tractor** on a clip
whose every sentence is about Bill Gates. Count is still first; among layouts of
the same size, the one that shows the subject's face now wins.

Result on that clip: **8 candidates → 9, now including Bill Gates at +15.9s and
Elon Musk at +62.5s.**

#### The title is the cheaper half, and it is wired now

The owner's follow-up: *"if we have it in the title, it's not gonna realistically
matter that much ... because the title and all the titles and the posting sheets
will be optimal as well because it'll be tied into it. Correct?"*

**It was not correct.** `context.py` was imported by `broll.py` and nothing else,
and it fed the b-roll path only. Titles, the hook and the posting sheet are
hand-authored in the slate with no connection to it — which is why that clip
shipped titled "Not just white collar" with no mention of Gates anywhere.

He is right about the principle, and it is the cheaper half: **a portrait helps
whoever presses play; a headline helps everyone who scrolls past**, which on a
feed is most of them. So the subject now flows through:

* `propose` records `about` on the **clip**, not just on one insert, so it
survives the portrait being dropped by the scheduler.
* preflight's **ABOUT** line says whether any title, hook or caption names him.
Reported, never refused — a headline that deliberately withholds the name
("He says AI takes your job") is a real editorial choice.
* `make\_sheet` prints it **directly above the boxes the operator types into**.

Demonstrated on the delivered clip, metadata only and no re-render: retitled to
*"Bill Gates: not just white collar"*, and both the gate and the sheet go green.

#### The lesson that cost two rounds, again

The first wiring referenced a `cues` that does not exist in that scope. It raised
`NameError` on every clip, a **blanket `except Exception`** caught it, and it
silently did nothing — so both fixes looked shipped and neither was. This file
already records the same shape costing three attempts on `\_person\_bigram`. A
swallowed exception here is indistinguishable from "there is no carried
subject", which is the correct answer most of the time. **Catch the exceptions
you expect, and say what you skipped.**

### Crosstalk is a PICKING problem before it is a detection problem

The span that failed measured **8.7 short cues per minute — the 73rd percentile
of that show**. Four handovers inside eleven seconds ("Well, that's good." /
"Good." / "Yeah." / "I'll say hi to them."). The detector was being asked to
follow something no measurement on this material can follow, and a clip of rapid
crosstalk is worse to watch anyway.

`pick.banter\_rate()` counts cues shorter than 2.5s per minute — free, because
`cues.json` is already loaded — and `score()` now penalises it on the two
templates that must cut to a talker. On the 08.26 two-up run it moved the top
candidate from 9.2/min to **4.3/min**, off the banter and onto a stretch where
one person holds the floor. preflight prints it as `CROSSTALK` and refuses above
12/min (p90).

**The fix for crosstalk is a different moment, not a cleverer cut.**

### A compliance pattern that only looked backwards

Found by running the picker in anger on 08.26. The top-ranked head candidate
contained:

> "For those of you who are buying SpaceX stock with me, I'm still going to be
> buying even more today."

**Zero flags.** The `position` pattern matched `bought`, `own`, `my position` —
past tense and possessives — and forward-looking intent walked straight through,
on a live markets show, in the single most sensitive phrasing there is. It now
matches "I'm going to be buying", "I'll be buying", and inviting the audience
into the same trade ("...with me"). Three more spans flagged across the master,
including "I'll be buying even more here on the open."

### A MEASUREMENT THAT WAS WRONG, and what it cost

**Retracted: every "does the face on screen match the voice" figure quoted before
2026-08-28 evening — 1.32x, 0.90x, 1.06x, 1.47x, 1.22x.** They came from a metric
with the *same* fixed-ROI flaw as the detector: it measured a fixed box in the
delivered frame, and because the two speakers' faces land in different places
after the crop, it measured one man's mouth and the other man's cheek. It scored
whichever schedule happened to align better, not whichever was correct — and it
disagreed with what the owner could plainly see.

Re-measured with a corrected metric that finds the face in the delivered frame
and tracks *its* mouth, the two detectors come out **1.05x (old) against 1.11x
(new)** — the right way round, and both close enough to 1.0 that the metric is
weak evidence either way. **The frames are the evidence; the ratio was never
strong enough to carry the weight put on it.**

Two guards were justified with those retracted numbers and are therefore
**provisional**: `FOLLOW\_MAX\_DOMINANCE` (0.65, warns when one speaker holds most
of the floor). **`FOLLOW\_MIN\_TILE\_W` no longer exists** - it was replaced by
`FOLLOW\_MIN\_FACE\_W` when the 500px figure turned out to rest on the retracted
ratio above; the guard now measures the FACE the detector scored, not the tile.
(The sentence below describes the retired constant and is kept for the reasoning.)
The old rule was (500px, warns when the camera tiles are too
small to read a mouth in). Both still fire on the right clips for reasons that
hold up independently — a lopsided span is not a conversation, and a 348px tile
carries a mouth a few pixels across — but the specific ratios behind them should
not be quoted until they are re-measured.

### A long turn decided on nothing

The confidence floor is **global**, and a global pass hides the shape that
matters. On the 08.28 test cut the schedule measured **63% overall** — comfortably
clear of the 45% floor — while containing a single **25-second turn at confidence
0.00**: a quarter of the clip decided purely by inheriting the previous answer.

Checked by pulling frames from the middle of it, the held decision was **right** —
the speaker's mouth is open at both ends. But it was right *by inheritance rather
than by measurement*, and nothing told the operator there was anything to look at.
`FOLLOW\_HELD\_MAX` (15s) and `FOLLOW\_HELD\_CONF` (0.25) name it: a turn long enough
to matter, decided on nothing.

**This is the general shape to watch for in this pipeline: an aggregate that
passes while one component of it is unmeasured.** The same error produced the
"NOT measured is not a pass" family of fixes recorded elsewhere in this file.

### Template 3 on a small camera rail — validated, and the guard was wrong

`conversation\_share` was shipped with a warning that this rig's 348px camera rail
was too small for reliable attribution. **That warning was wrong, and finding out
is what the frame standard is for.**

Re-validated by pulling a frame from the middle of **every** segment of a real
clip and looking at whose mouth is open:

|segment|detector|margin|frame|
|-|-|-|-|
|0.0–13.4|flanagan|1.98x|BigBeat hand on chin, mouth closed — **correct**|
|13.4–22.1|steve|2.83x|BigBeat mouth open — **correct**|
|22.1–32.3|steve|1.67x|BigBeat mouth open — **correct**|
|32.3–63.9|steve|1.50x|BigBeat mouth open — **correct**|
|63.9–74.7|steve|2.34x|BigBeat mouth open — **correct**|

**5 of 5.** The faces inside those 348px tiles measure **175px and 105px** wide
and the margins run 1.50x–2.83x. The doubt came from two things and neither
survived: a retracted sync ratio, and my own misreading of a transcript line
("I understand that, Steve") as proof the detector had the speakers swapped.

**So the guard is now on the FACE, not the tile** — `FOLLOW\_MIN\_FACE\_W` 80px,
set below the 110px that is validated and above nothing, because the signal is
untested under it. A tile width was only ever a proxy for the thing that matters,
and it was a proxy calibrated against a broken measurement.

The lesson generalises: **a guard justified by a number you cannot re-derive is a
guess wearing a threshold.** When the number turned out to be wrong, the guard
was refusing work that was fine.

### The two animations a follow clip needs, that a head clip never did

Measured before changing anything, on a delivered clip, 1912 frames: **zero
flash signatures** (no luma spike that jumps and returns), cutaway dissolves
running their full 0.35s, jump cuts clean, and the whitewash wipe into the outro
behaving. Nothing in the existing set is broken. What was missing is what only
exists once the screen switches between two people.

**1. The picture leads the voice.** Every follow cut is a binary overlay — the
whole screen swaps on one frame — and it was landing exactly on the turn
boundary. That reads a beat late: the viewer hears the new voice and the picture
*answers* it. Editors cut the other way round, so the face is already there when
the voice starts. `FOLLOW\_LEAD = 0.10`, three frames, applied as a uniform shift
of every window edge so both directions move at once — B arrives early, and so
does A when B's window ends. Short enough that the outgoing speaker's last
syllable is not orphaned on the wrong face.

**2. The second speaker gets named.** A conversation clip used to name ONE
person; the other could hold the screen for forty seconds unidentified. The
owner's rule is that every clip carries the white box with the name on it, and
the spirit of that is that people *on screen* get named — so the second speaker
is plated at their **first appearance**, once, which is where broadcast plates a
person and the only moment the viewer needs it.

```json
"speakers": {
  "Kimberly":    {"name": "Kimberly",    "title": "Host, Work<Ai>"},
  "flanagan": {"name": "Stephen Flanagan", "title": "Markets Commentator"}
}
```

Keyed by TILE, so the plate can be matched to the face it belongs under. The
clip's own `speaker` still names whoever opens it; `speakers` says who the other
one is. preflight's `NAMED2` line says which of the two will be named before you
render, and warns when one is missing rather than letting them ship unnamed.

The card has to clear three things and each is a defect if it does not: **the
first plate** (two bone cards in one strip), **a cutaway** (two cross-fades
running through each other is the mud `attr\_window` already records), and **the
tail** (still fading as the outro wipe starts). If nothing survives that, the
second speaker goes unnamed and render SAYS so rather than squeezing the card
somewhere it does not belong. `selftest` asserts the two cards are never both on
screen, frame by frame.

### Captions: no card may flash

**Audited on a delivered clip, 71 cards.** Twelve were on screen for under 0.45s
and two ran **0.13s — four frames**. Measured at the pixels, "Even though"
appeared and vanished between "the last meeting." and "the Democrats are". Peak
rate 23.6 words per second. The eye catches the flicker and reads nothing, which
is worse than the words never being there at all.

`\_tail\_cost` already charged a card too brief to read — and was **outbid**. A
cost can lose; this needed a floor. `CAP\_MIN\_ON = 0.45`, applied after the
program has run.

**It rebalances a word at a time, and merging whole cards does not work.** That
was the obvious first move and selftest caught it failing: two cards combined are
usually wider than the measure, so the merge is refused and the flicker
survives. Borrowing a SINGLE word from the next card extends this one's span to
that word's end, which is usually all the floor needs, and leaves both inside
the measure. Forward first — a brief card at the head of a thought reads as the
start of what follows. A backward borrow is taken only when it does not push the
previous card under the floor in turn, or the flicker just moves.

The merge may exceed `max\_words`: the hard constraint is that the card fits ONE
LINE, the word count is a style preference, and a five-word card that can be
read beats a two-word card that cannot.

**When it cannot borrow a WORD, it borrows TIME.** Eight cards survived the
first pass because they are *width-bound* — the line physically cannot hold
another word — and "Even though the" still measured 0.31s, which is not a
speakable duration. Whisper's word alignment is simply wrong at those points and
no amount of regrouping repairs a bad timestamp. So the NEXT card is shown
slightly late instead, handing its slack to the card that needs it. Ordinary
subtitle practice; a caption need not start on the frame of its first phoneme.

Bounded, because a caption drifting from the voice is its own defect:
`CAP\_LATE\_MAX = 0.20`, and never past the end of the word it labels. Applied
inside `group\_words` rather than in either caller, because `build\_caption\_ sequence` and `write\_srt` both group through it and a display time computed in
one would silently disagree with the other — the exact divergence `CAP\_LINGER`
and the tempo term were both added to close.

&#x20;   cards under 0.45s   12  ->  8  ->  4
    shortest card       0.13s -> 0.24s -> 0.36s   (4 frames -> 11)
    peak reading rate   23.6 -> 13.3 -> 11.1 w/s


The last four sit at 0.36-0.45s, held there by `CAP\_LATE\_MAX`. That bound is
deliberate and should not be raised to close them: past \~0.2s the caption stops
belonging to the word.

### The show has TWO people and one of them was being renamed

`fix\_spelling` rewrote **every** "Stephen" to "Steven", case-insensitively. It
was written when Steven E. Orr was the only person who appeared, and whisper
mishears his name. The co-host is **Stephen Flanagan** — this file's own notes
record the master's burned-in lower third reading "Stephen Flanagan / Forex
Educator" — so a correction for one man's name was burning the WRONG NAME onto
the other man's face:

&#x20;   "Stephen Flanagan makes a good point"  ->  "Steven Flanagan ..."


Text alone cannot tell the two apart, and a wrong name under a real person is a
worse defect than a first name spelt the other way. The rule now stands down
entirely whenever the show's own config names somebody who really is a Stephen,
and keeps its original behaviour when it does not. The NAMEPLATE was never
affected — it is set from config, never from the transcript.

### WHOEVER IS TALKING IS CENTRED

The owner, 2026-08-28: *"whoever's talking, it needs to be centred. Their face
needs to be centred while they talk. A lot of times they're shifted to the side.
Everybody has to be centred."*

**Two separate faults, and the first one is a key that lied about its own name.**

`analyze.py` wrote `"face\_crop\_x"` into every project as the **geometric centre
of the frame**, without ever looking for a face. A configured value beats a
measured one, so that number was the reason speakers came out off centre — the
"override" that won the argument *was* the bug. On the 08.28 master the face
centre sits at 866 of 1920 in the source, and the frame-centred window at x=656
put it at panel x=373: **167px LEFT of centre**, with the empty half of the room
filling the other side.

It is measured now (`auto\_crop\_x`, `faces.face\_box`), and a configured
`face\_crop\_x` that is *exactly* the geometric centre steps aside as the
auto-written default it is. A hand-tuned value still wins.

**Second: the two-up crops pointed where somebody typed.** `follow\_crops` are
authored, and the authored left crop put Steve **+189px** off centre once the
516px window is blown up to a 1080 panel. The right crop happened to be correct
at +0px — which is exactly why nobody caught it: checking one speaker showed
nothing wrong.

`centre\_on\_face` fixes the principle rather than the numbers: **the authored
crop says how TIGHT the shot is; the face says where it POINTS.** Those are
different decisions and only one of them is taste. A hand-typed x cannot follow
a speaker who leans, and will not survive a guest sitting differently next week.
Clamped to that speaker's own tile, so a crop sliding to centre a face can never
show the edge of the other person.

&#x20;   steve      +189px  ->  +1px
    flanagan     +0px  ->  +0px
    head clip  -167px  ->   0px


### A refusal that measured the jaw and said "mouth"

Centring the crop made `HEADROOM` **refuse** the clip: *"the face runs to y1479,
49px BELOW the chrome line — the mouth is behind the platform UI."* It was
reading the cascade box BOTTOM, which on a Haar frontalface rect sits below the
chin, jaw and neck. Pulled a frame: the mouth is plainly above the line and the
composition is good.

The old crop had been hiding this by cutting the face in half, so the cascade
locked onto a 217px fragment and the check passed on a false reading — a green
tick over a worse picture.

`HEAD\_MOUTH\_FRAC = 0.85` measures the mouth for the refusal. A chin that clips
the UI while the mouth is clear is now reported as what it is: cosmetic, worth a
look, not a stop. On this clip the chin runs 49px under and **the mouth is 113px
clear**.

**And a warning about the measurements in this section.** Three separate cascade
readings of the delivered panel disagreed with each other and with the picture,
in BOTH directions, because a width filter meant to reject background faces was
silently rejecting the real one once the crop got tighter. The figures above are
arithmetic on a known face position, checked against frames. See "A MEASUREMENT
THAT WAS WRONG" — this is the same trap, and it caught me twice in one session.

### Choosing between them

One person holds the floor for the whole span → **`head`**; a bigger face beats
anything else. The floor moves → **`conversation`**. The floor moves *and* there
is a screen worth showing → **`conversation\_share`**.

Neither conversation mode falls back to the show's `host` for the nameplate: the
frame changes person part way through, so a fallback would put one name over both
people in one clip. Set `speaker` to whoever holds the frame while the plate is
up (+3.3s to +7.5s); the turn schedule printed by the render says who that is,
and `render()` warns when the authored name and the tile disagree.

Verify who is speaking rather than guessing: `turns.py <start> <end>` prints the
schedule, and `whospeaks.py` answers it for a whole span.

Hooks are
**sentence case**, 3 to 8 words, in the speaker's voice, no em dashes, no "game
changer" — and they wrap balanced, so a hook whose last word would strand alone
still sets cleanly.

**Asked for one clip rather than a set?** Run the same lens sweep and the same
kill discipline, then ship the single best. Picking one moment well takes the whole
sweep; grabbing the first decent line is how you end up with a boring clip.

## Titles: four per clip, written to be pasted

Every clip carries a `titles` object in the slate with four entries. They land at
the top of the posting-sheet card, each on its own copy button, because the title
is the part that actually gets retyped and it goes into four different boxes.

|slot|what it is for|shape|
|-|-|-|
|`youtube`|to be FOUND in search|keyword first, under \~70 chars, no clickbait|
|`tiktok`|to stop a scroll|the hook, curiosity, no keyword stuffing|
|`linkedin`|to be taken seriously|the insight, guest named with their firm|
|`x`|to be read fast|short and punchy, room for the link|

**Cashtags go in the post copy, never in the title.** `$GS $JPM` at the end of the
caption indexes on X and StockTwits and stays copy-pasteable; the same string in a
title just makes it harder to read. Write firm names out in titles.

Rules that apply to all four:

* **Sentence case, not Title Case.** Title Case reads like a press release.
* **No em dashes, no colons used as a hook device** ("The truth about X: why Y").
* **Front-load the noun that is being searched for.** "Cash-secured puts" before
"explained", "Jackson Hole" before "what it means".
* **The YouTube title must be honest about what is in the clip.** If it promises a
prediction, the prediction has to be in the clip.
* **Name the guest in `linkedin` and `youtube`**, because their name is the search
term. Skip it in `tiktok` where nobody is searching.
* Never abbreviate to just "Quasar" - it is "Quasar Markets" or "WLAM".

## Rendering

```bash
python3 broll.py propose                 # candidate cutaways -> slate, no download
python3 broll.py fetch                   # DOWNLOAD what you approved, and bake it
python3 build\_all.py                     # everything in the slate
python3 build\_all.py some-clip-slug      # just one
python3 make\_sheet.py                    # the posting sheet
```

`build\_all` ends with the caption colour every clip was given. Read it: the accent
is the one part of this look that can differ between two clips in the same set, and
a set that came out mixed is only visible there.

Roughly 20 to 40 seconds of build time per clip. Output is 1080x1920 H.264 + AAC at the
master's own frame rate, plus a `.srt` per clip and a self-contained
`POSTING-SHEET.html` carrying every hook, caption and hashtag with copy buttons.

**The renderer needs Python 3.12 or newer.** `qmclip.py` uses backslashes inside
f-string expressions, which is a syntax error before 3.12 - so `analyze`, `pick`
and `preflight` all import and run clean on 3.11 and the job dies at the render
on `import qmclip`, naming a line 5,000 deep in a file you did not open.
`build\_all.py` now checks the version and says so instead. On a machine carrying
both 3.11 and 3.13 the interpreter is what picks the failure.

**Run these with a python that has numpy and Pillow**, and do not assume `python3`
is it. macOS ships 3.9 at `/usr/bin/python3` and Homebrew may have a newer one with
no numpy, and which of them wins on PATH is not stable between shells. Check with
`python3 -c "import numpy, PIL"` before blaming the code.

**Name the tickers.** Every clip that mentions an instrument gets a `tickers` list
in the slate and an `onscreen` string naming the chart visible behind the speaker.
Both render as a copyable row on the posting sheet and into `TICKERS.txt`, because
they get written into the post and nobody should have to re-watch a clip to find
them. Take the on-screen one off a real frame - the chart header carries the
company name and the exchange, which is more reliable than the audio.

## Tempo: two timelines, and they are not interchangeable

**Adaptive tempo works again as of 2026-08-18.** It had been dead for six days -
every clip shipped `"speed": 1.0` because a tempo clip retained dead air the log
said it had removed, including 2.1 seconds of literal digital silence before the
end card. It was three bugs with one cause.

EVERY overlay in the filter graph is applied BEFORE the trailing `setpts`. So:

&#x20;   SOURCE (pre-tempo)   the trims, the captions, the hook, the address, the
                         b-roll. Length `body\_src`. This is what the compositor
                         actually sees.
    DELIVERED            what the finished file measures. Only the audio fades
                         (they follow atempo) and the .srt. Length `out\_dur`.


The old code scaled the words and the removal windows into DELIVERED time and
handed them to consumers that composite in SOURCE time:

* `cut\_graph` trimmed the un-sped source at delivered offsets. Eleven of twelve
jump cuts missed their silence: \~4.7s of real SPEECH spliced out mid-clip and
\~5.1s of dead air left in. The log reported the edit it INTENDED, because
`residual\_silence` runs on the unscaled list.
* the caption, hook and address tracks were authored on the delivered timeline
and then sped AGAIN by the trailing setpts - captions ran up to 3.3s ahead of
the voice and then froze on the last card.
* every b-roll insert fired seconds early, for the same reason.

And the body overran `out\_dur`, which `afade` holds at gain zero past its end -
so the clip's real last words were multiplied by zero. That was the 2.1s hole.

The comment in `render()` used to assert the opposite, that authoring on the
delivered timeline was what kept the tracks on the words. Believing it cost the
feature six days. If you touch this, the test is an A/B: render the same clip at
1.0 and at 1.08 and confirm every caption change lands at exactly 1/1.08 of its
1.0 time. Measured after the fix: median ratio 0.930 against a target of 0.926,
the residual being one sample of a 20fps detector.

Note what tempo does NOT do: on the 08.18 set all three clips measured 202, 201
and 226 WPM, inside or within 2% of the 185-225 band, so the pass left all three
alone. That is correct. The point of fixing it is that a clip OUTSIDE the band
can now be corrected without shipping a hole.

## Pace: the rate is measured, not assumed

**Do not apply a blanket speed-up.** Measured across 44 delivered clips, the median
is 197 words per minute with a range of 142 to 263 - already fast, because the
silence pass removes about 19% of the runtime before anyone sees it. A flat 8%
would take the median to 213 and the top of the range to 284.

So `tempo\_for()` measures each clip and pulls it toward 185 to 225 WPM, capped at
1.12 up and 0.96 down. Most clips are already inside the band and are left alone.
`"speed": 1.0` on a clip overrides it, which is what you want on a slow deliberate
line whose whole point is the pause.

**The tempo and the 45 second floor fight each other, and the floor wins.** The
floor is measured on the DELIVERED duration, after the tempo. Get that order wrong
and a 41 second body at 1.08 ships at 42.0 seconds while both guards read 45.0. On
a slow clip already near the floor the answer is usually to widen the span, not to
speed it up.

## Cadence: the cuts are already dense, and mostly invisible

Measured across 63 delivered clips: the pipeline makes about **23 cuts per minute**
against the reference reel's 13.2, but only about **1.6 visible picture changes per
minute**, and the median clip holds one unchanging frame for **29 seconds**. On a
locked-off webcam a removal takes a quarter second of air out and the speaker is in
the same position either side, so the join is real in the audio and invisible in
the picture. `cut-mechanic.md` predicted this in writing.

The number to manage is therefore not cuts per minute, it is **how long the picture
goes without changing**. Preflight's `CADENCE` line reports it on every clip, but
it only WARNS when the clip carries no approved b-roll at all: the test is
`worst > 12 and not b`, and the harder second line past 20s is gated on the same
`not b`. A clip with cutaways in it gets the measurement and an OK, because the
inserts are what breaks the gap up. Do not try to fix it by cutting harder; there
is nothing left to cut without clipping speech. B-roll is the lever.

**And the lever has to scale with the length of the clip.** Until 2026-08-21 the
insert count was fixed at two or three, which was set when a clip ran 45 to 60
seconds. On the 91.3 second body delivered that day it asks for three, which is one
picture change every 30 seconds, two and a half times the 12 second warning above,
and the picture sits on one unchanging chart for a third of a minute at a stretch.
So the count is derived from the body rather than fixed. It was one cutaway per
18 seconds when that was written, then 16, and it is **one per 10 seconds since
2026-08-30** — see "FASTER B-ROLL", which also records that the derivation
divides by `BROLL\_HOLD`, so the ceiling and the count move together. The rule
and the numbers it came from are in "The things that are not negotiable".

There is no music bed and there should not be. As a business account TikTok
restricts you to its Commercial Music Library, which carries no rights for Reels,
Shorts or LinkedIn, and a ducker's release would pump against 17 jump cuts in 44
seconds. The one audio signature is the end card swipe, which plays under no speech.

## The polish pass (2026-08-24)

Seven measurement lenses were run over the 91 delivered clips asking one question
— what would make these read as professionally made — and thirty proposals came
back. Fifteen survived adversarial verification; of those, nine were built and two
more were killed at implementation by measurements that only appear once you write
the code. What follows is what changed and, just as importantly, **what was tried
and refuted**, so nobody's taste reopens it.

### The cover frame reaches the posting sheet

`poster()` has always picked a good frame and written a `.jpg` beside the mp4, and
the sheet has never shown it. Measured: `<img` and `data:image` appear **zero**
times across all 42 delivered `POSTING-SHEET.html` files, while **71 of 91** clips
have an unused `.jpg` sitting next to them. So every clip ever posted went up on
frame 0.

**Frame 0 is wrong by construction, not by luck.** `HOOK\_IN` 0.30, `HOOK\_SLIDE\_IN`
60, `HOOK\_ALPHA0` 0.85 — at t=0 the headline card is always 60px right of where it
was designed to sit and always 15% transparent. Measured on a delivered clip, card
interior luma 224.0 (sd 7.11) against 253.0 (sd 0.13) on the poster: the wall
behind the speaker is visibly coming through the words.

The frame now lands on each card of the sheet with the timestamp it came from
("cover +1.50s"), because most upload forms let you scrub and a number makes that a
two-second job. `poster()` records the time in `POSTER\_AT`, `build\_all` writes it
into the **slate** (the sheet is regularly re-run days later in a fresh process,
where the dict is empty), and `make\_sheet` embeds the jpg downscaled to
`POSTER\_W` 320 — the raw posters are a median 210KB and the sheet is a
self-contained file that gets emailed. A clip with no `.jpg` degrades to a card
with no image; 20 of 91 delivered clips predate `poster()` and the sheet still gets
re-run over archived shows.

### The caption band, three edits

The captions are on screen for every second of every clip, so this is the
continuous smoothness lever. All three were measured across the 43 delivered
caption files (2,380 cards) before and after.

Scored against the shipped `CAP\_NO\_TAIL` over the 43 delivered caption files.
**Quote these, not the intermediate figures from the tuning sweep** — that sweep
ran before subject pronouns joined the list and before the over-wide-word fix, so
it scored a different rule against a smaller archive and its "30.3% → 11.0%" is
not this table.

||delivered|now|
|-|-|-|
|cards|2,469|2,458 (−0.4%, unchanged)|
|ending on furniture|37.3%|**15.3%**|
|cards too brief to read|235|195|
|one-word cards|75|**64**|
|accent density|—|22.5%|

**`CAP\_LINGER` = 0.40.** The last card of a chunk used to drop 0.30s after its last
word even when the next card was further off, so the band went **empty 2.19 times
per clip, 12.75s in total** — and one of those holes is five consecutive frames
sitting *over a b-roll cutaway*, where the caption is the only thing carrying the
speech. 0.40 because `MAX\_GAP` is 0.34, this pipeline's own declaration of the
longest pause a finished clip may contain, plus two frames of whisper slop; a card
can therefore never hold past something the cut mechanic already calls not-a-pause.
**Do not raise it to \~0.9 to close the rest of the holes.** Measured, the largest
gaps are the *loudest*: a 1.67s hole peaks at −11.7 dBFS against a −14.5 dBFS
speech level. Those are live speech whisper failed to timestamp, and a long linger
parks a stale card over a different sentence. The same constant now sets the
`.srt` cue ends, which disagreed with the burn-in by up to 0.30s on every cue.

**`group\_words` costs the break instead of filling greedily.** One card in five
ended on "the", "of", "to" — the classic amateur tell, and the same fault
`wrap\_balanced` was written to fix for the hook headline forty lines above. It is
now a short dynamic program inside each sentence; the hard constraints (one line at
`CAP\_MEASURE`, `max\_words`, a sentence end closes a chunk) are unchanged and still
hard. Two terms are load-bearing and both were arrived at by failing first:

* **`CAP\_BREAK` = 3.0**, a flat charge for making a card at all. Without it the
program has no reason to pack and split gratuitously: **+365 cards (+15%)** on
the first run, which is a churnier band, not a calmer one.
* **`CAP\_ORPHAN` = 9.0.** The first attempt charged 5.0 and produced **265**
one-word cards — a stutter worse than the fault being fixed. It saturates at
9.0; past that the remaining orphans are *forced* (a word too wide to share a
card — "neuromorphic", "announcements").

**And a single word ALWAYS fits, however wide.** Without that, a word wider than
`CAP\_MEASURE` has no legal cut at all, `INF` propagates back through the cost
array, and the fallback discards the plan for the **whole sentence** — turning
every word of it into its own card. `interconnectedness` is 796px against a 740px
measure and is the only one of 6,702 tokens in the archive over it; it shipped **28
consecutive one-word cards across 10.9s** of a delivered clip. `CAP\_ORPHAN`
already prices the orphan this creates. The point is that it stays *one* orphan.

`max\_words` went 3 → 4 and this does **not** make cards longer: the mean is
unchanged at 2,390 cards for the same words. What the extra slot buys is room to
rebalance a sentence (4 words as 2+2 instead of 3+1) rather than being forced into
an orphan by arithmetic. `CAP\_NO\_TAIL` is deliberately narrow — seeding it from
`STOP`, which holds *is / are / was / that / this*, is what produces the 181-orphan
failure. Subject pronouns were added after a render came out reading "level they";
measured, they take bad tails 17.9% → 15.6% for four extra cards in 2,390.

**`\_keyword` strips the apostrophe before the furniture test.** It tested the raw
token, so `they're` matched nothing in `STOP`, fell through to the capital rule and
took the accent colour. Measured: **157 accented words across 4,860 were
contractions**, and 27 caption lines in 25 delivered clips came out *entirely*
accent-coloured — including one frame reading just `what's` in accent blue over a
chart. `they're` alone is 29 of the 157. **This is not cosmetic:** `\_keyword` also
drives the punch ladder, so a key rung that was firing on a contraction now fires
on the next real noun or number, a median 0.60s later. **Re-read preflight's PUNCH
line after touching it — that is the acceptance test, not the accent count.**
Accent density lands at 22.1%; below 20% means the `STOP` additions went too far.

### A crop may not cut the show's own logo in half

Measured: **4 of 20 archived duo clips** ship with the WLAM mark sliced by the crop
edge. `check\_graphics` finds a persistent coloured graphic in the master and fails
a crop that keeps between `GFX\_KEEP\_LO` and `GFX\_KEEP\_HI` of it — a half-logo.
Both extremes are fine and SKILL.md already said so: kept whole it is free
attribution, "excluded cleanly" it is simply not there. The defect is the middle.

Two things cost a version each, and they are why this is not a one-liner:

* **Sample across the SHOW, not the clip.** The first version sampled the clip's
own span, where a slide or a backdrop is genuinely static: it returned 10 to 77
components per clip, one of them 335,592 source pixels. Unusable. Across the
whole show the only thing that holds still through every layout change is a
graphic burned into the broadcast — the MAD floor over a 59-minute master is
1.69, and the only region under `GFX\_MAD` that is also coloured is the mark.
* **Dilate before labelling.** A logo is not a blob, it is a set of STROKES.
4-way components returned the mark as five fragments of 216–396 source pixels,
every one under any sane floor, so the whole mark vanished. A 2px dilation
merges them and the same master returns exactly one box, x72..198 y72..138,
against an independently measured x74..195 y72..139.

It also scores the **punched** rectangle, which is deterministic and needs no
aspect: `\_punch\_box(..., keep\_badge=True)` takes 48 rows off the top at PUNCH 1.06.
And it says what it cannot see — colour bugs only, so a white-on-dark lower-third
name badge is invisible to it, and a master whose bug is only up for part of the
show will not register at all. That is a false negative, which is the safe
direction: this check only ever refuses, never approves what it did not measure.

A graphic sitting inside the crop but within `EDGE\_MARGIN` (0.15, which is
`check\_crops`' own tolerance) of an edge is a WARN, because the aspect trim can
still take it — how much it trims is CROPS's business, and two owners of that
arithmetic is how they drift apart.

### The same picture may not appear in two clips of one set

`check\_broll` fails a repeat inside one clip and had never looked next door.
Measured: **5 cross-clip collisions, all inside a single five-clip set**, and three
of the five are byte-identical downloads under two different filenames. The right
framing is concentration rather than rate — one clip in that set carries six
inserts and **four of its six pictures were already used by a sibling**.

`check\_set\_broll` walks **every clip in the slate**, not the ones named on the
command line: `main()` skips unnamed clips, so a set-wide dict filled only by
scored clips sees one clip when anyone runs `preflight.py <slug>` and passes
silently — a gate with no key. `"repeat\_ok": true` is the escape; 15 of 16 shows
score clean, so a hard fail blocks one show and nothing else. Cause worth naming
when it fires: `broll.py` ranks the shared library first on every term, and 7 of
the last 18 approvals pointed at a picture the library already held.

### The audio is measured, and `denoise` stopped downmixing to mono

**The real defect is that clips in one set do not play at the same level.**
Measured over a random 16 of the 91 delivered clips, integrated loudness runs
−15.93 to −14.01 LUFS, **sd 0.48 LU** — about 2 LU end to end, which is audible
when two clips play back to back in a feed.

`report\_loudness` and `report\_timbre` now print I / TP / LRA and the 4–6 kHz band
per clip, and `build\_all` prints the **spread across the set**, which is the number
that matters — one clip at −15.9 is fine on its own and only wrong next to a
sibling at −14.0. Do NOT turn either into a correction loop: `loudnorm` is
single-pass by design here, chasing `|I − target| < 0.1` would ship unnormalised
audio on the three `denoise` skip paths, and `references/pipeline.md` already sets
the bar at "within about a dB across the set". This makes that bar checkable.

**A claim that did not survive.** The audit proposed that `denoise`'s `-ac 1`
downmix cost 3.01 LU and split the archive into two loudness cohorts, and built a
"do now" item on it. Checked: the downmix is real — running the exact command, the
merged body is genuinely a **one-channel file** — but the end card concat at
`endcard.py:747` upmixes it back against the card's stereo audio, and that
conversion is power-preserving. **All 91 delivered clips measure 2 channels with L
and R identical to 0.00 dB.** The loudness survives the round trip and a 16-clip
sample found 15 of 16 above the stated fingerprint threshold. The spread is real;
that explanation for it is not, and the cause is still open.

The downmix was removed anyway, for a different and smaller reason: averaging two
channels means a Zoom or StreamYard recording with one dead or noisy channel has
the good channel halved and the bad one folded in, and nothing downstream can tell.

**The 4–6 kHz band is reported and NOT corrected**, deliberately. Its between-clip
spread is sd 4.51 dB and it correlates only r=0.146 with source bandwidth, so it is
real microphone difference. But a guest whose mic is 8 dB bright is something to
fix at the source next week, not to paper over every week — and correcting timbre
on top of a level difference whose cause is unexplained is guessing twice. If it is
ever built: one band, correct only outside a window, move only to the window edge,
clamp, one pass, and **never treat a `duo` as one signal** — the duo demanding the
largest correction has a *within*-clip swing of 14.70 dB, larger than the
between-clip spread the stage would exist to fix.

### The clip opens on the first word, and preflight prints the opening clause

`collapse\_silence` skipped any leading pause under `MAX\_GAP` entirely and left
`KEEP\_AIR` in front of the cut when it did fire, and nothing pulls the in-point
onto the first word — `render()` trims only the out-point. Measured over 90
delivered clips, time to first speech: median 0.05–0.12s, p75 0.16–0.27s, **worst
0.61s**, with 8–14 clips at 0.30s or more. The worst is literal digital silence —
the first 60ms of one reads −240/−126/−90/−124/−195/−240 dBFS with no caption word
until +0.59s. That is the stay-or-scroll window spent on nothing.

**Clamp, do not delete**, and that resolution came out of two lenses disagreeing.
A near-zero lead collides with two things: the 80ms `afade=t=in` would then sit on
the first phoneme (the exact mirror of the out-fade defect fixed the same day), and
the opening is *staged* — measured on a delivered clip the hook card plateaus at
t=0.233 and the caption pops at t=0.267, so the headline lands and then the first
word does, two frames apart. `KEEP\_AIR` is what the well-behaved clips already
have. The `0 < i` guard also came off the brief-and-quiet bridge, which excluded
index 0 by construction, so a clip whose head sits *on* the room-tone line (−44.4
dB against a −44.2 floor) had no leading pause to find at all.

Preflight gained an **`OPENER`** line: the opening *clause*, every word inside the
hook card's life, because `EDGES` prints the first word and on the clip that
actually looks bad it printed `opens 'In'`. SKILL.md's own kill rule is "it opens
on filler" and there was no reporting behind it. Beside it, a warn gated on a
discourse marker **and** a bare pronoun in the first four words — both conditions,
because the pair fires on 8 of 90 clips and is right about six, where the marker
alone fires on 25 at about 36% precision, which is alert fatigue rather than a
check. Do **not** import `broll.py`'s `OPENERS` for this: it holds *the / a / what
/ why / how / i / we / you* and flags 60 of 90 delivered clips.

### Sub-30fps b-roll is rate-conformed instead of frame-duplicated

A bare `fps=30` on 25fps stock repeats every fifth frame — nearly invisible at
tempo 1.0 and arrhythmic the moment the adaptive tempo applies its `setpts`, gaps
of \[5, 6, 11, 11, 6, 5, ...]. It is latent rather than theoretical: 32 of 86
delivered clips sit under the WPM band and would take a tempo.

**Get the direction right by measuring, not by reasoning.** The first version had
both formulas the other way round and made things *worse*: 12.9% frozen frames
against 8.5% for doing nothing. The correct direction compresses presentation
timestamps (`setpts=PTS\*src\_fps/fps`) and pulls more source (`hold \* fps / src\_fps`), so playback comes out about 20% *faster*. Measured across five 24/25fps
library assets, frozen frames: 26%→4%, 11%→6%, 8%→5%, and two unchanged (both
genuinely static shots where the residual is real stillness). Nothing regressed.

`\_check\_frozen` runs after every bake, because a filter-graph direction error
looks exactly like a correct one until you count frames. **Its threshold is 25%
and that is not a slack number, it is a measured one.** It first shipped at 2% and
fired on half the library, because the metric measures STILLNESS as much as
duplication: baked both ways across six sub-30fps assets, a flat-lay of banknotes
scores 8.5% duplicated and 5.0% conformed, and a desk of paperwork scores 16.9%
and 16.4% — both correct. SKILL.md is explicit that a line crying wolf on correct
work is worse than no line, so the gate is set from the failure it exists to
catch: an inverted conform measured 30.5% against 16.2% for doing nothing. It sits
above every correct bake measured and below that. It will not catch a subtle
direction error and is not trying to.

The bake also pulls **two source frames of margin**. The exact arithmetic lands
one frame short at the seek boundary — 4.67s against a 4.70s `BAKE\_HOLD`, which
survives `\_short\_bake`'s 0.05s tolerance but only just. Over-length is free; a
short bake is a hard preflight failure.

The cost is that 20% speed-up, which is undetectable on a flag, a facade, a wafer
line or a rig and **detectable on walking people** — `"gait": true` on an index row
keeps the old duplication for that asset.

### `restore\_case` no longer deletes long runs of real speech

The `delete → continue` branch drops words the word pass has and the reference does
not, on the grounds that the word pass invented them. Every invention this pipeline
has recorded is a **single token** ("eat" heard in a gap, "milliseconds" repeated).
A shipped clip had **seven** deleted: the audio plainly says "You've got to be very
wake up and look at what the Treasury is doing because" and the caption reads
"You've at what the treasury's doing because" — 1.97s of clear speech gone,
ungrammatical text burned into a delivered clip, and nothing reported it.

`CASE\_DROP\_MAX` is 3. Note where the branch sits: `drop\_unspoken` has already run,
so every word reaching it has real audio energy underneath. A run that long with
energy under it is speech, whatever the reference thinks.

### Measured and refuted — do not rebuild these

|Proposal|Killed by|
|-|-|
|**Quantise the cutaway travel onto the delivered frame grid**|Built, then simulated over 300 phases per tempo: as it ships the worst frame of the 1080px swipe is 246px at *every* tempo from 0.96 to 1.12; quantised with `ceil` it is **440px**. The premise — that the trailing `setpts` drops frames out of the curve and doubles a step — is false, because the curve is a continuous function of source time and sampling it on the delivered grid samples the same curve over a proportionally longer source window. Nearly twice as bad as doing nothing. Reverted, with the table in `WLAMclip.py` beside where it would go.|
|Remove filler from the AUDIO as well as the captions|Pure filler is **0.71% of body, mean 0.35s a clip, median 0.00s**. It fires on 41 of 90 clips and does nothing on 45. A guest-segment cleanup, not a smoothness lever — and the "filler plus discourse marker" class that would make it bigger is where every measured miscut came from ("The winter's coming" → "Winter's coming"). It also needs two whisper decodes to agree, since one flag swings the token count 4.7x. If it is ever built, preflight must print the exact tokens and timecodes removed: this is a finance brand editing its CEO's recorded speech.|
|A standalone DRAG warning on local WPM|Fires on 62 of 90 clips. The worst-8s window correlates 0.76 with the global rate `TEMPO` already prints, and on all three recent clips an approved cutaway already sits inside the window it would name, so a words-only number overstates by a third to a half. Append the position to the existing `TEMPO` line if you want it.|
|Speed the clip in segments at the joins|21 `atempo` fragments accumulate 127.8ms of A/V drift, \~23 downstream consumers read `tempo` as a scalar, and it puts an audible rate step **at** the joins — manufacturing the exact "feel the edit" the brief forbids. Honest gain 0.5–1.0s.|
|Put the audio in-fade behind the first word|17 of 89 clips have a pre-fade head at or **above** their own speech level, up to +9.8 dB. The 80ms fade is the only thing making those entries survivable. The tail rule works because the tail is padded (`END\_PAD\_MIN` 0.30 > `END\_FADE` 0.25); the head deliberately is not.|
|Shorten the end card to 2.6s|The picture is still moving at +2.6s (MAD-vs-final 2.23, mean luma +38%), the CTA's settled dwell drops 55%, and replaying a committed 4s plate over 65 frames at 2.11x is the judder the card was reported for. Truly dead stretch is 0.4s.|
|Match the cutaway grade to the shot it cuts into|The probe measures the caption ink strip, not the panel, and points the wrong way on the clip with the biggest step. `eq=contrast` sends 25% of the picture to true black.|
|Balance the two bands of a duo|The 77.7-code "white point difference" is a blue virtual background. Faces differ by 6.5 codes and the sign flips across the archive. Rendered, the fix makes the cream wall grey and the skin sallow.|
|Allow two-row caption cards|All the gain comes from the second row, which lifts the first line of ink 52px in a pipeline engineered around an 8–11px shift. 62% of sub-0.4s cards carry no keyword — they are furniture, held longer.|
|Normalise linearly|`loudnorm` contributes 0.05 dB; the wobble is the compressor riding pink noise. And `linear=true` falls back to dynamic anyway, while shipping unnormalised clips on all three `denoise` skip paths.|
|Pass `-D` to deep-filter to fix "feel"|Real — a constant +30.00ms picture lead — but under every published perception threshold and running the same direction as the deliberate 0.15s b-roll lead. Free to add; answers nothing.|

**One open question nobody has put to the owner.** The swipe already runs at 246px,
23% of frame *width*, against the 1/6 rule `fx\_ease` cites; the rise is 284px of
1920, 15% of frame *height*, comfortably inside it. The two halves of the move are
not cut to the same rule. `BROLL\_OUT` 0.300 was set after the owner watched the
first version and called it glitchy, so it is a reviewed number — do not change it
on the arithmetic alone.

### The review pass, and what it found

The polish pass above was then reviewed against the code and the archive, and it
found six things that had to be fixed before any of it was used on a show. Two
were regressions the polish pass itself introduced. They are recorded because
every one of them was invisible in the log.

**The body could ship UNTRIMMED.** The leading-silence clamp made a removal able
to start at `0.0`, and when that was the *only* removal `cut\_graph`'s
`len(keep) < 2` test returned the passthrough graph — so the picture and sound
ran their full length while `out\_dur`, the caption, hook and CTA sequences, the
`.srt` and the out-fade were all authored X seconds shorter. The build log said
it had cut. preflight structurally cannot catch this: it never calls
`cut\_graph`. Fixed by bailing out on `not rem or not keep` and handling one kept
span, plus an assertion in `render()` that the graph and the arithmetic agree
about the body's length.

**Nine of 27 sub-30fps b-roll sources baked SHORT.** `bake\_video` planned its
window for `hold` and then read `take` — up to a second past the window the
planner had certified. Two consequences from one cause: a short bake, which is a
hard preflight failure that sends you to `sweep`, which re-bakes, refuses its own
output and blames the source (a loop with no exit); and a shot change the planner
had dodged landing back *inside* the insert. Fixed by planning for what is
actually read, plus a fallback to frame duplication when a source cannot cover a
conform. All 27 now bake full length.

**A word wider than the measure turned its whole sentence into one-word cards.**
`INF` propagated through the cost array and the fallback discarded the plan for
the entire sentence. `interconnectedness` is 796px against a 740px measure, is
the only one of 6,702 archive tokens over it, and shipped **28 consecutive
one-word cards across 10.9s** of a delivered clip. A single word now always
"fits"; `CAP\_ORPHAN` prices the orphan, and the point is that it stays *one*.

**`plan\_ending` scored a straddling word as "landed".** `w.start < dur` let a word
that starts inside and *ends past* the out-point count as the last word inside, so
the clip reported a clean landing while its closing word was cut mid-utterance —
and `render()`'s own note claimed the out-fade had been held back to clear it.
`w.end <= dur` turns a straddler into a forward move, which already carries the
run-on cap, the `hard\_out` veto and `layout\_ok`.

**Malformed `.srt` timestamps.** `int(sec)` truncated while the millisecond field
rounded, so a fraction ≥ .9995 emitted a four-digit field (`00:00:21,1000`). Five
delivered `.srt` files carry one. Round once in milliseconds, then decompose —
**235 malformed → 0** over 500k values, byte-identical elsewhere. Fixed in
`WLAMclip.write\_srt` and `analyze.\_stamp`, because analyze's own reader parses with
a strict `(\\d\\d\\d)` and turns a malformed stamp into a dropped cue.

**A sentence-final number was not a sentence end.** The dotted-token rule that
exists for `U.S.` and initials was swallowing every decimal, price and percentage
that closes a sentence. Across one show, 28 real endings were invisible: 10 made
the clip delete its closing sentence and 18 made it run on to the cap. One clip
lost `"Down 2.3%."`, the number it existed for. `"no"` also came out of `ABBREV` —
zero real `No. <digit>` ordinals in the archive against seven emphatic "No."

Nine more were fixed in the same pass, and three are worth knowing:

* `check\_graphics` scored punched rectangles in modes the renderer never punches,
which swept to **3,667 false hard failures** across the archive. It follows
`PUNCH\_MODES` now, and inside `share` punches only the camera tile.
* `\_crop\_boxes` modelled an unauthored head crop as the **whole 1920x1080 frame**,
so every graphic looked contained and `check\_graphics` was structurally unable
to fail the commonest mode — while firing a false warning on every head clip.
`WLAMclip.head\_box()` is now the one owner and preflight asks it.
* `build\_all` was rewriting the whole slate document after every clip, from a copy
read at t=0. Anything typed into `slate.json` during a 15–30 minute build was
silently reverted. Cover timestamps go to a `posters.json` sidecar now, and the
build is read-only on the slate.

### The caption band cannot run under the action rail

`layout\_chunk` keeps a single word on its own row whatever its width — it has to,
there is nowhere to break a word — and the painter then drew it at full size and
centred, putting the last letters behind the platform share icon.

Each row is now sized independently, condensed only when it would otherwise pass
`CAP\_INK\_MAX`. Three terms go into that measure and all three were needed:

|||
|-|-|
|the advances|what `getlength` gives|
|`+ 2 \* CAP\_STROKE`|the stroke grows each glyph outward on **every** side, so the ink is wider than the advance at both ends. Measuring advances alone passed a 796px word through a 780px ceiling and then drew 806px.|
|`+` the pop headroom|the live word grows to `CAP\_POP\_MAX` about its own centre, so a row sized to fit at rest overflows the moment its widest word lights. Reserved up front on the widest word, so the shrink is **constant** across every state — a per-state shrink would visibly resize the caption as each word went live.|

`CAP\_SHRINK\_WARN` (0.72) is where it says something; `CAP\_SHRINK\_MIN` (0.55) is
where it stops, because ink under the rail is worse than small type. Render-
verified coverage: **a single token up to 26 characters** is held inside the rail
at maximum pop, against an archive worst of 18 characters. Past that it condenses
to the floor and says so.

### Where a clip ends, finally

Two more things came out of the review, and one of them is a measurement worth
having written down.

`END\_PAD`/`END\_PAD\_MIN` now apply on the **landed** path too — 57 of 82 delivered
clips sat under `END\_PAD\_MIN` because the pad only ran when the out-point moved —
and `hard\_out` is clamped where the pad is applied rather than only in the veto,
on both branches, so the delivered out-point can no longer land past a ceiling the
slate documents as never-cross.

**And the tail cannot be made much better than it is.** Measured over a real 80s
decode: 219 word transitions, only 11 carry any gap at all, the median gap after a
sentence end is **0.010s** and the largest anywhere is 0.26s. Not one sentence end
has `END\_PAD\_MIN` of transcript gap after it, so `min(END\_PAD, gap)` never binds
and every clip is padded by exactly the floor. On top of that the closing word's
acoustic release rings about **0.15s past** the timestamp the word pass gives it,
so a 0.30s pad is roughly 0.15s of real air.

Three fixes were tried on this and two made it worse, so do not re-try them:
placing the fade off the acoustic end **shortened** the fade and took the final
250ms from +2.0 to +5.4 dB against median speech; extending the tail to the
acoustic end without clamping to the gap pulled the next word's onset into the
clip. What survives is an acoustic tail guard that extends only into genuine
silence and never past the next word — which on continuous speech correctly does
nothing. On a speaker who runs straight into the next sentence there is no
silence to end on, and the honest options are to fade over the release, to run on
into the next sentence, or to pull back and lose the payoff. **Fading is the right
one**, and raising `END\_PAD\_MIN` past about 0.30 does not buy air, it buys the
next word.

## The rig's own nameplate CANNOT survive a vertical crop

This was switched off on 2026-08-24 on the plan that StreamYard already names
everybody and the crop would simply keep it. The owner watched a clip and said the
name tag was not there. He is right, and the reason is geometric rather than a
setting:

**The rig draws its badge at the BOTTOM of a 1080-tall source, so any crop that
keeps it puts it at the bottom of the 1920-tall output.** Measured on the
delivered Morrison clip it lands at **y1673..1919** — 243px below
`CAP\_SAFE\_BOTTOM`, and behind the UI on all three platforms (TikTok cuts at
y1440, Reels y1500, Shorts y1620).

There is no crop that fixes this. Cropping less height moves the badge up relative
to the SOURCE but not relative to the OUTPUT, because it is pinned to the bottom
of both. So either we draw it or nobody is named on any vertical clip. **We draw
it** — `"name\_card"` defaults back to true.

`NAMED` still checks `source\_badge\_box` when it is set, because knowing where the
rig's badge lands is what tells you whether it is competing with ours.

## Naming the speaker (2026-08-24)

**Nobody on screen was ever named.** On a finance or a health clip the speaker's
authority IS the product - the affiliation is the reason to believe the sentence -
and the slate had no speaker field at all.

`"speaker": {"name": ..., "title": ...}` on a clip, or a bare string for a name
with no title. Omit it and the show's `"host"` from project.json is used, which is
what most clips want; set it per clip for a guest. It draws **at +3.25s**, just
after the hook card clears, holds 4s and leaves. One tracked line, name in the
caption weight, affiliation a size down and dimmer, no plate and no rule - the
same treatment the closing address gets, and for the same recorded reason.

**IT SHARES THE ADDRESS'S BAND AND SO COSTS NOTHING.** y1020..1084 is empty for
all but the last `CTA\_TAIL` seconds of every clip and already has an overlay input
in the filter graph. The name takes that rectangle earlier, the address takes it at
the end, `speaker\_state` clamps so they can never be up together, and both are
drawn into the sequence that was already being built. No new PNG sequence, no new
ffmpeg input, no extra overlay, no measurable render cost.

**THE SHOW ALREADY PAYS TO PRODUCE THIS AND THE CROP THROWS IT AWAY.** Measured on
the 08.24 master, the source carries proper burned-in lower thirds at x15..600,
y850..1058 - "BigBeat / Founder and CEO of Quasar Markets", "Stephen Flanagan /
Forex Educator" - and the default head crop is 608px wide and centred, x656..1264,
which clears that plate entirely. Every head clip discards the attribution the show
paid to make.

**It is retyped rather than lifted, and the reason is the host's own plate.** It
says **"BigBeat"** - a screen handle. That is exactly what a finance clip cannot put
under a face. Read the plate off the master for the *facts*; type the person's name.

Preflight prints the full string, where it came from and when it draws, because the
failure that matters is not a missing name but a WRONG one under a guest's face,
and only a human reading it back against the picture catches that. It warns rather
than refuses: a montage or a cold open may legitimately have no single speaker, and
the check cannot tell that from a forgotten field.

**The credential was sized up on 2026-08-24** - *"the names of the people need to
be cleaner"*. `ATTR\_NAME\_PX` 32 -> **42** with +0.4 tracking so it reads as a
byline, the role 26/24/22 -> **30/27/24** at alpha 190, and `ATTR\_GAP` 22 -> **36**.
At 32px hard under the headline it read as a stray line rather than an
attribution. **Nothing was added to fix it** - no rule, no dash, no box. Size and
air, which is how this system fixes things.

**AND IT SHIPPED IN THE WRONG PLACE.** The first build put it in a band of its
own at y1020..1084. Two measurements killed that, and the frame decides both:

* **It sat on the face.** On a head crop the 9:16 crop of a 16:9 source is a
tight close-up, and the band landed across the speaker's **nostrils** - mean
luma 137.6, lit skin. That is the same defect that got the hook card unpinned
from y96 on 2026-08-22 ("it covered his face to the nose"), and it had already
been solved once: `place\_hook` finds a clear band around the face and nothing
else in this pipeline does.
* **It sat on the chart.** Measured across 17 delivered share clips, the
`SPLIT\_GAP` seam lands anywhere from y400 to y993 depending on how `pack\_share`
divides the panel, and `APP\_MIN\_FRAC` forces the app band to at least 998px -
so the app's top edge is at **y969..1038 in every default pack**, and a fixed
band at y966 is ON the shared chart. There is no safe fixed y in share, because
the packer moves the seam per clip.

**So the credential goes into the HOOK CARD** - slate type on the bone the card
already paints, below the headline. It inherits `place\_hook`'s whole face-clearing
machinery, it needs no curves, no PNG states and no inputs of its own, it reaches
100% of impressions instead of the fraction who survive to +3.4s, and - the thing
nothing in this pipeline did before - **`poster()` scores only the first
`HOOK\_HOLD` seconds, so the cover frame the feed judges the clip on now carries
the credential.**

`ATTR\_H` is **added** to the card, never taken out of the headline: `HOOK\_MAX\_BLOCK`
stays 390 for the headline and the card's total is capped at `HOOK\_ATTR\_BLOCK` 460.
The alternative costs a mean 6.5px and a max 24px of headline type across the 41
distinct shipped hooks, pushing one below `HOOK\_MIN\_SIZE`. **The shrink order also
inverts**: the card used to shrink the headline the moment `place\_hook` failed; it
now drops the attribution first (stacked → one line → name only → nothing,
re-placing at each rung) and shrinks the headline only once the credential is
gone. The headline stops the scroll; the credential is second. A credential that
will not fit at 22px falls to name-only rather than condensing - shortening a real
person's job title by algorithm risks misstating it.

### But the card ALONE loses the feature on the commonest mode

**Measured against the real face geometries this pipeline produces, the credential
never fits on a head crop at any rung.** Faces span y369..1125 (Morrison) and
y438..1488 (08.24 clip 3), so the largest clear band is \~229px against a card
needing 314-410px even at name-only. `place\_hook` refuses all four rungs. Head is
20 of 44 delivered clips.

So each placement is used where it is safe, and only there:

|||
|-|-|
|**card**|share, duo, and any head clip with a clear band. Never on the face, reaches every impression, lands in the poster frame|
|**band**|**head only**, when no rung fits. y966..1084 sits on the lower face, which is the least-bad place on a crop that has no clear band at all - and it is up for four seconds, not the whole clip|

The band is gated to head **deliberately**. Its other defect was landing on the
shared chart, and share is exactly where the card DOES fit - so the fallback never
runs there and can never hit that seam.

**A duo or duo\_share clip may not fall back to `host`.** On a two-up the card sits
between two faces and names ONE person, which works only because it is a *quote
attribution* - it claims authorship of the sentence above it. Defaulting to the
host there would put the host's name on a guest's sentence half the time, and this
pipeline has no reliable per-band speaker attribution to prevent it (whospeaks
margins of 1.13x and 1.12x over 40-56s spans are why duo is excluded from the
punch). Name the speaker by hand or the card carries no credential.

**Share modes suppress it when the source already carries a badge.** A meeting tile
burns its own lower third in, `\_punch\_box(keep\_badge=True)` already anchors the
share punch bottom-left to preserve it, and SKILL.md already says that badge
attributes the speaker for free. Two nameplates on one frame is the mistake read.
`"source\_badge": false` on a clip whose tile has none.

**If no name resolves, nothing is drawn** and the card renders exactly as it does
today. No "Guest", no placeholder, no company-only fallback, no machine-truncated
title. Every degradation is a rung and every rung is logged.

## `check\_burned\_in` had a false-positive mode, and it cost a good clip

It counted qualifying rows ANYWHERE in the lower band and called eighteen of them a
caption plate. That is a much weaker claim than its own comment ("a plate is TALL")
intends, and a guest against a bright background trips it with no caption in sight:
measured on the Morrison master, **81 of 990 rows qualified on one frame in FOUR
separate runs of 29 to 37px** - the bottom edge of his shirt against the table at
97% height, and sunlit pergola columns behind his head at 13-16%. Summed they clear
eighteen easily. Not one of them is a plate.

Two changes. It takes the **longest contiguous run**, not the total; and the
threshold is **5% of the crop height** rather than a flat 18 rows, because a band
that actually holds legible text is 8-15% of frame - the 08.18.26 master this check
was written for measured 182px of a 1080 source. Verified by painting a caption
plate onto a clean Morrison frame: the false positives top out at 29px, a real
plate measures 83px, and 5% of a 990px crop puts the line at 49px between them.

**And there is a case luminance simply cannot decide.** His maroon shirt with his
hand and a gold bracelet across it is a 103px bimodal band in the lower third -
taller than the threshold, in the right place, and not a caption. Persistence would
separate them (a plate holds its position, a hand does not) but that is a different
and much larger detector. So `"burned\_ok": true` skips the check and says that it
did. **Set it only after pulling frames and looking**, which is what the failure
message asks for anyway and is how this false positive was found.

## What a non-finance guest job teaches (Dr John Morrison, peptides)

**The b-roll vocabulary is finance-only, and it silently returns nothing.**
`propose` found **0 candidates** across a whole clip about creatine, dosing and
cognition, because `EXPAND` maps spoken words to physical pictures and every entry
in it is oil, the Fed, markets and freight. A word with no mapping can never be
proposed. On a guest outside the usual subject matter, expect to author the chain
by hand - which is the documented fallback, not a failure.

**Author it, then LOOK, then retype.** The first two terms typed by hand
(`creatine powder scoop supplement`, `scientist laboratory research microscope`)
fetched a woman scooping powder into bags in what reads as a craft workshop, and
four lab-coated people **posing at the camera** holding clipboards. `propose`'s own
note had already said the video hits "match nothing in the query - they are stock
footage that happens to be nearby". Retyped to `man lifting weights barbell gym`
and `laboratory research bench pipette`, previewed on the contact sheet, and both
came back unmistakable. **The term is not the picture; the contact sheet is.**

**On a two-up, check where the guest's own badge sits before authoring the crop.**
Morrison's plate sits across the lower part of HIS half, so a standard
`head\_crop\_right` slices it. The fix is vertical, not horizontal: a crop of
`\[557, 990, 1162, 0]` ends above the plate at y997 and frames him properly, where
no 608-wide horizontal placement could both centre his face and keep the badge
whole. With the nameplate now drawing the name itself, excluding the source badge
cleanly is the right answer rather than a compromise.

## The sign-up line rides the cutaways

The owner asked for "invest into quasar markets, or sign up for free" on the clip.
The gap it answers is measured: the mark appears ONLY in the closing card, so the
\~90% who scroll never see it - and during b-roll cutaways the SPEAKER is gone too,
which on a 48s clip with three inserts is 12.6 seconds, **a quarter of the runtime
with nothing on screen saying whose clip this is.**

**IT RENDERS ONLY OVER A CUTAWAY, AND THAT IS THE WHOLE IDEA.** A cutaway is the
one written exception to the face-at-all-times rule, so the objection that killed
the persistent capsule twice - "it competes with the face for exactly the duration
you want the face winning" - cannot apply: there is no face to compete with. The
gap and the slot are the same seconds, so the line costs the face nothing.

It is `endcard.py`'s own lockup arriving forty seconds early. Nothing new enters
the system: a sentence-case line, the closing card's **148x2 accent rule** lifted
unchanged in width and hue, and the address UPPERCASE and tracked beneath it. No
pill, no outline, no icon, no arrow - a signature, which look.md already decided
twice.

**FIXED BONE, NEVER THE CLIP'S ADAPTIVE PICK.** `choose\_caption\_colours` samples
the SPEAKER's picture, and this element never sits on the speaker's picture.
Inheriting that pick would be a measurement of the wrong frame. The cover is a
baked asset already corrected into broll.py's `LUMA\_BAND` (45..160), so this is
the one background in the clip where a fixed colour, a fixed size and a fixed y
are all safe - the invariance the removed scrim used to provide.

### The verb and the host are ONE authored pair, and a crossed pair is REFUSED

The first build put **"Sign up free" over INVEST.QUASARMARKETS.COM** and that is a
defect the viewer eats: the line names a free product action and the address is the
**raise page**. SKILL.md holds what is ON SCREEN to the same standard as what is
said, and an imperative that lands on a securities page, burned over a strategist
discussing markets, is a solicitation sitting on top of market commentary - the
archive already carries a clip whose own note reads *"Do not overlay any raise,
valuation or CTA card on this one or it stops reading as a disclaimer."*

So the default is the product action over the product **host**:

```
Sign up free
QUASARMARKETS.COM
```

`"Invest in Quasar Markets"` over the invest host stays a legal pair for a set that
wants it. What is refused, at import, is **crossing them**. It is also the owner's
own second phrasing verbatim, and it is aimed at the people who scroll - which is
the gap this element exists to close. A raise ask aimed at a first-time
fifty-second viewer is not.

### It lives at the BOTTOM, and the captions ride up to let it

Owner, 2026-08-24: *"it should be on the bottom of the video, and it should be
more animating in towards the bottom. It should, like, fly in and fly out on the
very bottom, not in the middle because it kinda fucks the video up a little bit."*

It first shipped in the old address band at y966..1084, which is **dead centre of
a 1920 frame** — across the speaker's chest on a head crop and over the chart in
share. He is right that it hurts the picture there.

**92px is what the frame actually has at the bottom, and it only exists if the
captions move.** Below `CAP\_SAFE\_BOTTOM` 1430 is platform chrome (TikTok's \~480px
puts the floor at y1440); above is the caption band. Measured:

|||
|-|-|
|1-line caption, centred|ink y1228..1331|
|2-line caption, centred|ink y1177..**1383**|
|2-line caption, **top-aligned**|ink y1130..**1336**|
|the invitation strip|**y1338..1430**|

So `CAP\_RAISED`: for exactly the frames the invitation is on screen, the caption
renders at the TOP of its band instead of centred, which opens the strip with 2px
to spare against the worst case and leaves 10px to the chrome. It is only ever
true while the invitation is up, so nothing moves on a clip without cutaways.

**ORDERING, and it now catches TWO sequences.** The invitation's windows come from
`BROLL\_WINDOWS`, which `broll\_chain` fills — and the captions need the *same*
window list to know when to ride up. Both `build\_caption\_sequence` and
`build\_capsule\_sequence` therefore run AFTER it. Building either earlier gives an
empty window list, and the two failures look completely different: the invitation
silently vanishes, and the captions silently do not move.

### Type and motion

|||
|-|-|
|line|`CTA\_VERB\_SIZE` **38**, sentence case, tracking 0.6 (the card's own tagline tracking)|
|rule|148x2 `ACCENT`, on a dark plate - at the card's own alpha with no plate it vanished over a stock photograph|
|address|`CTA\_ADDR\_SIZE` **24**, UPPERCASE, tracking 4.0 (the card's own URL tracking)|

Compacted from 52/34 to fit the 92px strip: 38 + 8 + rule 2 + 8 + 24 = 80, with
room for the stroke.

**The verb has to lead, and WIDTH decides that, not size.** At 46/26 the verb was
the bigger type and still lost, because the address is a long string and came out
WIDER than the invitation above it - so the eye took the address first and the
offer read as a subtitle to a URL. Dropping the `invest.` host shortened the
address and fixed most of it; 52 over 34 finishes the job.

**IT FLIES.** 110px on out\_quart in (0.24s) and in\_cubic out (0.20s), subpixel — a
bottom strip carries a bigger, faster move than a mid-frame one, because there is
no face beside it and nothing above it but a caption that has moved out of the
way. Still the house compass: type arrives from the RIGHT, everything leaves LEFT. It arrives into
and leaves from a **static** picture - the cover has settled and has not begun its
swipe - so the type travel never competes with the biggest move in the clip.
`CTA\_BROLL\_PAD` insets it from both ends of the insert for exactly that reason.

**Ordering trap:** the windows come from `BROLL\_WINDOWS`, which `broll\_chain`
fills. `build\_capsule\_sequence` therefore runs AFTER it. Building the band earlier
gave it an empty window list and silently dropped every cutaway instance - which
looks identical to the feature being off.

## One way that type arrives (2026-08-24)

The owner sent a reference — youtube.com/shorts/gaRRMkRjoHE — and said *"the
captions, the way that animates is exactly what we wanna do... it's a flow of the
captions... if it's a flow, it's seamless."* It was downloaded and measured frame
by frame at its native 30fps rather than described, and the answer is smaller and
more specific than it looks:

**A new caption card expands HORIZONTALLY into place. Nothing else moves.**

```
frame    0      1      2      3      4+
width    0.717  0.886  0.964  1.000  held
```

The glyph rows held at 42px through the whole expansion, so the height does not
change — it is a horizontal scale about the centre and nothing else. No fade, no
vertical travel, no per-word entrance. `CAP\_SNAP\_CURVE` carries those four
measured numbers rather than an easing fitted to them: four numbers is less code
than the curve that approximates them, it is exact, and it cannot drift when
somebody re-derives an exponent. (out\_cubic gets within 0.03 if the shape is ever
needed at another frame rate; the deltas are +0.169, +0.078, +0.036, each about
0.46x the last.)

It fires once per CARD, not per word — it is the card arriving. The words inside
it still light up on `CAP\_POP` as they always did. Cost is four extra unique PNGs
per card and nothing at render time.

**Why it reads as "flow" and a plain appearance does not:** a card that simply
switches on reads as a cut. A card that expands into place reads as one continuous
line of speech being laid down, which is what the whole clip is.

### And the invitation arrives the same way, which is the actual fix

The sign-up line first flew 110px in from the right. The owner watched it: *"it
needs to be smoother... more professional the way it comes in... we don't want it
to be clawish."*

The problem was not the speed or the distance. It was that **the clip carried two
different ideas of how type arrives** — captions expanding, invitation sliding —
and a second motion vocabulary inside one clip is what makes an edit feel
assembled rather than authored. The invitation now expands on the SAME
`CAP\_SNAP\_CURVE`, over the same four frames, with a short fade under it. Nothing
travels. `CTA\_SLIDE` is gone.

That is what "if it's a flow, it's seamless" means in code: the elements are not
animating individually, the clip has ONE way that words appear.

Copy went to **`Sign up free today`** over `QUASARMARKETS.COM` — the owner asked
for more call to action, and "today" is the urgency without inventing a claim. The
crossed-pair refusal still stands: a free-signup line may not land on the raise
page.

## Let the rig name them, and CHECK the crop keeps it

Owner, 2026-08-24: *"the nameplates don't have to go because the nameplates will
be there on the bottom anyway from the StreamYard. It will just crop that in."*

That is the plan and it is the right one — the rig already draws a proper lower
third, and drawing a second is a duplicate. **But it only works if the crop
actually contains the badge, and the default crop does not.** Measured on the
Morrison master, the rig's glyphs run x1002..1389, and a 608-wide *centred* head
crop is x656..1264 — it cuts the name in half. On the 08.24 WLAM master the badge is
at x15..600 and a centred crop clears it completely, so the clip ships naming
nobody at all.

So `NAMED` now checks it. Record the rig's box once per show as
`"source\_badge\_box": \[x0, y0, x1, y1]` in project.json and preflight will confirm
the resolved head crop contains it, or warn with the numbers when it does not.

**Author the crop off the badge, not off the face.** On Morrison, x1000 is the
RIGHTMOST 608-wide crop that keeps the name whole; it costs 136px of face
centring, which on a talking head is nothing next to shipping a clip that names
nobody. Worth knowing: widening that crop also gave `place\_hook` a clear band it
did not have before, so the hook card moved from overlapping the face to sitting
cleanly above it. The crop that keeps the attribution made the card better too.

`"name\_card": true` still draws our own, for a source with no badge of its own.

## The cutaway CROSS-DISSOLVES, and that is the third answer (2026-08-25)

Three styles have been put in front of the owner in one day. The first two were
both wrong in ways he named, and the sequence matters because it is the reason
the reference measurement did not settle this:

|`broll\_style`|what it does|his verdict|
|-|-|-|
|`slide`|cover rises, swipes off left|*"still not clean ... needs to be more seemless"*|
|`cut`|hard cut, both ends|*"that is good"*, then *"it's not smooth"*|
|**`dissolve`**|cross-dissolve on the ALPHA, both ends|**ships**|

His words the third time, and they are not ambiguous: *"the way that this comes
in is still very kind of just, like, it's not smooth. It should be like a
seamless transition ... a little bit slower, a little bit cleaner ... you can
have it be smoother and kinda flow into it."* And then: **"Every single b roll
shot that comes up has to transition into the video. That's the idea. The smooth
transition to the b roll, the smooth transition to the sign up for free quasar
markets, and then it should be a smooth transition out."**

**WHY THE REFERENCE MEASUREMENT DID NOT SETTLE IT, AND WHY THAT IS NOT A FAILURE
OF THE MEASUREMENT.** gaRRMkRjoHE hard-cuts every one of its cutaways, 28 of 28,
and that measurement is still correct - it is quoted in full under BROLL\_STYLE
in WLAMclip.py and nothing has invalidated it. What it could not tell us is
whether hard-cutting is what HE wants for OUR clips, and it is not. He has now
said "smooth" or "seamless" about this element across three separate rounds.
**Do not re-open this with the reference again.** It has been asked and answered:
a measurement of somebody else's video is evidence about that video.

**THE MECHANISM WAS ALREADY WRITTEN DOWN IN THIS CODEBASE, and it is the alpha
plane, not the picture.** From a comment that predates the slide:

> \*"format=yuva420p + alpha=1 because a plain fade=t=in on an opaque stream
> fades from BLACK: the first frame of every insert measured RGB(0,0,0)
> full-frame, which reads as a flash on the cut. Fading the ALPHA instead
> dissolves from the speaker, which is what a cutaway is."\*

So it is two filters restored, not a new effect: `format=yuva420p` then a
`fade=t=in`/`fade=t=out` with `alpha=1` on the insert's own stream, before the
`setpts` that puts it on the composite clock. The overlay then composites the
insert OVER the speaker at a ramping opacity - a true blend between two live
pictures, never a dip through black.

**0.35s each way**, not 0.25: *"a little bit slower, a little bit cleaner."*

**NOTE WHAT THIS OVERRIDES.** `references/look.md` rejected a dissolve by name as
"the CapCut/iOS card tell", and the note at the top of the b-roll block still
lists "no dissolve" among the things the design panel refused. That was a taste
call made without the owner in the room. He has now asked for it three times in
one message. Recorded so nobody reverts it as a regression.

**Verified on the delivered re-render** by solving `F = a\*B + (1-a)\*S` per frame
for the blend weight, on all three inserts of the Ellman clip:

&#x20;   IN   0.00  0.17  0.25  0.34  0.42  0.51  0.59  0.68  0.76  0.92  0.98
    OUT  0.99  0.87  0.79  0.70  0.62  0.53  0.45  0.36  0.28  0.11  0.00


Monotone, mirrored, 8 to 13 intermediate frames at each edge, on every insert.
A cut has zero intermediate frames; a slide has none either, because a slide
leaves the old picture whole and merely moves it.

**THE HOLD WINDOW MOVED WITH IT, because the travel is a real cost again.** The
settled floor is still the owner's 3.0s, so a legal hold is now **3.70 to 4.20**

* `BROLL\_HOLD\_MIN + BROLL\_IN + BROLL\_OUT` at the bottom, `BROLL\_HOLD` at the
top. That is also "the b roll clips should be a little bit longer", which he
asked for in the same breath. `BROLL\_HOLD` is 4.2 and NOT higher, because
`BAKE\_HOLD` was derived from it; it carries its own FLOOR now, so it no longer
tracks `BROLL\_HOLD` down (the ceiling moved to 3.6 on 2026-08-30 and the library
is still baked at 4.7s, which is correct - a shorter hold can always be cut from
a longer bake, never the reverse) -
raising it past 4.2 makes every asset on disk short.

**AND THE SIGN-UP MOVED WITH IT TOO**, because he asked for that in the same
sentence. `PILL\_IN\_FRAMES`/`PILL\_OUT\_FRAMES` go 7 -> 10 (0.233s -> 0.333s, the
same register as the dissolve beside it) with `PILL\_SCALE` RESAMPLED onto ten
frames rather than re-invented - the shape is still the one measured off the
reference button. And it fades in over the first third of its travel instead of
being opaque from frame one: "it stays opaque the whole way" was right when
everything around it cut hard, and is the only hard edge left in a sequence that
now dissolves.

**A frame-timing bug came out with it.** `kin = int((t - a) \* FPS)` truncated
`(1/30)\*30 = 0.9999999999999999` to 0, so the entrance ran 0,0,1,2,3,4,5,5,6,7 -
the first frame drawn twice and another pair doubled mid-travel. It has been
there since the pill shipped and it is part of what "it's not smooth" was
pointing at. `+ 1e-6` before the truncation; measured after, ten distinct frames
and a monotone deceleration.

## The white card ALWAYS carries the name (2026-08-25)

Owner, on a share clip of Dr Alan Ellman whose source burns in its own lower
third: *"the white box will always have people's names in it. Even though that
Dr Alan Ellman, the president of Blue Collar or whatever, is on there ... the
white box that comes up, right, we wanna have their name in there the same way
we did it this morning. Those are very good."*

The credential was being suppressed by default on `share` and `duo\_share`, on
the reasoning recorded two sections down - a meeting tile burns its own lower
third, `\_punch\_box(keep\_badge=True)` already preserves it, and "two nameplates
on one frame is the mistake read". That reasoning is sound and he has overruled
it, and the frame says why: **the source badge is inside the shared panel** -
small, in the guest's own rig's typeface, saying whatever they typed into it -
while the card is ours, is the thing the eye lands on, and is the only
attribution that survives a crop. They are not two of the same object.

`"source\_badge"` is now OPT-IN (default `False`). Set it `true` for a source
whose badge genuinely makes ours redundant.

## A cutaway is a SEQUENCE OF BEATS, not one moment (2026-08-25)

Owner, on the first re-cut: *"the flow needs to be a bit smoother ... cuz the
broll + signup feels very rushed. the whole sequence of them needs to be feel
smooth and clean and seemles."*

`CTA\_BROLL\_PAD` was ONE symmetric number and it had just been cut to 4 frames
(0.133s) because a hard cut has no travel for the invitation to clear. Correct
in itself, and it produced a cram: the picture and the button **landed on the
same beat**, and the button left as the picture cut back. Two events of about two
seconds collapsed into one, which reads as rushed however clean each individual
move is.

Split into `CTA\_BROLL\_LEAD` 0.60 and `CTA\_BROLL\_TAIL` 0.45, so the cutaway is
five beats rather than two collisions:

&#x20;   the picture lands and holds ALONE           CTA\_BROLL\_LEAD   0.60s
    the button arrives                          PILL\_IN\_FRAMES   0.23s
    it holds, and is read
    it leaves                                   PILL\_OUT\_FRAMES  0.23s
    the picture holds ALONE again               CTA\_BROLL\_TAIL   0.45s
    cut back to the speaker


**The lead is longer than the tail on purpose.** The picture is the thing the
viewer has to understand first; the button is a second thought laid over a
picture they have already read. Landing them together makes the button an
interruption and the picture an afterthought.

Measured on the delivered re-cut, all four cutaways: **3.60s each, 0.60s of
picture alone, 2.53s of button, 0.47s of picture alone.** Before the split, at a
2.0s hold, it was 0.13s / 1.12s / 0.13s.

**This is why `BROLL\_HOLD\_MIN` cannot go back down.** The five beats need about
2.9s at the absolute minimum (0.60 + 0.23 + a readable hold + 0.23 + 0.45), and
that is the whole of the owner's "min 3 seconds" arriving from the other
direction. The two numbers are one decision.

## The button is ONE object, and it is symmetrical (2026-08-25)

Owner, watching the 08.25 clip: *"the pill is not symetreical"*. He was right
five times over, and every one was found by rendering `render\_cta\_png` directly
and measuring the PNG rather than by reading the code.

**1. The label sat 11.5px low - a 23px asymmetry in a 150px pill.** It was drawn
at `(ph - f.size)/2 - 2`, which centres the font's NOMINAL POINT SIZE (62) while
PIL draws from the ASCENDER line. Measured: ascent 61 / descent 15,
`getbbox("Sign up free")` = (0, 15, 346, 74), so the ink ran 58px down from a
draw origin of 54.0 and landed with **58px of air above it and 35px below**.
(The dead `asc, \_ = f.getmetrics()` on the line above was the abandoned start of
this fix.) Four placements were rendered side by side and looked at:

&#x20;   current  (ph - size)/2 - 2      top 58  bottom 35   ASYM +23
    INK BOX  centre bbox\[1]..\[3]    top 46  bottom 46   ASYM   0   <- ships
    cap band captop..baseline       top 53  bottom 40   ASYM +13
    optical  cap + a quarter desc   top 43  bottom 50   ASYM  -7


The cap-band version is the usual typographic answer and it is WRONG here:
"Sign up free" carries two descenders and one sits under the word's optical
centre, so centring the caps still reads low - which is the defect being fixed.

**2. The drop shadow was clipped to a RECTANGLE around a capsule.**
`GaussianBlur(10)` reaches 24px before its alpha hits zero and the canvas gave
it 12px left, 11 right, 16 above, **7 below** - so it was cut mid-gradient at
alpha 9/17/21 and **46/255** along the bottom. On the delivered file that
measured **+20.5 luma across a single row** at the plate's bottom edge. A hard
rectangular halo around a round button is exactly the kind of thing that reads
as "not symmetrical" without being nameable. `PILL\_SHADOW\_PAD` is 30 now -
larger than the blur's own reach - equal on all four sides.

**3. The address did not scale with the pill, so the lockup was two objects.**
It was drawn onto the band AFTER the plate was resized, at a fixed 30px: it
measured 22px of glyph on EVERY frame, including the ones where the pill was at
`PILL\_SCALE\[0]` 0.79. On frame 0 the button was 364px wide and the URL beneath
it was **405px** - the subordinate line wider than the button, at full weight.
That is the "two vocabularies in one clip" failure this file already records for
type, happening inside a single element. Button and address are drawn on ONE
plate now and scale as one object.

**4. The pill grew DOWNWARD only.** `x` centred the scaled plate; `y` was its
top-left. So the 1.03 overshoot landed as +0.4px above and +4.9px below, and the
pill's own centre moved 139.6 -> 137.0 between two frames on which `dy` was 0
both times. Both axes are centres now.

**5. Three centres disagreed by a pixel.** Frame 539.5, plate 540.0, address
539.0. PIL's `rounded\_rectangle` is INCLUSIVE of x1 and y1, so a rect from 12 to
`12+pw` draws `pw+1` columns - that one extra column is the plate's whole error,
and it had been there since the element was written. The lockup is drawn on a
full-frame-width canvas now and the far edges are `-1`. Measured after: plate
462x150 exactly, **cx 539.50 (off +0.00)**, label margins 58/58 and 46/46, and
**0 of 150 cap rows with a left/right mismatch**.

Two more came out of the same pass and are not about symmetry:

**The entrance stopped dead and then jumped 3%.** `dy` reached 0 at kin=6 while
`PILL\_SCALE` was still at its 1.03 peak, and the next frame dropped to 1.00 with
nothing between - **13.9px of width in one frame at 30fps**, and again at the
start of every exit, six ticks in a three-cutaway clip. On an element whose
brief is *"smoother ... more professional the way it comes in"*. The overshoot
is kept (it is the measured character of the reference button) and the RETURN
from it is spread over the last three frames: `1.03 -> 1.02 -> 1.01 -> 1.0`.
Worst single-frame scale step 0.030 -> 0.010.

**The address was drawn INTO the platform chrome, and preflight said it was
not.** Bone ink reached frame **y1448** with its stroke - 18px past
`CAP\_SAFE\_BOTTOM` 1430 and 8px past the y1440 TikTok floor. The only guard
tested the BAND (`ay + f\_a.size < CTA\_BAND\_H`, 380px below the line that
matters), and preflight's SAFE check rebuilt the geometry from four constants
(`rest + PILL\_H + 6 + CTA\_ADDR\_SIZE + 6`) and reported "the invitation to
y1422" - `CTA\_ADDR\_SIZE` is a point size, not an ink height, and the stroke was
not in the sum at all. **Two owners of one quantity, and the one that could not
see the ink was the one doing the checking.** Now: the rest position is DERIVED
from `CAP\_SAFE\_BOTTOM` by `\_pill\_metrics()`, and preflight asks
`q.pill\_ink\_bottom()`, which renders the real PNG and measures its alpha. It
clears by 14px and cannot drift from what ships.

`\_pill\_metrics()` also ASSERTS that `CTA\_BAND\_H` contains the whole
`PILL\_RISE` travel - the clipped-entrance defect this file records being fixed
once by taking the band to 630 had to be found by watching the clip. It fired
immediately (650 needed, 630 present) and the band is 700.

**And the pill's window had to follow the shorter cutaways.** `CTA\_BROLL\_PAD`
0.35 was sized to clear the SLIDE's travel; with a cut there is nothing to
clear, and holding it would have taken 0.70s out of a 2.0s cutaway for nothing.
It is 4 frames now. The feasibility gate in `cta\_windows` also tested
`2.0 \* CTA\_FADE + 0.4`, built from a constant belonging to the "line" style that
the pill branch never reads - at its own limit the button would have spent 53%
of its life travelling. It tests `PILL\_TRAVEL + PILL\_SETTLE\_MIN` now, so at a
2.0s hold the button settles for 1.12s instead of 0.83s.

## The button (2026-08-24)

The owner pointed at a MrBeast short and asked for its Subscribe animation, in WLAM
terms: *"it's about the subscribe, but for our case it would be follow for more,
sign up for quasar markets... that's kinda the idea where it's a nice animate
overlay."*

**NOTE WHAT THIS OVERRIDES.** `references/look.md` rejected an enclosed shape
against the video twice, on the grounds that *"a button that cannot be tapped is a
small broken promise on every clip"*. That objection is still true and the owner
has overruled it with a specific, extremely successful reference. It is his call.
Recorded here so nobody reverts it as a regression.

**Measured**, off youtube.com/shorts/hYahU\_Cqwp8 at its native 30fps:

|frame|y0|width||
|-|-|-|-|
|0|1632|419|enters from below, already part-scaled|
|2|1368|482||
|5|1275|542|width **overshoots**|
|6|1263|545|peak|
|…|1245|529|settles — width comes back, y keeps easing up|

So it is a **spring**: rises from below the frame, overshoots in scale, settles,
holds about ten frames, drops back out. Resting geometry 529x153 centred at
y1245..1398, total life \~0.75s. `PILL\_SCALE` carries those measured widths.

**Ours is the same size and the frame had to be rearranged to allow it.** His
captions are 46px at y936 — tiny and dead centre — so a 153px pill at y1245 has
the lower third to itself. Ours are 86px in a band ending at y1430. The fix is
that under a cutaway there is **no face**, so the captions can ride much higher
than "top of the old band": `CAP\_BAND\_H` went 300 → 480 at y950, with
`CAP\_BAND\_Y\_REST`/`CAP\_BAND\_H\_REST` reproducing the old centring exactly for every
ordinary frame — **a normal caption does not move by a pixel**. Raised, a two-line
block ends at y1156, which leaves y1180..1430 for a 150px pill.

**And the raise tests OVERLAP, not containment.** `a <= t0 < b` only raised a card
that BEGAN inside the window, so a card that started before the pill came up
stayed low — caption at y1228..1331 against a pill at y1230..1380, the same rows.
It collided on screen. `t0 < b and t1 > a` is the fix.

**Type fills the pill.** Set side by side with the reference at the same crop and
scale, 40px type in a 150px pill read as a small chip against its button — the
reference's cap height fills most of its pill and ours had twice the air. 62px is
about 0.41 of `PILL\_H`, where the reference sits, and takes the pill to \~470px
wide against the reference's 529.

### The band has to CONTAIN the rise, or there is no animation

This is what made it read as a pop rather than an entrance, and it was invisible
in the code: the band was 250px tall and the pill starts 380px below its resting
place, so **the entrance was drawn outside the canvas and clipped**. The pill
simply appeared. `CTA\_BAND\_H` is 630 now (y1180..1810) so the whole travel is
inside it — nothing else lives down there, the invitation is the only tenant
below the captions.

Two more things separate an entrance from an appearance, both from the reference:

* **The travel IS the animation.** `PILL\_RISE` was 150 against the reference's
387. Measured after: y1461 → 1242 over six frames, settling within 3px of the
reference's own resting y1245.
* **It stays OPAQUE the whole way.** It used to fade up over three frames, and
fading a rise makes it read as a dissolve. The reference is a solid object
entering from off-frame, so ours is too.

**The address rides under it.** Owner: *"it should be sign up for free
quasarmarkets.com"*. Inside the pill it would crowd a 150px button; underneath it
reads the way the closing card reads, and it travels WITH the pill so the two
arrive as one object rather than as a button and a caption.

**And `SAFE` had to learn to measure ink rather than canvas.** Both bands are now
deliberately taller than what they draw — 480 for the captions so a raised card
can ride high, 630 for the invitation so the rise is not clipped — and scoring the
canvas failed a clip whose ink rests at y1422 against a y1430 line. A check that
calls correct work broken is worse than no check.

**No cursor.** The reference has a hand cursor over the button; the owner was
explicitly unsure (*"we don't really want the thumb to click it. Maybe we do."*).
It is left out because a cursor is the part that actually promises a tap, which is
the objection above at its strongest. It is a small addition if he wants it.

`"cta\_style": "line"` keeps the tracked verb-over-address version.

## The b-roll vocabulary, 288 → 2,168

Twelve subject domains proposed in parallel and **every term was searched against
the real libraries before it was kept**, then audited by a second pass that cut
anything returning off-subject or posed stock. 1,880 keys over 306 pictures.

It exists because a clip about creatine, dosing and cognition returned **zero**
candidates across its whole runtime. The acceptance test is that same span: zero
before, **two after**.

Three findings worth more than the entries:

* **`search\_library` needs only `len(toks)//2` token overlap AND FUNCTION WORDS
COUNT.** So `"students in a lecture hall"` matched on "in"+"a" and returned a
messy office table, an MRI machine and two scientists. 21 terms were rewritten
to content words only. **Three or four content words is the working shape** — a
function word, or a bare "man"/"person", hands the top of the contact sheet to
unrelated library assets.
* **A lowercase multi-word key is dead.** `candidates()` only looks up a bigram if
it is in `\_MULTI\_HINTS`, so `gas station`, `social media`, `fast food`, `power plant` could never fire. 27 dropped. Capitalised proper-noun pairs survive via
the `\_is\_entity` branch.
* **Homonyms a markets show would fire wrongly** were dropped outright: `rally` (a
price rally, not a protest), `notes` (Treasury notes), `read` ("my read on
this"), `machine` ("machine learning"), `freeze` ("hiring freeze"), `thaw`,
`transmission`, `social`, `timeline`, `passage`, `striking`.

`gdp` was deliberately left OUT so the learned pairing (container ship port
cranes, approved by eye on a shipped clip) keeps winning — EXPAND beats a learned
pairing, so adding it would have masked a decision somebody actually made.

**Where the libraries are still empty**, so nobody re-derives it: institutions
(`imf`/`world bank` rests on 2 assets, `recession` on 2, `news anchor` on 3),
consumer apparel is a total void — no clothing, shoe or retail-rack picture exists
in any source — and supplement powder, batteries, quantum, bathroom scales,
cybersecurity padlocks and underground mining are unfindable. Those words route to
adjacent physical pictures instead. Pexels is the only motion source
(`PIXABAY\_API\_KEY` is unset) and it 429s in bursts, which `search()` swallows as an
empty list — always retry before recording a term dead.

## The 2026-08-25 standard: title, then name in a box, and nothing static

The owner, watching `01-tariffs-timed-to-early-voting`: *"I actually love this
look here of the person's name, what they have, whoever they are. That is
actually perfect. **This should be the standard for every single WLAM clip cutter
going forward.**"* Then four changes, and the order he gave them is the order
the elements appear in:

> \*"The only thing it needs to be, it needs to be a white box behind it so it's
> cleaner, you can view it better, with black text - but then that should animate
> in and it should animate out ... instead of it, like, go swiping, it should
> kinda fade in."\*
> \*"The top is the title. And then after the title goes, it will be the person's
> name in a box."\*
> \*"The sign up? It needs to pulse. It needs to move as it's sitting there ... it
> needs to flow in there slower and smoother ... and then after the clip's done,
> it's gonna come out and smooth out."\*
> \*"We wanna be able to switch around the transitions from b roll clips to going
> out. It should not always be fade ... slow moving and clean, and it just flows
> across the screen. We don't want any staticness."\*
> \*"We need to have more vocab. Expand our library of vocab."\*

### 1\. The nameplate is a card now, and it had been drawing under the chrome

`render\_attr\_band\_png` drew two tracked bone lines with a stroke, straight onto
the picture. It is a **bone plate with slate type** - the hook card arriving a
second time, not a second vocabulary - centred, `ATTR\_PLATE\_R` 16, the hook
card's own soft drop, sized to the wider of the two lines and shrunk to
`CAP\_MEASURE` the way a caption is.

**The plate width is forced EVEN** so its centre lands on the frame's 539.5
rather than half a pixel right of it - the same defect this file records being
found on the button.

**AND IT WAS RENDERING INSIDE THE PLATFORM CHROME ON EVERY HEAD CLIP THIS RIG
HAS SHIPPED.** Measured on the delivered file: the old ink ran **y1460..1548**.
`CAP\_SAFE\_BOTTOM` is 1430 and the note above it says "nothing that must be read
may sit below y1440", because TikTok draws over roughly the bottom 480px. It was
never noticed because `check\_safe` scored exactly two tenants - the captions and
the invitation - and the nameplate was a third one nobody had added. The credit
line, the thing that carries the speaker's authority, was under the like button.

Fixed the way the invitation's was: the rest position is **derived** from
`CAP\_SAFE\_BOTTOM` by `\_attr\_metrics()`, so the plate's bottom edge lands on
**y1416 - the same row the invitation's address inks on**. Two tenants of one
strip, ending on one line. `check\_safe` now scores three, asking
`q.attr\_ink\_bottom()` (which renders the real PNG and reads its alpha) rather
than rebuilding a sum out of constants.

**It cross-fades. No slide.** `ATTR\_BAND\_SLIDE` is gone: 0.50s in on an ease-out,
0.42s out on an ease-in, no dx at all. Verified on the delivered file by solving
the blend per frame - alpha 0.00 -> 0.98 over 0.45s, monotone, and the plate's
edges pinned at **x212..867 on every frame of its life**.

**The captions ride up for it**, through the same `raise\_wins` mechanism the
invitation already used. Without that the plate lands on the resting caption's
own rows.

**It is clipped off the first cutaway.** The first cut put its fade-out across
the first insert's dissolve - at +7.35s, the nameplate at 12% over a cover at
43% - and two cross-fades running through each other is the mud "we don't want
any staticness" is about. `ATTR\_BAND\_GAP` 0.30s. If a cutaway lands so early
that clipping would leave under `ATTR\_BAND\_MIN`, the card keeps its full life
and they overlap: an unnamed speaker is a worse clip than a busy second.

### 2\. The credential came OFF the hook card, and that overturns a rule

**This overturns "The white card ALWAYS carries the name" (2026-08-25, earlier
the same day).** Recorded as an overturn, not done quietly.

"The top is the title, and then after the title goes, the person's name in a
box" is an ORDER, and a credential set into the title card cannot deliver it -
it arrives with the headline and leaves with it. The old rule was written when
the alternative was tracked type on the picture, gated to `head`, that vanished
on `share`; the choice then was "card or nothing". It is not that now: the
nameplate is a card of its own, on **every mode**, and the argument that settled
the old rule - "the card is ours, is the thing the eye lands on, and is the only
attribution that survives a crop" - is satisfied in full by it.

Keeping both is the one option that is definitely wrong: the name on screen
twice in eight seconds, in two sizes. `"attr\_on\_card": true` puts the rung
ladder back for a show that wants it; the ladder is kept, not deleted.

`duo` and `duo\_share` still name nobody. Unchanged and deliberate - see
`speaker\_label`.

### 3\. The button breathes, and it leaves the way it arrived

**The pulse.** `pill\_pulse` is a **raised cosine**, `1 + 0.024\*(1-cos)/2`, over
`PILL\_PULSE\_FRAMES` 36 (1.20s at 30fps). It starts at exactly 1.0 with **zero
velocity** and returns to 1.0 with zero velocity, so the seam with the entrance

* which now lands on exactly 1.0 - is free in both position and speed. A sine
would start at 1.0 travelling at its maximum rate, which is a kick on the frame
the travel ends.

+2.4% is **11px of the 462px button**. Measured on the delivered file: the pill
oscillates 430 -> 442 -> 429 -> 442 px through each hold, centre pinned at
539-540, roughly two breaths per cutaway.

**In FRAMES, not seconds.** `SRC\_FPS` is 25 on most shows and 30 on this one, and
the raised cosine is only a palindrome - and therefore only cheap to dedupe - on
an integer number of frames. The phase is `kin - PILL\_IN\_FRAMES`, an integer, so
all three cutaways in a clip breathe **in step** and share their PNGs. The whole
pulse costs about 19 extra PNGs for a 50s clip, not 361.

**It is closed BEFORE the exit, over `PILL\_PULSE\_TAPER` 8 frames.** The first
version tapered it across the exit using the exit's own progress, and the exit's
curve is the entrance reversed - so it climbed back through the 1.0264 overshoot
while the pulse was near its peak and the two **multiplied**: 1.0435 on the way
out, 20px wider than at rest, with a 0.007 jump on the exit's first frame.

**10 -> 15 frames each way** (0.500s), `PILL\_SCALE` resampled onto 15 by the same
method the 7->10 pass used - the measured shape, more samples. Worst step near
the settle falls 0.0100 -> 0.0028. The ceiling is 17: `cta\_windows` needs
`PILL\_TRAVEL + PILL\_SETTLE\_MIN` inside the inset window, which at
`BROLL\_HOLD\_MIN` is 1.95s, so `N <= 15\*(hold - 1.85)`.

**And the exit was easing the wrong way.** `u` counts DOWN across the departure,
so `u \*\* 3` read as a function of time is an ease-OUT: the lockup's first
departing frame moved **113.1px** and its last moved 0.5px - it leapt off the
frame and then crawled. `1 - (1 - u) \*\* 3` mirrors the arrival: **0.1px on the
first frame**, accelerating to 75.8px. That, and not the frame count, is most of
"it's gonna come out and smooth out".

Three guards came out of this and are now asserted rather than remembered:
`PILL\_IN\_FRAMES == PILL\_OUT\_FRAMES == len(PILL\_SCALE)` (both branches index one
tuple by their own k), `PILL\_SCALE\[-1] == 1.0`, and `pill\_ink\_bottom` takes an
`sx` so `check\_safe` scores the button at its **peak** (y1419) instead of at rest.
A window the feasibility gate refuses now prints a line - it used to drop in
silence, taking the caption raise with it.

### 4\. The cutaway varies, and the dissolve never goes away

**What does not vary is the cross-dissolve.** Every insert still dissolves on
the same `BROLL\_IN`/`BROLL\_OUT` ramp through the same two alpha `fade` filters.
Putting the hard cut or the full-frame slide back into a rotation would re-ship,
on one insert in six, something recorded three sections up as rejected by name.
*"It should not always be fade"* is answered by giving the dissolve somewhere to
come FROM, not by taking the dissolve away.

**What varies is an 80px drift underneath it**, and its direction.
`BROLL\_ROTATION` is six pairs, adjacent entries always different (asserted, wrap
included), picked by a **SHA-1 of the slug** - `hashlib`, never the builtin
`hash()`, which is salted per process and would make a re-render of a delivered
clip come back different. A slate pins either half with `"move\_in"` /
`"move\_out"`. **At most one half of any insert moves**: two different moves in
one insert is an object with no physical story, and a matched pair is the
picture retreating the way it came.

**The drift has its OWN clock, and that is the difference between it reading and
not reading at all.** Run over the dissolve's 0.35s on an `out\_quart`, 97% of
the travel happened while the insert was under 50% opaque - frame-stepping the
delivered file, the trucks had stopped before they were readable. It now runs
over `CTA\_BROLL\_LEAD` in and `CTA\_BROLL\_TAIL` out, on a **smoothstep**, so the
picture lands exactly as the invitation arrives and starts moving again exactly
as it finishes leaving. *"The picture lands and holds ALONE"* becomes literally
true - it is still landing through that beat. Measured after: 30px of the travel
happens at full opacity, monotone, 2 to 8px a frame.

**The insert is over-scaled `BROLL\_BLEED` 1.17, and without that the whole idea
is worse than doing nothing.** The bake is 1080x1920 exactly, so a translated
insert shows a hard-edged band of SPEAKER at whatever opacity the dissolve has
reached. The bleed is **derived from the drift** with an assert, not hand-set - a
first pass at 1.10 gave 54px of horizontal cover against a 64px drift. Only a
moving insert is over-scaled; `soft/soft` keeps `scale=W:H` and renders
byte-identically.

**`BROLL\_IN + BROLL\_OUT` is unchanged at 0.70** and that is load-bearing:
`BROLL\_HOLD`, `BROLL\_HOLD\_MIN`, `BROLL\_EVERY`, `BAKE\_HOLD`, broll.py's
`MIN\_HOLD` and `PAN\_DONE` and preflight's 3.70..4.20 band are all functions of
it. Give one move its own duration and all seven become per-insert on the same
day, and every slate in the archive is re-scored.

**A real bug came out with it.** The dissolve's fade-out ran to `a1` while the
gate closes at `a1 - hb`, so the last frame drawn still carried the insert at
11% and that 11% vanished between two frames - the same off-by-one the slide's
swipe was fixed for. `d = max(f1, dout - f1)`.

**WHAT THIS RELAXES.** `references/look.md`'s compass is *"picture arrives from
BELOW, type arrives from the RIGHT, everything leaves LEFT"*, one rule for every
element. A four-direction rotation relaxes the picture half of it **for travels
under about 100px**, on the argument that a 4% offset is beneath the resolution
at which a direction reads as a rule. Every large travel still obeys it: the
hook card, the end card's wipe, and `broll\_style: "slide"`. Said out loud
because the alternative - keeping the compass - allows exactly one legal pair,
which is no variety at all.

Verified on the delivered file the way this element is always verified: blend
weight solved per frame, 8-9 intermediate frames in and 4-7 out on all three
inserts, monotone; and the drift extracted by cross-correlation against the
settled frame, monotone and in the authored direction on each.

### 5\. The vocabulary, 2,168 -> 2,868 (and then to 10,697 — see the big run below)

721 entries from a sweep of what finance, policy, energy, health, tech and sport
interviews actually say, plus the probe's own top misses; **20 were then taken
back out and 18 re-pointed** - see the homonym note below. Zero collided with an
existing key, and no existing key changed value or was removed. Same rule as
every entry before them: **the value is a physical thing a camera can point at**.

**A BIGGER VOCABULARY CAN MAKE A CLIP WORSE, AND THAT IS THE LESSON HERE.**
`candidates()` ranks a word group by `(-(in EXPAND), -(is multi-word), -len)`, so
a NEW key that is longer than the right one **wins**. An adversarial pass caught
eleven of these by replaying the ranking over real sentences, before/after:

&#x20;   "Fed governors are split"        Eccles Building  ->  a state capitol
    "the Fed's balance sheet"        financial ledger ->  a brass weighing scale
    "the debt ceiling fight"         a stack of bills ->  a skyscraper
    "the benchmark ten year yield"   the Treasury     ->  a sprinting runner
    "greenhouse gas rules"           a gas pipeline   ->  a seedling
    "scaling compute"                a data centre    ->  a tower crane


Every one of those is a fixed phrase this material uses constantly, and in every
one the *addition* displaced a picture that was already right. They are dropped
rather than re-pointed: an unmapped word falls back to a literal search, which is
what it did before, and that is the correct behaviour for a word whose commonest
sense here is not a picture. **Adding a word is not free; test it against the
phrase it lives in.**

Also caught and fixed by measurement, not by reading: four dead queries (a
prairie that returned a lion, an arch that returned the India Gate, an "alarm"
that returned an alarm clock), and a set that showed the wrong subject outright -
lean hogs got beef cattle, a kidney got a brain, a synagogue got a church steeple.

**`"president"` had no entry at all** - the most spoken noun in this master, 29
times - so it was searched **literally**, and a literal search for "president"
returns photographs of identifiable living politicians. That had been true of
every politics clip this rig has cut.

It resolves to **`podium microphones press conference`**, and that is the second
answer: the first was `white house north portico exterior`, which put the White
House under "President Xi" and under every foreign head of state - and which,
searched live, returned **suburban houses**. A podium is the office rather than
the officeholder AND rather than the country. Both parties resolve to the same
polling station, which is the point rather than a shortcut: any picture that told
them apart would be a picture of partisans.

Measured on the Nathan Dean master: coverage of its content words went **93 ->
133**, picking up every US state it names, Canada, Iran, Hormuz, potash,
impeachment and the Gulf states.

### What the adversarial pass caught, and it was all mine

Four lenses over the diff and the delivered files, each finding independently
re-run before it was believed. **Eleven real defects in code that had already
been measured once and looked right**, which is the argument for the pass:

**Two callers deriving one quantity, again.** `build\_capsule\_sequence` called the
bare `cta\_windows(dur)` while `render()` called `cta\_windows(dur, attr=...)` -
so on a clip whose first cutaway lands inside the nameplate's window they
disagreed: render dropped it, the band kept it, and the nameplate outranks the
invitation in the band's key, so the button's whole 15-frame entrance was
suppressed and it appeared at full opacity on one frame. The window list is
handed in now rather than recomputed.

**A hardcoded frame count is a different duration on every show.** `SRC\_FPS`
defaults to 25 and this job is 30, so `PILL\_IN\_FRAMES = 15` was 0.500s here and
0.600s everywhere else - which took `PILL\_TRAVEL` to 1.200s, the feasibility gate
to 2.000s, and a `BROLL\_HOLD\_MIN` cutaway's window is 1.95s. **The button would
have been dropped off every minimum-length cutaway on every 25fps show.** It is
`int(round(PILL\_TRAVEL\_S \* FPS))` now, and `PILL\_SCALE` went from a tuple indexed
by the frame counter to a SHAPE that `pill\_scale(k, n)` samples - which also
retires the three-way coupling between the curve's length and the two counts, and
the hand-resampling it had needed three times.

**The drift was multiplied by the tempo, and the tempo is not a distance.**
`d = BROLL\_DRIFT \* k` made a tempo'd clip drift further as well as faster, while
`BROLL\_BLEED`'s assert is written against the unscaled drift. Measured over all
25 move pairs: the coverage margin fell from 11.8px at tempo 1.0 to **exactly
0px at `SPEED\_MAX` 1.12** and went negative above it - a hard-edged strip of the
speaker along the frame edge, the one failure the over-scale exists to prevent.

**The nameplate arrived before the title had gone at any tempo over \~1.005.**
`ATTR\_BAND\_AT` was a bare 3.25 while the hook card's exit is tempo-scaled.
Stepped at 1.04 the title is still at full alpha, sliding off left, while the
nameplate fades up at 0.42. It is `(HOOK\_HOLD + HOOK\_OUT) \* tempo + ATTR\_AFTER\_HOOK` now - **the ordering this whole change exists to deliver, broken
by the one number that did not follow the clip.**

**A tile tag is not a name.** `"speaker"` has two meanings in this pipeline:
`check\_speaker` uses it to say which TILE is talking, and the archive's share and
duo slates carry `"exchange"`, `"alan"`, `"steve"`. Those were survivable while
the credential only reached the hook card behind a ladder that usually refused
it; the nameplate is unconditional, so **a bone card reading "exchange" would
have shipped on a two-up.** `speaker\_label` refuses a name with no capitals and
says why - it does not title-case it, because "steve" -> "Steve" is a different
wrong answer.

**A warning in a per-frame function is not a warning.** The nameplate/cutaway
overlap note lived in `attr\_window`, which `attr\_band\_state` calls once per
frame: 1,440 identical lines per clip, burying the "invite: no room" notice this
same change had just added on the argument that it *"used to drop in silence"*.

**And a bigger vocabulary made some clips worse** - eleven fixed phrases where a
new key outranked the right one. See the note under the vocabulary above.

**And then the pixel lens found three more on the delivered files, one of which
is the biggest single win in this whole pass.**

**THE COMPOSITE WAS BEING RE-GRIDDED, AND EVERY ANIMATED OVERLAY PAID FOR IT.**
The source is opened at a FRACTIONAL `-ss` (a slate start is 189.34s, not a frame
boundary) and `cut\_graph` then trims and concats spans, so the composite's PTS
grid sits a sub-frame constant off `k/FPS`. The output `-r` re-grids it by
nearest PTS - **so overlays were locally duplicated and dropped rather than
sampled 1:1.** Measured on the invitation's own plate top through its first
entrance:

&#x20;   delivered   1334  1302  1302  1260  1244  1244  1231
    the PNGs    1334  1302  1277  1258  1244  1235  1231


Two frames drawn twice, two never drawn - the button hitched twice on the way in,
on the element whose entire brief is *"smoother ... the way it comes in"*.
`cta\_state` is not the cause: 4,000 random windows through it produce no repeated
entrance step. **The frame mapping was.** `settb=1/FPS,fps=FPS` on the base
before the overlays. Measured after, all six cutaways across both clips: **zero
stalls**, and the worst single-frame step falls from 86px (pre-change) to 32px.

This was pre-existing and it affected the captions, the hook card and the cutaway
exactly as much as the button. It is the answer to a complaint this file records
being made three separate times.

**The rotation was seeded on the clip's RANK.** `build\_all` passes `render()` the
delivered name, `"NN-slug"`, because that is what the file is called - so hashing
it made the transitions depend on the clip's POSITION in the slate.
`no-good-answers-on-hormuz` and `02-no-good-answers-on-hormuz` pick different
rotations, and the delivered file had the second. Re-ordering a slate, or
dropping one clip, silently re-rolled every other clip's transitions - which
breaks the one promise the hash exists to keep. The rank prefix is stripped
before hashing.

**A caption was raised for a nameplate that had already gone.** The raise rule
lifts a card that OVERLAPS the window at all, so a card starting 70ms before the
window closed rode high for its whole second while the plate under it was at 15%
alpha. Measured: three consecutive cards at rows 987, 1265, 987 inside 1.1s - a
278px jump up and back for nothing, in the element the eye is locked to. Two
fixes, because there were two faults: the raise window now ends where the plate
stops being legible (two thirds through the fade), and `merge\_raise` closes any
gap under `CAP\_RAISE\_BRIDGE` 1.2s, so the nameplate hands straight over to the
first cutaway's invitation instead of the captions dropping and coming back.
**Moving the captions is the cost; holding them high is free** - the band is
480px tall for exactly this reason.

**One finding survived refutation, and it was a real hole in the new vocabulary.**
`candidates()` joins two adjacent capitalised words into one term and then does
`i += 2`, so **"Donald Trump" is looked up WHOLE** and the surname entry - which
does resolve to a building - is never reached. The full name went out as a
literal search and came back with protest footage of the man. Same for every
other head of state, central banker and chief executive this desk names. Both
forms are in now: a head of state resolves to their CAPITAL, a central banker to
their BANK, a chief executive to what their company makes. None of those can be a
photograph of somebody, which is the whole rule.

The rest were stale prose that had become false: a comment claiming the cover
frame carries the credential (it cannot - the nameplate arrives after `poster()`'s
window closes, and that is a real cost of the new ordering, now recorded rather
than discovered), a block arguing about a 64px drift beside a constant reading
80, and `build\_capsule\_sequence`'s own lead comment describing a two-tenant band
and pointing at a deleted symbol.

## The big run: 10,697 words and a library that gets built ahead of the show

The owner, the same evening: *"We need to do a massive run on just b-roll now ...
we should ALWAYS have something. Like if it says 'think' — okay, we have a shot
for thinking. We need to have a shot for every single word we can think of ...
add all these shots up, all the B-roll shots we can get, as many as we can."*

### The vocabulary, 2,826 -> 10,697

Fourteen domains written in parallel and merged: abstractions and states of mind,
finance, policy, energy and climate, tech and AI, space and defence, health and
biotech, science, industry and logistics, consumer and retail, work and society,
everyday objects and actions, and time/weather/place-types.

**Measured on eight real transcripts, the share of spoken content words that have
a curated picture goes 13.0% -> 25.8%.** That is the number *"we should always
have something"* is actually about.

**The hard part was the abstractions, and they are why he asked.** A word like
"decide" has no photograph, so it gets a physical metaphor a stock library
actually holds — a crossroads signpost; "doubt" a forked path; "hesitate" a foot
hovering over a stepping stone; "regret" a crumpled letter in a wastebasket. That
is a picture of the IDEA, which is what b-roll is for, rather than a picture of
the word, which is what a literal search returns.

### The homonym gate is mechanical now

The previous pass shipped eleven regressions that a human had to find by reading
sentences. `candidates()` ranks a word group by `(in EXPAND, multi-word, LENGTH)`,
so a longer new key BEATS a shorter correct one.

So every candidate is now tested before it is allowed in: the corpus is every
transcript this rig has plus thirty canonical fixed phrases (**2,512 sentences**),
the pick is computed with and without the candidate, and anything that displaces
a CURATED pick is dropped. **8,080 candidates in, 213 dropped, 7,867 shipped.**

It only protects a *curated* pick. When the old answer was the word itself the
search was LITERAL — the failure this expansion exists to end — so displacing
that is the improvement, not the regression. Without that distinction the gate
dropped "starlink", "metals" and "help" for beating literal searches.

Dropped for cause, as examples of what it is for: **"pumping"** would have turned
*"gold pumping hard"* into an oil pump jack; **"possible"** beat "AI";
**"expensive"** beat "debt"; **"decades"** beat "gold".

**And the gate was outvoted twice, on the owner's own examples.** *"If it says
THINK"* and *"if he's talking about STARLINK"* are two of the three examples he
gave, so a vocabulary that ships without them has missed the brief. The objection
to "think" is real and small — 13 displacements in 2,512 sentences — and it is
five letters, so it only ever wins a group with nothing more specific in it,
which is exactly the group that would otherwise go out as a literal search.

### `broll.py stock` — the library gets built ahead of the show

`fetch()` is slate-driven, which is right for a show and useless for a library.
`stock` walks the VOCABULARY instead, **commonest picture first** — the rank is
how many spoken words point at a query, so "two people shaking hands" (the answer
to merger, acquisition, buyout, negotiators and a dozen more) earns its disk
before a query only one word can reach. 10,697 words resolve to **2,116 distinct
pictures**.

&#x20;   python3 broll.py stock --max=400        # the vocabulary, commonest first
    python3 broll.py stock --people         # portraits only
    python3 broll.py stock --dry --max=20   # what it would take, and from where


**Resumable by construction**: the index is the state, anything already held is
skipped, and the index is written after EVERY asset — a four-hundred-asset run
WILL be interrupted, and an index written once at the end turns every completed
download into an orphan nothing can find.

**It takes the top hit unreviewed, and that is the honest trade.** Every other
route into this library goes past a human looking at four thumbnails. This one
does not — which is acceptable for a SHARED pool because `propose` still
shortlists per clip and the operator still approves per insert, so a weak library
asset loses to a fresh search on the day. It would not be acceptable as the last
word, and it is not one: `sweep --metrics` scores what lands and `retire` removes
it.

### Three things the run itself broke, all of them silent

**The index was written non-atomically.** `write\_text` truncates and then writes,
so a reader in that window gets a JSONDecodeError. Theoretical while the only
writer was a slate fetch running alone; `stock` writes after every asset for
hours. It killed a tool mid-run within minutes. Every write goes through
`\_write\_index()` and an `os.replace` now.

**`learned\_vocab()` was re-parsing a 600KB document once per WORD.**
`\_is\_concrete()` asks it for every token `candidates()` walks — measured, a pass
over 2,500 sentences did seventy-five thousand full index reads and did not
finish in two minutes. Memoised on the index's `(mtime, size)`, 2,000 calls take
10ms. Keyed on the file stamp rather than cached outright, because fetch and
stock add rows WHILE it is being called.

**Two runs at once clobber each other.** Not corruption — every write is atomic —
but each holds a dict read at its own start and writes the whole thing back, so
the second to finish silently drops everything the first fetched. Found by
starting a portrait run while a 250-asset run was going. There is a pidfile lock
that clears itself if the holder is gone.

## When the show names a person, cut to that person (2026-08-25)

The owner: *"If we're talking about famous people — Steve talks about Elon Musk,
then they should cut to a picture of Elon Musk. If we're talking about the Fed
and Fed Warsh, cut to a picture of the chairman. Talk about Trump, Trump comes
up, cut to Trump's face."*

**THIS OVERTURNS "the PLACE, never the person", written the same morning.** That
rule was the right answer to a different problem: a name with no vocabulary entry
was searched literally and came back with protest footage and campaign
merchandise — which is not a portrait of anybody, it is a picture of a crowd's
opinion. The fix for that is a *curated portrait*; the fix I shipped was to
refuse to show the person at all. Recorded as an overturn.

### The licence is the whole of the engineering

A photograph of a living public figure is the one subject where the free stock
libraries have nothing usable and the good frames are agency work nobody has
licensed to us. Wikimedia Commons is the exception for a specific statutory
reason: **a photograph taken by a US federal employee in the course of their
duties is public domain.** Between the State Department, the Air Force, the White
House, the Federal Reserve and the IMF, that covers most of the people this desk
names.

&#x20;   PD / CC0 / PDM      taken, no obligation            <- preferred, always
    CC BY               taken, attribution recorded
    CC BY-SA            REFUSED


**ShareAlike is refused and that is deliberate.** It asks that a derivative be
released under the same terms, and the derivative here is a commercial brand
clip. Nobody is going to CC-BY-SA a Quasar Markets short, so taking the picture
would mean taking it on terms we do not intend to honour. That costs us the
highest-resolution frames of several people — Jensen Huang's are all BY-SA — and
the answer is to name a different picture, not to look away from the licence.

### What it can and cannot find, measured

Verified live against Commons: **Trump, Powell, Warsh, Lagarde, Xi, Zelensky,
Bezos, Barra, Sanders and Musk all have a usable frame.** Musk's is a US Air
Force photograph, Lagarde's an IMF official portrait, Xi's a State Department
one — which is the statutory rule doing the work.

**Private individuals mostly do not.** Sam Altman, Jamie Dimon, Cathie Wood, Andy
Jassy, Ray Dalio, Satya Nadella and Narendra Modi have no correctly-licensed
portrait, because nobody who photographs them works for the US government. Every
name therefore carries a FALLBACK — a head of state to their capital, a central
banker to their bank, a chief executive to what their company makes — and
`search()` prints a line saying it fell back. That is the honest state of
affairs, not a bug to keep grinding at.

### Three filters, and each one was earned

`search\_people` is a SEPARATE TIER, not another entry in `SOURCES`, because
`search()`'s ranking puts motion above stills — and for a living person there is
no correctly-licensed motion at all, so a stock clip that merely shares a word
would outrank the actual portrait every time.

* **The surname must be in the title.** Commons titles name their subjects.
* **No group shots.** *"Joko Widodo and Christine Lagarde in Jakarta"* passed the
surname test and is a handshake at a summit — cut to it while the show says
"Lagarde" and the viewer has to work out which one she is. A joiner in the
title IS the test.
* **Nothing named after somebody.** *"Narendra Modi Stadium Ahmedabad"* contains
the surname, is a single-subject title, is 3024x4032 and is CC0 — it passed
every other test and it is a cricket ground. Public figures get buildings named
after them constantly.

### And a portrait run may only bake portraits

`stock --people` fell over on exactly this within two assets and it is worth
recording because the failure was silent. `search()` falls back to the person's
PLACE when Commons has nothing — correct for a render — and `stock` names the
asset after the TERM. So it baked a Pexels clip as `alexandria-ocasio-cortez` and
another as `andy-jassy`, and once a row with that name is in the index,
`search\_library` serves it under her name **forever**: the library would assert
that a stock video IS the person. The portrait run now refuses any hit that did
not come from the portrait tier. Both rows were scrubbed.

## Where the mirror lives

`\~/Desktop/WLAM clipping/` is a browsable copy of everything here — the code, the
docs, the brand assets, the baked b-roll library, the two reference clips, and a
current `.skill` package. **It is a mirror, not the thing that runs**: the tool
runs from `\~/.claude/skills/WLAM-clip-cutter/`, and the mirror is refreshed with
`./sync.sh` inside it.

It also carries **`B-ROLL LIBRARY.html`** — one self-contained page showing every
clip in the library with a thumbnail, the word it answers and its licence, with a
filter box. `make-library-sheet.py` rebuilds it and `sync.sh` calls that. Looking
at that page is how the Trump portrait was caught being a monochrome art
photograph in a grid of forty official ones; a list of filenames would never have
shown it.

What the mirror deliberately leaves out: `broll-library/src/` (9.7GB of the raw
originals the bakes came from — re-downloadable, and only needed to re-bake) and
`work/` (per-show state, which belongs to a show and not to the skill).

## The b-roll connection run (2026-08-26)

The owner's brief, after the animation standard was signed off: *"The animation
side is done. It's about the connection now from the b roll to the words and how
long they're on there for and why they're on there."* And the second half:
*"every clip really makes sense from start to finish. There's an idea that starts
it and an idea that ends it ... and all the posting sheets are a lot more
optimal, clean, professional the way they're laid out."*

### Measure firing rate, not cohort size

**`vocabcheck.py` is the tool this run is built on, and it exists because the
first diagnosis was wrong.** The only number that was easy to get about EXPAND
was its SHAPE — 11,864 keys over 2,189 terms, and which terms serve the most
words. It is nearly useless: over the delivered corpus the correlation between a
term's cohort size and how often it wins a group is **r-squared 0.079**.

A whole diagnosis was built on cohort size and thrown away. It targeted `signing contract documents pen` (89 words), `courthouse columns` (61) and `copper ore mine` (52) — and across 76 authored slates **those three have delivered zero
inserts between them**, while `man thinking looking out window`, cohort of
twelve, fires more than all of them together.

```bash
python3 vocabcheck.py fires --top 30   # term, fires, cohort, inserts SHIPPED
python3 vocabcheck.py save base        # snapshot the winners
python3 vocabcheck.py diff base        # every group a code change displaced
```

`save` then `diff` is the harness this file's own rule has always needed —
*"adding a word is not free; test it against the phrase it lives in"* — and which
was previously done by reading. **Run it before and after any change to the
vocabulary or the rank key.** The sort key lives in `broll.\_rank\_key` and both
the renderer and the harness import it, because a copy would drift.

### What the ranking now says

The key is the show's editorial policy. As of this run:

```python
(query\_for(x) in used\_terms,      # not the same picture twice
 -(x.lower() in PEOPLE),          # a named human is the strongest subject
 -(" " in x),                     # then a specific multi-word subject
 -(x.lower() in EXPAND),          # then anything with a picture
 x.lower() in ABSTRACT,           # concrete before abstract
 -len(x))                         # last resort
```

Two of those moved. **A named person used to lose to any ordinary mapped noun** —
0 of the 133 PEOPLE keys are in EXPAND, so a person never cleared the
concreteness tier: "George Soros" lost to "Fund", "CoreWeave" to "earnings".
And **multi-word now outranks EXPAND membership**, which is the precondition for
growing the vocabulary at all: while EXPAND sat above specificity, every key
added made displacement worse — which is exactly what the eleven recorded phrase
regressions in the section above are.

Measured over the normal-case corpus: **79 displacements, 90% landing on a
multi-word term, 15 on a named person, zero moving away from a person.**

&#x20;   gold      -> Fort Knox           on "more gold than fort knox"
    crude     -> Texas Intermediate  on "what's the difference between WTI and Brent"
    SPR       -> Saudi Arabia        on "does saudi arabia need an spr"
    Facebook  -> data center         on "nobody wants a data center"
    hack      -> Salt Typhoon        on "your data is already there"


### Block capitals carry no case signal

`\_is\_entity` reads `core\[:1].isupper()`. On an all-caps transcript — a hearing
feed, a broadcast caption track — **every word passes**, so the entity path welded
adjacent pairs into two-word "names": INCLUDE MEETING, URBAN AFFAIRS, REPUBLICAN
COLLEAGUES. 48 of the 191 delivered caption files on this machine are all-caps,
and they produced 66,717 of 66,796 measured ranking displacements.

`caps\_blind(words)` reads the transcript once. When there is no case signal,
`\_is\_entity` stops guessing and only a name already in PEOPLE counts — because
that knowledge does not come from the case. **84,358 manufactured groups
disappear.** The genuine multi-word place names come back through the dictionary
route below, which is the right way to find them.

### A lowercase phrase can be a subject

`\_bigram\_is\_subject` used to consult only the five multi-word entries in
CONCRETE\_HINTS, so **41 of EXPAND's 44 multi-word keys were unreachable by
construction**. The owner's own example is the proof:

> \*"each of us will have our \*\*AI twin\*\*, whatever we're called. Everyone is
> \*\*building\*\* some version of that."\*

The subject is "AI twin". It is lowercase, so the entity path cannot see it; it
is two words, so the bigram path could not either. The anchor fell to the verb
`building` and the show cut to a programmer typing code.

`PHRASE\_SUBJECTS` now carries 34 phrases the show actually says, measured over
all 191 caption files: interest rates 3,036 times, credit card 1,896, health care
1,421, balance sheet 1,101, supply chain 756, artificial intelligence 654.
**Every value was checked against the index first** — 659 existing terms have no
baked asset and fall through to a live search whose ordering is unstable, so a
key pointing at nothing is worse than no key.

**`interest rates` is deliberately NOT a key.** It is the most spoken phrase in
the corpus and it is a number, not a photograph. Drop rather than force.

### How long a picture stays up

It was 3.7 seconds. All of them. `MIN\_HOLD` computes to exactly 3.7 and the
ceiling was `BROLL\_HOLD` 4.2, so **the legal band was half a second wide** and no
formula could express anything inside it: 72% of proposed inserts came out at
exactly 3.7, the whole set spanned 0.3s, and 16 of 17 clips held every picture
for the identical number of seconds. Duration correlated with how long the idea
ran at **r = -0.05**.

The formula asked the wrong question — `span\_end - t + 1.4`, where `span\_end` is
the last HIT TIME IN THE GROUP and the grouping window is 3.0s, so the
idea-derived term could only clear the floor when two hits sat 2.3s apart.

**It holds to the end of the sentence carrying the subject now.** In 19 of 25
archive cases the picture was still up after its own sentence had ended. The
ceiling moved to 4.6 — what the bake can carry, since assets bake at 4.7s — and
`hold\_ceiling()` divides by the tempo so a fast clip cannot run off the end of
its own asset onto tpad's frozen frame.

&#x20;   OLD  median 3.70  spread 0.00s  100% at the floor
    NEW  median 3.70  spread 0.90s   70% at the floor, 29% above it


preflight says when a clip's inserts are all identical — one line that would have
flagged 16 of 17 clips.

### The re-rank's lexical signals were overruling meaning

Two narrowings in `semantic.py`:

* **`phrase\_rescue` is proper nouns only.** It kept any hit sharing a two-word
phrase with the query, and on a lowercase term a shared bigram is not a name —
it is two ordinary words next to each other. It overrode the floor's whole-set
rejection in 14 of the 18 entries where the floor fired, on "shopping cart" and
"mountain trail". The Eccles Building case it was built for still works, because
a search term is not a sentence and a capital in one is always a name.
* **`named` is a tiebreak inside the score bucket, not a key above it.** A hit
that echoed the query while scoring below the floor used to outrank the only
on-topic hit.

### Both edges, checked against each other

preflight owned the in-point and the out-point separately and never asked whether
the thing promised at the top is still there at the bottom. Measured on 96
delivered clips: **39% never return to the hook's subject after the first third**,
and the subject is first spoken a median 10.8s into a clip whose card lives 3.0s.

The `ARC` line reports both. Like the `HOOK` line it is a **report, not a gate** —
on this archive no lexical statistic separates a landing from a trail-off well
enough to refuse on, and a gate that refuses good clips gets ignored.

### The posting sheet is in the poster's order

It was in the editor's order: rationale, then all four titles together, then the
raw transcript, then two caption boxes — nothing grouped by destination, and four
title slots served by only two caption bodies with nothing saying which. The
quote was 18% of a card's height and sat between the titles and the captions, so
the two things you paste were separated by the one thing you never paste.

One row per destination now, each carrying title + caption + hashtags behind one
**Copy post** button. The rationale and transcript fold into a Reference block.
The sheet also states, for the first time, **what the clip cuts away to** — the
trigger word, the picture and the hold.

Four things on it had never worked at all:

* `--rule` was used twice and declared nowhere, so the Titles dividers **have
never rendered on any of 62 sheets**
* no viewport meta on any of 587 sheets, so the phone breakpoint never matched
once and a 375px device got a scaled 980px desktop page
* no `@media print`, so cards split mid-title and a dark-toggled sheet printed
solid black
* the Tickers box rendered on `tickers` OR `onscreen`, so 51 of 62 sheets shipped
an empty box whose Copy wrote `""` and still flashed "Copied"

And the largest type on the page was a raw download filename — *"One clip from
master"* four times across the archive. `show` and `date` in project.json now
carry the headline; `analyze.py` seeds both.

## The things that are not negotiable

> \*\*THE OWNER MADE THESE EXPLICIT ON 2026-08-25\*\*, pointing at the Kim Ann Curtin
> clip as the reference: \*"that needs to be uploaded into the WLAM clip cutter
> skill as a non-negotiable, that all of these things happen."\* They are not
> preferences and they are not subject to a per-clip judgement call. If a clip
> cannot satisfy one of them, the clip is wrong — pick a different span.

**1. EVERY CLIP CARRIES THE WHITE BOX WITH THE SPEAKER'S NAME.** Not most clips,
not the ones where a rung happens to fit. *"Every clip needs to have the white
box, and then their name comes on there. That's great. Like Kim Ann Curtin, the
most recent one. That's great."* The title card leaves, the nameplate arrives —
in that order, on every mode. A clip whose `speaker` is unset or is a lowercase
tile tag ships with nobody named, which is a **defect to fix in the slate**, not
an acceptable outcome. `preflight`'s NAMED line tells you which it is before you
render.

>
> \*\*ENFORCED SINCE 2026-08-25.\*\* This was a WARN until the audit, and all four
> exits of the check returned True — so the non-negotiable was unenforceable by
> construction and an unnamed clip shipped on a green ALL CLEAR. preflight now
> REFUSES, and `build\_all` will not render. The escape is explicit and logged:
> `"allow\_unnamed": true` on the clip, for the montage or cold open the old
> wording worried about.

**2. A CLIP NEVER CUTS OFF MID-SENTENCE.** *"They don't cut them off at the end of
the sentence. Every sentence makes sense — the way it starts, the way it
finishes."* Both ends: it opens on the first word of a sentence and it lands on
the last word of one. `plan\_ending` runs a clip on to finish a sentence and
`preflight`'s ENDING and EDGES lines report both edges — read them. A ragged end
requires `"allow\_ragged\_end": true`, which is a deliberate, logged override and
should be close to never.

>
> \*\*THE OPENING EDGE IS NOW CHECKED TOO, and it never was.\*\* plan\_ending has
> always moved the out-point onto a full stop; the in-point had nothing behind
> it at all, so a clip could open on the back half of somebody else's sentence
> and preflight printed ALL CLEAR. `check\_opening\_edge` decodes the 4s BEFORE
> `start` and asks what the previous word was.
>
> It is CALIBRATED, not strict: a full stop passes, a comma/semicolon/colon/dash
> passes as a clause boundary, and a pause of 0.60s+ passes as a boundary
> whisper failed to punctuate. Only coming in mid-CLAUSE — no terminal
> punctuation at all AND no pause — refuses. That line matters: 01-tariffs comes
> in after "...a strategic direction on their part," and opens on "The reason
> why these tariffs really don't take effect until Labor Day", which is a clean
> opening clause. Refusing that would get `"allow\_ragged\_start": true` pasted
> onto every slate, and then the gate is worth nothing.

**3. EVERY CLIP IS ONE COMPLETE IDEA.** *"There's a logical idea behind every
clip. Every clip makes sense."* Not a striking sentence with its setup missing,
and not two half-thoughts joined because the span was the right length. The test
is whether somebody who has not seen the show understands the whole point from
the clip alone. If the argument needs a sentence you cut, put the sentence back
or pick a different moment.

**4. EVERY CLIP RUNS A MINUTE TO A MINUTE THIRTY.** Added 2026-08-28: *"every
clip has to be minimum a minute to a minute thirty."* `MIN\_CLIP` is 60 and
refuses; `CLIP\_BAND` is (60, 90) and reports. See "Length" above for what the
raise costs — 71 of the 96 delivered clips are under it, so any re-cut of an
older show will stop on LENGTH, and the fix is to widen the span.

**5. THE PICTURE IS CORRECT FOR THE WORD, AND NEVER A RELIGIOUS SYMBOL FOR A
SECULAR ONE.** Added 2026-08-28: *"make sure the vocab is correct on all the
different captions because we messed up. You put, like, a religious symbol for
mystery — you can't have that."* `SACRED\_WORDS` enforces it on the picture and an
import-time lint enforces it on the vocabulary. See "A RELIGIOUS PICTURE MAY ONLY
ANSWER A RELIGIOUS WORD".

**6. THE HEAD IS WELL PLACED IN EVERY FORMAT.** Added 2026-08-28: *"we need to
make sure that the head placement of all the people in all different formats is
correct."* preflight's HEADROOM line measures where the face lands in the
delivered panel and REFUSES a chin below the platform chrome. On a two-up where
the floor moves, `head\_follow` is the mode that satisfies this; `duo` structurally
cannot keep the lower speaker's mouth above the chrome line.

**7. THERE ARE THREE TEMPLATES, AND TWO PEOPLE ARE NEVER ON SCREEN AT ONCE.**
Added 2026-08-28: *"it should always be one person talking at one time... they'll
never be cut side by side."* `head`, `conversation`, `conversation\_share` — and
all three always carry b-roll. `duo` and `duo\_share` are retired and refused.
See "THE THREE TEMPLATES" above.

**8. WHOEVER IS SPEAKING IS THE ONLY PERSON ON SCREEN, AND YOU PROVE IT BY
LOOKING.** The owner, 2026-08-28, after watching a clip that got it wrong:

> \*"Whoever is speaking, you need to understand that's who you need to cut to...
> You gotta understand who is talking at all times. Make sure whoever's speaking,
> their mouth is open in the stream — that is who's on the screen. Never the
> opposite."\*

That is the acceptance test for every conversation clip and it is settled by
**pulling frames and looking at whose mouth is open**, never by a summary
statistic. See "Who is talking" for how the schedule is built and "A MEASUREMENT
THAT WAS WRONG" for what happens when you trust a ratio over your eyes.

**9. THE MOTION STANDARD OF 2026-08-25 IS COMMITTED.** Title card, then the
nameplate cross-fading in and out; the invitation breathing while it rests and
mirroring itself on the way out; the cutaway cross-dissolving with a drift that
varies per insert. *"The animations in between the clips are very good."* See
"The 2026-08-25 standard" above. Do not re-derive any of it from a reference
measurement — every element in it has been through three rounds of owner
verdicts.

**The speaker's face is on screen at all times, with ONE written exception.**

The exception is a b-roll cutaway: the picture leaves the speaker entirely for
about two seconds and comes back. It was granted deliberately on 2026-08-11, and
it is bounded so it stays an exception rather than becoming the format. Never
more than 30% of the body, never in the first 5 seconds or the last 3.

`BROLL\_HOLD` is **4.0** and `BROLL\_HOLD\_MIN` **3.0**. It is the TOP of a range
now rather than THE hold: `propose` picks per insert with
`min(MAX\_HOLD, max(MIN\_HOLD, clause\_end - t + 1.4))`, so a picture is held to a
bit past the end of the clause it illustrates and a real slate comes out at 3.0
to 4.0.

**IT WENT TO 2.6 FOR ONE AFTERNOON AND THE OWNER SENT IT BACK.** 2.6 came from
measuring his reference, whose cutaways run 1.60 to 2.40s, mean 1.91. He watched
a clip cut to it: *"i feel like the broll is to short and its to fast it needs to
be min 3 seconds so it doesnt feel rushed. cuz the broll + signup feels very
rushed."*

He is right and the reason is structural: **the reference does not carry an
invitation button inside its cutaways and ours does.** A 2.0s cutaway has to land
a picture, bring a button up, hold it long enough to read, take it away and cut
back - five beats in two seconds, which is a cram however clean each individual
cut is. The reference's holds are correct for a reference that only has to show a
picture. **Do not "correct" this back toward 1.9s on the grounds that the
measurement says so.** The measurement was of a clip with less to do.

Note also what the floor MEANS now the travel is zero: it is the whole insert,
not what is left after a rise and a swipe. A 3.0s insert is 3.0s of settled
picture, where under the slide it would have been 2.37s. Three seconds is a
number he has now landed on twice, unprompted.

**The two numbers moved together with `BROLL\_EVERY`, and what stays constant is
the SHARE of the body.** See "ONE cutaway per 14 seconds" below. And it is only
affordable because the transition became a cut: under the slide, 0.633s of every
window was travel, so a 3.6s hold would have settled for 2.97s - under the 3.0s
floor by a hair, and a 3.0s hold would have settled for 2.37s. With `BROLL\_IN` = `BROLL\_OUT` = 0 the whole hold
is settled picture. **Put `broll\_style` back to "slide" and these numbers are
wrong; they are a matched set.** Everything
else on screen keeps running underneath: the captions, the hook and the address do
not blink out because the picture changed, because the words are the product.

The reference clip sits at 22% of its body, well inside the 30%, so the density
below is not the exception pressing against its own ceiling. It is the same
exception taken more often on a longer clip.

The numbers live in ONE place, `WLAMclip.BROLL\_\*`, and broll.py and preflight.py
import them. They used to be duplicated, and the duplicates disagreed: `hold`
defaulted to 2.6 at bake time and 4.0 at render, so an insert authored without one
baked 2.6 seconds of picture and was played for 4.0, the last 1.4 a frozen frame
that nothing reported. A stale `MAX\_FRAC = 0.14` also sat in broll.py, unread by
anything, and this paragraph quoted it for months while the live ceiling was 0.30.

**EVERY clip ships with at least one b-roll insert, in EVERY mode, and THE
PICTURE LANDS ON THE WORD.** Both rules are the user's (2026-08-12), and the
second superseded an earlier end-of-clip placement the same day: he watched
"SpaceX" spoken at +35 with the rocket arriving at +52 and said the wording has
to be connected to the picture. A clip with no insert is not finished -
`check\_broll` fails it in preflight - and an insert that is not on its word is
decoration, not illustration.

How the sync actually holds, because it took three bugs to get there: the slate
stores each insert's WORD ("on") and its approximate source time; the renderer
then RE-SNAPS the insert onto that word in its own decode - the same word list
the captions are built from - and leads it by 0.15s so the picture is up as the
word lands. Do not trust the stored time alone: propose and render each run their
own whisper pass, and the two decodes disagreed by 1.56s on a real word -
"exploded" at 41.24s in the render's pass and 42.8s in propose's. So the re-snap
window is 2.5s, not 1.5: a window tighter than the disagreement silently skips
the snap and re-ships the exact lateness it exists to kill, and 2.5s is still far
inside the spacing of a repeated word (the other "explode" in that clip is 7s
away). Both numbers were measured, not imagined.

**ONE cutaway per 14 seconds of delivered body, 3.0 to 4.0 seconds each.** The
count is DERIVED, not fixed: `WLAMclip.broll\_target(body)` returns the target and
both broll.py and preflight.py ask it rather than carrying a number.
`BROLL\_EVERY` was 14.0 when this was written and is **10.0 since 2026-08-30**;
ask `broll\_target(body)` rather than reading a number off this page, because it
also divides by `BROLL\_HOLD` and both have moved. At the current settings a 45s
body wants 4, 59s wants 6, 91s wants 9 and 120s wants 12.

**AND AT 14.0 THE 30% CEILING IS LOAD-BEARING, WHICH IT WAS NOT AT 18.0.** The
scan recorded further down this file fixed the threshold at `BROLL\_EVERY` 15.95
and concluded "Do not read the 30% ceiling as protecting anything at the cadence
we actually run." 14.0 is BELOW that. Re-measured over every body from 41.0s to
200.0s in tenths, `ceiling` truncates the raw target on **166 of 1591** - about
one length in ten, and they are lengths the house ships in (50s, 63s, 80s, 91s,
120s). Priced at `BROLL\_HOLD`, the target costs **22.6% to 30.0%** of the body,
hitting exactly 30.0% at 53.4s and at 80.0s.

That is the ceiling doing its job rather than a fault - at 14.0 and a 4.0s hold
the raw target really would ask for more than 30% on those lengths. But it means
two things are now true that were not this morning: the count on a 53s body is
decided by the ceiling and not by `BROLL\_EVERY`, and `render()`'s hard raise sits
within hundredths of a second of firing. `render()` therefore carries one frame
of tolerance, because preflight scores this against its PREDICTED body and
render against the MEASURED one, and this file already records those two
differing by 0.3s on a real clip. A montage overshoots by seconds; a frame
cannot hide one.

**18.0 -> 11.0 -> 14.0 on 2026-08-25, and `BROLL\_HOLD` 4.2 -> 2.6 -> 4.0 in the
same moves, because the pair is what holds the share constant.** The owner asked for "more
transitions" and his reference (`gaRRMkRjoHE`, see the cutaway transition
section) spends 22.1% of its runtime on b-roll against our 22.0% - the same
budget in six pieces rather than three. On the 57.3s body of the 08.25 test
clip:

&#x20;   original 3 inserts x 4.2s = 12.6s = 22.0% of body, one every 19.1s
    08.25 a   5 inserts x 2.6s = 13.0s = 22.7% of body, one every 11.5s (too fast)
    08.25 b   4 inserts x 3.6s = 14.4s = 25.4% of body, one every 14.2s <- ships


**Going to a cut is what UNLOCKED the higher count.** Measured on that body:
under the old constants the maximum legal count was **4**, not 5 - five inserts
needed `3.0 + travel <= 3.438`, i.e. `travel <= 0.438s` against the slide's
0.633s, so it was impossible at any legal hold. With the travel at zero the
maximum is 6 and the target of 5 is comfortable.

**`BROLL\_MIN\_FACE` (6.0s) is now the term that caps the count, not the budget.**
On the 08.25 clip the arithmetic allows 6 and the material allowed 5, because an
insert has to land on the word its picture was chosen for and the concrete
subjects only fall in so many places. The reference's own face gaps run 2.47 /
3.00 / 3.20 / 10.80 / 11.37s, so three of five are under our floor - there is a
case for lowering it, and it has NOT been made. It is the rule that stops a set
of cutaways reading as a montage and it should move on its own evidence.

**And more cutaways can mean FEWER picture changes, which is a real cliff.** The
punch ladder resets its dwell at every cutaway return, so a face gap G yields a
framing flip only if `G > PUNCH\_FREEZE + PUNCH\_RUNG\_KEY` = 8.0s. Measured on
this body: 5 inserts leaves G = 8.94s and keeps 4 free flips, for 14 designed
changes; 6 inserts drops G to 6.64s, the flips **collapse to 1**, and the total
falls to 13. Five is the optimum here and it is not the maximum.

**Where 18 comes from.** One clip, cut on 2026-08-21 from the Mike McGlone /
Bloomberg Intelligence master, which the owner watched and ruled on: "that clip
was literal perfect, that flow, the amount of B-roll, should now be the standard."
Measured off the delivered file: 95.3s total, a 91.3s body and a 4.0s end card.
Preflight PREDICTS 91.0s and 95.0s for that same clip, because that is what its
arithmetic yields BEFORE the render: a 93.51s span less 2.50s of collapsed
silence, `speed` unset. The 0.3s is a prediction sitting next to a measurement,
not two files disagreeing, so do not chase it in code - making preflight print
91.3 would mean making it lie about its own arithmetic. The delivered file carries
5 inserts at 4.0s each, 20.0s of cutaway, 22% of the body, one every 18 seconds
(the cadence of the day — there is no single band now, and it is one per 6s),
and no gap under 6s from the end of one insert to the start of the next. It ran
1:35 because the owner asked for a 1:30 minimum, and the only thing carrying that
length is the cutaway cadence. At the old two-to-three the same 91.3s sat on
one unchanging chart for 30 seconds at a stretch.

**The rounding is load-bearing.** The target is `math.floor(body / BROLL\_EVERY + 0.5)`, not `round()`. 45 / 18 is exactly 2.5, Python's `round()` is banker's
rounding and returns 2, and 45 -> 3 is the one case the new rule has to reproduce
from the old one. `round()` would have broken it silently.

**What preflight does with the target.** It FAILS below
`max(BROLL\_MIN\_INSERTS, target - 1)`, WARNS below the target while naming both the
target and the body length, and FAILS above the ceiling, because more than one over
reads as a montage. **The ceiling is a bare `target + 1`.** The count check owns
the EDITORIAL cap and nothing else; the SHARE of the body is owned by exactly one
other line, the FRAC check at the bottom of `check\_broll`, which sums the slate's
REAL holds.

That split is recent and it replaced a ceiling of `min(target + 1, int(BROLL\_MAX\_FRAC \* body / BROLL\_HOLD))`. The frac term was deleted because it
priced every insert at `BROLL\_HOLD` 4.0 while real slates hold 3.0: counted over
every slate.json on the Desktop, 74 approved inserts across 23 clips, the median
hold is 3.0s, the mean 3.11s, and 53 of the 74 are 3.0s or shorter. So a 45.0s
body carrying four 3.0s inserts is 12.0s of picture, 26.7% of the body, every hold
inside the settled-time window preflight enforced AT THE TIME (a 3.0s hold fails
it today: travel is 0.633s now, so the raw window is 3.63..4.20) - and the count
check FAILED
it while the FRAC line PASSED it, quoting a 30% derivation it had never performed
on the slate's real holds. Two derivations of one quantity from different inputs
is what produced BOTH that contradiction and the mirror-image one the frac term
had been added to fix, so the fix is one owner each rather than a third attempt at
making the two agree.

The case the frac term was reading is still caught, by the line that owns it: a
45.0s body with four inserts at a full 4.2s is 16.8s, 37.3% of the body, and that
slate now prints count OK and FRAC FAIL, which a re-run confirms prints as 37%.
The FRAC line catches it on its own, off the real holds, which is the point.

`BROLL\_MIN\_INSERTS` is still the absolute floor of 2, and
a clip with one cutaway is still refused outright. There is no `BROLL\_MAX\_INSERTS`
in any script now and no default of 3: the only cap left is an optional
`project.json` key, `broll\_max\_inserts`, read once into `WLAMclip.BROLL\_MAX\_CFG`,
and it can only pull the target DOWN. It cannot pull it below `BROLL\_MIN\_INSERTS`
either - a cap of 0 or 1 is clamped up to the floor, because `0` read as unset
for a while and a project asking for no cutaways at all silently got no cap.
`BROLL\_BIG\_BODY` is gone: there is no 45 second step to hard-code any more, the
step falls out of the arithmetic.

Two other terms sit inside `broll\_target` and neither of them binds at 18.0: the
30% ceiling, and a feasibility check that lays the inserts out against
`BROLL\_LEAD\_IN`, `BROLL\_MIN\_FACE` and `BROLL\_TAIL\_CLEAR`. Scanning every body from
1s to 300s in tenths, the full expression never disagrees with plain
`max(2, floor(body / 18 + 0.5))`. They are insurance, not guards. On that same
scan the first one to bite is the 30% ceiling at `BROLL\_EVERY` 15.95, where a
39.9s body asks for 3 and the ceiling allows 2; at 15.96 and anything above it,
nothing bites at all. Over the bodies we actually ship, 41s and up, they stay
dormant down to 15.23. 13.3s is the asymptotic crossover, `BROLL\_HOLD` over
`BROLL\_MAX\_FRAC`, and because the ceiling truncates with `int()` the real first
bite sits well above it - do not quote 13.3 as the threshold. It is also not the
13s in `broll\_target`'s own comment, which is about BODIES rather than about
`BROLL\_EVERY` and is correct as written. Do not read the 30% ceiling as
protecting anything at the cadence we actually run.

**Retro-compatibility, stated exactly, and it is not free.** The derivation
reproduces the old two-tier rule over bodies of 45.0s to 62.9s, which is where most
of the archive lives; at exactly 63.0s the target steps to 4 and the reproduction
stops, so do not quote the band as "45 to 63". Every delivered clip was
re-measured against it, ffprobe on the shipped mp4 minus the 4.0s end card and NOT
the authored span. The span is always LONGER than the body, because the removals
come out of it, so the body is a FRACTION of the span and never the other way
round: re-measured over all 42 clips that fraction runs 0.632 (a 133.0s span
carrying an 84.1s body, "this-is-yield-curve-control" on 08.19.26) to 0.980, and
0.632 to 0.977 over just the 22 b-roll clips. Scoring off the span would have
inflated every target, in the worst case by more than half. Across the 42
delivered clips under `COMPLETED WLAM PROJS/WLAM Viral Clips/Quasar Markets Live \*`,
22 NAME an asset in the slate for at least one approved insert. That is a count of
slates, not of files: only 21 of the 22 still have any of those assets in
`broll-library`, and the 08.12.26 Patrick Bell clip
"we-need-to-fail-intelligently" names four and has lost all four, so preflight's
own missing-asset test would FAIL it today. The slate is the record for this
measurement; the library is not. Five of those score exactly on
target (46.2s/3, 47.8s/3, 52.0s/3, 90.8s/5, 91.3s/5), six sit in the WARN band,
five sit one over the target, and none is more than one over, so nothing in the
archive fails the ceiling.

Twenty-six of the 42 clips fall under the new FAIL floor of
`max(2, target - 1)`, and 23 of them were already failing the old flat floor of 2
(20 with no inserts at all, 3 with a single one, at bodies of 42.8s, 49.9s and
59.7s), so the derivation did not do that. The two counts are not interchangeable
and were welded together here for a while: 23 is the number that failed the old
floor, 20 is the number carrying nothing. **Name the population whenever you quote
26 and 23**, because preflight's comment on the same subject says six and three.
Both are re-measured and both are right: 26 and 23 score ALL 42 delivered clips in
this population, while 6 and 3 score only the 22 of them that carry at least one
insert. Two files opening a sentence "in the archive" over different populations
is the whole confusion. **Three clips are newly failed by this change:**
a 71.8s body with 2 inserts (target 4), an 84.1s body with 2 (target 5), and an
89.5s body with 3 (target 5). All three are long clips that shipped with the old
cap of three cutaways, and that is precisely the defect this rule exists to catch:
89.5s carrying three inserts is one picture change every 30 seconds of body, and
84.1s carrying two is one every 42, which is the cadence the owner ruled against
on 2026-08-21 in the first place. The rule does not get softened to make the
archive look better. Those clips are posted and finished and are never re-run; the
FAIL line names the body and the target so it reads as a re-scored old clip, not a
bad one.

**And the other half of the trade, which the paragraph above used to leave out:
SEVEN clips are newly PASSED.** 57.9s/4, 88.6s/6, 89.8s/6, 90.8s/5, 91.3s/5,
95.1s/6 and 95.4s/6 all carry more than three inserts, all of them broke the old
flat cap of 3, and every one sits inside the new ceiling of `target + 1`. So the
archive-wide score of this change is three newly failed against seven newly
passed, and stating only the three reads as a rule that costs and never pays.
Widening the population does not move it either: across all **78** delivered
clips under `\~/Desktop/COMPLETED WLAM PROJS`, **62** fall under the new floor and
**56** carry no `broll` key at all, because they predate b-roll entirely.

**State the method with the figures, because three people measured this and got
three answers.** These are: glob `\*\*/slate.json` under that tree, match each
clip's `slug` to an `.mp4` sitting in ANY `clips/` directory anywhere beneath it,
take the body as the file duration less the 4.0s end card, and count an insert
only when it is `approved` AND carries an `asset`. Every disagreement was in the
matching step, not the arithmetic - the under-floor and no-key figures came back
62 and 56 every time, while the delivered count moved between 76 and 79 purely on
how hard the lookup tried to find an mp4 in a sibling directory. Two traps are
worth naming. `COMPLETED WLAM PROJS/WLAM Viral Clips/tools/slate.json` holds ten
clips and sits in a `tools/` directory rather than a `\_project/` one, so a
`\*\*/\_project/slate.json` glob walks straight past all ten. And one slate entry,
"if-youre-trading-for-free-youre-the-product", has no delivered file at all, so a
count of slate entries is one higher than a count of delivered clips.

The conclusion is unchanged by any of it, and slightly stronger than the version
that read 66 / 50 / 44: most of the archive predates b-roll entirely, so the
floor is scoring shows that had no cutaways to score.

**The subjects form a CHAIN, not a loop.** Adjacent nouns still group into ONE
picture ("Elon Musk... SpaceX... rocket" is one subject), each insert is anchored
on the word its picture was chosen for, and no subject is used twice. The
reference clip ran a working pumpjack in a dusty field, onshore production ("oil
pump jack working in field"), to jack-up rigs silhouetted at sunset, production at
sea ("oil drilling rig at sunset"), to the red hull of a loaded crude tanker,
transport ("crude oil tanker ship"), to a pan across a gas plant, pipe and turbine
stacks, refining ("natural gas pipeline through landscape" - the term says
pipeline, the picture is a processing plant, and the picture is what the viewer
judges), to an aerial over a frosted valley, winter demand ("snow covered winter
landscape"), landing on oil, Kuwait, supply, products and winter. Five
links of one story, and a repeat of any one of them would have read as a loop. At
two inserts a loop is hard to hit by accident; at five it is the default failure,
which is why the chain is written down rather than left implied.

**Written down on 2026-08-11 and enforced by nothing until 2026-08-23.** `propose`
de-dupes on the TERM (`used\_terms`), which is a DIFFERENT test, and the library is
what makes the difference expensive: 114 index rows (105 live) resolve to **83
distinct pictures**, 19 of them reachable from two or more live rows and TEN under
two or more live TERMS. One supermarket clip answers to four terms that barely
share a word - "retail shopping supermarket aisle", "supermarket aisle shopper
cart", "shopping mall crowd shoppers", "grocery store shopping cart aisle" - so a
three-link chain asking three different words could be served that one piece of
footage three times and pass every other line in `check\_broll`. It gets worse as
the vocabulary loop compounds, because every approval adds another word pointing
at a picture that already exists.

`check\_broll` now FAILS a repeat, naming both terms and the picture's own title;
the fix is to retype one term and re-run `propose`. **The identity is the
PHOTOGRAPH, not the bake and not the source file** - a union-find over `page` and
`src`, the same widening `retire` already does. Keying on `src` alone was the
first attempt and a DELIVERED clip had already fallen through it:
`it-acts-before-you-feel-it` carries "hospital emergency equipment" and "heart
monitor ecg hospital", two downloads of one Pexels video under two src filenames -
same page, same title, byte-identical frame hash at t=1s. That clip shipped the
same picture twice. It is posted and finished; it is not re-cut. Scored across
every slate on this machine - 32 clips, 99 inserts - it is the only collision, so
the hard FAIL costs nothing on real work.

**Five links need a findable subject, and not every show has one.** The 2026-08-18
survey below scores oil at 0.62 findable and the Fed at 0.48, so a five-link oil
chain is exactly what the free libraries can carry and a five-link Fed chain is
not. On an institutional segment the derived target will regularly ask for more
subjects than the vocabulary can supply. That is what the WARN band is for. Take
the warning, add what the material honestly supports, and do not pad the chain
with a second picture of the same thing to reach a number.

Spacing is measured END-to-START, not anchor-to-anchor. The old rule was 5s
between anchors, which with a 4s hold leaves ONE second of face between two
cutaways - the montage the rule exists to prevent. `BROLL\_MIN\_FACE` is 6s of
speaker between the end of one insert and the start of the next, and the reference
clip never came under it. It is also the term that would cap density before the
count does: each insert costs 4.2s of picture plus 6.0s of face, so a body only
buys a cutaway every 10.2 seconds at the absolute limit. Running at 18 leaves that
limit a long way off, which is the point. The target is a rhythm, not a maximum.

**And until 2026-08-23 that 6s lived only in `propose`.** It is word for word the
hole the lead-in check beside it was already written for - propose respects the
number, a hand-edited `at` never had to - and the fix was applied to the lead-in
and not to the spacing sitting next to it, so two inserts authored two seconds
apart passed every line in `check\_broll`. It is a FAIL there now, on the DELIVERED
timeline: `at` is remapped through the removals and divided by the tempo, and a
slate's `hold` is already what the viewer sees (`broll\_chain` scales it by the
tempo on the way INTO the pre-tempo composite), so both sides of the subtraction
are in the same units. Two inserts that overlap once the silence is removed get
their own message rather than a negative quantity of face time.

**Fixing that exposed a real disagreement, and `propose` was the wrong side.** It
placed inserts in PRE-TEMPO seconds - `to\_clip` stopped at `remap\_time` - while
enforcing LEAD\_IN and TAIL\_CLEAR against the SOURCE span, and it derived its
insert target from `delivered\_body(dur, rem, clip.get("speed"))`, the slate
OVERRIDE, which is None on every clip since 08.12.26 and so divided by 1.0 while
the render applies the adaptive tempo. Left alone, preflight would have FAILED the
slate propose had just produced on any clip with a tempo, and re-running propose
would emit identical numbers: a gate with no key. `candidates()` now computes
`q.tempo\_for` once and uses it for the body AND the placement, so both files read
the delivered timeline. The stored `at` is untouched - it is still the word's own
SOURCE timestamp, which is what keeps the picture on the word.

Assets bake ONCE, at `BAKE\_HOLD`, which is 4.7s and not 4.2s. `BAKE\_HOLD` is
`round(BROLL\_HOLD \* SPEED\_MAX + 0.02, 1)`, and that factor is not decoration: the
insert is composited PRE-tempo, so 4.2 DELIVERED seconds needs 4.704 source seconds
at the fastest tempo the pipeline will apply. **MOVE `BROLL\_HOLD` AND THIS MOVES
WITH IT, LEAVING EVERY ASSET ALREADY ON DISK SHORT THE SAME AFTERNOON.** That is
what 4.0 -> 4.2 did on 2026-08-22, and nobody noticed until 2026-08-23, when 97 of
the 105 live bakes measured under the new 4.7s floor - 75 sitting at the old 4.5,
13 at 4.0, and nine at 3.4s or less left over from the retired hold-in-the-filename
scheme. `broll.py sweep` is the migration, and it is the reason that command
exists.

**`sweep` is deliberately not destructive, and re-baking is the repair rather
than retiring.** `retire` means "this picture was wrong": it deletes the bake,
marks the row and takes the pairing out of the vocabulary. A stale LENGTH says
nothing about whether the picture was right, so auto-retiring would silently
delete learned anchors a human approved by eye. `sweep` re-bakes what it can and
only REPORTS what it cannot, printing the `retire` line to run with the real
reason quoted back. Report mode is the default; `--apply` is the half that writes.

Four things it does that are worth knowing, all of them written after a review
broke the first version:

* **The fps comes out of the BAKE NAME, never from `project.json`.** The trailing
`-<fps>` IS the cache key - it is why `fetch` writes `-{fps}.mp4` and why a
25fps show creates its own files instead of touching a 30fps show's. Re-baking
at the current project's `src\_fps` would rewrite a `-30` asset at 25fps on a
SHARED library, and nothing downstream would catch it: both existing guards
measure only duration, and the overlay chain has no `fps=` filter, so the insert
would judder over every 30fps render from then on.
* **It bakes to a temp name and only replaces on success.** This is the half that
overwrites the only copy. A truncated source silently replaced a working 4.5s
asset with 0.17s in testing, and nothing checked the result. It now verifies the
new file reaches `BAKE\_HOLD` before `os.replace`, and otherwise leaves the old
one alone and reports that the SOURCE is the problem.
* **A bake ffprobe cannot read gets its own bucket, not a `continue`.** That is
exactly the state a failed re-bake leaves behind, and the first version reported
it as healthy on the next run.
* **Live rows whose bake is missing from disk are named.** There are five in the
shipped library. They are served to `search` and cannot be played, and they are
not re-bakeable from a src alone because their names carry no fps token.

It also lists source files no live index row references - rejected picks and
retired pictures, 151 MB of them today, including the price-wall asset retired
after 08.18 and both 1.2s refinery flames. It never deletes them; that stays a
decision you make. The hold is also no longer part of the baked filename. It used
to be, and the consequence was silent: raising `hold` in a slate after fetch never
re-baked anything, so the renderer got the short clip and clone-padded the
difference as a still. `fetch` now re-bakes anything shorter than `BAKE\_HOLD`
(`\_short\_bake`, with a 0.05s rounding allowance), so lifting the whole library to
a new length is one re-run.

**A source shorter than the hold is now rejected before it is downloaded.** No
amount of baking makes a short clip long; the renderer clone-pads it and the rest
of the hold is a frozen frame. On 2026-08-21 the best oil picture the search
returned was "vertical video of flame from oil refinery tower", and its Pexels
source is 1.2 SECONDS. It was downloaded, baked, and re-baked five times under
five different terms before preflight said "is 1.2s but the slate holds it 4.0s -
the rest would be a frozen frame". The duration was in the search result the whole
time: broll.py records `dur` on every Pexels video hit and never looked at it,
while the Pixabay branch had been dropping anything under 4 seconds for months.
Both branches now apply the same floor, through the one function `\_long\_enough`,
so the number has one owner instead of a literal in one function and nothing in
the other. **THE FLOOR IS `BAKE\_HOLD`, NOT `BROLL\_HOLD` AND NOT `BROLL\_HOLD\_MIN`**,
which is 4.7s, the same 4.7s the paragraph above bakes every asset at. A floor of
`BROLL\_HOLD\_MIN` (3.0) reads like the minimum hold and is a hole: it ADMITS a 3.0s
to 3.99s source, which downloads, bakes SHORT, and then hard-fails preflight with
the very "the rest would be a frozen frame" message the test exists to prevent.
Pixabay's old literal 4 was nearer the truth than that. This paragraph said
`BROLL\_HOLD\_MIN` for a while and described the exact hole the floor closes, which
is the stale-number trap this file confesses to further up, recreated inside the
file that confesses to it. A hit that reports NO duration is still not a reject:
Pexels omits the field on some entries, stills have none at all, and a still bakes
to any length. Preflight's ffprobe check on the BAKED file stays as the second
line of defence for that case. **The LIBRARY tier is no longer part of that
exemption.** It used to be waved through as carrying no duration by construction,
and that was a hole: it serves the ORIGINAL src rather than the bake, so a clip
too short to cover a hold could be offered from the library after being refused
everywhere else, masked today only by the two sub-4.7s srcs in there being
retired. `search\_library` now ffprobes its own local file - cheap, because the
file is local, and cached back into the index row - and applies the same floor as
every other video source.

**The floor is deliberately strict, and the strictness costs something.** Pexels
and Pixabay report duration in WHOLE SECONDS, so `d >= BAKE\_HOLD` is in practice
`d >= 5`, and a true 4.8s clip reported as 4 is refused although it would have
baked fine. That is the safe direction to be wrong in: a short bake is a hard
preflight failure and a lost render, while over-strictness costs one search
result, and findability did not bite on 08.21.26 - all five McGlone subjects were
found. If it ever does bite, the available loosening is `d + 0.999 >= BAKE\_HOLD`,
which admits the truncation and also admits a genuine 4.0s clip that will bake
0.7s short. Written down so nobody re-derives it from scratch, and so
nobody loosens it without knowing what it buys back.

**THE SEARCH TERM IS THE PRODUCT OF A VOCABULARY, AND THE VOCABULARY IS THE
LEVER.** `EXPAND` maps a spoken word to a PHYSICAL picture, and a word with no
mapping can never be proposed at all. On 2026-08-18 a survey of 24 recurring WLAM
subjects (424 candidates, scored against sentences the host really said) found
that planes, airports, trillions, groceries, freight, gigawatts, bonds and yields
all returned "not concrete" - which is why a show about airports and trillions
kept producing one insert about "data". Fifty-eight entries were added, each
checked against the free libraries first.

The same survey found the shape of what is out there, and it is worth knowing
before you write a term. The free libraries are strong on the PHYSICAL WORLD and
empty on INSTITUTIONS:

&#x20;   findable       airports 0.72 | crypto 0.68 | black friday 0.67 | gold 0.66
                   consumer 0.66 | the dollar 0.66 | the grid 0.63 | oil 0.62
    not findable   the Fed 0.48 (best hit: a MILITARY press conference)
                   Washington 0.49 (a Budapest street, the Hungarian parliament)
                   Wall Street 0.53 | inflation 0.53 | chips 0.53 | recession 0.52


A markets show says Fed, bonds, Washington and Wall Street constantly, and those
are the four Pexels does not have. NAME THE BUILDING instead and Wikimedia
answers: "US Federal Reserve Eccles Building", "US Treasury Department Building
Washington", "United States Capitol building exterior" all return real
photographs. That is what the institutional EXPAND entries do.

**Two guards on the term, and both were written after a real failure.**

`COMPLIANCE\_WORDS` is unconditional - no query can switch it off. `\_rejected`
used to skip a banned word when the QUERY contained it, so the term "global stock
market world map digital" disabled the rule that blocks price walls, and a
full-frame wall of live red and green quotes shipped in a delivered clip on
2026-08-18. The junk half keeps the escape (so "vintage television set" can still
return titles saying vintage); the price-display half does not. An import-time
lint refuses to load if any EXPAND value contains a blocked word - a mapping like
that is a dead word, silently unsearchable, and it caught four the day it landed.

Matching is by WORD, never substring, in both directions. The lint really does run
at import now - for a while it sat below the `\_\_main\_\_` guard, so on the CLI it
fired after `propose` and `fetch` had already finished. Bare substring matching
was deleting good results: "graph" inside "photograph", "chart" inside "charter
flight", "doll" inside "dollar".

**THE LIBRARY TEACHES THE TOOL. `learned\_vocab()` is the loop.**

Every fetched insert records the WORD it was anchored to (`on`) and the term that
found its picture, and a human approved that pairing by looking at a contact
sheet. So `broll-library/index.json` is not a cache of files - it is a record of
editorial decisions - and `learned\_vocab()` reads it back as vocabulary.
`\_is\_concrete()` and `query\_for()` consult it after EXPAND, so the next show that
says a word somebody has already chosen a picture for needs no term typed at all.
That is the compounding: "we can start building these b roll shots up and up and
up" (the owner, 2026-08-18).

Five guards, because a loop that learns its own mistakes is worse than no loop:

1. **A hand-written EXPAND entry always wins.** Learned mappings fill gaps; they
never overrule a decision somebody sat down and made.
2. **Nothing whose term carries a COMPLIANCE\_WORD is ever learned.** This is not
hypothetical: the library held the price-wall asset TWICE, under the spoken
words "markets" and "ETFs", because it shipped before the escape hatch in
`\_rejected` was closed. Switching the loop on without this guard would have
made that defect permanent and self-reinforcing. Both assets are retired.
3. **Nothing retired is searched, fetched or taught from.**
4. **Function words are never learned** (`\_NEVER\_LEARN`, plus a 3-character
floor), so a picture approved next to "this" or "going" teaches nothing.
5. **Collisions go to the most-used, then the most recent.** Two shows can anchor
the same word on different pictures; the one that keeps being approved earns it.

```bash
python3 broll.py vocab                      # what has been learned, and what disagrees
python3 broll.py retire <fragment> \[reason] # unlearn a pairing and delete the bake
python3 broll.py learn <shipped slate.json> # backfill anchors from a delivered show
```

**`vocab` reports DISAGREEMENT, and that is the most useful thing it prints.**
EXPAND wins, so a shipped pairing that differs from the hand-written entry changes
nothing on its own - but it is evidence that somebody looked at a contact sheet
and chose something else, which is the strongest signal there is that the
hand-written entry wants editing. The loop improves the half it is not allowed to
overwrite by telling you where it would have.

**What it learns from is an APPROVAL, and the unit is word -> TERM, not word ->
asset.** A term keeps working when a library adds better footage; a pinned asset
would freeze the picture at whatever was best the first time. The cost is that a
term's top result can drift, which is what the contact sheet is still for.

**Four things the loop was attacked over before it was switched on**, because a
system that writes its own inputs deserves to be broken on purpose first. Twelve
breaks were found and confirmed; they came down to four causes, and all four are
now closed. Do not undo any of them without re-running the attack.

1. **The anchor must not be a FRAGMENT.** `candidates()` stores `on` as the first
token of the chosen term, because that is what the renderer re-snaps on. For a
multi-word entity that token is an ordinary English word: "President Obama"
stores "president", "New York" stores "new". Learning from it binds a common
word to a one-off subject forever, and every later show saying the plain word
cuts to that picture. Four independent attackers found this the same way.
`on\_full` is now recorded beside `on`, and `\_learnable\_anchor` refuses any
pairing where they differ. The proper-noun heads are in `\_NEVER\_LEARN` too.
2. **Retirement is about a PICTURE, not a row.** An index row is keyed on a bake
filename, and one photograph holds several - a different term, a different
pick, a re-bake. Retiring one left the rest live to be re-fetched. `retire`
now widens to every row sharing the page or the source file, and `search()`
re-applies retirement to CACHED hits - the cache is seven days deep and stored
its list from before anything was retired, so a retired picture kept being
served, and re-fetched, for another week.
3. **The pick index must never fall off the filename.** The whole slug was cut at
52 characters, so "US Treasury Department Building Washington" at picks 0, 1,
3 and 7 all produced ONE name - reintroducing the exact bug the pick-in-the-
name was added to fix, and crossing the licence and creator of what shipped.
The TERM is truncated now; the source and pick are always appended intact, and
a cached bake is only reused when its page URL matches the hit being approved.
4. **A count is an APPROVAL, not a fetch.** `uses` counted writes to a file, so a
show that mentioned a subject in three clips voted three times from one
editorial decision, and a re-bake pass (documented as safe) re-counted the
whole slate. Counts now live per (picture, word) in an `anchors` map - which
also fixes a row losing its previous word every time it was re-anchored.

The compliance audit reads the TERM **and the TITLE**, because a term with no
banned word in it can still have fetched a price screen. That is exactly how the
08.18 asset got in.

### The other half: it learns from what you REJECT

An approval says "this one will do". A retype says "the one you offered was wrong
and here is the answer" - a correction of `query\_for` itself, written by hand.
That is the stronger signal, and until 2026-08-18 it was destroyed at the moment
it was created: the operator edited the term in the slate, the edit overwrote the
proposal, and the next show proposed the same losing term again.

`propose` now writes an immutable `term\_proposed` beside `term`. `fetch` diffs
them, because fetch is the first thing that runs after a human has edited the
slate. Three signals come out of that diff, all kept in
`broll-library/corrections.json` - deliberately NOT in index.json, because a
rejected term usually names no asset at all and has nothing to hang on:

|signal|what it means|what it does|
|-|-|-|
|`term` != `term\_proposed`|a RETYPE|the chosen term wins for that word; the rejected one is remembered|
|`pick` > 0|cells above it were on the sheet and not taken|those pages sort last next time|
|nothing on topic|the term itself is barren|after two failures it stops being offered|

**A correction outranks a learned approval and is outranked by EXPAND.** Same
principle as the positive half: a hand-written entry is an editorial decision and
is never overruled, but `vocab` prints the disagreement so it can be edited.

**Passed-over pictures are DEMOTED, never dropped.** A shot that was wrong for one
sentence can be right for another, and the evidence is only about what the default
should be. They stay on the contact sheet, at the bottom.

**`approved: false` is deliberately not learned from.** It means both "wrong
picture" and "I only wanted two" and there is no way to tell them apart. Guessing
would poison the vocabulary with the operator simply being finished.

Guards, all tested: a correction whose chosen term carries a compliance word is
ignored; function words and anything under three characters cannot be corrected
into a picture; a correction on a multi-word name teaches nothing, the same
`\_learnable\_anchor` test the approval half uses.

**Five things this half got wrong before it shipped**, found by attacking it. Two
of them were not learning bugs at all - they changed which picture went in the
clip. Do not undo any of them.

1. **A RETYPED TERM MUST BE RE-SEARCHED.** `fetch` reads the shortlist propose
persisted, and the shortlist belongs to the term that produced it. After a
retype it belongs to the term the operator just rejected - so the clip shipped
the picture they retyped away from, filed its licence under a term nothing was
ever searched for, and recorded a "correction" vouching for a photograph
nobody had seen. `fetch` now re-searches on a retype and resets `pick`, since
the indices no longer point at the same list.
2. **A stored shortlist has not been through `search()`,** which is where
retirement is applied - so a picture retired after propose would still ship.
Retirement is re-applied to the shortlist at fetch.
3. **"Demoted, never dropped" was false.** Sorting a passed-over picture to the
bottom of a twenty-hit list pushed it out of the four-entry shortlist, off the
contact sheet, and out of reach of `pick` - deletion wearing demotion's
clothes. The penalty is now one score bucket, and a passed-over hit also loses
its `phrase\_rescue` privilege, because being named is a reason to survive the
floor and not a reason to outrank the operator.
4. **A term must die from being WRONG, never from the network.** `search()`
returns \[] on any exception, and an empty result was being cached for seven
days - so one timeout made a healthy term look barren all week, and the
counter killed it. Empty results are no longer cached, a dead mark is only
recorded when the libraries actually answered and the re-rank rejected
everything, and the unit is DISTINCT SHOWS, because the documented workflow
re-runs propose after edits and raw calls counted the same job twice.
5. **There has to be a way back.** `broll.py revive <term>` (or `--all`).

```bash
python3 broll.py vocab            # corrections, dead terms, passed-over counts
python3 broll.py revive <term>    # put a dead term back in circulation
```

**A candidate is ranked on what it is ABOUT, not on the words in its title.**
`semantic.py` embeds the SENTENCE the word was spoken in and re-ranks the search
results against it, dropping anything below a floor. It exists because the
keyword ranker, which is good, can never reject a result that matches the query
perfectly and means something else. Measured before it: "boil" returned a seafood
pot, "federal reserve" returned a computer cooling fan, "portfolio" returned an
artwork. After it, "federal reserve" returns an actual Federal Reserve asset and
"CPI" returns the Consumer Price Index. The sort is bucketed and STABLE so the
video-first tier order above survives inside a bucket.

Two things it does NOT do, both worth knowing before trusting it:

* It cannot see the picture, only the caption. "portfolio" scores 0.655 against an
artwork titled "Portfolio" - right word, wrong sense. The guards for that are
`NOT\_A\_PICTURE` and the contact sheet, which is why approval is always a look.
Judging the frame needs an image model (CLIP/SigLIP on the thumbnail) and is the
obvious next step.
* It cannot rescue a bad TERM. A figurative "equities are going to explode"
produces "explosion fireball", and the honest outcome is that every hit is
rejected and the proposal says RETYPE THE TERM. Expect that on roughly a third
of candidates; it is the designed workflow, not a failure.

**`CONCRETE\_HINTS` matches on word boundaries, not substrings.** It used to be a
bare `hint in word`, which is a false-positive machine on short hints: "boil" was
proposed as a picture for a gold clip because **"oil" is inside "boil"**. The same
trapdoor holds "port" in "report", "mine" in "determine", "rail" in "derail" and
"coal" in "charcoal" - all eight were live before the fix. Single-word hints now
match exactly or as a plural; multi-word hints are matched as a BIGRAM of two
spoken words in `candidates()` ("data center" is one subject); they used to be
tested as a substring of ONE token, which could never match, so every
multi-word hint was dead.

**Video first. Stills only where no video exists.** The user's rule
(2026-08-12): motion is the format, and a run of still photographs turns a clip
into a slideshow. Search ranks the library first, then video, then stills, and
inside each tier by how well the title matches the query - phrases weighted
above loose words, because "distribution center" scored the same as "data
center" on the word "center" alone.

**The picture metrics are RECORDED, not policed.** Every index row carries the
asset's luma, saturation and motion (`sweep --metrics --apply` backfills), so
preflight can report what an insert is without decoding it. What it does NOT do
is warn on a luma band, and that is a decision from measurement: after the push
and exposure passes landed, a band would fire on 15 assets that are all in a
deliberate state - the ones the black floor capped short on purpose, the ones
inside the gamma deadband, and two pictures that are simply monochrome. A line
that cries wolf on correct work every run is worse than no line. What IS warned
about is an asset outside the band carrying no `eq` - which means it never went
through the pass at all, a fact about the pipeline rather than a judgement about
the photograph.

**Exposure is CORRECTED, not graded.** Inserts used to arrive at whatever
exposure the source shipped with - luma 12.7 to 196.0 across the library, sd 40 -
against a speaker's shot that is consistent all clip. A house LUT is refused: it
imposes a look, and the insert is evidence, not decoration. What ships is a luma
gamma toward a neutral band \[45, 160] that leaves 84% of the library untouched,
with a BLACK FLOOR so a picture whose darkness is structural (a black field with
neon on it) is protected while one whose darkness is a shadow problem is lifted.
Gamma, not brightness, so the black point holds - **and it only holds because the
curve is applied in the right RANGE.** `eq=gamma` is a full-range curve and 61 of
101 bakes are tv-range, where black sits at code 16, so the first version pinned
something the picture did not contain and lifted the actual floor instead: four
assets shipped with their true-black population wiped from 80-93% to zero and
their floor at code 11-24. `\_stream\_range` probes the stream and `\_eq\_chain` wraps
the gamma in tv->pc->tv when it needs it. Verified on a fresh tv bake: floor 0.0
and 5.7% true black through the range-aware curve, against floor 24.0 and 0.0%
through the old one. `sweep --recorrect --apply` re-bakes from src to repair it,
because no gamma above 1 can push code 11 back to zero. `sweep --exposure --apply`
migrates, and is idempotent through an `eq` marker on the index row - NOT by
construction, because the black floor stops the correction short of the band and
"still outside the band" therefore reads a finished asset as unfinished. Full reasoning and the frames that
set the floor are in `references/look.md`.

**A locked-off VIDEO gets the push too.** "It is a video" is not the same claim
as "it moves", and the exemption used to assume it was. Five library sources are
tripod stock that move LESS than a photograph does under the push (0.41 to 0.69,
against a push that produces 0.22 to 1.14 across the narrow stills, median 0.65)

* a dead frame for the whole settled hold. The push is decided on measured
motion now, from the same decode that picks the window: under `PUSH\_IF\_UNDER`
0.8, which sits above the push's own median AND inside a real gap in the
library (0.69 then 0.97). p25 across all 56 sources is 2.37, so it only catches
the tail.

**A WIDE still pans; a normal one pushes.** The 9:16 frame is the constraint - at
scale 1.0 a cover crop already shows the most width the frame can hold without
bars, so there is no zoom that makes a landscape photograph fit, only a move
across it. Of the 32 library stills, 11 are wider than 1.15:1 and every one came
from Wikimedia or Openverse, the tier with no `orientation=portrait` to ask for
and the tier carrying the institutions: the crude-oil tanker keeps 21% of its
width in a 9:16 frame, the Capitol 32%, the Fed 38%. Nothing is cropped out of
frame - the subject is centred in all 32 - but a wide subject stops BEING that
subject at 21% of its width. The pan travels half an output width on an EASE-OUT
(deliberately breaking look.md's smoothstep-for-large-travels rule, which is
about velocity and was written for a 344px-a-frame move, not a 10px one - the
ease-out halves how long the subject is absent), about 0.5% of the frame per
frame, and **it ends exactly where the static crop
already sat**, so the last frame is no worse than today's and the travel is pure
reveal. It finishes by `PAN\_DONE` 3.49s, the shortest source window any legal
hold and tempo consumes, NOT across the 4.7s bake - easing over the bake left the
pan still moving when the insert came off screen, 126px short of centre at the
common slate hold, which made that "ends exactly where" claim false for every
real clip. Ending it on the gradient-energy centroid was tried first and was worse
than doing nothing - on the Capitol the centroid is the TREE. Full reasoning in
`references/look.md`. Wikimedia results are now also ordered portrait-first, a
preference and not a filter. `broll.py sweep --treatment --apply` migrates
both a still whose pan plan changed and a video whose push decision changed.

Stills are NOT banned and must not be: a Falcon 9 launch or a pad explosion has
no CC0 footage anywhere, and the good frames are agency photographs. That is the
case the user named himself. `propose` prints a NOTE against any term whose video
hits are all irrelevant - stock footage that happens to be nearby rather than the
subject - and against terms that returned no video at all. Both mean the same
thing: take the still, or reword the query toward something that actually gets
filmed.

**Approve from the contact sheet, never from the listing.** `broll.py propose`
ends by writing `broll-library/PREVIEW.png` - four candidates per term, labelled
with the `pick` index. Look at it. (Until 2026-08-22 every fresh VIDEO candidate
was missing from it - the shortlist dropped the thumbnail and the sheet skipped a
video with none - so the video-first tier, cell 0 by construction, was being
approved unseen. A video with no thumb now gets a frame pulled from the media.) Pexels video objects return `alt: null` and
`tags: \[]`, so titles are recovered from the page-URL slug - readable, but a
caption someone typed, not a description of every frame. The \[n] in each cell
label counts per term, not across the sheet.

**Retyping a term is work to do, and `fetch` now treats it that way.** It did not
before. `fetch` selected entries by "approved, and either no asset or a short
bake", so an entry whose term you had just rewritten but which still carried the
picture from the OLD term was filtered out before the retype test could run. It
printed "1 approved insert(s) to fetch", did nothing to the retyped entries, and
shipped the pictures you had retyped away from. That happened twice on 2026-08-21
and neither retype took effect until the `asset` field was deleted by hand. The
retype test (`term` against the immutable `term\_proposed`) is now part of the
selection itself and clears the stale asset, so rewriting the term is enough.

Outside that exception the rule stands. Single-camera stretches run
full frame. **Two-up stretches crop to the half of whoever is talking** — set
`head\_crop` on the clip, and take a different half for a clip of the other person —
or use `mode: duo` to stack both when it is a real exchange. Screen-share stretches
use a split — their camera above the shared screen — because a clip of a slide deck
with a disembodied voice does not hold anyone. If the source only has them as a
small picture-in-picture, that caps how large they can be; size the face band to the
crop's native aspect rather than stretching it, and say so plainly rather than
shipping something blocky.

A two-up usually burns a lower-third name badge into the bottom of each half.
**Keep it inside the crop** — it attributes the speaker on screen for free, which
matters most on exactly the clips where someone makes a strong claim. Measure the
badge's text extent and crop to the box's edge rather than through it; a half-cut
name looks like a mistake, so if it cannot survive, exclude it cleanly and name the
speaker in the post caption instead.

**Every clip ends on a finished, landed sentence, then a beat of air, then the
card.** The owner's rule, 2026-08-24: "we gotta make sure the clip ends
professionally, and then it goes to the end card... whoever's talking stops
talking, and then it goes to the end card." All three parts are enforced —
`plan\_ending` REFUSES a span it cannot land, `END\_PAD\_MIN` guarantees the air, and
the out-fade is placed off the last word rather than off the end of the file. See
"A clip must end when the speaker stops talking" above for the measurements. Do
not lower `END\_PAD\_MIN` or re-pin the fade to `out\_dur`; that is the exact pair
that shipped two thirds of the archive ending at speech level.

**Every clip ends on the closing card** — a broad diagonal sheet of light crosses
the frame and takes it, carrying a swipe (`assets/brand/swipe.mp3`, loudnorm'd to I=-19 so it
sits under the voice level rather than over it; `endcard\_audio.py` synthesises a
fallback if the file is missing), then the Quasar Markets wordmark, "One Platform.
Built for the Way You Live." and the address, over a night city that drains to
black under them. **Four seconds**, appended automatically by `endcard.py`,
identical on every clip. That sameness is the point: someone who sees six clips
this week should finish all six on the same frame. Set `"endcard": false` in
project.json to render without it.

Three switches, all at the top of `endcard.py`:

|||
|-|-|
|`ENTRANCE`|`"wipe"` (ships) or `"rise"`|
|`TYPE\_STYLE`|`"bone"` (ships) or `"glass"` — the two lines under the wordmark|
|`T\_\*\_AFTER`|line staging, **offsets from the end of the entrance**, not absolute|
|`TAG\_PX` / `URL\_PX`|40 / 40. `TAG\_PX` is a safe-area number — see below|
|`q.CARD\_SECONDS`|4.0. Lives in `WLAMclip.py`; `preflight.py` reads the same one|

**`RISE = 0.33` is a floor, not a preference.** The cover travels the full 1920
of the frame, so at 30fps ten frames is the fastest smoothstep whose worst frame
still sits under the 1/6-of-frame rule broadcast pans are cut to — 0.33s peaks at
318px (16.6%), 0.30s at 354 (18.4%), 0.28s at 410 (21.4%). Past that a full-frame
jump with no motion blur stops reading as a move and reads as a flash. When the
card has to feel faster, take it out of the line staging or the plate's own
retime, never out of this.

**The wipe ships, and that was the owner's call over the alternative.** The other
entrance, `"rise"`, is the b-roll cover move: the outro arrives from below on the
same smoothstep a cutaway uses, which makes it obey the clip's own motion compass
(picture from below, type from the right, everything leaves left) instead of
reading as a bolted-on card. It was built, shown, and rejected — Steven's words
were "I like the flip up, but it should be something different... I kinda like
the little whitewash on the screen comes across. I like that one for the end of
the clip." Both stay behind the switch. **Do not quietly restore the rise on the
argument that it is more systematic; it is, and it lost anyway.**

**Every path that renders the card must get its sound from `card\_audio()`.**
Never call `endcard\_audio.write()` directly — that is the SYNTHESISED fallback,
for a missing `swipe.mp3`, and it is a different sound from the recorded swipe
`append()` puts on delivered clips. The audio selection lived inside `append()`
for months, so the preview and every build script written against it quietly
used the synth: the clips Steven ships carried one sound and every outro rendered
for him to APPROVE carried another. He caught it by ear — "it needs to have that
noise that we had before on the current clips" — and it measures as cleanly as
you would expect (0.9996 correlation to the recorded wav after the fix, 0.03
before). If a wav lands in `tmp/` named `endcard-synth-\*` on a machine that has
`swipe.mp3`, something is calling past the owner.

**"Make the wipe brighter" cannot be done with alpha.** It already peaks at
0.992 — the core is opaque — so raising the coefficients adds no brightness and
instead flattens a few hundred pixels to solid white, destroying the gradient
that `core`, `lip` and `mix` exist to produce (measured: 0.16/0.90/0.11 clips
249px; 0.20/0.96/0.12 clips 387px). Brightness comes from `WIPE\_WHITE` (lifts the
wash's base off `ACCENT\_HOT` toward bone — 0.55 halves the visible colour cast)
and `WIPE\_CORE` (widens the hot band — 340→460 grows the genuinely bright part
from 259px to 358px at zero clipping). A wider core needs more `WIPE\_TRAVEL` to
leave the frame; 460 needs 3100, or \~2% of the light is still in the bottom
corner on the last frame.

**No card ink may pass 86% of frame width.** All three elements of the lockup sit
inside 16.7%–83.2% (wordmark 719px, tagline 715px, address 704px), and that is a
TikTok constraint before it is a composition one: at 52px the tagline ran to 93.5%
and put 843px of ink under the like/comment/share rail, so the end of "Live." sat
behind an icon. Re-measure if `TAGLINE` ever gets longer or a line is added —
threshold the luma on the card's last frame, find the ink columns, assert the max
is under `0.86 \* W`. Width is the only axis at risk; the block ends at 62% of
height and the lowest platform chrome starts at 76%.

**A line that arrives on integer pixels is not smooth, however good the curve
is.** The two lines slide 46px into place, and that move was `int(...)` for its
whole life, so over twelve frames it stepped 3,4,4,3,4 — a 25% swing in per-frame
velocity on a move slow enough for the eye to track. Measured as acceleration
spikes: the quantisation contributed 3.00 against the eased curve's own 1.60, so
it was the DOMINANT source of judder and switching to a gentler curve alone would
have been mostly wasted. `place()` now shifts by the fractional part with a
bilinear affine before compositing, and the rendered acceleration matches the
ideal exactly. Steven asked for the tagline to come in "smoother"; this is what
that turned out to be, not the easing.

**Line staging is measured from the END of the entrance** (`T\_TAG\_AFTER`,
`T\_URL\_AFTER`, `T\_SWEEP\_AFTER`), never from the top of the card. The face is
built with `t` forced to 0.0 for every entrance frame, so a line whose absolute
start falls inside the entrance has already passed by the first real frame: it
appears fully formed, with no slide, on the frame the entrance ends. Absolute
times are therefore only ever right for one entrance length, and the two here
differ by nearly half a second. This bit once, switching from a 0.33s rise back
to the 0.78s wipe with the lines still at 0.52 and 0.72.

**The backplate is where the production value is.** `assets/brand/WLAM-backplate.mp4`
is 5s of 1080x1920 footage the card composites its lockup over; swap that file and
the whole outro changes without touching a line of code. The one that ships is a
Seedance 2.5 night skyline over a wet mirror plane which drains to black across
the five seconds, so the world leaves and the mark is what remains. Gates any
replacement has to pass, all measurable before you render anything:

* **the type block is 35.6%–64.4% of frame height** — measure the plate's luma
there, centre 80% of width. The shipping plate runs 12–20 mean with p95 under
38. Type on this card is borderless by design, so a plate that needs a scrim is
the wrong plate, not a scrim problem. **But do not grade a plate down to hit a
number** — the shipping street runs p95 86 at its brightest and reads fine,
because bone white at 253 over 86 is still a wide margin. Pulling its head to
0.50 to "fix" the measurement crushed the depth and reflections that were the
reason for choosing it. Measure to rank candidates; judge the composite.
* **it has to come to rest.** Mean abs frame difference in the last third; the
shipping plate ends at 0.14. The lockup is static for seconds and a plate still
drifting under settled type reads as a mistake.
* **it has to get darker.** That is the "and then it goes away".
* **no glyphs anywhere.** Generated video renders garbled text on any surface it
decides is a sign; ban it in the prompt at material level and then scan the
frames, do not trust the ban.

`tools/backplate/` holds the three that decide this — `measure.py` ranks
candidates, `lumamap.py` gives per-height luma, `trace.py` finds the window —
plus `conform.py`, which cuts the chosen roll to length with the fall-off baked
on a smoothstep, and `PROMPT.md`, the Seedance 2.5 call and prompt that produced
the shipping plate along with the five concepts that lost and why.

The card carries the address, so the in-body address line **switches itself off**
whenever the card is on — showing it twice in a row reads as a mistake rather than
as emphasis. `"cta\_in\_body": true` forces it back (use it if the card is off).

**The panel is the whole 1080x1920 frame, and it is the same box in every mode.**
`head`, `duo`, `share` and `duo\_share` are ways of packing that box, never different
boxes. One overlay position, nothing computed per mode. When `share` derived its own
height it came out 21px short and top-aligned, and every screen-share clip sat
visibly high.

**The captions sit ON the picture, at y1130..1430, in every mode.** There is no band
under the video and no scrim. That bottom edge is derived from platform chrome
(TikTok covers the bottom \~480px), and the measure — `W - 340` — is derived from the
right-hand action rail. Their colour is chosen per clip from what is actually behind
them, so a speaker in a blue shirt does not get blue keywords. Full reasoning, the
palette and the overrides are in `references/look.md`.

**Know what they land on.** Chest in `head` — but the chin on a close-framed webcam
shot, because a 9:16 crop of a 16:9 source is a tight close-up and there is no wider
crop to take. The shared app in `share` and `duo\_share`. The lower speaker's **face**
in `duo`, which is unavoidable at this band position and is an accepted cost: where
one person holds the floor, use a `head` crop instead. Adaptive colour keeps captions
legible over a face; it does not stop them covering one.

**The hook overlays the picture and leaves after 3.0s, and it places itself off
the face.** Since 2026-08-22 the card is no longer pinned at y96 (inside the
chrome, and across the eyes on every `share` clip): `panel\_faces()` finds the
face in the reframed panel and `place\_hook()` puts the card in the clear band
nearest y480 - above a low face, below a high one, between two - shrinking to
84px type before it will overlap, and saying so in the log if it must. It swipes
in from the right over 0.30s and swipes out to the left over 0.233s.

> \*\*On cutaway transitions, this section is out of date.\*\* Where the text below
> describes the HARD CUT as the house standard, that was superseded on
> 2026-08-25: `"broll\_style": "cut"` sets `BROLL\_IN`/`BROLL\_OUT` to 0.0 and
> strips the transition off every cutaway, and \*\*preflight now REFUSES it\*\* —
> "There's animations for every b roll cut." The standard is `dissolve`, at
> `BROLL\_IN` = `BROLL\_OUT` = 0.35s. The hard-cut measurement is kept below as
> the reasoning that was current at the time, not as the rule. Nothing sits above it: no
eyebrow, no logo, no show name, no rule. Feeds that letterbox a 9:16 in the
timeline (X on mobile above all) crop the top strip off, so anything permanent
up there is the first thing lost and reads as a clipped mistake. If a clip needs
the show named, name it in the post caption. Placement, animation and the
survey behind both are in `references/look.md`.

**A cutaway is a HARD CUT, in and out** (`BROLL\_STYLE` "cut", `BROLL\_IN` =
`BROLL\_OUT` = 0). No travel, no dissolve, no sound, no whip, no shadow. The
insert is whole on its first drawn frame and gone on the frame after its last,
and the `enable` gate is the entire transition.

**This overturned the owner's own 2026-08-22 instruction, and only because his
own reference overturned it.** He watched the 08.25 clip and said *"The
transition is still not clean as the YT video i showed b4. needs to be more
seemless ... seemless more transitions and smooth"*. **"Still"** is the word
that mattered: the slide had already been tuned twice - 0.233/0.200 on a
quart+cubic, then 0.333/0.300 on two smoothsteps after he called the first
version glitchy - so instead of cutting a third curve, the reference was
downloaded and measured.

`youtube.com/shorts/gaRRMkRjoHE`, 1556 frames at 30fps. It is the SAME FORMAT
as ours: a talking head on a dark studio background, karaoke captions burned on
the picture, and full-frame b-roll cutaways that leave the speaker and come
back. Measured frame by frame:

* **Every cutaway is a hard cut. 28 of 28 across both references.** On the cut
frame ZERO of 360 columns and ZERO of 640 rows are closer to the OLD picture
than the new one, and the frame is a clean member of the new shot
(|cut - after| 0.7 to 11.0 mean abs luma against |cut - before| 48 to 156).
A slide, wipe or push leaves part of the frame behind by construction.
Nothing is left behind. The change occupies ONE frame.
* **It cuts twice as often for the same share of the runtime.** Six cutaways in
51.87s - one every 8.6s, holds of 1.60/2.17/1.60/1.60/1.83/2.40s, mean 1.91 -
totalling 22.1% of runtime. Ours was 22.0%. The share was already right; the
GRANULARITY was not.

The same measurement on our delivered clip: **55 to 352 of 360 columns and 207
to 507 of 640 rows still showed the OLD picture** on the frame the cover was
supposed to have taken. Half the frame stale for a third of a second, six times
a clip. That is what "not clean" was pointing at, and no easing fixes it - a
cut has no seam to judge, which is the whole point.

After the change, the same test on the re-render: **0/360 and 0/640 at all ten
boundaries**, identical to the reference.

So a half-second sliding rectangle was never going to satisfy "seamless". The
slide is KEPT behind `"broll\_style": "slide"` because he asked for it once and
may want it back. **Do not quietly make it the default again on the argument
that a move is more designed than a cut.**

`BROLL\_IN`/`BROLL\_OUT` remain the ONE OWNER of the travel and are derived from
the style, so five consumers follow with no second switch: `broll\_chain`, the
punch ladder's forced flip at `a1 - BROLL\_OUT` (now `a1` exactly - the first
uncovered frame, which is correct for a cut, where nothing is progressively
exposed, so the return is ONE cut instead of the double cut that comment
describes), preflight's settled-time test, and broll.py's `MIN\_HOLD` and
`PAN\_DONE`.

The speaker's
framing FLIPS under every cutaway (at its first exit frame, while the cover is
still full-frame), and flips at sentence-end cuts between them:
two framings, 100% and 106% about the face, cut from the source - so the 23
invisible removals a minute become visible picture changes (11 on the
reference clip, longest hold 11.4s where it was 29s). **The first change is
seeded into the opening** rather than waited for, landing on the first keyword
between 0.8s and 2.0s: the join-driven ladder was firing at +7.2s, leaving the
whole stay-or-scroll window (\~1.3s) on one static frame. The live caption word
pops to 1.05 and holds at 1.02. Every number and the ladder that picks the
toggles are in `references/look.md` ("Punch-ins").

**`duo` punches too now, with BOTH bands moving together.** It was excluded for
as long as the punch existed, on the grounds that it needed per-band speaker
attribution. That attribution is now MEASURED, with whospeaks' speech-gated
ratio across three two-up spans of the 08.22 master, and it is WEAK on two of
three - margins of 1.13x and 1.12x over spans of 40 to 56 seconds. A punch window
is 2 to 8 seconds with a fraction of the samples, so per-window it would be
worse, and a punch that follows a wrong verdict zooms in on the LISTENER, which
is the defect the exclusion existed to avoid. Punching both bands delivers the
whole point of the punch - invisible removals becoming visible picture changes -
and can never name the wrong person. The shrink anchors bottom-left on each band
so the burned-in name badge survives, the same call `\_punch\_box` already made for
the share tile. Rendered on a real duo clip: 7 framing changes across 56s, and
the lower third legible in both framings. `duo\_share` stays out; it carries the
shared app, and moving a chart's axis labels was rejected by name.

**A clip never sits in silence. There is always someone talking.** This is
enforced in `render()`, not left to the picker, because a live show is half dead
air and a span that looks fine in the transcript can arrive 31% silent. Four
things run automatically, and each one exists because it shipped a bad clip:

1. **The out-point is pulled back to the last spoken word** (audio, not words), so
a clip cannot run out over dead air.
2. **The decode window stops at the first silent hole**, because whisper spreads a
chunk's words across the whole chunk - a gap inside the window drags the words
before it LATE, and they come back timestamped after the audio stopped. That is
what produced a caption reading "...shares have already traded lot."
3. **Words with no energy under them are dropped**, in runs. whisper does not
return nothing for silence, it invents fluent text over it. One clip ended on
"That's a lot." laid across eight seconds of -85 dB. Runs, not single words -
an isolated quiet word is a soft "I'm" or "a", and dropping those wrote
"Something happens at bank".
4. **Every silent gap is collapsed** to `KEEP\_AIR`, not just the ones after a full
stop. The old pass only cut at sentence ends, took at most `cut\_frames`, and
gave up when speech did not resume inside `resume\_window` - so the longest
holes were precisely the ones it skipped.
5. **A brief, quiet poke above the floor does not end a pause.** `collapse\_silence`
thresholds the envelope, and a threshold alone SHREDS a long hole: on the
08.18.26 master a 1.45s pause carried two room-tone transients at -44.5 and
-45.8 dB against a floor of -46.0, which split it into runs of 0.95s, 0.20s and
0.20s. Only the first cleared `MAX\_GAP`, so 0.65s shipped - and the residual
check reported it as three short pauses rather than one long one, so nothing
warned. A stretch above the floor is now bridged into the pause when it is both
shorter than `MIN\_SPEECH\_RUN` (0.12s) and never more than 8 dB clear of the
line. Both conditions are load-bearing: brief alone swallows a clipped "yeah.",
quiet alone swallows a mumbled sentence. Same reasoning as `last\_speech`'s
`min\_run` - speech is SUSTAINED - applied to the other end of the problem.

The build prints what it did (`removed 7.3s of silence in 9 cut(s); longest pause left 0.32s`) and warns if anything over `MAX\_GAP` survives. **Verify on the
rendered file**, not the log: decode the audio and look for runs under -42 dB. The
log can be honest and still wrong - a pause split into three sub-`MAX\_GAP` runs is
reported as three short pauses, and "longest pause left 0.35s" was printed over a
hole that measured 0.65s in the delivered file. The log describes the cut list; only
the render describes what a viewer hears.

**VAD is on, and it fixes a subtler thing than it sounds like.** whisper.cpp runs
Silero itself (`--vad`), wired into both passes via `WLAMclip.vad\_args()` and a copy
of it in `analyze.py` - copied, not imported, because importing WLAMclip deletes the
transcripts analyze is writing. The failure it was installed for LOOKED like
hallucination over dead air: a clause appearing across 1.9s of -80 dB silence. It
was not. The words were real, spoken fast on the far side of the pause, and what
was wrong was their TIMESTAMPS - the word pass spread them backwards over the hole
and `drop\_unspoken` then deleted them for having no energy underneath, shipping a
caption that read "...don't time the market. that." Measured on that span: 8 words
landed inside the silence without VAD, 2 with it, and the clip that had to be
abandoned over it now renders correctly. It is an improvement, not a cure, so
`drop\_unspoken` stays. Off with `"vad": false`.

**Speech denoise runs on the finished body.** `denoise()` puts DeepFilterNet
(`tools/deep-filter`, a binary, so it cannot be a link in the filter graph) over
the clip before the end card goes on - off the card deliberately, because the
swipe is a produced sound and does not want a speech denoiser near it. Measured on
30s of the 08.12.26 master: the room-tone floor went from -81.8 dB to digital zero,
the speech peak moved -0.3 dB. Then loudnorm is re-applied, because the first pass
measured a signal that still had a floor in it. Off with `"denoise": false`.

One consequence, and it will bite whoever writes the next QC script: every pause in
a denoised clip reads as -240 dB, the same signature as a real hole. **Judge the
LEVEL on the source and the LENGTH on the render.** An absolute dB reading off a
delivered file will call every natural breath dead air, but the DURATION of a quiet
run is exactly what you want to measure there, and it is what caught the shredded
pause above.

The interaction runs the other way too, which is the part that is easy to miss. The
silence pass works off `audio16k.wav`, upstream of the denoise - so it sees room
tone that the delivered file does not have. A transient sitting 1 dB above the
floor in the source is inaudible there and plays at -80 dB after DeepFilterNet
strips the tone around it. The pass is not wrong to work on the source; it just has
to assume anything marginal will be pulled DOWN later, which is what
`MIN\_SPEECH\_RUN` now does.

**Never burn a whisper transcript in unchecked.** It mishears proper nouns and
sometimes whole phrases — on the WLAM webinar it wrote "what the buyers sell" for
"what to buy or sell", which would have inverted the meaning of the single
clip whose entire point was that the product gives no advice. `TERMS` and
`MERGES` at the top of `WLAMclip.py` hold the corrections; read the `.srt` of
any clip before it ships. Two failures are handled automatically but still worth
knowing, because both are silent: a segment transcript with no casing or
punctuation is detected and ignored rather than being aligned against (it would
downgrade good captions *and* leave no sentence ends to cut on, so the clip would
also lose every retention cut), and the bare `-` whisper emits at a speaker change
is filtered before it can burn in as "- It's already there."

## `head\_follow`: the crop follows whoever is talking (2026-08-28)

The owner: *"if we're doing a duo clip and it's single face, if, for example, Steve
is talking, and then Stephen Flanagan talks after, it will switch different
talkers."*

**THE GAP WAS REAL AND THE ARCHIVE SHOWS IT.** On a two-up the slate had exactly two
options: `head` with one fixed crop, which shows a **silent face** for every second
the other person holds the floor, or `duo`, which stacks both and halves everybody.
Neither is right for an exchange where the floor moves — which is most of a
two-hander — and `head` is the better-looking of the two whenever one person
actually IS talking. So: take the head crop, and move it.

```bash
python3 turns.py 1852 1960                       # print the turn schedule
python3 turns.py 1852 1960 --tiles '{"a":\[w,h,x,y],"b":\[w,h,x,y]}'
```

```bash
python3 turns.py <start> <end>                   # print the turn schedule
python3 turns.py <start> <end> --tiles '{"a":\[w,h,x,y],"b":\[w,h,x,y]}'
```

**HOW `turns.py` DECIDES — this is the current method.** The full reasoning, and
the three defects that produced it, are under "Who is talking" above; in short:

|||
|-|-|
|**WHEN**|boundaries come from the AUDIO — `whisper-cli -tdrz` (tinydiarize), every utterance boundary a candidate, not only the marked changes|
|**WHO**|each segment is scored as a WHOLE, \~300 samples rather than the 10 a one-second window holds|
|**WHERE**|the mouth region comes from the face the cascade FINDS in each tile, never a fixed fraction of it — a fixed box put one speaker's animated background inside his "mouth"|
|**WHEN NOT TO ACT**|`MARGIN\_CLEAR` 1.25 sets the running answer; `MARGIN\_DECIDE` 1.08 acts without resetting it; below that the previous answer holds. Holding is also a decision, and it is the one that shipped the wrong face for 47 seconds|

The old sliding-window pass survives as `plan\_windowed` and runs **only** when the
tinydiarize model is missing, with a warning saying it is materially worse. Do not
reach for it: it is the thing that was wrong.

Then the schedule is smoothed:

|||
|-|-|
|**the strobe**|people interrupt. `MIN\_TURN` 2.2s holds a framing before it may be given up.|
|**the shrug**|a listener laughs or says "right". A turn under `MIN\_TURN` is absorbed into its longer neighbour.|
|**the tie**|over silence neither tile wins and the ratio is meaningless — both score their own noise floor.|

**`FOLLOW\_MIN\_CONF` 0.45 REFUSES** a clip whose schedule is mostly held rather than
measured — a guess produces exactly the defect the mode exists to remove.
**`FOLLOW\_MAX\_DOMINANCE` 0.65** warns when one person holds most of the floor: that
is a `head`/`share` clip, not a conversation. **Superseded: `FOLLOW\_MIN\_TILE\_W`
was retired for `FOLLOW\_MIN\_FACE\_W` (80px on the detected face).** The old rule
read: `FOLLOW\_MIN\_TILE\_W` 500 warns when
the camera tiles are too small to read a mouth in — a 348px tile carries a mouth a
few pixels across. Both of the last two are **provisional**: see the retraction
under "A MEASUREMENT THAT WAS WRONG".

**Rendering is the punch ladder's shape**, not a new mechanism: both crops cut from
the source at full quality, one overlaid on the other under an `enable` gate. **The
switch is a HARD CUT, deliberately** — two framings of the same room are the one
place in this pipeline where two pictures are the same scene, so any blend reads as
a glitch. Broadcast cuts between cameras; so does this. The conversation modes stay
out of `PUNCH\_MODES`: their turns already break the picture up.

**HOW IT WAS VERIFIED, and it is the standard for verifying the next change too:**
the render's own log names the tile holding each turn; **49 of 49** sampled frames
showed the framing the schedule authored; and the acceptance test was pulling
frames at +1s, +3s and +5s and checking **whose mouth is open**. The summary ratio
that was also quoted here has been retracted — see the section above for why.

## An insert can be too BUSY for the words on top of it

Found on 2026-08-28 by auditing delivered frames for motion defects, after the
owner asked what subtle things were left: *"there's subtle animations, there's
subtle flashing, whatever can be the difference."*

The captions sit **ON** the picture, so what matters is not an insert's motion in
the abstract but how much the **caption band** moves underneath them. Measured on
two delivered clips — asset motion against band motion at y1130:

|asset motion|caption band||
|-|-|-|
|1.2|4.0|speaker baseline is **2.3 – 3.9**|
|2.5|4.0||
|4.5|6.1||
|5.6|3.6||
|15.5|5.5||
|21.2|5.5||
|**37.2**|**19.9**|**5–9x the baseline**|

Everything up to 21 keeps the band within a couple of points of the speaker; 37
is a step change, and the words sit on a flickering field. `BROLL\_MAX\_MOTION`
28.5 is the library's own p90 and lands in the empty gap between those two
populations, which is where a threshold belongs.

It fires on **8.2% of the 195 approved inserts** across every slate on this
machine — about one in twelve. A WARN, because a busy picture can be the right
picture and only a person looking at it can say.

**What this was NOT.** The audit first reported "24 hard cuts" in a clip and it
looked like a strobe. It was one bokeh light-field insert whose flicker a
frame-difference detector counts as cuts — the same shape of error as every other
proxy this file records. Pulling the frames showed a dissolve behaving correctly
and a picture that was simply busy. **The detector was wrong about the defect and
right that something was there.**

Also measured and NOT a problem, so nobody re-checks them: **zero** one-frame
brightness flashes in either clip, and the only frozen runs are the end card
coming to rest, which is what it is designed to do.

## Nouns: what the vocabulary was missing, and the month trap

The owner, 2026-08-28: *"expand the vocab. Make sure the vocab connects to all
different types of things, especially nouns. If a noun is brought up, you
definitely wanna show a picture of that, because that's easy to show for visuals."*

**MEASURED FIRST, on WLAM shows only** — the hearing corpus is another job's material
and it swamps the counts. Across the 123 WLAM caption files the show speaks **249
distinct proper nouns and 130 of them have no picture at all. 52%.** A word with no
mapping is searched LITERALLY, which is the same road that shipped the graveyard
angel above.

The uncovered *common* words are almost all grammar and verbs — know, going, want,
really, mean, those, back — which correctly have no picture. **It is the PROPER
nouns that were missing, and they are the most visual words the show says.** Added,
each the BUILDING or the ROOM, never a logo and never a person, the rule the Fed and
Treasury entries already follow: `sec`, `cme`, `bloomberg`, `mcp`, `solarwinds`,
`gulf`, `hemisphere(s)`. A Bloomberg TERMINAL is a wall of live prices, which
`COMPLIANCE\_WORDS` refuses outright and rightly, so `bloomberg` is a newsroom.

**THE MONTHS WERE ADDED AND THEN TAKEN BACK OUT, by the harness rather than by
taste, and this is the part to keep.** Seven of twelve months had no picture, so
pointing them all at a flipping calendar looked like an obvious win. `vocabcheck save` then `diff`, over 79,905 groups, said otherwise: **a capitalised month is an
ENTITY, which outranks an ordinary noun**, so it displaced the better subject every
time.

&#x20;   FED      -> SEPTEMBER    the Eccles Building -> a calendar
    CRYPTO   -> JANUARY      a physical bitcoin  -> a calendar
    BANKS    -> JANUARY      a bank facade       -> a calendar
    CONGRESS -> DECEMBER     the Capitol         -> a calendar
    PRICES   -> DECEMBER     a supermarket aisle -> a calendar
    payroll  -> September    counting banknotes  -> a calendar


Every one a downgrade — and **a date is not really a picture anyway**, the same
reason "interest rates" is deliberately not a key. `chatgpt` went with them for
displacing `ai`, whose data centre is the better shot. 139 displacements before the
cut, 55 after, and **all 55 that remain replace an ABSTRACTION** (think, transparent,
potential, motivation, achieved, jurisdiction, worry, thoughts, success, relentless,
process, priorities, focused, team). A concrete institution beating an abstract noun
is the direction this vocabulary is supposed to move.

**Two guards run on the way in and both fired on this pass.** Every value is checked
against the baked library before it is written — a key pointing at nothing is worse
than no key — and six of twenty proposed keys already existed and were refused
rather than silently overwritten. `may` and `march` were never candidates: one is a
modal verb and one of the commonest words in English, the other is a verb and a
protest.

## A two-token term matched on ANY ONE word, and it crossed names

Found on 2026-08-28 by pulling frames from a verification render rather than by
reading code. A clip whose speaker was discussing **Bill Gates** cut to a **$100
bill** on a green chroma background.

**THE ROOT CAUSE IS THE OVERLAP RULE, NOT THE ASSET.** `search\_library` needs
`len(toks \& mt) >= max(1, len(toks) // 2)`, and for a TWO-token term that
collapses to `>= 1` — which is not an overlap test at all, it is an *any shared
word* test. "Bill Gates" and "us dollar bill macro detail" share `bill`.

Measured over the 1,761 live rows, **42 of the 76 two-token terms** reach some
other picture that way, and the ones that matter are **names**:

&#x20;   'Elizabeth Warren' admits a photograph of WARREN BUFFETT
    'Warren Buffett'   admits a photograph of ELIZABETH WARREN
    'Kevin Warsh'      admits a photograph of KEVIN HASSETT
    'Kevin Hassett'    admits a photograph of KEVIN WARSH
    'Mike Johnson'     admits Mike Starkey, a soybean farmer
    'Bill Gates'       admits a dollar bill


**Putting the wrong person's face on screen when the show names someone is about
the worst thing this pipeline can do.** Registered names survived only because
`search()`'s person branch re-filters on an exact term match — an **unregistered**
name has no protection at all, and `\_person\_of("Bill Gates")` was empty, so the
person branch never ran for him. It is not only names either: `oil refinery`
admits a crude tanker, `tokyo skyline` admits Shanghai, `courthouse columns`
admits a bank in Buenos Aires.

**A two-token term now needs BOTH tokens.** Longer terms keep the loose rule,
which is what lets "spacex falcon 9 launch" and "falcon 9 liftoff cape canaveral"
find one photograph — verified still working. A term always finds its own row
regardless, since the row carries it.

**THREE MORE HOLES WERE CLOSED, because one bad row got in by every route.** Keep
all three; each is the only thing standing in one of the doorways:

|||
|-|-|
|**write time**|a person's name may only be written over a portrait. `stock --people` has refused a non-portrait since it baked a Pexels clip as `alexandria-ocasio-cortez`; the ordinary `fetch` never did. The read-side guards *cannot* undo a bad row, because the exact-term test passes when the row's term really is the name.|
|**read time**|a baked VIDEO may not answer a person. There is no correctly-licensed motion of a living public figure anywhere in these libraries — that is why the portrait tier exists — so any video filed under a name got there by matching a word. It also outranked both real photographs, because `search()` puts motion first.|
|**the tier**|a QUOTE of somebody is not a picture of them. *"Quote of Bill Gates at the Cafeteria of IIIT Hyderabad"* names him, is single-subject, is CC0, and is a photograph of a **wall**. Same class as the Narendra Modi Stadium case the title filter already covers.|

**The lesson for a run: pull frames from the delivered file.** Every check in
preflight passed on that clip. The b-roll was approved, baked, correctly licensed,
on the right word, at the right hold, and it was a picture of a banknote where the
show said a man's name. Only looking found it.

## A fetch failure names its cause, and it used to name the wrong one

Found by taking the pipeline end to end on 2026-08-28. On a retype `fetch()`
re-searches and hands the results to `semantic.rerank`, which drops anything
off-subject. `\_before` was measured AFTER that, so when the re-rank emptied the list
the failure printed **"nothing free for commercial use without attribution"** — a
claim about licensing, made about hits that were all correctly licensed.

Measured: `"government building columns"` returned **30 hits, every one
Pexels-licensed or public domain**, and printed the licence message. The operator is
then sent to re-word a term for a problem it does not have.

The real cause is worth knowing because it will happen to you: **the insert's stored
`context` still belonged to the word it was anchored to BEFORE the retype.** If you
re-point `on` and `term` by hand, clear `context` too — the re-rank is scoring the
new picture against the old sentence. There are three causes now and they send you
to three different places.

## Where the face lands, in every mode

The owner, 2026-08-28: *"we need to make sure that the head placement of all the
people in all different formats is correct."*

**Nothing measured it.** `check\_crops` scores a crop's GEOMETRY — is it inside the
source, does it match the panel's aspect. `check\_pip\_face` asks only whether a face
EXISTS in the share tile. And `panel\_faces`, which has always measured exactly the
right thing (faces in the reframed 1080x1920, through the clip's own chain),
existed solely to place the hook card AWAY from them. Nobody ever asked whether the
face was well placed for a viewer.

**MEASURED OVER 96 DELIVERED CLIPS**, which is why this is not a hypothetical:

|||
|-|-|
|**12**|chin BELOW the platform chrome line — the mouth is behind the TikTok UI. Worst 463px past it.|
|**28**|chin inside our own caption band, so the words sit on the mouth|
|**5**|crown sliced off at the top of frame|
|**5**|head-mode face under 300px wide of 1080 — a small head in a large empty frame|
|**7**|head-mode face more than 170px off centre|

The thresholds are **read off the layout** rather than chosen: `CAP\_BAND\_Y\_REST` is
where our captions start, `CAP\_SAFE\_BOTTOM` is where the platform's chrome does, and
a chin below either is behind something.

**WARN, except the chrome line.** A cascade returns nothing for a profile, so a low
reading is sometimes the detector rather than the framing — and this file's
recurring lesson is that a check which refuses good work gets ignored. A chin past
`CAP\_SAFE\_BOTTOM` is not a matter of taste: no viewer can see the mouth.

**A SMALL-FACE OR OFF-CENTRE WARNING IS THE ONE WITH A REAL FALSE-POSITIVE RATE**,
and one was caught the day the check shipped: on the 08.26 head clip it reported a
229px face at x754 while the frame plainly shows a face filling most of the crop,
because the speaker had his head tilted back and eyes half-closed at that instant
and the frontal cascade locked onto something small. **Pull the frame before you
re-author a crop on the strength of those two lines.** The chin and crown lines are
positional and do not have this problem.

**THE FIX HINT'S GEOMETRY IS THE PART WORTH READING.** `panel\_y = (sy - cy)\*H/ch`,
so the two ways to lift a face are to move the crop **DOWN** the source or make it
**TALLER**. A *shorter* crop enlarges the picture and pushes the face further down —
the first version of the hint recommended exactly that and would have made every
clip it fired on worse. When the crop is already the full source height the hint
says no crop can fix it rather than inventing a number.

## A RELIGIOUS PICTURE MAY ONLY ANSWER A RELIGIOUS WORD

The owner, 2026-08-28, watching a delivered clip: *"make sure the vocab is correct
on all the different captions because we messed up. You put, like, a religious
symbol for mystery — you can't have that."*

He is describing one asset. The library held a funerary **angel statue** captioned
"mysterious winged figure in cemetery", and `mystery`/`mysterious` had no `EXPAND`
entry — so they fell through to a **literal search**, `search\_library` matched on
title tokens, and "mysterious" landed on a graveyard. Nothing objected, because
every guard here was about compliance or junk.

**THE FAILURE IS A CLASS, NOT AN ASSET, and it arrives by three separate roads:**

|road|example found|
|-|-|
|literal search|an unmapped abstract word matching a religious CAPTION. `mysterious` → the cemetery angel. This is the reported one.|
|learned anchors|the library had taught itself `credibility` → "push in shot of a pulpit" and `questions` → "engaged audience at indoor church gathering". Both approved by eye once, live for every later show.|
|wrong captions|a secular term whose best hit is a religious photograph: "house of representatives chamber" stored against *"chairs inside a church"*, "bombed building ruins rubble" against the ruins of the Great Synagogue after the Blitz.|

So the guard is on the **PICTURE**, at the same choke point as compliance.
`SACRED\_WORDS` refuses a hit whose caption carries religious, funerary or occult
iconography **unless the QUERY asked for it**.

**THE QUERY ESCAPE IS DELIBERATE HERE AND IS A HOLE IN COMPLIANCE.** The two rules
are not the same shape. A price wall is never something this desk wants, so letting
a query switch that off was pure hole and it shipped one. Religion is a legitimate
**SUBJECT** — a segment about Ramadan should show a mosque — and what is
illegitimate is religion used as a **METAPHOR** for a secular word. The escape is
exactly that line: ask for a mosque and you get one, say "mysterious" and you do not.

**AND THE VOCABULARY ITSELF POINTED SECULAR WORDS AT RELIGION.** Measured by
replaying `broll.candidates()` over all 198 delivered caption files:

&#x20;   66x  church steeple        <- belief(13) faith(10) beliefs(6) secular(4)
                                  devotion(2)   ... 35 of 66 secular
    16x  monk raking zen garden <- discipline(9) disciplined(3) restrained(3)
                                  diligent(1)   ... 16 of 16 secular
     2x  istanbul mosque       <- turkey(2), and BOTH were the BIRD: "PORK,
                                  TURKEY, in order to set maximum price"
     1x  fortune teller crystal ball <- predict


`secular` was the clearest: it means NOT religious, it is a finance word here (a
"secular bull market" is a long-horizon one), and it pointed at a church.
`discipline` is core trading vocabulary and cut to a zen monk every time. **A
crystal ball under a strategist's forecast is occult imagery AND an editorial
insult** — it says on screen that the analysis is soothsaying.

22 keys repointed, 4 metaphor-prone keys dropped (`mecca`, `pilgrimage`, `pilgrims`,
`prophecy` — "a mecca for startups", "a pilgrimage to Omaha"), 2 anchors unlearned,
4 assets retired. **Measured after: sacred pictures fire 112x → 52x, and all 52
remaining triggers are words that genuinely mean religion or death** (religious,
church, theology, preacher, pastor, praying, died, grave, mortality). No secular
word reaches a religious picture.

**An import-time lint refuses a secular key pointing at a sacred picture**, in the
same shape as the compliance lint beside it. Running it over the real vocabulary is
what found the two caption-side traps now recorded in the list, and both are worth
knowing before you add a word to it:

* bare **`cross`** matches "cross section", "cross-border" and "cross-examination".
It flagged the tree-rings picture, which is a tree.
* **`angel`** matches **"Los Angeles"** through `\_word\_rx`'s plural rule — besides
being this desk's own word for an investor.

`SACRED\_KEYS` is a separate list from `SACRED\_WORDS` and the distinction is
load-bearing: one asks *"is this picture religious"*, read off a stock CAPTION; the
other asks *"did the speaker mean religion"*, read off a spoken WORD. A caption says
"minaret"; a person says "Muslim". Testing a mapping by whether the key appears in
its own value fails every correct entry in the vocabulary, because a value carries
several sacred words at once and only one of them can be the key.

`LANDMARK\_TERMS` exempts three city skylines — Istanbul's is the Blue Mosque, Rio's
is Christ the Redeemer, Bangkok's is a temple. Enumerated rather than inferred: a
rule like "any value containing 'skyline' is fine" would wave through a genuine
devotional picture the day somebody captions one that way.

## Compliance applies to what is ON SCREEN, not just what is said

A `share` clip burns the shared window into the picture for its whole length, so
the slide or the chart is subject to the same rules as the speaker's mouth. On an
options interview the narration was purely conceptual - no ticker, no number - while
the deck behind it was an option chain listing ten strike prices with the underlying
last price across the top. Shipping that would have put a ticker and a table of
strikes on screen for 48 seconds.

**Pull a frame from the middle and the ends of any share span and read what is
actually visible** before committing to the mode. If the window carries a price, a
strike, a position or a return figure, either pick a stretch with a different slide
or drop to a mode that does not show it. Note what IS visible in the ticker file,
so nobody has to re-watch the clip to find out.

Crop the app to its content, not its window: a visible title bar, filename or
minimise/maximise buttons is what makes a clip read as a screen recording rather
than a post.

**A caption is not a redaction.** Captions cover part of the shared screen now, and
the tempting move is to pick a span on the grounds that the words will sit over the
number. They will not, reliably: the block is one line or two depending on what is
being said, so what it covers changes second by second, and the frame you checked is
not the frame that ships. Read the screen as if nothing were on top of it.

## Compliance, when the footage is a raise or a market opinion

Keep it out of the clip rather than caveating it afterwards. No clip should
contain a returns promise, a share price, buy/sell advice, or the invest call to
action from the speaker's own mouth — the capsule is the CTA. Where the speaker
cites a statistic as their own read rather than a published figure, say so in
the post caption. This is a real constraint on which spans you can use, not a
disclaimer you bolt on at the end.



### The rest of the settings, generated from the code

Every remaining key the pipeline actually reads, with its default and the
module that owns it. **Generated by scanning `CFG.get` / `\_num` / `\_int` /
`\_cfg\_val` call sites**, not written by hand, because a hand-kept list of 76
settings is a list that drifts — 38 of these were live and documented nowhere
when the audit looked.

|key|default|owner|
|-|-|-|
|`adaptive\_captions`|`True`|WLAMclip.py|
|`adaptive\_speed`|`True`|WLAMclip.py|
|`app\_min\_frac`|`0.52`|WLAMclip.py|
|`broll\_black\_floor`|`15.0`|broll.py|
|`broll\_every`|`10.0`|WLAMclip.py|
|`broll\_hold`|`3.6`|WLAMclip.py|
|`broll\_hold\_min`|`2.5`|WLAMclip.py|
|`broll\_lead\_in`|`5.0`|WLAMclip.py|
|`broll\_luma\_hi`|`160.0`|broll.py|
|`broll\_luma\_lo`|`45.0`|broll.py|
|`broll\_max\_frac`|`0.38`|WLAMclip.py|
|`broll\_min\_face`|`4.5`|WLAMclip.py|
|`broll\_min\_inserts`|`2`|WLAMclip.py|
|`broll\_push\_if\_under`|`0.8`|broll.py|
|`broll\_tail\_clear`|`3.0`|WLAMclip.py|
|`broll\_vary`|`True`|WLAMclip.py|
|`cap\_size`|`86`|WLAMclip.py|
|`cta`|`"invest.quasarmarkets.com"`|WLAMclip.py|
|`cta\_on\_broll`|`True`|WLAMclip.py|
|`cta\_signup`|`"quasarmarkets.com"`|WLAMclip.py|
|`cta\_verb`|`"Sign up free"`|WLAMclip.py|
|`denoise\_atten`|`24`|WLAMclip.py|
|`duo\_crops`|`—`|WLAMclip.py|
|`fix\_stephen`|`False`|WLAMclip.py|
|`fonts`|`—`|WLAMclip.py|
|`graphic\_box`|`—`|preflight.py|
|`hook\_hold`|`3.0`|WLAMclip.py|
|`layout\_version`|`1`|WLAMclip.py|
|`min\_clip`|`60.0`|WLAMclip.py|
|`model`|`—`|WLAMclip.py|
|`out\_dir`|`WORK / "out"`|WLAMclip.py|
|`punch\_open`|`True`|WLAMclip.py|
|`source`|`""`|WLAMclip.py|
|`speed\_max`|`1.12`|WLAMclip.py|
|`speed\_min`|`0.96`|WLAMclip.py|
|`vad\_model`|`—`|WLAMclip.py|
|`wpm\_max`|`225.0`|WLAMclip.py|
|`wpm\_min`|`185.0`|WLAMclip.py|

## EVERY COMMAND, IN THE ORDER A JOB USES THEM

The whole runnable surface in one place. Everything runs from
`\~/.claude/skills/WLAM-clip-cutter/scripts`, and `WLAM\_WORK=<show folder>` points
the per-show state (cues, slate, project.json, captions) at that show instead of
at `scripts/` — set it for every command in a job, or set none of them.

```bash
export WLAM\_WORK=\~/.claude/skills/WLAM-clip-cutter/work/<show>
```

**This variable did nothing until 2026-09-09.** Every script read `QM\_WORK`; the
string `WLAM` appeared nowhere in the code. Setting the documented name left
`WORK` on its fallback - the `scripts/` directory - so the whole per-show set
(`slate.json`, `project.json`, cues, captions, `posters.json`) read and wrote the
DEFAULT folder while the operator believed it was pointed at the show. That is
the exact failure `build\_all.py`'s header describes: "it read the DEFAULT
directory's slate and started re-rendering a DELIVERED clip, which is the one
thing SKILL.md's first rule forbids". `scripts/posters.json` in the shipped tree,
naming a delivered clip, is the evidence it happened.

`selftest.py` could never catch it: it set `os.environ["QM\_WORK"]` directly, so
1141 checks exercised the mechanism and never the documented interface.

Both names are now read, `WLAM\_` first, so no existing shell breaks. The same
applies to `WLAM\_VOCAB` / `QM\_VOCAB` and `WLAM\_BROLL\_LIB` / `QM\_BROLL\_LIB`.

**Set up the show**

```bash
python3 analyze.py "/path/to/video.mp4" --out \~/Desktop/"Quasar Markets Live MM.DD.YY"
python3 newjob.py \[--apply]          # archive a finished job, clear the work dir
python3 speakers.py <transcript>     # inspect the stream's own speaker labels
python3 speakers.py <transcript> --map   # just the name -> tile mapping
```

**Pick the moments**

```bash
python3 pick.py                      # candidate spans that open and close on an idea
python3 pick.py --mode conversation  # only spans whose layout offers that template
python3 pick.py --gap 10 --dirty --full
```

**B-roll**

```bash
python3 broll.py propose             # candidates -> slate, nothing downloaded
python3 broll.py preview <terms>     # a contact sheet for bare terms
python3 broll.py fetch               # download + bake what you approved
python3 broll.py vocab               # what the library has taught the tool
python3 broll.py retire <fragment>   # unlearn a pairing, delete the bake
python3 broll.py learn <slate.json>  # backfill anchors from a shipped show
python3 broll.py sweep \[--apply]     # re-bake anything short of BAKE\_HOLD
python3 broll.py size | prune-src    # what the library costs on disk
```

**The b-roll library's default path still names the old skill folder**
(`\~/.claude/skills/qm-clip-cutter/broll-library`). If the skill lives in a folder
called `WLAM-clip-cutter`, the default misses the library and every search comes
back empty with no error explaining why. Set it explicitly:

```bash
export WLAM\_BROLL\_LIB=\~/.claude/skills/WLAM-clip-cutter/broll-library
```

**Check before rendering**

```bash
python3 preflight.py                 # the whole slate, no ffmpeg, seconds
python3 checkdupes.py                # two clips carrying the SAME SPEECH - build_all runs it
python3 fillercheck.py               # what the clean decode deleted. REPORT ONLY, cuts nothing
python3 verify\_turns.py <slug>       # REQUIRED for a follow clip - see below
python3 verify\_turns.py --start S --end E --samples 4
python3 railcheck.py                 # the camera rail on a share layout
```

**Render**

```bash
python3 build\_all.py                 # preflight, then render - refuses on a fail
python3 build\_all.py <slug>          # just that clip
python3 build\_all.py --force         # render anyway, and say so loudly
python3 make\_sheet.py                # the posting sheet
```

**Regression and measurement**

```bash
python3 selftest.py                  # 1141 checks, seconds
python3 selftest.py <clip.mp4|dir>   # ...plus the non-negotiables on a real file
python3 vocabcheck.py fires --top 40 # which terms actually win groups
python3 vocabcheck.py save <name>    # snapshot before a vocabulary change
python3 vocabcheck.py diff <name>    # what the change displaced, group by group
```

**Growing the vocabulary** (see "THE MASSIVE VOCABULARY RUN")

```bash
export WLAM\_VOCAB=/some/scratch/dir            # where the agent output lives
python3 vocab\_merge.py                       # validate + dedupe -> additions.json
python3 vocab\_merge.py --write
python3 vocab\_apply.py                       # report the splice
python3 vocab\_apply.py --write               # splice it in, verified by re-import
```

`references/vocab-rules.md` is the brief those agents are given — the four
destinations, the term style, and the hard rules. Hand it to anything writing
vocabulary, and let `vocab\_merge.py` be the thing that actually enforces them.

**The one command a follow clip cannot skip.** `render()` refuses a
`conversation` or `conversation\_share` clip without `"speaker\_verified": true`,
because the schedule's own confidence was measured at 69% confident and 43%
correct. Run `verify\_turns.py`, read the sheet, then set the flag.

## Settings, and the ones added on 2026-08-28

Everything below lives in `project.json` unless it says per-clip.

|key|default|what it does|
|-|-|-|
|`speaker\_transcript`|—|path to the stream's own labelled transcript; beats every other route to who-is-talking|
|`speaker\_names`|—|`{"Stephen Flanagan": "flanagan"}` when the platform's names do not match the tile names|
|`speakers`|—|**per-clip**, `{"<tile>": {"name":…, "title":…}}` so BOTH people in a conversation get a nameplate|
|`speaker\_verified`|`false`|**per-clip**, records that a human read `verify\_turns.py`'s sheet. Follow clips refuse without it|
|`allow\_crosstalk`|`false`|**per-clip**, ship a conversation clip above `BANTER\_MAX` short cues/min anyway|
|`drift`|`true`|the slow continuous move under the punch|
|`drift\_overscale`|`0.04`|how much margin the drift has to move inside|
|`drift\_amp\_x` / `drift\_amp\_y`|`14` / `18`|travel in panel px|
|`drift\_period\_x` / `drift\_period\_y`|`7.0` / `11.0`|speed is `4\*amp/period` — 8.0 and 6.5 px/s|
|`drift\_bias\_y`|`10.0`|raises the face slightly on average; the safe direction for chins vs chrome|
|`grade`|`true`|the light contrast/saturation lift on the face|
|`grade\_contrast`|`1.03`|keep it under \~1.10 or it stops being siblings and becomes a look|
|`grade\_saturation`|`1.05`|same|
|`face\_crop\_x`|measured|now derived from the FACE, not the frame centre. A value equal to the geometric centre is treated as the old auto-written default and stepped over|

## References

Read these when the relevant thing comes up — they carry the reasoning, which
is what stops someone undoing a decision that was made from evidence.

* `references/look.md` — the type, colour and layout system, where each value
came from, and how to retarget it to a different brand.
* `references/cut-mechanic.md` — why the retention cut is a **removal** and not
a freeze, how it was measured, and the three things it depends on.
* `references/pipeline.md` — what each script does, the config keys, the
whisper and ffmpeg gotchas, and how to debug a clip that came out wrong.

