# The retention cut

**It removes footage. It does not add a hold.** Clips come out *shorter*.

This is the one thing in the skill most likely to be got backwards, because
"pause for retention" sounds like inserting a pause. It is the opposite: at the
end of a sentence, about a quarter second of the natural pause is cut out, so
the next line starts on the join. Speech runs straight through and the picture
snaps.

## How this was established

Two wrong versions shipped first — a 0.4s freeze, then an 80ms freeze. Both
read as glitches. The reference (a Ron Insana reel) was then measured rather
than eyeballed:

- Frame-to-frame difference over the reel area found **three cuts in 13.6s**,
  roughly every 3.6s, spiking 15x over the baseline.
- Audio sliced in 40ms windows straight through each cut showed **speech
  running continuously with no silent trough**.

A freeze shows the opposite on both counts: frames identical across the hold,
and a silent gap bracketed by speech. Continuous audio across a visual
discontinuity is a removal. That is the whole diagnosis, and it is worth
re-running on any new reference someone offers.

## Cut only real silence

Whisper's word-level timings are **contiguous by construction** — a word's end
*is* the next word's start. The "gap" between words is an artefact, not silence.
Cutting on it clips speech.

So the removal is found in the waveform. `find_removals()` computes a 10ms RMS
envelope, then for each sentence end:

1. walks **forward** to where speech actually resumes (energy back above
   threshold and staying there for 40ms),
2. walks **back** from there to where the pause began,
3. removes up to `CUT` seconds **butted against the resuming speech**.

Step 3 matters. An earlier version took the removal from the middle of the
pause, which left silence either side and put the cut in dead air — the audit
showed silence both before and after the join, unlike the reference. Anchoring
to the resumption gives silence-before / speech-after, which is what a trimmed
pause sounds like.

A fixed search window is not enough either: pauses run past it, so its far edge
is not the real end of the silence.

## Three things it depends on

**Quantise to whole source frames.** `trim` snaps to frame boundaries. At an
unquantised 0.38s the drift reached 0.2s across one clip and the captions slid
off the words. `CUT` is expressed in frames (`cut_frames` in project.json).

**Render at the master's own frame rate.** Converting 25 to 30 duplicates
roughly every fifth frame, and that pulldown judder is indistinguishable from —
and masks — a short edit. Measured on one clip: 4 to 6 scattered frame holds per
half second at 30fps output, versus exactly the intended ones at 25fps. All
three platforms accept 25.

**Word timings must be remapped onto the shortened timeline**, or the captions
drift. `apply_removals()` maps each word through the removal set; a time inside
a removed window collapses to that window's start.

## Tunables

| key | default | what it does |
| --- | --- | --- |
| `cut_frames` (project.json) | 6 (0.24s at 25fps) | how much to remove. Raise it to collapse pauses harder. |
| `resume_window` (project.json) | 1.60s | how far past a sentence end to look for speech resuming |
| `MIN_AIR` (qmclip.py) | 0.10s | skip the cut unless there is at least this much real silence |
| `MIN_SPACING` | 1.10s | never cut twice inside this window |
| `--no-beats` | — | render straight through, no cuts |

## Interviews need both tunables raised

The defaults were set on a solo webinar. A conversation leaves bigger holes — one
speaker finishes, the other takes a beat before answering — and on those two things
go wrong at once:

**A pause longer than `resume_window` is not shortened at all.** The forward search
gives up, `resume` comes back `None`, and the cut is skipped. So the *longest* pause
in the clip, the one most worth trimming, is precisely the one that survives. On the
AI Matters clip a 1.88s hole sat 1s in and the 1.60s default sailed straight past it.
Raise it to about 2.5 on an interview.

**`cut_frames` of 6 barely touches a 1.9s hole.** Removing 0.2s of it leaves 1.7s of
dead air at second one of a short clip, which is retention death. That clip used 36
(1.2s at 30fps), leaving a 0.68s beat — a crisp pause after a cold-open declarative
rather than a gap.

Raising `cut_frames` is safe because the removal self-limits to the air that is
actually there (`take = min(CUT, air - 0.04)`), so a pause with only 0.3s in it still
only loses 0.26s. It changes the long pauses and leaves the short ones alone.

## What it cannot do

Where the speaker happens to be physically still through a pause, the join is
near-invisible. There is no way to manufacture a jump without clipping speech,
and clipping speech is worse than a soft cut. Expect roughly half the cuts to
show a strong visual snap and the rest to just tighten the pace.

## Verifying it on a new render

Confirm the mechanic rather than assuming it. Sample frames either side of each
join: the picture should change more than typical motion, and audio measured in
short windows should show silence before and speech after. If you see identical
frames and a silent gap, something has reintroduced a freeze.


## No silence, ever — the guarantee on top of the retention cut

The retention cut is about pacing. This is about a promise: **a viewer must never
be watching someone not talking.** They are different passes and both run.

`find_removals` alone cannot deliver it. It only cuts at sentence ends, takes at
most `cut_frames`, and abandons a pause when speech does not resume inside
`resume_window`. On a live markets show the host goes quiet mid-thought to read a
chart, so the longest holes have no sentence end in front of them and outrun the
resume window — exactly the ones that get skipped. One 40s clip came back **31%
silence**, including a 4s hole near the front and a 4.2s dead tail.

`collapse_silence` works straight off the RMS envelope and squeezes EVERY silent
run down to `KEEP_AIR`, ignoring sentences entirely. `merge_windows` unions the two
sets before `apply_removals` — they overlap, and `remap()` sums over the windows,
so an un-merged overlap is subtracted twice and the whole timeline drifts.

**The floor matters more than the algorithm.** Measured across four clips off one
master: speech sits at about -16 dB (85th percentile), real silence at -60 to -85.
The first attempt put the floor 35 dB under speech, which lands at -51, and room
tone lives above that — so a 1.3s dead tail passed the check and still shipped. It
is 28 dB under now, about -44, clamped to [-46, -40].

**Detect speech as a sustained run, not a frame.** A single 10ms transient clears
any threshold; one -43 dB click nine seconds into dead air was enough to defeat the
out-point trim entirely. `last_speech()` requires 0.15s continuously above the floor.

**And trigger the out-point trim generously — 1.2s, not 0.6s.** At 0.6s it ate the
"right?" off "There's no protection in crypto, right?", which was that clip's whole
hook, because a quiet trailing syllable dips under the floor for about that long.
The trim is there to catch a clip running SECONDS past the last word, not to shave
a soft final one.
