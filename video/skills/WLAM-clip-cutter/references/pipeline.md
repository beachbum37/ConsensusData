# Pipeline, config and gotchas

## The scripts

| script | does |
| --- | --- |
| `analyze.py <video>` | probe, transcribe, write `project.json`, `cues.json`, `transcript_compact.txt`, `sections.json`; detect two-up and emit per-half crops |
| `qmclip.py <slug> <start> <end> <hook>` | render one clip; also the module everything imports |
| `build_all.py [slug...]` | render the slate, or named slugs |
| `make_sheet.py` | build `POSTING-SHEET.html` from the slate |
| `endcard.py` | the 4s closing card; `append()` puts it on a finished clip, `python3 endcard.py out.mp4` renders it alone to look at. Switches at the top: `ENTRANCE`, `TYPE_STYLE`, `WIPE_WHITE`, `WIPE_CORE` |
| `faces.py` | finds the face in a column and returns a framed crop; `python3 faces.py video.mp4 x0 x1 at` |
| `glass.py` | glass letterforms for the card; `python3 glass.py out.png "text"` to see one line |
| poster frame | `qmclip.poster()` writes `<clip>.jpg`, the still the feed shows before play |
| `endcard_audio.py` | synthesises the card's whoosh — the FALLBACK for a missing `swipe.mp3`, not the shipping sound. Reach for `endcard.card_audio()`, never this directly |
| `preflight.py` | every check, before a render. Also `check_picture`, which reports each insert's recorded luma/motion and warns only when an asset never went through a pass |
| `broll.py sweep` | library maintenance. `--treatment` re-bakes a still whose pan plan changed or a video whose push decision changed, `--exposure` corrects luma outside the band, `--metrics` records luma/sat/motion on every row, `--recorrect` re-bakes from src everything carrying an `eq`. All report first; `--apply` writes |
| `newjob.py` | end a job: archive this show's state into `<out_dir>/_project/` and clear the working directory. Reports first; `--apply` moves |
| `whospeaks.py` | which camera tile is talking over a span, by mouth motion against the audio. The measurement the duo punch decision was made from |

## QM_WORK — where a show's state lives

`project.json`, `slate.json`, `cues.json`, the transcripts, `audio16k.wav` and
`tmp/` belong to ONE video. They default into `scripts/`, which is why the last
job's state used to sit there until the next one overwrote it. Set `QM_WORK` to a
directory and the whole set moves there:

    QM_WORK=~/Desktop/"Quasar Markets Live 08.23.26" python3 broll.py propose

Unset, everything resolves exactly as it always did, so it cannot break a job in
flight. `newjob.py` is the other half for a job that ran in the default place.
`HERE` still means the CODE directory in every script; only per-show paths follow
`QM_WORK`, and `broll-library` never does — it is shared across every show.

`analyze.py` **overwrites `project.json`** every run, so any hand-tuned
`cut_frames` / `resume_window` / `head_crop` is lost. Re-running it on a source you
have already tuned (to refresh the section map, say) means copying those keys back.

## project.json

| key | meaning |
| --- | --- |
| `source` | the master video |
| `out_dir` | where clips land (may contain spaces; only the build dir may not) |
| `model` | whisper weights; defaults to `~/tableflip-app/data/models/ggml-large-v3-turbo.bin` |
| `fonts` | font directory; defaults to the skill's own `assets/fonts` |
| `src_fps` | master frame rate — output matches it, never raise it |
| `cut_frames` | retention cut length in source frames |
| `resume_window` | how far past a sentence end to look for speech resuming (default 1.60s). A pause LONGER than this is not shortened at all — the search gives up. Interviews leave bigger holes than a solo talk; raise it to ~2.5 or the longest pause in a clip is the one that survives |
| `cta` | the address, used by the closing card and the in-body line |
| `endcard` | append the 4s closing card (default true) |
| `cta_in_body` | show the address inside the clip too (default: only when `endcard` is false) |
| `hook_hold` | how long the hook card holds before it leaves (default 3.0s) |
| (code) `HOOK_IN` / `HOOK_OUT` | the card's 0.30s swipe-in from the right and 0.233s swipe-out to the left; `HOOK_PREF` (300, 660) is where it wants to be, `HOOK_MIN_TOP` 140 / `HOOK_MAX_BOTTOM` 1090 where it may go; `panel_faces()` + `place_hook()` decide per clip |
| (code) `tools/backplate/` | the prompt, the rejected concepts, and `measure`/`lumamap`/`trace`/`conform` — everything needed to replace the card's plate |
| (code) `BROLL_IN` / `BROLL_OUT` | the cutaway's 0.333s rise from below and 0.300s swipe-left out, both smoothstep and both on even pixels; `BROLL_HOLD` 4.2, settling 3.57s |
| `punch` | the B framing's scale about the face (default 1.06; 1.0 turns the punch-ins off) |
| `punch_open` | seed the FIRST framing change into the opening instead of waiting for a join (default true; `PUNCH_OPEN_LO/HI` 0.8-2.0s, `PUNCH_OPEN_AT` 1.2s) |
| `cap_size` | caption point size; `write_srt` and the burn-in both read it, so they chunk identically |
| `adaptive_captions` | pick the caption colour from the picture (default true). Set false to pin the house cyan for a whole set |
| `adaptive_speed` | measure each clip's words per minute and pull it toward the band (default true). Set false to render everything at 1.00 |
| `wpm_min` / `wpm_max` | the target band, 185 to 225 by default. Calibrated off 44 delivered clips whose median is 197 |
| `speed_max` / `speed_min` | the caps, 1.12 and 0.96. Past about 1.15 a time-stretch starts to be audible |
| `app_min_frac` | the least of the panel a share clip's app band may have (default 0.52) |
| `layout_version` | which generation of the layout this project was authored against. 2 is the full 9:16 panel with captions on the picture. Missing means 1, and the renderer warns that its output will not match anything delivered from it |
| `face_crop_x` | horizontal offset of the default camera crop — centred by default; shift it if the subject sits off-centre. **It is an offset for a specific crop WIDTH**, so a value written under an older panel no longer centres what its author centred: at 9:16 the crop is 608 wide, not 748 |
| `head_crop` | `[w,h,x,y]` overriding the centred crop entirely. Needed on a **two-up master**, where the centre of frame is the seam between the two speakers, so the default crop lands half on each face. Set it to the speaking half. Keep w/h at the panel aspect — **0.5625**, the panel being the whole 9:16 frame. Anything else is re-cut by TRIMMING width from both sides, never stretched, so a crop authored at 0.9 quietly loses a third of itself. Re-author it; do not rely on the trim |
| `duo_crops` | `[[w,h,x,y] top, [w,h,x,y] bottom]` for `mode: duo`, both speakers stacked. Keep w/h at the BAND aspect, `PANEL_W / ((PANEL_H - 14) / 2)` = **1.133** at 1080x1920. Derive it rather than copying a number — this entry read 1.82 while the real figure was 1.397 |
| `share_crop` | `[w,h,x,y]` of the shared screen minus browser chrome and the PIP gutter. **Crop it to the CONTENT, and do not overshoot** — the app is fitted, never trimmed, so its own aspect decides how tall it lands, and a crop that runs a few pixels past the slide picks up whatever is behind it. The outermost 2% is dropped when the band is being filled, which absorbs a small overshoot but not a large one |
| `app_min_frac` | the least of the panel the app's BAND may have (default 0.52). It stops the face taking every pixel the panel gained; it does not make the app itself bigger |
| `pip_crop` | `[w,h,x,y]` of the speaker's camera tile, inside the meeting furniture. Its aspect drives the face band: the packer holds the band within 12% of `band_width x h / w`, the one height that crops nothing off the tile. **Include the name badge** if the tile burns one in — the trim is bottom-anchored so it survives |
| `face_h` | height of the face band in the split; keep it matched to `pip_crop`'s aspect |

`head_crop`, `share_crop` and `pip_crop` are the only genuinely per-recording
numbers. Find them from a real frame rather than reusing the defaults.

## Layouts, and the one test that lies

`detect_sections()` returns three modes and runs its tests **in this order**:

1. **`two_up`** — two speakers side by side, found from the dark vertical divider
   at frame centre (`find_seam`). Reliable; a single camera never has one.
2. **`share`** — a shared application. Needs **two** things at once: it *looks* like
   an app, **and** there is a hard vertical gutter where the camera rail meets it.
   "Looks like an app" is itself two cases, because a LIGHT app (browser chrome) and
   a DARK app (a trading terminal) are opposites — a bright low-variance strip along
   the top, or a dark frame bulk with the camera tiles the only lit thing in it.
3. **`head`** — anything else: one camera, full frame.

The order matters. Brightness came first originally, and on the AI Matters master it
inverted the entire map: every solo shot of a guest backlit by a window came back
`share`, and every genuine two-up came back `head`. The two-up test now wins outright.

**Why brightness alone can never settle it.** Each app signature has a doppelganger
in ordinary camera footage: a white wall behind a speaker reads exactly like browser
chrome, and an unlit room reads exactly like a dark terminal. Both misfired on real
masters — the dark case swallowed 25 minutes of genuine terminal on one video and
invented four solo stretches on another. What a composited share has and a room does
not is the **hard vertical edge** at the rail. `rail_gutter()` measures the strongest
luma cliff in the rail-edge zone on either side; a room scores 7 to 21 and a genuine
share 23 to 119, so the rule is `looks_app and gutter >= 22`.

Checked against 16 hand-labelled frames across four masters: **16/16**, where
brightness alone got 12/16.

The limit worth knowing: a share with **no camera on screen at all** has no rail and
will be missed. That is the right failure — such a stretch breaks "the speaker's face
is on screen" anyway and is not clip-worthy in share mode.

**Why the divider and not, say, comparing the two halves:** the divider is a
property of the compositor, present in every two-up frame regardless of what the
speakers are doing, so one column profile settles it. Measure only the *contiguous*
dark run through centre — collecting every dark column in a window swallows dark
hair or a shoulder at the inner edge of a half and reports a divider far wider than
it is, which then crops real picture away.

On a two-up, `analyze.py` writes `two_up_seam` plus `head_crop_left` and
`head_crop_right` into `project.json`. Those keep each half whole, bottom-aligned so
a burned-in lower-third badge survives. Put the speaking one on the clip as
`head_crop` and render `mode="head"`. Do not try to make `mode="share"` do it —
that mode stacks two crops for a slide deck plus a camera tile, a different problem.

**`head_crop` is per clip, not per project.** On an interview one clip is the guest
and the next is the host, so a single global setting cannot serve both. The slate
entry wins over the project default.

### Tightening a half for a bigger face

The generated hints keep as much of the half as a 9:16 panel can take. To enlarge
the face: keep the bottom at frame height, shrink the height, set width to
`0.5625 x height`, and centre x on the face. Note the taller panel already takes the
upscale from 1.44x to 1.78x, so there is less headroom for tightening than there was. Then **check the name badge survives** —
measure its text extent and stop at the box edge rather than cutting through it. On
AI Matters the badge text spanned x1002..1328, so a crop from x990 kept the name
intact while the box bled off the panel edge, which reads as deliberate.

Find the face by **motion energy**, not skin tone: average `abs(diff)` across a few
seconds of frames and take the dense region. Skin-tone thresholds pick up warm
walls — on this master the room was beige and the detector returned the whole half.
Motion has its own trap: on a set with a live scoreboard or a TV behind the speaker
it locks onto that instead, so restrict the search to the upper two-thirds.

### Which of them is talking

Never guess. Cropping to the wrong half is 30 seconds of a silent face, and on a
screen share the two PIP tiles are small enough that mouth motion alone is
inconclusive. **Correlate each face's motion against the audio envelope** — the
speaker's mouth moves when there is sound, the listener's does not:

```python
env  = per-frame RMS of the clip's audio          # at, say, 10fps
mot  = per-frame abs(diff) of a mouth-box crop    # same rate
score = np.corrcoef(mot[:k], env[1:k+1])[0, 1]    # env lags by one frame
```

The higher score is the speaker, and the gap is usually unambiguous (+0.27 vs -0.09
on a pair of PIP tiles where raw motion had them tied at 4.1 vs 4.0).

## Crops come from face detection

`faces.py` runs OpenCV's bundled frontal-face cascade over ~14 sampled frames and
keeps the **median** box — any single frame can catch a blink, a turn, or a hand
across the mouth, and one bad frame would place the crop for the whole clip.
`analyze.py` uses it for `head_crop_left/right` and `duo_crops`.

Requires `opencv-python-headless<5`. **The pin matters**: 5.0 removed
`CascadeClassifier` and ships no cascade data at all, so it silently cannot detect
anything.

Two heuristics were tried first, and both are worth knowing about because they look
reasonable and are not:

- **motion alone** — a talking head moves and a wall does not, but a TV, a ticker
  board or a live scoreboard behind the speaker moves *more*, and the box lands
  on that.
- **motion x skin** — cancels the scoreboard, but a neck, a hand resting on a chin
  and a lit collar are all moving skin. On a real clip the peak landed on the
  speaker's collar.

**Anchor the crop on the face's CENTRE, not an edge.** Placing it by the top (for
headroom) or the bottom (for the chin) breaks as soon as the head is bigger than the
crop, which is most close-ups — an early version sat 200px low on every one of them.

Sanity check: on the David Russell master the auto crops came out within a pixel of
the hand-tuned ones horizontally, and better vertically — they kept the guest's name
badge in frame, which the hand version had cut.

## ffmpeg on this machine

**No libass, no drawtext.** The Homebrew build has neither, so `subtitles=` and
`drawtext=` both fail with `Unknown filter`. Every glyph is rasterised with
Pillow and composited as an image layer. For the word-by-word captions only the
unique states are drawn; the per-frame sequence is built from **hard links**, so
a 40s clip costs about 100 renders rather than 1000.

**The filter-graph parser treats literal quotes as data** and splits option
values on unescaped whitespace and `:`. Do not quote paths inside
`-filter_complex`. Run ffmpeg with `cwd` set to the build dir and use short
relative paths. This is why the build dir must have no spaces.

## whisper

**Word-level timing needs `-ml 1 -sow`.** The plain segment JSON has none.

**Word-level decoding is unreliable for punctuation.** On some spans it returns
the whole thing lowercase with no full stops — two clips came back that way,
which broke the caption casing *and* left no sentence ends to cut on, so both
rendered with zero cuts. The segment pass punctuates the same spans correctly,
so `restore_case()` aligns the two with `difflib` and takes casing and
punctuation from the segment text while keeping word-level timing.

**It fails the other way round too, and then the reference is the problem.** On
the AI Matters master the *segment* pass came back all-lowercase and entirely
unpunctuated for all 23 minutes while the word pass was clean — correct sentence
case, full stops, and `SolarWinds` / `Salt Typhoon` spelled right unprompted.
Aligning against that reference *downgrades* good text.

**This is now checked, not assumed.** `reference_usable()` measures the whole
`cues.json` and ignores it when under 2% of tokens carry a capital or there are
essentially no sentence ends; `analyze.py` warns about the same thing at transcribe
time. Judged over the whole file rather than the span, because a short span can
legitimately have no capital and no full stop.

Worth knowing **why this needed a code fix rather than a note.** The failure is
silent and doubly damaging: bad casing in the burned-in captions, *and* no sentence
ends for `find_removals()` to cut on, so the clip also renders with zero retention
cuts and nobody notices the pacing is wrong. It bit twice — the second time was
re-running `analyze.py --skip-transcribe` to refresh the section map, which quietly
regenerated the `cues.json` that had been moved aside, and the next render came out
18.4s and lowercase.

**A long span decodes flat, a short one does not.** On a 43s duo clip the word pass
came back **2.4% capitalised with zero sentence ends**, while hand-run 12s windows of
the same audio were properly punctuated. That costs the caption casing *and every
retention cut*, since cuts are placed on sentence ends - the clip renders with none
and nobody notices the pacing is wrong.

`word_times()` now checks its own output (`_punctuated()`) and, if flat, re-decodes
in ~14s chunks and stitches them. **Chunk boundaries are placed at the quietest point
near each target** (`_quiet_split`, off the same RMS envelope the cuts use) rather
than at a fixed stride, so an edge never lands mid-word. It only does this when the
first pass came back flat, so the normal case costs nothing.

**Word-level whisper emits a bare `-` where it thinks the speaker changed.** On an
interview master that lands on the first token of a clip and burns in as
`- It's already there.` Tokens with no letters or digits are filtered in
`word_times()`.

**`cues.json` must sit next to the scripts** — that is the reference it aligns
against. Without it the renderer still works, but any span whisper decodes flat
stays flat.

**Proper nouns are wrong out of the box.** `TERMS` (single tokens) and `MERGES`
(phrases, where the replacement may be a different number of words than the
source) hold the corrections. Matching is case-insensitive and splits trailing
punctuation off first — matching the raw token fails on `"sell."` while
succeeding on `"sell,"`, and the sentence-final case is the one that matters.

## Debugging a clip that came out wrong

**Captions drift from the words** — something changed the timeline without
remapping word times, or `cut_frames` is not a whole number of frames.

**Hook runs past its band** — measure it rather than squinting: read the hook
plate's alpha and find its lowest non-transparent row, then compare to the plate's
own `band_h`. The fit loop shrinks the type until the block fits and should prevent
this. (There is no separate overlay PNG any more, and `PANEL_Y` is 0 — the panel is
the frame.)

**Captions sink into the background** — read the `captions:` line the render prints:
it gives the measured luminance, hue and chroma of the caption zone and the accent
those chose. If the numbers look nothing like the picture, the probe sampled the
wrong rectangle; check the `fg` chain it ran through. If they look right and it
still reads badly, force it with `"cap_colour"` on the clip. **Do not fix it with a
plate or a scrim** — see look.md for why that band is not coming back.

**Captions cover the lower speaker in `duo`** — expected, and an accepted cost of
the caption position. The band starts at y1130 and the duo seam is at y953, so a
face anywhere natural in the lower band is under the words. The fix is a `head` crop
for that moment, not moving the captions.

**Clip looks like a screen recording** — `share_crop` is including browser
chrome. Re-crop below it.

**Face band is blocky** — `face_h` is stretching beyond `pip_crop`'s native
aspect. That ceiling is in the source; do not fight it.

**Levels inconsistent across clips** — `loudnorm` is single-pass and lands
around -15.5 to -16 LUFS. Consistency across the set matters more than hitting
-14 exactly; platforms renormalise anyway.

## Checking a finished set

Worth doing before handing over: confirm every clip is the right dimensions and
frame rate, that integrated loudness sits within about a dB across the set, and
that the burned-in captions of at least the flagship clip read correctly
word for word. A contact sheet of one frame per clip catches layout breaks in
one look.


## audio16k.wav belongs to ONE video, and nothing used to check which

`analyze.py` extracts the whole master to `scripts/audio16k.wav`, and every clip
decodes its words out of that file. `project.json` names the source video, but
until this was fixed **nothing tied the two together**. Point `project.json` at a
different master without re-running `analyze.py` and the render takes its PICTURE
from the new video and every WORD from the old one, at the same timestamps.

It does not error. It does not look wrong in the build log. The clip comes out
with confident, fluent, correctly-timed captions belonging to a completely
different conversation. It happened: a clip of the host talking about MCP servers
rendered with a guest's natural-gas commentary burned into it.

`qmclip.ensure_audio()` now runs at the top of every `render()` and compares the
WAV's duration against the source's, re-extracting on a mismatch:

```
note: audio16k.wav is 1312s but QM Live 07_31_26.mp4 is 3682s - it belongs to a
different video. Re-extracting.
```

**When you switch projects, swap all of it**: `project.json`, `slate.json`, and
delete `sections.json`, `cues.json` and `transcript*` — those are per-video too.
`sections.json` is the worst of them, because `check_layout` will happily validate
a span against another video's layout map. Archive the set into the output folder
as `_project/` so a clip can be rebuilt later.

## The word-level pass drops words the segment pass hears

`-ml 1 -sow` (word timings) is a different decode from the plain segment pass, and
it is noticeably worse at unstressed function words. On one clip it left a 0.77s
hole between "going" and "to" and burned in "what are you going to the grocery
store?" - broken English on screen. The plain decode of the same 3 seconds returns
"what are you going to **do at** the grocery store" cleanly.

Look for it as a **timing gap**, not as bad text: dump `tmp/<slug>.json` and any
inter-word gap over ~0.5s in continuous speech is a dropped word. A `MERGES` entry
repairs it, because `_respan` spreads a longer replacement across the matched span.


## Live tape-watching shows: most of the runtime is unusable

A daily markets show is not an interview. Long stretches are the host silently
watching the tape, and **whisper hallucinates fluent filler over silence** - the
same short line repeating dozens of times ("Thank you.", "We'll be right back.",
"It's over the last bid here"). On one 61-minute master roughly nine consecutive
minutes were dead air rendered as speech. Treat a repeating line in
`transcript_compact.txt` as a silence marker and never pick a span inside one.

The other constraint is compliance, and on this kind of show it removes more
material than quality does. Out of 36 candidates swept from one hour, 17 died -
almost all on spoken share prices, the host's own fills, or a performance boast.
Recurring killers worth grepping for before you fall in love with a span:

- a fill or a level: "I am out at 52.50", "now we're at $102 a share"
- a performance boast: "we crushed it", "we've made more money than I've ever made"
- his own book: "I went long Apple on that dip"
- claimed private access: "I had chats with two members of Congress"

Spans are often boxed in by these on both sides, so **check 30s either side of an
in/out point**, not just inside it. On that master the best line in the show (a
Buffett paraphrase about transferring money from the impatient to the patient) was
unusable because compliant material around it ran only 24 seconds.


## The reference transcript is decoded in CHUNKS, and collapsed chunks are re-decoded

`analyze.py` used to transcribe the whole master in one whisper call. Whisper
degrades over a long input: on a 13.8 minute master that pass came back **0%
capitalised with zero sentence ends**, so `reference_usable()` rejected it, and the
pipeline fell back to the word-level pass - which is a materially worse
transcriber. Essentially every caption error hand-corrected in `TERMS`/`MERGES`
came from that fallback: "the artwork" for "the R word", "training stations" for
TradeStation, a guest called "Mark" when he is Mike, a dropped "do at".

It now splits at quiet points into ~90s chunks (`REF_CHUNK`) and decodes each.
Same master, after: **14.6% capitalised, 197 sentence ends**, `reference_usable()`
True, and "the R word", "Warsh", "Powell" and "Tuttle" all correct with no
corrections at all.

**The collapse is intermittent, not content-driven.** Two of ten chunks came back
flat on the first run, and the identical audio decoded correctly on a re-run. So
`_healthy()` scores each chunk (needs >=3% capitals and at least one sentence end,
skipped under 20 words) and `_decode_healthy()` simply asks again, twice, then
falls back to splitting the chunk in half. On that master it re-decoded 2 chunks
and ended with zero collapsed.

Consequence worth knowing: with the reference trustworthy, `TERMS`/`MERGES` should
shrink over time rather than grow. Before adding a correction, check whether the
reference already has the word right - the entry may be papering over the old
fallback rather than a real mishearing.

## Layout: gallery is a real mode, and it is detected by EDGE POSITION

The old share test asked "is a shared app on screen" from brightness and the
longest straight line. It labelled a 76-second three-across **gallery** as a screen
share, which would have cropped a camera rail out of frames that have no rail - the
clip would have opened on eleven seconds of the wrong picture.

`layout_edges()` measures the vertical brightness STEP at two places instead:

- the **rail** zone, the outer fifth of frame either side
- the **gallery** thirds, at w/3 and 2w/3

A screen share reads about 30 against 3. A gallery reads about 7 against 125. The
ratio decides, and it is not close. Verified against a hand-built ground-truth map
of one 61-minute master: the detected gallery runs (987-1253, 1445-1500, 2003-2081)
land within a second of the measured ones.

`MODE_NEEDS` now includes `gallery`, and only `head` accepts it - `share` and `duo`
applied to a gallery crop a rail and a divider that are not there. A `head` clip on
a gallery span with no `head_crop` is refused outright, because the default centre
crop lands between faces.


## The camera rail re-flows inside a share run

`sections.json` tells you the frame is a screen share. It does not tell you where
the camera tiles are, and they move. The compositor drops a tile when that person
stops speaking, then re-centres and resizes whatever is left.

Measured on one master: two tiles spanning y278-801 for most of a minute, a single
tile at y410-669 for twenty seconds in the middle, then back. A `pip_crop` authored
for either arrangement renders a black gap for the other, and it shipped - the gap
sat under the speaker for a third of the clip.

`railcheck.py` reports it:

```
    1194.0 -  1208.0  (  14s)  tiles=[(272, 800)]
    1209.0 -  1228.0  (  19s)  tiles=[(408, 664)]
    1229.0 -  1255.0  (  26s)  tiles=[(272, 800)]
  -> RE-FLOWS 4 time(s).
```

`--windows` sweeps a whole run and lists only the stretches that hold still for at
least the clip floor. **Run it before picking, not after** - on that master only two
windows in a fifteen-minute share run qualified, and the best moment in the hour
straddled the boundary between them and had to be abandoned for a different one.

There is no fixed crop that survives a re-flow. Overlapping the two tile positions
does not work either: in the two-tile arrangement the shared rows are the speaker's
head, in the single-tile arrangement they are his chest.


## Whisper's lowercase collapse is LENGTH-driven, and it is partial

Two refinements after a master where the first three attempts all shipped a clip
reading "...for an absolute stone fact. because when i was on the trading floor all
the big banks had two brokers now our pit was so big".

**It is not random.** The earlier note assumed flakiness and re-asked for the same
window. On this master a 90s chunk came back flat every single time while the
identical audio in a 45s window decoded at 9.7% capitals with 11 sentence ends,
three runs out of three. So `REF_CHUNK` is 45, and `_decode_healthy` now HALVES a
failing window and recurses instead of asking again at the same size (one cheap
retry is kept for genuine flakiness).

**It is partial.** A chunk often reads correctly at the start and goes flat
partway through, which averages out to a passing score. `_healthy()` and
`_punctuated()` both judge in sub-windows now, so a stretch cannot hide behind the
good half.

**And the real fix is that alignment must never make text worse.** Even with all of
the above, a file can be healthy overall while one twenty-second stretch inside it
is flat - and `restore_case` takes casing FROM the reference, so aligning against
that stretch DOWNGRADED a word pass that had the text right all along. That was the
actual defect here: the word pass read "That's my opinion. I don't have a fact in
that" correctly, and the reference overwrote it in lowercase.

`word_times` now scores both over the span and skips the alignment when the
reference is flatter:

```
note: <slug> reference is flatter than the word pass over this span; keeping the
word pass.
```

`reference_usable()` remains a whole-file gate; this is the per-span one. Keep both.


## Audit, 2026-08-04: what was actually wrong

Seventy-three candidate defects, fifty-six survived refutation, and the two ranked
most severe went opposite ways when measured. Both lessons are worth keeping.

**The headline finding was wrong.** It was argued that the three split-mode packers
composite onto a `color=` source with no `r=`, that ffmpeg defaults it to 25fps,
and that every duo and share clip therefore judders. Measured instead: delivered
duo, share and head clips all decode 120 unique frames in 4 seconds with ZERO
duplicates, and a controlled A/B (`color` with and without `r=30` under an overlay)
produces zero duplicates either way - overlay takes its rate from the video input,
not the background. `r={FPS}` was added anyway because it makes the frame count
exact, but nothing was broken. **Measure before you fix.**

**The second finding was real and had already shipped.** `mute` windows were
applied by the caller into one `[amuted]` label, and `cut_graph` consumed that
label once per kept span. A filter OUTPUT may only be consumed once: ffmpeg 8
silently rebinds the second and later references to the raw input. Proven on a
tone - a mute at 2-3s inside the first `atrim` came out at -99 dB, the identical
graph with the mute at 6-7s inside the second `atrim` came out at -21.1 dB,
untouched. A shipped clip escaped only because its single mute happened to fall in
span zero. `cut_graph` now owns muting and `asplit`s the muted stream once per
span.

Also fixed in the same pass, each of which could ship a wrong clip silently:

- **`face_crop_x` was 474 where frame centre is 586.** The default head crop takes
  its WIDTH from the current panel (748px) but its LEFT EDGE from a value computed
  for the retired 972-wide box, so every single-camera head clip was cropped 112px
  left of centre.
- **An unknown `mode` failed open.** `MODE_NEEDS.get(mode, {names[0]})` defaulted to
  whatever layout the span was, so the guard was a no-op, and the dispatch chain
  ended in a bare `else` that is the share packer. `"mode": "two_up"` - a name
  sections.json actually uses - rendered as a share. Now rejected by name.
- **A hole in the layout map read as agreement.** `_runs()` drops runs shorter than
  its minimum without closing the gap, and `check_layout` only looked at runs that
  overlap the span, so a span crossing an unmapped stretch passed. It now demands
  gapless coverage.
- **Only `audio16k.wav` was tied to the source.** `cues.json` and `sections.json`
  are per-project too and were not, so a swapped master could align captions
  against the previous show's transcript. `ensure_audio` now clears them when it
  detects a mismatch.
- **`endcard: false` credited 4 seconds that were never added**, so a 41s span
  shipped as a 41s file under a 45s floor.
- **An empty hook crashed** with `max() arg is an empty sequence` after the whole
  whisper decode had been paid for. Now rejected up front.
- **`duo_share` could never derive its face band** - `face_h or DUO_SHARE_FACE` is
  never None, so `pack_share`'s deriving branch was unreachable and the app was
  always trimmed to fill.
- **opencv is not installed for `/usr/bin/python3`**, so every "measured" crop hint
  was a geometric guess and nothing said so. `faces.py` now warns loudly.
- **`("big","beat") -> "BigBeat"` was removed.** It fired on the bare token pair, so
  on a markets show it rewrote "a big beat on earnings". A merge that corrupts
  correct English is worse than one that never runs.

## B-roll sources, and the two keys

Six sources, tried in order, ranked by usable resolution with a bonus for video
and a double bonus for the house library:

| source | key | what it is good for |
| --- | --- | --- |
| `library` | none | anything approved on a previous show. Always ranked first - it has already been looked at and shipped. |
| Pexels video | `PEXELS_API_KEY` | lifestyle motion. Titles are usually EMPTY, so approve from the contact sheet, never the listing. |
| Pixabay video | `PIXABAY_API_KEY` | a second free motion library, a lot of genuine 4K, and its tags are real metadata - better filtering than Pexels video. |
| Pexels photos | `PEXELS_API_KEY` | rich alt-text sentences, so the reject list has something to bite on. Stills get the Ken Burns push. |
| Openverse | none | CC0 and public domain only. |
| Wikimedia | none | CC0/PD. Where the real NASA and agency photographs come from. |

**Keys live in `~/tableflip-app/.env`, mode 600 - never in `project.json`**, which is
archived into every delivered show folder, and never in the skill bundle.

Get a Pixabay key at pixabay.com/api/docs (free account, the key is on that page
once logged in), then add `PIXABAY_API_KEY=...` next to the Pexels one. Without it
`search_pixabay_video` returns an empty list and the other five carry the search -
silently, which is why `doctor` reports which keys are present.

**Ranking is library, then video, then stills** - a tier, not a weighting. A
plain 1.25x bonus for motion was tried first and never won: a 6000px photograph
outscored 4K video every time, so the format kept coming out as a slideshow.
Plain video-first was tried next and regressed the other way - for "spacex falcon
9 launch" it lifted a boy holding a toy rocket above the NASA photograph that had
already shipped. Hence the library on top: an approved asset is the only thing
here a human has actually looked at.

Inside a tier, hits sort by title relevance with **bigrams worth three unigrams**,
then by usable resolution (`min(w, h * 9/16)` - the columns that survive a 9:16
cover-crop, which is why a 1920-wide HD clip is worth only 608).

**Pexels video titles come from the page-URL slug.** The API returns `alt: null`
and `tags: []` on every video object, so `title` was empty from day one - which is
how a fireworks display outranked a rocket launch while "fireworks" sat in
REJECT_WORDS the whole time, unable to match against nothing. The slug carries the
caption: `/video/spectacular-nighttime-fireworks-display-29266990/`.

**Two filters exist because of what these libraries now carry.** AI-generated stock
is a large and growing share of both, and it looks synthetic on a phone; Pixabay
labels it in the tags, and that check is deliberately NOT routed through
`_rejected()` - that helper lets a reject word through when the word is part of the
query, and "AI" is a term this house says constantly. CGI and 3D renders go the
same way. Separately, the compliance reject list drops anything whose title says
trading, chart, candlestick, forex or crypto: a price on screen is a compliance
problem no matter how good the shot is.

**A candidate that cannot be previewed is never silently dropped.** If a thumbnail
404s - Pixabay has moved its thumbnail hosting more than once - `contact_sheet`
pulls a frame from the media itself instead. A candidate missing from the sheet is
a candidate nobody looked at, and approving one of those is how a child holding a
toy rocket once shipped as SpaceX.

## Helpers added 2026-08-22, and the bugs they closed

- `probe_panel(t, graph, nbytes, pix_fmt)` - decode THREE frames of the reframed
  panel and return the last. In `share`, `duo` and `duo_share` the chain
  composites onto a `color=` source and overlay is main-driven, so a one-frame
  probe returned the bare slate stack (luma 19 vs 32.6). Both
  `sample_caption_bg` (caption colour) and `panel_faces` (hook placement) read
  that blank frame before this; on a share clip the caption colour was being
  chosen off slate, not off the chart.
- `check_box(slug, key, box)` + `src_size()` - every authored crop is validated
  against the master's real size and named on failure. ffmpeg's crop CLAMPS x/y,
  so a pip_crop that ran past the frame rendered a different rectangle silently.
- `fit_geometry(box, bw, bh)` - the arithmetic under `fit_chain`, so preflight's
  PACK line prints the same drawn size the render uses (it was 40px off).
- `fill_crop` rounds to EVEN sizes; the head and duo re-cuts call it instead of
  carrying their own copies.
- `ensure_audio` clears cues/sections/transcripts only on a duration MISMATCH.
  A missing wav (fresh checkout, archived `_project/`) used to wipe a
  hand-written `sections.json`.
- `hard_out` is a real ceiling on the out-point in `render()` and in preflight.
- `endcard.append` keys its wav cache on the swipe file + filter + length and
  trims by sample count: the old keyless `endcard.wav` meant the 08-11 atrim fix
  never reached a delivered clip (first sound 71ms late), the preview overwrote
  it with the synthesised fallback, and every card's audio ended 46ms before
  its picture.
- `make_sheet` copy buttons on Titles and Tickers copied an empty string; the
  "Before you post" bullets come from `slate["notes"]` / a clip's `note`
  instead of four lines hard-coded from one August show.
- `hook_overlay(card_w, tempo)` - the card's travel as an overlay x expression
  plus the exit fade as a stream filter; `build_hook_sequence` returns
  `(frames, y, card_w)` and carries only the alpha ramp.
- `punch_windows(words, rem_sent, rem_sil, rem, inserts, body, tempo)` - the
  B-framing windows from the toggle ladder; `punch_enable()` the gate
  expression; `_punch_box()` the B crop; `reframe_chain(punch=...)` builds the
  split A/B chains in head and share. `BROLL_WINDOWS` is the module record of
  the last `broll_chain` call's (a0, a1), which the ladder reads. render()
  builds `fg0` (framing A) first for the face and colour probes, then `fg`.
- `fx_unit()` / `fx_ease()` - the easing curves as ffmpeg expression strings,
  one place, so every element moves on the same three.
- Caption sub-states: `build_caption_sequence` splits each word into per-frame
  pop states (`CAP_POP`, `CAP_POP_NUM`, `CAP_POP_HOLD`), deduped by
  `(word, scale)`; `render_caption_png(..., pop=)` draws the live word bigger
  with `anchor="mm"` on its own slot.
- The opening move lives in `punch_windows` as an event of kind `"open"` with
  a zero dwell, appended only when no `sent`/`sil` event already falls in the
  window. It goes through the same locks, frame snap and anti-double guard as
  every other toggle, so it can never land inside the hook card's travel or
  under a cutaway. `preflight`'s PUNCH line reports the FIRST change and warns
  when it is later than `PUNCH_OPEN_HI + 0.5`.
