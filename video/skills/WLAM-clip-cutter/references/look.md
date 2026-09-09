# The look

Every value here was read off the **computed styles** of the Quasar Markets
landing page (`COMPLETED QM PROJS/Quasar Landing NEW VERSION/index.html`),
rendered in a browser. Not guessed, and not taken from the CSS source — that
file declares `--display` and `--mono` twice and only the later block wins, and
it names Space Grotesk in a fallback stack that never actually loads. Grepping
it gives you the wrong answer with confidence.

If you ever need to re-derive it, serve the page and read
`getComputedStyle()` on the hero. Do not read the stylesheet.

## Type — Inter only

| role | font | weight | size | tracking | line height |
| --- | --- | --- | --- | --- | --- |
| hook headline | Inter | **400** | auto-fit, up to 128px | **-0.02em** | 1.02 |
| captions | Inter | 600 | 86px | 0 | 1.20 |
| closing address | Inter | 500 | 27px, uppercase | +3.0px | — |

Hook and caption sizes were raised twice (96 → 112 → 128, 70 → 78 → 86) after
viewing on a phone rather than a monitor: at thumb distance the old sizes were
legible but not *arresting*, and the hook is doing the whole job of stopping the
scroll. The second raise was paid for by taking the CTA out of the body.

The hero is Inter **400 at -2.72px tracking on 136px**, which is where the
-0.02em comes from. Display type in this system is *large and light*, not bold.

**Space Grotesk is banned.** A bold geometric display face paired with Inter is
the single strongest "AI made this" tell, and removing it was the explicit ask.
Captions sit at 600 rather than 400 purely for legibility on a phone; that is
the one deliberate departure.

**Sentence case** for display and captions. UPPERCASE is reserved for the closing
address — that is how the page uses it.

Pillow has no letter-spacing, and this look depends on it, so `draw_tracked()`
lays out character by character. That is why it exists.

**The hook wraps balanced, not greedy.** `wrap_balanced()` keeps the line count a
greedy fill would choose and then moves the breaks to even the lines out, by
minimising squared slack against the measure. Greedy packing strands orphans —
`Your data is already / there` — which reads as text that overflowed rather than a
headline that was set; balanced gives `Your data is / already there`. Do not
revert this to `wrap_tracked()` for the headline; that function is still there
because `wrap_balanced` needs it to pick the line count.

## Colour

| token | value | use |
| --- | --- | --- |
| slate veil | `#0e1319` | page background |
| carbon | `#101010` | panel letterbox |
| bone white | `#fffdf9` | all type — **never pure white** |
| muted | `rgba(255,253,249,.55)` | secondary type |
| accent | `#6f9fb2` | rules, marks |
| accent hot | `#9cc4d4` | rules and marks |
| caption key | **chosen per clip** | keyword caption words — picked against what is actually behind the caption zone. `#68d6ff` stays the house default and is kept whenever it survives |
| caption base | bone white, or ink over a genuinely bright zone | the body of the caption |
| caption stroke | the opposite of the base | a 5px outline on every glyph — this, not the colour, is what makes captions legible over live video |

The accent is a muted slate blue, deliberately not the bright `#38BDF8` cyan
from the qm-design skill. **This look is for video; qm-design still governs
terminals and dashboards.** They are allowed to differ — do not "unify" them
without being asked.

## Layout, 1080x1920

```
y    0..1920   video panel, 1080x1920 - THE PANEL IS THE FRAME
y    0.. 130   KEEP CLEAR - top strip. Nothing permanent, ever.
y  140..1090   hook: centred bone card ON the picture, first 3.0s only,
               placed per clip off where the face is (wants y300..660)
y 1020..1084   closing address, last 2.6s only (off when the end card is on)
y 1130..1430   captions, 86px, ON the picture, block centred on y1280,
               colour chosen per clip from what is behind them
y 1430..1920   KEEP CLEAR - platform chrome. TikTok is the worst at ~480.
x  920..1080   KEEP CLEAR below y900 - the right-hand action rail
```

There is no band above the picture and no band below it. Every number in the
KEEP CLEAR rows is a constraint imposed by the apps, not a taste call; the two
live rows are derived from them.

### The hook is a centred white card, and it finds its own place

**A bone-white box with slate type, centred, held 3.0s, then gone.** Not white type
on a scrim: over live video a scrim has to be heavy enough to carry white text
against a lit face, and by then it has dimmed the picture anyway. A filled card is
the same contrast with none of the murk, and it reads as a deliberate title rather
than as text dropped on a frame.

**Where it sits is measured per clip, not pinned (2026-08-22).** It used to be
pinned at y96, and two things were wrong with that. It sat inside the top strip
this file itself marks KEEP CLEAR: TikTok's chrome runs to ~140, Shorts' to
~288, and the 4:5 crop Reels and LinkedIn apply in the feed takes 285 off the
top, so the first three seconds of every clip opened with the headline clipped.
And in `share` the camera tile is at the top of the panel, so the card landed
straight across the speaker's eyes for three seconds - on the 08.21.26 McGlone
reference it covered his face to the nose. The owner's note was "the little
white box could be more centred", and the measurement agreed.

So `place_hook()` now does this, in order:

1. The card WANTS `HOOK_PREF` = y300..660, centred on y480: below every app's
   top chrome, inside the 4:5 feed crop, above the captions.
2. `panel_faces()` finds the face(s) in the REFRAMED panel - through the clip's
   own `fg` chain, exactly as the caption colour is sampled, because the
   question is where the face is in the 1080x1920 the viewer sees. OpenCV's
   frontal cascade over eight frames of the card's own window, clustered so
   `duo` gets two boxes.
3. Every face, padded 24px, is cut out of y140..1090 and the card takes the
   free band whose centre is nearest y480: ABOVE a face that sits low (`head`),
   BELOW a face that sits high (`share` - flush to the bottom of the band, as
   far from the face as it can get, which also clears the name badge most
   sources burn in under the chin), BETWEEN two (`duo`).
4. If no band is tall enough the card is re-set smaller, down to 84px type and
   no further; if it still does not fit it takes the tallest band, flush to the
   far edge so the overlap is hair rather than eyes, and the build log SAYS
   "OVERLAPS a face". A card under the right-hand rail (bottom past y900)
   narrows to the caption measure.

The render log prints the decision on every clip (`hook: card at y700..1090,
below the face (free band y426..1090)`). No OpenCV for the interpreter, or no
face found, and it takes the preferred band and says which of those happened.

**It swipes in and it swipes out; it does not switch on and off, and it does
not pop.** Arrival: 60px of travel in from the RIGHT on an ease-out quart
(`1-(1-p)^4`) over `HOOK_IN` 0.30s, alpha 0.85 to 1 on a smoothstep - not from
zero, because frame 0 is the cover a feed shows before anyone presses play, and
the card must already read on it. Exit from `HOOK_HOLD`: off the frame to the
LEFT on an ease-in cubic (`p^3`) over `HOOK_OUT` 0.233s, with a 133ms alpha
fade under the last third so it never clips the edge at full opacity. No scale
on type: scale belongs to the punch-ins and the live caption word. The alpha
ramp is a handful of PNG states; the travel is an overlay `x` expression and
the fade a `fade` filter on the same stream, so the hold is one hard-linked
file. A first version (same morning) popped the card 0.92 to 1.018 and drifted
it out; the design panel rejected it as a second arrival vocabulary next to the
rise, and the owner asked for a swipe.

**The compass, one rule for every element:** picture arrives from BELOW, type
arrives from the RIGHT, everything leaves LEFT. The end card's light wipe is a
reveal edge travelling right, not content travelling right, so it does not
conflict.

> **RELAXED FOR SMALL TRAVELS, 2026-08-25.** The owner asked for the cutaway's
> transitions to vary ("it should not always be fade"), and the compass allows
> exactly one legal pair, which is no variety at all. `BROLL_ROTATION` now
> drifts an insert up, down, left or right by **80px** under the unchanged
> cross-dissolve - 4% of the frame's height, 7% of its width. The compass still
> owns every LARGE travel: the hook card, the end card's wipe, and
> `broll_style: "slide"`. See SKILL.md, "The 2026-08-25 standard".
>
> **AND THE NAMEPLATE NO LONGER ARRIVES FROM THE RIGHT.** It is a bone card now
> and it cross-fades, because the owner asked for exactly that: *"instead of it,
> like, go swiping, it should kinda fade in."* A card that fades has no
> direction to be inconsistent about.

### Captions live ON the picture, in the lower third

`CAP_BAND_Y = 1130`, 300px tall, so the block is centred on y1280 — exactly two
thirds down, which is where short-form captions sit everywhere else.

**This position has flipped twice. Read the whole history before changing it.**

1. On the picture, on a blurred plate.
2. Below the picture, on a gradient scrim, in a 360px band — on instruction.
3. On the picture again, no plate and no scrim — on instruction, 2026-08-11.

The reason for (3) is that the band was costing 360px of every frame, 23% of the
picture, to buy a caption position the apps cover with their own chrome anyway.
The panel is the full 9:16 now and the captions moved into it.

**The y range is derived, not chosen.** Two constraints set it:

- Every app draws chrome over the bottom of a vertical video — roughly the bottom
  480px on TikTok, 420 on Reels, 300 on Shorts. TikTok is the worst, so
  `1920 - 483 = 1437`, floored to `CAP_SAFE_BOTTOM = 1430`. The band's TOP is
  derived from that bottom, so anyone who later needs a taller band walks it
  **up**, never down into the chrome.
- Every app also draws a right-hand action rail — like, comment, share — over
  the same vertical range, up to about 160px wide. That is what sets the measure:
  `CAP_MEASURE = W - 340 = 740`, which inks to about x915 at worst.

Those chrome figures are published spec and judgement. **Nobody has measured them
on a device.** The way to settle it is to burn a 100px ruler grid over a throwaway
clip, post it privately to all four apps and screenshot them.

**What the captions now sit on, and the cost of that.** In `head` it is usually
the speaker's chest — but on a close-framed webcam shot it is the chin and
sometimes the mouth, because a 9:16 crop of a 16:9 source is a tight close-up and
there is no wider crop available. In `share` and `duo_share` it is the shared app,
so it covers part of the chart. In `duo` it lands on the **lower speaker's face**,
and that is unavoidable: the seam is at y953 and the band starts at y1130, so a
face sitting anywhere natural in the lower band is under the words.

This was the stated reason the in-picture position was reversed the first time,
and it has not stopped being true. It is now an accepted cost. The adaptive colour
keeps captions LEGIBLE over a face; it does not stop them COVERING one. Where one
person holds the floor, prefer a `head` crop over `duo` — that was already the
advice for a bigger face, and it now avoids this as well.

### The caption colour is chosen per clip

Captions no longer sit on a surface we control, so a fixed colour cannot work. The
old vivid cyan was safe only because there was always a scrim under it. Over live
video it sinks: a speaker in a blue shirt gives cyan keywords almost no
separation, and the keyword highlight — the device that lets someone take the
point off a muted frame — stops working.

`sample_caption_bg()` takes eight frames spread across the span, pushes each one
through the clip's own reframing chain, and crops the rectangle the ink will
actually occupy. Sampling the SOURCE frame instead would be wrong in three of the
four modes. Eight input-seek single-frame decodes off a 2GB master measure at
about a second in total, so it is free next to a render.

It measures three things:

| | |
| --- | --- |
| median relative luminance | the median, not the mean — a caption zone regularly holds one small bright thing (a collar, a gridline, a lamp) and a mean is dragged by it into calling a dark room mid-grey |
| dominant hue | saturation-weighted, because an unweighted average returns a confident hue for what is essentially black |
| chroma | below `BG_GREY` the background has no colour to clash with, and hue distance is ignored |

`choose_caption_colours()` then scores a small palette. **Hue distance is weighted
above luminance contrast**, which is the opposite of the usual advice, and it is
right here: the 5px stroke already carries legibility, so the failure that
actually happens is a colour clash, not a brightness clash. Cyan on navy clears
every contrast check on paper and still vanishes.

The palette rules:

- **Saturated red and saturated green are banned.** This is finance footage and
  those two carry direction. A keyword in red over a market clip reads as a call,
  and the skill's compliance stance is that what is on screen is subject to the
  same rules as what is said.
- **The house cyan carries a prior** (`+0.35`), so a clip only leaves it when it
  genuinely cannot be read. Most clips keep it.
- **The light and dark sets never mix.** A dark accent beside bone base type reads
  as recessive rather than emphatic, so the base picks the set and the accent is
  chosen inside it. The base only flips to ink above `CAP_FLIP_L = 0.62`, which is
  deliberately high: white-with-a-black-stroke is what short-form captions
  actually use, and flipping eagerly is the most visible thing this system can do.
- **One colour per clip, never per caption.** A colour that re-picks itself
  mid-clip reads as a glitch. When the span swings across the light/dark boundary
  the renderer says so and takes the choice that survives both halves.

Overrides: `"cap_colour": {"key": "amber", "base": "#fffdf9"}` on a clip in the
slate (a hex string, an `[r,g,b]`, or a palette name), or
`"adaptive_captions": false` in project.json to pin the house cyan for a whole
set. `build_all` prints every clip's pick together at the end of a run and flags
a set that came out with more than one accent.

### Superseded, kept only as history

These describe layouts this skill has actually shipped and moved on from. They are
here so nobody re-derives a decision that was already made and reversed. **Do not
follow them.**

**Be careful with the first entry.** The caption position has been live in both
states — on the picture, then below, then on the picture again — so an entry here
about captions is a *previous* state, not the opposite of the current one. The
"Captions live ON the picture" section above is what ships. Check which of the two
you are reading before acting on either.

- *A 1560-tall panel with captions in a 360px band below it, at y1596..1856, on a
  gradient scrim.* Shipped for several sets, then reversed on 2026-08-11: it spent
  23% of every frame on a band the apps cover with their own chrome anyway. The
  captions went back onto the picture and the panel became the full 9:16.
- *A blurred plate under the in-picture captions.* Came with the first on-picture
  version. Legibility is carried by a 5px stroke and the per-clip colour pick
  instead. A plate is a small scrim: it brings back exactly the murk that removing
  the scrim was for. Do not solve a hard clip by re-adding a plate, a scrim or a box.
- *Hook as white type on a gradient scrim, top-left, 3.6s.* Replaced by the centred
  white card, which carries contrast without dimming the picture.
- *Live-word-only caption highlight.* Replaced by keyword colouring: the live word
  says where you are, keywords say what matters.

### Full bleed

**The panel runs to the top and to both edges.** It was inset 36px with 28px rounded
corners, which left a margin of blurred backdrop down each side and a strip across
the top — and that reads as a video pasted onto a background rather than as a video.
There is nothing to inset toward: the format *is* the frame.

The panel grew **1120 → 1410 → 1560 → 1920** as the hook moved onto the picture,
then the inset came off, and finally the caption band came off the bottom. That is
what makes a duo work at all: each band is now **`(1920 - 14) / 2 = 953px`**, where
553 clipped every head at the forehead *and* the chin.

Derive that number, do not paste it. The line here used to read `(1120 - 14) / 2 =
773`, which was arithmetic for neither panel — 553 for the 1120 it named, 773 for
the 1560 it meant — and it survived two panel revisions because the answer looked
plausible.

### One rectangle, every mode

**The panel is the same 1080x1920 box — the whole frame — in `head`, `duo`,
`share` and `duo_share`. A mode is a way of packing that box, never a different
box.** The caption band is likewise one rectangle in all four modes, at one y.

This was violated and it showed. `share` used to build its height from a fixed
612px screen band plus the face band plus the gap, which came to **1099** — 21px
short of a head clip, and top-aligned, so every screen-share clip sat visibly high
with a sliver of dead space under it. Two clips in the same set did not line up,
which is exactly the kind of fault that reads as "not quite professional" without
being nameable.

The screen band now takes whatever the face band leaves
(`screen_h = PANEL_H - face_h - SPLIT_GAP`) and the share crop is **re-cut to that
band's aspect** — trimming a little off the shared screen rather than squashing it,
because a stretched chart is instantly obvious and a slightly tighter one is not.

### Nothing goes above the hook

There is **no eyebrow and no hairline rule**. There used to be a small tracked
`QUASAR MARKETS · AI MATTERS` label at y94, and it was removed on evidence:
watched on a phone, feeds that letterbox a 9:16 in the timeline — X on mobile
above all — crop the top strip of the frame, and that label was the first thing
to go. A brand label that only survives on desktop is worse than none, because
it reads as a clipped mistake.

The card never rises above `HOOK_MIN_TOP` = y140, and prefers y300, so removing
the label did not push anything to the frame edge. Branding is carried by the
closing card, by the address in the final seconds, and by whatever name badge the
source itself burns in.

**Do not re-add a label, logo, show name or rule above the hook.** If a clip needs
the show named, put it in the post caption, not in the top strip.

### The closing address

`invest.quasarmarkets.com` is **one tracked line, in the last 2.6 seconds only**.
No pill, no outline, no fill, and nothing for the other 95% of the clip.

It sits at **y1020**, above the captions. It sat at 1846 for as long as there was a
scrim down there to sit on, which put it 74px off the frame bottom — inside
TikTok's ~480px of chrome, Reels' ~420 and Shorts' ~300, so it was unreadable on
all three. It survived that way because it is off by default whenever the closing
card is on, which is nearly always. On the picture it takes the clip's own base
colour and a 2px stroke, like the captions.

It went through a persistent outlined capsule, then a capsule cycling in and out,
and both were wrong for the same reason: an enclosed shape sitting against the video
is the busiest element in the frame, and it competes with the face for exactly the
duration you want the face winning. Nobody types an address at second four. Putting
it at the end places it where the decision happens and buys the bottom of the frame
back for type — which is what let the captions go to 86px.

Set as plain tracked type it reads as a **signature**. An outlined pill reads as a
button, and a button that cannot be tapped is a small broken promise on every clip.

It arrives on a 0.45s ease-out and holds to the last frame, so the closing image —
the one that becomes a thumbnail — always carries it.

### B-roll

A cutaway, not a background. The picture leaves the speaker for 4.2 seconds, the
captions and the hook keep running over it, and it comes back. That breaks the
face-on-screen rule under a written exception in SKILL.md; preflight fails a hold
whose SETTLED time is under 3.0s, or whose window is over 4.2s - a raw hold of
3.63 to 4.20. The count is derived, not capped: one per 18 seconds of body,
floored at two, never past 30% of the body.

> **SUPERSEDED, TWICE.** What ships is a **cross-dissolve on the alpha plane**
> (2026-08-25, the owner's third verdict on this element - the slide was "still
> not clean", the hard cut "not smooth"), now with an **80px directional drift**
> under it that varies per insert. The paragraph below describes `broll_style:
> "slide"`, which is kept as an escape hatch and is not the default. Its
> analysis of curves, even-pixel offsets and the unfinished-travel bug is all
> still correct and still applied. The design panel's veto on "dissolve" in this
> section is the thing the owner overruled; its vetoes on a whole-panel PUSH and
> on a zoom are still live and still respected. Full record in SKILL.md, "The
> cutaway CROSS-DISSOLVES" and "The 2026-08-25 standard".

**It comes up and it swipes over (the owner's words, 2026-08-22), as a cover
over a static panel.** The insert rises from below the frame to y=0 over
`BROLL_IN` 0.333s, holds, and leaves to the LEFT over `BROLL_OUT` 0.300s, both
on a smoothstep, revealing the speaker - whose framing has
FLIPPED underneath (see "Punch-ins"), so every return is a new shot. Hard seam,
no shadow, no dissolve, no zoom, no sound. The design panel (three proposals,
two judges) rejected each of those by name: the edge shadow and the dissolve as
the CapCut/iOS card tell, a whole-panel PUSH because it moves a share-mode
chart with its axis labels at the edge for 13 frames on every insert, and the
morning's zoom-through because it was a second vocabulary. `BROLL_HOLD` is 4.2
now, not 4.0: 0.633s of every window is travel, so the SETTLED picture is
3.57s, and preflight measures the hold as settled time against the 3.0s floor.
Both times are delivered seconds; `broll_chain` scales them by the tempo.

**Both curves and both durations were changed the same day, on evidence: the
first version was GLITCHY and the owner said so.** Two faults, each measured
on the delivered file:

- *The rise strobed.* An ease-out quart over a 1920px travel puts 885px - 46%
  of the frame height - into the first moving frame (then 536, 294, 140).
  There is no motion blur in this pipeline, and a full-frame jump that size
  does not read as a move at all; it reads as a flash. On a smoothstep over 10
  frames the curve is 60/140/220/260/280/280/260/220/140/60 and the worst
  frame is 280px, 15% of the frame - inside the rule of thumb broadcast pans
  are cut to.
- *The swipe never finished.* The exit ran over `[a1-BROLL_OUT, a1]`, but the
  cover's gate closes at `a1 - hb`, which the travel never reaches: the last
  frame actually drawn sat at 58% of the way out with **451px of the insert
  still on screen**, and then all 451px disappeared between two frames. That
  was the pop. The exit's denominator is now `BROLL_OUT - one frame`, so the
  travel completes on the last frame the gate draws; measured after the fix,
  the closing steps are 200/180/180/120/40px and the final frame is genuinely
  off the edge.

**THE CURVE FOLLOWS THE DISTANCE.** Peak velocity is about 4x the average on a
quart and 3x on a cubic, against 1.5x on a smoothstep. Over the hook card's
60px arrival that difference is invisible and the quart's crispness is worth
having; over a full-frame travel it is the whole defect. So small travels keep
ease-out/ease-in and anything crossing a large fraction of the frame uses
smoothstep - including the hook card's EXIT, which crosses most of the frame
and was moving 344px a frame on a cubic.

**Both offsets are rounded to EVEN pixels.** The panel is yuv420p, so the
chroma planes are half resolution and an odd offset splits a chroma sample
across the moving seam, which shimmers along it for the length of the travel.

No motion blur, and not for want of trying: at 280px a frame the strobe is
already gone, and the only ways to fake blur here - `tmix` over the composite,
or compositing the insert several times at sub-frame offsets - either soften
the whole clip or cost more than the render.

**Video first, stills where no video exists: a sourcing constraint, not a taste.**
The keyless libraries are stills only, and Wikimedia's video returns a 1915
Chaplin short for "gold bullion". Pexels and Pixabay return real motion, but only
with a key, and a hit under the bake length is dropped before it is offered: a
1.2s refinery flame baked five times before preflight caught it. A still is
cropped to 9:16 and given a 1.00 to 1.06 push-in across the hold - unless it is
WIDE, in which case it pans instead (below). A clip usually gets neither, because
the footage already moves. Either way it is a chosen picture, and it cannot put a
price on screen by accident.

**"IT IS A VIDEO" IS NOT THE SAME CLAIM AS "IT MOVES", and the exemption used to
assume it was.** Five library sources are locked-off tripod stock that move LESS
than a photograph does under the push, measured in the 8fps 96x54 space this
module scores everything in:

    heart-monitor-ecg-hospital     0.41      hospital-emergency-equipment  0.41
    stopwatch-timer-closeup        0.46      us-capitol-building-exterior  0.49
    tokyo-skyline                  0.69

against a push that produces 0.22 to 1.14 across the 21 narrow stills in the
library, median 0.65. On screen they were a dead frame for the whole settled hold,
with less life in them than a photograph would have had — which is the exact thing
the push exists to prevent, waved through on a file extension.

The push is decided on MEASURED motion now, from the same decode that picks the
window (`_window_plan` returns both, so there is no second pass). `PUSH_IF_UNDER`
is 0.8, and it is justified twice over, which is the only reason to trust a
threshold drawn on a library this size: it sits ABOVE the push's own median output,
so the rule reads *push when the footage moves less than the push would add*, and
it sits in a real GAP in the distribution — the five above are all at or under
0.69 and the next clip up is 0.97. p25 across all 56 sources is 2.37, so it only
ever catches the tail. Re-baked, their delivered motion went 0.27→0.54, 0.27→0.54,
0.32→0.48, 0.32→1.37 and 0.41→1.14, landing them in the same band as a pushed
still.

`broll.py sweep --treatment --apply` migrates both directions: a still whose pan
plan changed, and a video whose push decision changed.

**A wide still PANS, because no amount of zoom can help it.** The 9:16 frame is
the constraint: at scale 1.0 a cover crop already shows the maximum width the
frame can hold without bars, so "zoom out until the whole building fits" is not a
smaller push, it is letterboxing. Moving across the subject over time is the only
option, which is what Ken Burns invented the move for.

It bites on the tier that is hardest to source. Pexels is asked for
`orientation=portrait`, so its stills arrive at 2:3 and keep 84% of their width.
Wikimedia has no orientation parameter and returns what the archive holds -
landscape - and Wikimedia is the tier carrying the INSTITUTIONS, the ones the
2026-08-18 survey scored lowest (the Fed 0.48, Washington 0.49). Of the 32 library
stills, 11 are wider than 1.15:1 and every one is Wikimedia or Openverse: the
crude-oil tanker at 2.64:1 keeps **21%** of its width, the Capitol 32%, the Fed
38%, the Treasury 43%. The subject is not off-centre in any of them - the
gradient-energy centroid falls inside the kept strip on all 32 - so nothing is
cropped out of frame. The defect is subtler: a wide subject STOPS BEING THAT
SUBJECT at 21% of its width. A tanker seen through a sliver is a hull.

The pan travels HALF an output width (540px) or half the available room, whichever
is smaller, landing on even pixels for the same chroma reason the b-roll travel
does. About 5.2px a frame at 30fps. **Pan or push, never both**, on the same
argument that keeps a push off moving footage.

**Half a width, not a whole one, and the difference is the rule the insert exists
to serve.** The pan ENDS on the subject, so at a full frame width it OPENS a whole
frame away from it: on 8 of the 11 wide stills the opening crop was literally
column 0 of the photograph, and at t=0.15s - the frame under the spoken word,
since the cut leads by PRE_ROLL - the rocket asset showed black sky and smoke with
NO fireball. This file uses that exact asset to state the rule: say "exploded" and
the fire is on screen as the word lands. At half a width the opening crop still
overlaps the closing one by 540px, so the subject is in shot from the first frame
and the pan reveals context AROUND it rather than travelling TO it.

It also halves peak velocity, which matters under the entrance: the ease-out is
fastest at t=0, exactly the ten frames in which `BROLL_IN` is still sliding the
panel up. 26% of the travel is still spent under that rise, but at 15px a frame
rather than 31.

**The curve is an EASE-OUT, and it is the one place that breaks the DISTANCE rule
above on purpose.** That rule sends anything crossing a large fraction of the
frame to smoothstep, because an ease-out's peak velocity is about 3x its average
and over a full-frame travel that strobes. It was written for the hook card's exit
and the b-roll cover: 1920px in 0.3s, 344px a frame. This pan is 540px in 3.49s,
where smoothstep peaks at 7.8px a frame and an ease-out cubic at 15.4px - 1.4% of
the frame width, an order of magnitude under the 15%-per-frame the strobe rule is
drawn at. The rule is about VELOCITY, not distance, and at this speed there is
room.

It is worth breaking because of WHEN THE SUBJECT ARRIVES. The pan ends on the
subject, so on a smoothstep the subject is absent for most of the insert.
Measured on the Capitol by correlating every frame against the final framing, the
dome is not recognisable until 89% of the travel - t=2.77s on a smoothstep, 75% of
the way through a 3.7s cutaway. An ease-out reaches the same point at t=1.82s,
49%. It roughly halves the time the viewer spends looking at something that is not
the subject, and the slow tail settles onto it rather than arriving and stopping
dead. The honest cost, which the reveal does not repay in full: a static crop
showed the Capitol dome for the whole insert, and the pan shows it for the back
half. What the pan buys is the colonnade wing the static crop never showed, a
moving frame instead of a held one, and a landing frame identical to the old one.

**`-framerate` GOES BEFORE `-i`, and leaving it out costs 5 frames a second.**
`-loop 1` on an image defaults the INPUT to 25fps, so a filter expression in `t`
is only evaluated 25 times a second and a trailing `fps=30` then DUPLICATES frames
to make up the difference. Measured on the first cut of this: 114 distinct
positions in 141 frames, every fifth or sixth frame frozen, which on a slow pan is
exactly the judder the eased curve exists to avoid. The old push path never hit it
because `zoompan` carries its own `fps=` and emits `d=` frames directly.

**The pan decodes and scales ONCE, and getting there disproved the obvious fix.**
The first cut baked 13x slower than a push - 32.7s against 2.5s on the widest
library still, an 8192x3108 JPEG scaled to 5060x1920 - because `-loop 1` makes
ffmpeg decode and rescale the image for EVERY output frame. Three approaches,
measured on that asset:

    crop in SOURCE coords first, scaling only the needed region   33.0s   no gain
    scale once to an intermediate file, then pan with a crop       9.9s   3.3x
    decode once, replicate with the `loop` FILTER, one command     1.5s  21.8x

So the cost is the repeated DECODE, not the scale, which is why cropping first
buys nothing. `scale=...,loop=loop=n-1:size=1:start=0,setpts=N/fps/TB,crop=...`
holds one decoded frame in the graph and re-crops it, needs no temp file, and
produces byte-identical frames. The whole eleven-asset migration went from about
six minutes to 24 seconds. The push path never had the problem: `zoompan` takes
one input frame and generates `d=` frames from it.

**GEOMETRY COMES FROM THE DECODE, NOT FROM FFPROBE.** ffprobe reports CODED
dimensions and ignores the EXIF orientation tag; ffmpeg autorotates on decode, and
they disagree on real assets. `surveillance-camera-security-wikimedia-0.jpg`
carries EXIF orientation 6: coded 4032x3024 (aspect 1.333, "wide"), decoded
3024x4032 (aspect 0.75, portrait). Planned off the coded size it was panned, and
an explicit `scale=<width>:1920` then stretched it 1.78x horizontally - a fat pole
and a blob where the camera housing should be, shipped into the library before
anyone looked. `_decoded_size` reads `showinfo`, which reports what the decoder
actually produced. The pan branch also scales with `-2:1920` rather than a forced
width, so the worst a wrong plan can now do is put the crop in the wrong place
instead of distorting the picture. `sweep --treatment` repairs in BOTH directions -
a still that should pan and does not, and one that was panned and should not be.

**Which is also why the expression is indexed on `n` and not on `t`.** The loop
filter and `setpts` do not reproduce a looped input's PTS exactly, and written
against `t` the two pipelines disagreed by 6 to 8px on early frames. `n/panfr` is
the same quantity (t = n/fps) with the completion rounded onto a frame boundary,
and it makes the two byte-identical.

**And ZOOMPAN CANNOT DO THIS PAN**, which is worth writing down because it is the
obvious thing to reach for and it was written into this file as the recommended
fix before anyone rendered it. Its region is always (iw/zoom x ih/zoom) - the
INPUT's aspect ratio - so asking it for a 9:16 window of a 2.64:1 image returns
the whole ship squashed into the frame, not a crop of it.

**AND IT FINISHES INSIDE THE SHORTEST WINDOW ANY CLIP WILL PLAY**, which is not
the same as the length of the bake. The bake is `BAKE_HOLD` 4.7s of SOURCE and is
shared by every clip, but `broll_chain` only ever plays `hold * tempo` of it. The
first version eased across the whole bake, so the pan was still moving when the
insert came off screen - measured over every legal hold and tempo it delivered
83.4% to 100% of the travel, and 100% only at the maximum of both:

    hold 3.63  tempo 0.96  ->  83.4%   179px left of centre
    hold 3.70  tempo 1.00  ->  88.3%   126px   (the common slate value)
    hold 4.20  tempo 1.12  -> 100.0%     0px

So "it ends where the static crop sat" was false for every real slate - the same
class of mistake as the centroid, a design claim that does not survive the
delivered pipeline, and caught the same way. `PAN_DONE` is the shortest source
window any legal clip consumes, `(BROLL_HOLD_MIN + travel) * SPEED_MIN` = 3.49s;
the pan completes there and the remaining 1.2s of bake sits on centre. Every legal
combination now delivers 100%.

**IT ENDS WHERE THE STATIC CROP ALREADY SAT.** That is the load-bearing part. The
first version ended on the gradient-energy CENTROID, on the Ken Burns argument
that a move should land on its meaning, and rendering it proved that worse than
doing nothing: on the Capitol the centroid sits in the TREE beside the building -
foliage, brick and clutter score high on gradient energy, a smooth white dome
scores low - so the pan ended right of the dome and clipped it, while the plain
centre crop it replaced had framed the dome cleanly. Ending at centre means the
last frame is exactly today's frame and the travel can only ADD the width in front
of it. A heuristic allowed to choose the final frame must beat the baseline, and
an edge filter does not know a building from a tree; that needs an image model.

`broll.py sweep --treatment --apply` is the migration for stills baked before
this existed (`--stills` still works as a synonym). They are the right LENGTH, so nothing else in the sweep would notice
them.

**Upstream, the still tiers were reordered so fewer pictures need a pan at
all.** Three changes, and two of them fix things that were already wrong:

- **Relevance is recovered from `index`.** MediaWiki keys `pages` by pageid, so
  iterating `.values()` threw the search ranking away - on "US Federal Reserve
  Eccles Building" the top-ranked hit came back LAST of twelve. Harmless while
  the function returned everything, fatal once it over-fetches and truncates.
  Across 54 real library terms, 8 lost a hit and 2 lost their best.
- **Near-duplicates are dropped.** Five of those twelve Fed hits were consecutive
  LCCN accession numbers of ONE construction photograph, same title and same
  10008x7752 dimensions, so five of six contact-sheet cells showed the same
  frame. Same title stem AND same dimensions is the test; two different
  photographs almost never share both.
- **Shape is preferred in three buckets**, on the share of the width that
  survives a 9:16 crop, applied to Wikimedia and Openverse alike. NOT two: `h >=
  w` reads as "portrait, so it fits" and is wrong for a square, which satisfies
  it and keeps 56%, not 100%. It is a PREFERENCE and not a filter - a landscape
  Eccles Building beats no Eccles Building, and the survey put the Fed at 0.48
  findability precisely because there is little to choose from. On "United States
  Capitol building exterior" every hit is landscape at 24-32% and the preference
  changes nothing, which is exactly why the pan had to exist.

Together they are visible on the terms that prompted this: the Fed went from six
slots holding five duplicates to three distinct pictures led by the 1937 facade,
and the Treasury now leads with a 3567x5000 PORTRAIT frontal - which needs no pan
at all.

**EXPOSURE IS CORRECTED, AND THAT IS NOT THE SAME AS GRADED.** Every insert used
to arrive at whatever exposure its source shipped with, against a speaker's shot
that is consistent all clip: measured over 101 baked assets, mean luma 109, sd 40,
range 12.7 to 196.0. At the extremes that is worse than "reads as stock" - a
full-frame cut to a 12.7 insert reads as the picture dropping out rather than as a
dark room.

The conventional answer is a house LUT at 60-80% and it is REFUSED here. A LUT
imposes a look, and the whole b-roll argument in this file is that the insert is
evidence rather than decoration: grading a photograph of the Eccles Building to
match a brand palette is the point at which it stops being a photograph of the
Eccles Building. What ships is narrower - a luma correction toward a neutral band,
no hue, no saturation, and nothing touched that is already fine. The band is
[45, 160] and it leaves **84% of the library completely alone**, which is what
"correction" has to mean if it is to be distinguishable from a look.

**Gamma, not brightness.** An additive offset lifts the black point with
everything else and the picture goes milky. Gamma pins 0 and 255 and moves the
midtones instead.

**AND IT ONLY PINS 0 IF IT IS APPLIED IN THE RIGHT RANGE.** `eq=gamma` is a
full-range curve, and 61 of the 101 bakes are tv-range (`yuv420p`/tv) against 40
full (`yuvj420p`/pc). On a tv asset the black field sits at code 16, so a curve
that pins 0 pins something the picture does not contain and lifts the real floor
instead. The first version did exactly that and four assets shipped with their
blacks gone:

    fresh tv-range bake, before any correction   floor  0.0   true black 46.0%
    through the OLD full-range curve             floor 24.0   true black  0.0%
    through the range-aware curve                floor  0.0   true black  5.7%

`_stream_range` probes the stream, `_eq_chain` wraps the gamma in tv -> pc -> tv
when it needs to, and the same wrap is used for the MEASUREMENT so the gamma is
chosen in the domain it is applied in. The wrap is conditional and not
unconditional: applying it to a pc asset too is survivable but shifts the result
(mean 33.7 against 31.8 on hacker-keyboard) and re-tags the output tv, so the
gammas already recorded for pc assets would stop meaning what they meant.

**BLACK_FLOOR did not catch this**, and that is worth sitting with. It measured
the lift correctly - p10 14, inside its own limit - and passed, because the
invariant it guards was never true in that domain. A guard can be right about the
number it measures and blind to the thing that makes the number meaningless.

The repair is `sweep --recorrect --apply`, which re-bakes from src. It cannot be a
re-run of the gamma: no curve above 1 pushes code 11 back to 0, and the damaged
bakes were rewritten in place.

**The black floor is what stops it washing a picture out, and a gamma cap cannot
do that job.** Rendered and looked at: the correction is good on
`hacker-keyboard-dark-room` at gamma 1.55 - still plainly a dark room, but the
hands and the keys are readable instead of lost - and BAD on
`artificial-intelligence-neural-network` at 1.73, where the black field behind the
neon goes grey and the glow stops popping. Those two cannot be separated by the
gamma, because 1.55 is fine on one asset and 1.50 is already too much on another.
What separates them is where the BLACK ends up:

    hacker-keyboard-dark-room     gamma 1.55   p10  1 ->  8   looked GOOD
    bank-vault-steel-door         gamma 1.50   p10  3 -> 14
    abstract-network-connections  gamma 1.50   p10  1 -> 29   would wash
    artificial-intelligence-neon  gamma 1.73   p10  1 -> 42   looked BAD

14 then 29 is a real gap, so the floor is 15 and the correction is bisected down
until it clears. An asset whose darkness is STRUCTURAL - a black field with
glowing lines - is protected; one whose darkness is a shadow problem is corrected.

**The floor only applies when LIFTING.** Gamma below 1 pushes blacks down, so the
guard can never bind on a bright asset - bisecting against it there converged back
to 1.0 and left a 196-luma white wall uncorrected, which was the first version's
one real bug. Highlights compress rather than clip, because gamma pins 255 too.

**"LUMA-ONLY" IS TRUE OF THE COLOUR AND NOT OF THE READING.** The filter rotates
no hue and changes no chroma - measured on a lifted asset, absolute chroma goes
7.28 to 7.28 and 36.89 to 37.07, both within a rounding error. But HSV saturation
drops 26 to 39%, and that is arithmetic rather than a colour shift: saturation is
(max - min) / max, so raising the value while holding (max - min) fixed must lower
the ratio. A brightened photograph reads slightly less saturated for the same
reason, wherever it is done. Worth knowing before someone measures saturation,
sees a 39% drop and concludes the filter is not luma-only.

**And the correction is MEASURED, not predicted** - but the first version of this
paragraph got the REASON half right, and the missing half is what let the range
bug ship. Simulating `eq=gamma` as `255*(v/255)**(1/g)` agrees on ordinary
pictures and is badly wrong on exactly the ones that matter: on the neon asset
ffmpeg returned mean 57.4 / p10 42.0 where the simulation said 36.1 / 10.4, and
decoding at higher resolution made it worse rather than better, so it is not a
downscale-order artefact.

The reason is the RANGE, and it is the same reason `_stream_range` exists. The
simulation ran on a `format=gray` decode, which has already expanded tv to full,
while `eq` was applying its curve to the tv-range Y underneath. Two different
domains, compared as if they were one. Writing that down as the vague "eq works in
video range" and stopping there was the mistake: the sentence was true, and
following it one step further would have shown that the FILTER had the same
problem as the simulation. It shipped four assets with their blacks lifted before
a review found it.

Measuring is still the rule - a decode through the filter costs no encode, so it
is cheap enough that guessing is not worth the risk - but the measurement now
happens through `_eq_chain`, so the gamma is chosen in the domain it is applied
in.

`broll.py sweep --exposure --apply` is the migration, and it is idempotent
through a RECORDED MARKER, not by construction - the first version claimed the
latter and was wrong. "Is the result still outside the band?" is the wrong test,
because the black floor deliberately stops the correction short: after one pass
the neon sits at 27.5 and the dark room at 35.0, both under 45 and both finished.
Re-running read that as unfinished work. The floor-capped ones do self-limit, but
`hacker-keyboard-dark-room` came back for another gamma 1.15 and
`archive-filing-cabinets` for 1.05, and they would have crept on every run, one
encode generation at a time. What is recorded is what was DONE - an `eq` value on
the index row, the same shape as `pan` and `push` - and a fresh re-bake clears it,
because a new bake carries no correction.

**No credit line, and derivatives allowed.** That is the one test, and the
tiers pass it two different ways. Openverse is asked for `license=cc0,pdm` and
Wikimedia is filtered on its own licence field, so the keyless pair is CC0 and
public domain only. Pexels and Pixabay - the sources the video-first tier now
ranks above those stills, because they are the only ones returning real motion -
ship under their own house licences, and every hit records that verbatim: "free,
commercial, no attribution". What is refused everywhere is a plain "commercial
use allowed" filter, which is a weaker and different test - Openverse's still
returns BY, which needs a credit line this layout has nowhere to put, and BY-ND,
which forbids derivatives, and cropping to 9:16 under captions is a derivative.
`broll-library/index.json` records the licence and source page of every asset, so
the provenance of any frame that shipped can be reconstructed.

**Each insert lands ON ITS WORD, led by 0.15 seconds.** Say "exploded" and the
fireball is on screen as the word lands - the cut comes a beat early, the way an
editor leads a cut, so the word arrives over the picture rather than the picture
trailing the word. The slate carries the word itself ("on"), and the renderer
re-snaps the insert onto that word in its own decode - the same word list the
caption PNGs are built from, so caption and cutaway are synchronous by
construction. The stored timestamp only gets the search into the right second:
propose and render each run their own whisper pass, and the two disagreed by
1.56s on a real word - "exploded" landed at 41.24s in the render's decode and
42.8s in propose's. That number is why the re-snap window is 2.5s and not 1.5s:
a window tighter than the disagreement silently skips the snap, which re-ships
the exact lateness the snap exists to kill. Join-snapping was tried first and
retired; its joins were in source coordinates, the words in delivered
coordinates, and the mixing put a launch failure under the word "investors".

**Where in the stock clip the bake is taken from is measured, and it avoids a
shot change.** `liveliest_window` decodes the source at 8 fps and takes the
highest-energy window, because stock footage routinely opens on a slate or a
fade-up and taking from t=0 shipped the dull end of a clip whose good two seconds
were in the middle. But the energy test ALONE PREFERS A CUT: a hard cut produces
the largest frame differences anywhere in a clip, so maximising energy is attracted
to one, and the picture then changes twice inside a beat the viewer was given no
reason to expect any change in.

**The 8 fps pass cannot decide this, and the first version pretended it could.**
On absolute magnitude alone, 7 of the 56 library sources flagged and SIX HAD NO
SHOT CHANGE - a camera dolly (factory-production-line, seven consecutive frames), a
car crossing the lens (highway-guardrail-barrier), a tote bag passing
(supermarket-dairy-aisle), a hand leaving frame (crypto-bitcoin), a lighting flash
(stack-of-bills, peak 71.9 with the same framing throughout), and a 3-frame
DISSOLVE (abstract-network, peak 78.3). The veto was hard, so three frames of a
passing car removed 55% of the search space and seven frames of a dolly removed
95%, moving factory-production-line from 4.88s to 0.62s and shipping a window
carrying 29% of the motion - the exact defect the function exists to prevent.

What separates them is the NATIVE frame rate. A hard cut is an IMPULSE: one frame
changes everything and its neighbours are ordinary. A dolly, an object pass and a
dissolve are RAMPS, high for many consecutive frames, and at 8 fps every ramp is
aliased into something impulse-shaped. Measured as peak over the strongest
non-adjacent frame, the one source with true cuts scores 6.03 / 8.48 / 19.15 and
everything else tops out at 1.54, so the threshold sits at 3.0 with about 2x of
margin each side. An 8 fps candidate is only a REASON TO LOOK: each is re-decoded
at native rate over ~1.5s and has to clear it. Exactly ONE source in 56 carries a
true hard cut.

**And the avoidance is advisory, not a veto.** A hard exclusion trades a suspected
cut for an arbitrarily dead window, which is the worse defect - a near-frozen
cutaway is visible on every frame, a cut is visible once. A cut-free window is only
taken when it keeps 60% of the best window's energy; otherwise the liveliest window
wins and stderr says what it is shipping. The coverage test uses `ceil(hold * 8)`,
not `int`, because `int` truncated 0.6 of a frame and left ~0.1s of rendered
picture unexamined - which is exactly where a cut can still land.

**The assets are baked once, at fetch time**, into ready 1080x1920 clips at the
master's frame rate. The render is then a plain timed overlay, measured at about
half a second on a 50 second encode, and the expensive scale of a 6000px photograph
happens once per asset rather than once per clip that uses it.

### The poster frame

Every clip writes a `.jpg` next to the mp4: the frame the feed judges it on before
anyone presses play. Left to default, that is frame zero, which lands on a blink or a
mouth mid-syllable about as often as not.

It is chosen by scoring the first ~3 seconds on gradient energy weighted by
brightness, and taking the best — a blink or a fast head turn is measurably softer
than a held expression, so the sharpest frame in the window is nearly always a usable
one. The window stops at `HOOK_HOLD` so the still carries the headline too.

### The closing card

Four seconds on the end of every clip, appended by `endcard.py` after the render:
a 0.78s diagonal sheet of light takes the frame off the clip's last picture, then
the wordmark, the line and the address over a night street that drains to black
under them, with a whoosh across the move.

| | |
| --- | --- |
| backdrop | `assets/brand/qm-backplate.mp4`, 4s of footage. Falls back to `qm-starfield.png` with a 5.5% push if the plate is absent |
| wordmark | `assets/brand/qm-wordmark.png`, 720px wide, on a soft accent bloom |
| line | Inter 400, **40px**, sentence case, **bone `#fffdf9`**. A SAFE-AREA size — see below |
| address | Inter 500, 40px, uppercase, +4px tracking, **bone**, over a 148px accent hairline |
| staging | the entrance reveals plate + mark; line at +0.08s and address at +0.26s AFTER the entrance ends, each gliding up 46px over 0.40s on a smoothstep, sub-pixel; specular travels +0.62s for 0.95s |
| entrance | `ENTRANCE = "wipe"`, **0.78s**, steep diagonal: a broad white wash, ~358px of hot core with a soft halo. Travels 3100px, not the 1920 the reveal needs, so the light LEAVES the frame instead of being dimmed in place |
| sound | the recorded `swipe.mp3`, via `card_audio()`. Never `endcard_audio.write()` — that is the synth fallback |
| total | 4.0s |

**The backdrop is a real street, and that was the owner's choice over a cleaner
one.** It was a soft blue aurora gradient built from the intro film's nebula,
which read as a stock motion background; it is now a Seedance 2.5 roll of a
rain-wet financial district shot at road level, retimed 1.375x, which **drains to
black across the four seconds** so the world leaves and the mark is what remains.

Eleven rolls were auditioned. A graphic skyline measured far better as a bed for
type — p95 38 in the type band against this street's 86 — and lost anyway,
because it reads as an abstract rather than as a place. **Rank on measurement,
decide on the composite.** Everything needed to choose the next one is in
`tools/backplate/`: the prompt, the five rejected concepts with the measured
reason each lost, and the four scripts that gate a candidate.

**The plate ships UNGRADED.** This street's brightest phase is its first half,
which is exactly where the type lands, so the obvious move is to pull the head
down and even it out. Done at 0.50 it fixed the measurement and ruined the
picture — the depth and the wet reflections went with the highlights.
`conform.py --head` exists and is deliberately not used. Bone white at 253 over a
streetlight at 86 is already a wide margin.

**No scrim, and none needed.** The old card graded a dark band in behind the text
because the type was glass and glass needs dark behind it to exist. Both halves
of that went: the lines are flat bone now, and the plate runs 12–20 luma through
the type block on its own.

#### The three things about this card that are constraints, not taste

**The sound comes from `card_audio()`.** The selection between the recorded swipe
and the synthesised fallback lived inside `append()`, so the preview and every
build script written against it reached past and used the synth. The clips
shipped carried one sound and every outro rendered for approval carried another,
for months, until the owner caught it by ear. After the fix the outro correlates
0.9996 with the recorded wav and 0.03 with the synth; before, exactly reversed.
**A test render must carry the delivered sound or it is not a test of the
delivered thing.**

**Brightness in the wash is not an alpha change.** It peaks at 0.992 — the core
is opaque — so raising the coefficients adds nothing and instead flattens a few
hundred pixels to solid white, destroying the gradient `core`, `lip` and `mix`
exist to build (0.16/0.90/0.11 clips 249px; 0.20/0.96/0.12 clips 387px). It lives
in `WIPE_WHITE` (base colour off `ACCENT_HOT` toward bone; 0.55 halves the visible
cast) and `WIPE_CORE` (width; 340→460 grows the bright band 259→358px at zero
clipping). Widening costs travel: 460 needs `WIPE_TRAVEL` 3100 or ~2% of the
light is still in the bottom corner on the last frame.

**A line arriving on integer pixels is not smooth, whatever the curve.** The 46px
slide was `int()` for its whole life and stepped 3,4,4,3,4 over twelve frames — a
25% velocity swing on a move slow enough for the eye to track. As acceleration
spikes, the quantisation contributed 3.00 against the eased curve's own 1.60, so
it DOMINATED, and changing the easing alone would have been mostly wasted.
`place()` now shifts by the fractional part with a bilinear affine and the
rendered acceleration matches the ideal exactly. When "smoother" is asked for,
check sub-pixel before easing.

#### The lockup shares one measure, and that is a safe-area rule

All three elements sit inside **16.7%–83.2%** of frame width: wordmark 719px,
tagline 715px, address 704px.

That is not a composition preference, it is TikTok. The tagline was 52px and ran
**6.2%–93.5%**, which put 843px of ink under the like/comment/share rail — the end
of "Live." sat behind an icon on a phone. At 40px it clears the rail on every
platform, and its glyph run lands within 4px of the wordmark's, so the middle line
stops being the widest thing on the card.

**The gate: no card ink may pass 86% of frame width.** Anything that lengthens
`TAGLINE`, or any new line, has to be re-measured against it. The check is three
lines of numpy on the card's last frame — threshold the luma, find the ink
columns, assert the maximum is under `0.86 * W`. The vertical bands are clear by a
wide margin (the block ends at 62% and the lowest platform chrome starts at 76%),
so width is the only axis that needs watching.

#### Line staging is measured from the END of the entrance

`T_TAG_AFTER` / `T_URL_AFTER` / `T_SWEEP_AFTER`, never absolute times. The face is
built with `t` forced to 0.0 for every entrance frame, so a line whose absolute
start falls inside the entrance has already passed by the first real frame: it
appears fully formed, with no slide, on the frame the entrance ends. Absolute
times can only ever be right for one entrance length, and the two here differ by
nearly half a second.

#### The entrance that lost

`ENTRANCE = "rise"` is the b-roll cover move — the card arrives from below on the
same smoothstep a cutaway uses, which makes the outro obey the clip's own motion
compass (picture from below, type from the right, everything leaves left) instead
of reading as a card bolted onto the end. It was built, shown and rejected: *"I
like the flip up, but it should be something different... I kinda like the little
whitewash on the screen comes across. I like that one for the end of the clip."*
It stays behind the switch. **Do not quietly restore it on the argument that it
is more systematic. It is, and it lost anyway.**

At 30fps the rise cannot go below **0.33s**: the cover crosses the full 1920, and
ten frames is the fastest smoothstep whose worst step stays under the 1/6-of-frame
rule (0.33s peaks at 318px/16.6%, 0.30s at 354/18.4%, 0.28s at 410/21.4%). Past
that a full-frame move with no motion blur reads as a flash rather than a move.


### The scrim, removed — and the argument it was making

There was a gradient from the panel's lower edge to the frame bottom, zero alpha at
the panel edge easing to near-slate at 1920, and the captions sat on it. It is gone
with the band it lived in.

**Keep its argument, because it is the strongest objection to what replaced it.**
The scrim existed so the same type read the same from clip to clip: without it,
captions sat on whatever the picture happened to be doing, bright over a white
chart and fine over a dark room. *Inconsistency between clips is what stops a set
looking like a set*, and it is invisible until you put two clips side by side.

Per-clip adaptive colour re-opens exactly that defect, so it has to answer it:

- The **treatment** is identical on every clip — same band, same y, same size, same
  5px stroke, same blurred drop. Only the hue moves.
- The **base stays bone** on every clip whose zone is not genuinely bright, which
  is nearly all of them, so the body of the type matches across a set by default.
- The house cyan carries a prior, so most clips keep the same accent.
- The decision is **one per clip, never per caption**.
- `build_all` prints every pick at the end of a run and says so when a set came out
  with more than one accent, because the failure is only visible set-wide.

Judge it on a real batch side by side. If a set does read as mixed, pin it with
`"adaptive_captions": false` or a per-clip `cap_colour`. **Do not solve it by
re-adding a scrim, a plate or a box** — that is the 360px this change bought back.

### The duo split

`mode: duo` stacks both speakers, each in a band of `(PANEL_H - 14) / 2 = 953px`.
The crops must match the **band's** aspect (1080/953 = 1.133), not the panel's
0.5625 — filling a full-height half into a 1.13 band squashes the face. `analyze.py` emits a
correctly-shaped pair as `duo_crops`.

It is centred on the upper third of each half, not the middle: in a webcam two-up the
face sits high and the lower third is chest and desk, so a vertically-centred band
cuts foreheads off.

Use it for a genuine exchange. For one person holding the floor, a single-half `head`
crop gives a much bigger face and is the better clip.

**The bands fill, edge to edge.** A version that *fitted* the crop to the band height
and let the leftover width show blurred did keep whole heads, but it put dead space
down both sides, which is worse than a tight crop. With the panel the full frame each
band is 953px, which takes enough of a 1080p half that only hair comes off the top.

Author `duo_crops` at the band's aspect (1080/953 ≈ 1.13) and **anchor the bottom on
the chin** — from a 957-wide half that is an **845-tall** box. Anything that does not
match the aspect is re-cut rather than stretched, so a pair authored at the old 1.397
still renders and simply loses **38% of its width**, centred, with no error anywhere.
`preflight`'s CROPS check exists to catch exactly that.

There is no backdrop: the bands fill the frame (this paragraph used to describe
a blurred slate backdrop that `PANEL_R = 0` removed).

**The hook card is capped at `HOOK_MAX_BLOCK` 390px and shrinks until the
block fits.** This matters more than it looks: a naive "at most 3 lines" fit
lets a long hook overrun the panel, which happened on two clips and was only
caught by measuring the rendered overlay's lowest non-transparent pixel against
the panel top. Its vertical place is then decided per clip by `place_hook()` -
see "The hook is a centred white card" above.

### Punch-ins: the cuts become visible

**In `duo` both bands punch together, and that is a decision about evidence, not
a shortcut.** Duo was excluded from the punch for as long as the punch existed,
on the grounds that it needed per-band speaker attribution. Measured with
whospeaks' speech-gated ratio across three two-up spans of the 08.22 master, that
attribution is WEAK on two of three - margins of 1.13x and 1.12x over spans of 40
to 56 seconds. A punch window is 2 to 8 seconds with a fraction of the samples,
so per-window it would be worse, and a punch following a wrong verdict zooms in
on the LISTENER. The punch exists to turn invisible audio removals into visible
picture changes; punching both bands delivers that in full and can never name the
wrong person.

**The duo punch keeps the badge**, for the reason `_punch_box` already recorded
against the share tile: a two-up half burns its lower third into the bottom of
the frame, and punching about the face shaved the name off the 08.22 clip - "that
cut the M off Mike McGlone". So the shrink anchors bottom-left on both bands.
Verified on a rendered duo clip: 7 framing changes, longest unchanged hold down
to 13.3s from the whole clip, and "BigBeat / Founder and CEO of Quasar Markets"
fully legible in both framings.


Measured before this: 23 removals a minute, and a median 29 seconds on one
unchanging frame, because a removal on a locked-off webcam leaves the speaker
exactly where he was. So there are now TWO framings, A at 100% and B at 106%
about the face centre, both cut from the SOURCE crop and scaled once (never a
zoom of the upscaled panel, which softens every frame), and the renderer
toggles between them at cuts with an overlay `enable`. The ladder, in
delivered seconds: a sentence-end join once 2.0s have passed since the last
toggle; failing one of those by 5.0s, a silence join that removed at least
0.30s; failing one by 7.0s, two frames before the next keyword. A FORCED flip
under every cutaway, at its first exit frame (the cover is still full-frame
there, so what the swipe uncovers is already the new framing - the review
caught a first version flipping at the first UNCOVERED frame, which exposed
five frames of the old framing and then snapped: a double cut on every
return); frozen for the second before a cutaway and under it; never inside
the hook's travel; never in the last second before the end
card grabs its frame; the first sentence toggle may land from 0.6s so there is
one change inside the 1.3s stay-or-scroll window. On the 08.21.26 McGlone
reference that is 11 framing changes, a longest unchanged hold of 11.4s and a
median of 7.7s, plus the 5 cutaways. `head` punches the whole panel; `share`
punches the face tile only - the chart is built once and never scales, and the
tile's punch is anchored BOTTOM-LEFT rather than on the face, because a meeting
tile's bottom strip is the burned-in lower third. Centring it on the face
clamped on both axes and shaved 18px off the left and 16px off the bottom,
which cut the M off "Mike McGlone" and dropped the credential line off the band
completely. It shipped that way on 08.22 before the review caught it; `duo`
and `duo_share` are not punched, because toggling "the top band by default" is
the wrong person half the time and the pipeline has no per-band speaker
attribution yet. `"punch": 1.0` in project.json turns it off. Preflight's PUNCH
line prints the cadence from the same function the render calls.

**The FIRST change is seeded, not waited for.** The ladder is join-driven, so
it fires wherever the speech happens to pause - and measured on the delivered
files that was **+7.2s** on the 08.22 clip and **+7.7s** on the 08.21
reference. The entire window in which a viewer decides whether to stay was one
unchanging frame with a card on it.

> **THE TWO NUMBERS THIS USED TO CITE DO NOT SURVIVE A CHECK, and they are
> removed rather than quietly left in.** It said "Meta's 2025 attention study
> puts the stay-or-scroll decision at 1.3s" and "VidMob measured visual hooks
> beating text-overlay hooks 2.4x on 3-second retention". A 2026-08-25 web pass
> could not trace either to a primary source - both circulate widely in
> short-form marketing blogs, neither is attributable to a published study or a
> named dataset. They were repeated here as if measured, which is exactly what
> this file tells everyone else not to do.
>
> **The decision does not need them.** It rests on the rig's OWN measurement,
> which is real: the first framing change landed at +7.2s and +7.7s on delivered
> files, so the opening seconds were one unchanging frame with a card on them.
> Whatever the true stay-or-scroll number is, seven seconds of stillness is on
> the wrong side of it. Do not re-import an unsourced figure to justify a
> decision that already has evidence.

A good span opens on someone talking, not pausing, so waiting for a join loses
that window on every clip.

So an opening toggle is seeded inside `PUNCH_OPEN` (0.8 to 2.0s), landing on
the first **keyword** in that stretch - a noun, a number or a name - so the cut
is motivated by a word rather than by a stopwatch, and falling back to
`PUNCH_OPEN_AT` (1.2s) when the opening carries no keyword. It is a punch IN:
the clip opens in A and tightens. Measured on the 08.22 clip after the change,
the first picture change is at **+0.83s**, on the word "5%", and its
frame-to-frame magnitude is 21.6 against 35.0 for a full b-roll cutaway - so it
is about 62% as strong a change as cutting away entirely, not a subtle nudge.

Two things it deliberately does NOT do. It is **skipped** when the material
already changes in that window - a **sentence** join at or before
`PUNCH_OPEN_HI` - because two toggles a few tenths apart is a flicker, not a
cut. Only a sentence join counts: a silence join that early carries
`PUNCH_RUNG_SIL` (5.0s) of dwell it cannot possibly have yet, so it can never
fire, and the first version of this rule let one SUPPRESS the seed in exchange
for nothing - putting the clip straight back to a static opening on 3% of real
spans measured over this master. And it **advances the rung clocks like any other toggle**, so it can
consume the slot a later rung would have used - on the 08.22 clip the +7.2s
keyword-rung change disappeared because only 6.4s had passed rather than 7.0.
That is correct: the rungs mean "this long since the framing last changed", and
it did change. The count stays the same and the change moves to where it earns
its keep. `"punch_open": false` in project.json goes back to waiting for a join.

### The live caption word pops, 6% at most

3 frames up to 1.05 (1.06 on a number, `$` or `%`), 3 frames settling to 1.02,
and it HOLDS at 1.02 while it is the live word. Colour shift plus a scale under
6% is the premium version of the highlight in the 2026 survey; bounce, fill and
word boxes are the template ones. The word is drawn bigger on its own,
anchored on the BASELINE and centred on its 1.0 advance width, so the row
never reflows, the neighbours do not move, and a word with a descender sits
where it sat (anchored on the em-box middle it dropped 8-11px). A chunk's
0.30s linger now stops at the next chunk's first word: the old overlap hid
the first word's pop on 110 of 117 chunks and made every chunk appear 317ms
late. Words under 4 frames get colour only. Chunk changes are
a hard switch.

### Two people plus the screen

`duo_share` puts both camera tiles **side by side** in a strip across the top and the
app below. Side by side rather than stacked because stacking costs twice the height
and this panel has none to spare — the screen is why the clip exists. It also matches
what the source gives: meeting PIP tiles are landscape, so each drops into half the
width with almost no trimming.

### How a share panel is split

Three numbers decide it, and they pull against each other. `pack_share()` resolves
them; `preflight`'s PACK line prints the result so you can see the trade before
spending a render.

| | |
| --- | --- |
| the app's natural height | `1080 x h / w` of its crop. A 16:9 slide is 608px and **nothing can make it taller** without cutting words off the ends of the bullets |
| the app's floor | `APP_MIN_FRAC` = 52% of the panel. The BAND, not the app |
| the tile's own height | `band_width x h / w` of the camera crop. The one band height that crops nothing off it |

**The app has a floor because the old rule had none.** It gave the app its natural
height and handed every remaining pixel to the face, which was defensible at 1560
and wrong at 1920: measured on a real slide clip, the app's share of the frame
*fell* from 44% to 35% when the panel grew, and the face went to 64% — two thirds
of a vertical video spent on an empty room behind a speaker.

**The face band is held near the tile's own height.** A camera tile has exactly one
band height that crops nothing, and deviating either way costs something specific:
too short and a portrait tile loses its bottom strip, which is the burned-in name
badge; too tall and a landscape tile loses width off both ends, which is the same
badge's ends. `TILE_TRIM_MAX` keeps it within 12% of that height in either
direction. Attribution beats a few percent of screen.

**The band height does not change how sharp the face is.** The band is always the
full width it is given, so a 228px-wide meeting tile is a 4.74x blow-up whatever
height the band has — measured at 1226, 908 and 700, identical every time. If the
face is soft, the tile is small, and no packing fixes it.

### The app is FITTED, never cropped to fill

The app is scaled to fit its band and never trimmed. What is left over is filled
with the **average colour of the app's own outermost rows**, which on a solid slide
is literally invisible — the blue simply continues — and on a chart continues the
chart's own background rather than introducing a slate bar.

Three details, each of which was a visible fault first:

- **The fill is a flat average, not a stretched edge row.** Stretching the row
  turns any structure in it into vertical streaks running the height of the fill;
  a chart with a blue element at the left of its top row grew a blue stripe up the
  frame.
- **The outermost 2% of the crop is dropped before drawing**, on whichever axis is
  being filled. An authored crop routinely overshoots its content by a few pixels
  — one slide crop ran 5px past the bottom of the slide into PowerPoint's black
  surround — and drawn, that sliver is a black hairline straight across the frame.
  Dropping it also makes the join seamless by construction, because the fill then
  continues the row it is next to.
- **The fill all goes at the BOTTOM.** The app band is the bottom of the frame and
  the bottom of the frame is where the apps draw their own chrome, so fill parked
  there costs nothing that was not already covered. Centring it spends half the
  fill above the app and pushes the app's content down into the caption band —
  on a slide, that is the title landing under the words.

`face_h` on a clip overrides the whole negotiation. Use it when the speaker matters
more than the screen, or when preflight says the two constraints cannot both be met.

### Screen-share split

Speaker's camera above the shared screen, both at panel width. On the QM
webinar the camera tile was only 280x132 native, so 1080 wide is already a 3.9x
blow-up — the crop is re-cut to the band's aspect rather than stretched to it. A
true half-and-half at 4x was tested and is visibly blocky.

There is **no global face-band height**. `pack_share()` derives the split per clip
from what the app naturally wants at full width, and the face takes the rest; a
per-clip `face_h` in the slate overrides that. A project-level `face_h` key never
reached the packer and is inert — do not reintroduce one, because a single number
cannot be right for both a portrait chart and a 16:9 deck. `preflight`'s PACK check
prints the resulting split, how much of the app's width survives it, and how far the
camera tile is being blown up.

The taller panel changes the arithmetic here in the clip's favour: on the 08.11.26
master the face band went from 401px to 761px while the chart kept **100%** of its
width, because the extra 360px of frame went to the face and the app was already at
its natural height.

Crop **inside** the meeting furniture — past the active-speaker border and above
the name badge. On that recording the border sat at master y461-463 and
x1632-1633 with the badge below y596. Find yours by looking for the border's
colour rather than assuming those numbers.

## Retargeting to another brand

Change the palette and font constants at the top of `qmclip.py` and the `cta`
key in `project.json`. The layout, the cut mechanic and the caption engine are
brand-independent.


## Ending on a finished sentence

A span picked off a transcript ends wherever the timestamp fell, and that is
regularly mid-clause. A clip that stops while someone is still talking reads as a
mistake no matter how good the moment was, so `render()` moves the out-point to
the nearest sentence end before anything else happens.

It decodes 5s past the requested end so it can see the *next* full stop, not only
the previous one, then takes **whichever move is smaller**. That matters in both
directions and real clips proved each: one lost its best line ("...the highest
since the end of 1928") by running on 1.6s into a weaker trailer when pulling back
1.4s kept it; another would have lost 7.2s of a 30s clip by pulling back when
running on 0.9s finished the thought. Running on is capped at 4s, pulling back at
a third of the clip, and running on is abandoned if it would cross a layout change.

**The tail pad is clamped to the real gap.** Padding a flat 0.42s past the final
word is right after a pause and wrong in continuous speech, where it drags the
first phoneme of the NEXT sentence in under the end card. Ending on a finished
sentence and then playing 0.4s of the following one is the same defect wearing a
different hat, so the pad is `min(0.42, gap to the next word)`.

**What counts as a sentence end is the subtle part.** A trailing period is not
enough, and both false positives shipped before this was tightened:

- an **ellipsis** ends with `.` — a clip went out ending "now that's a different…"
- an **abbreviation** ends with `.` — the next attempt ended on "Now, how Mr."
- **initials** ("E.") and internal-period tokens ("U.S.") are the same trap

`ABBREV` holds the exclusions. Add to it rather than loosening the test.


## The 45 second floor

Every delivered clip runs 45 seconds or longer, end card included. (35s until
2026-08-04, then raised.) `MIN_CLIP` in
`qmclip.py` holds the number and `render()` enforces it twice, because the two ways
a clip ends up short are different problems:

- **the span was too short to begin with** - caught before any decoding, so a doomed
  cut costs nothing
- **the silence pass shortened it** - caught after removals. This is the one that
  bites: collapsing dead air is exactly what makes a live-show span lose four or
  five seconds, so a span picked at 34s can finish at 29s.

Both refusals print the shortfall and what to do about it. Neither is a warning -
the build stops, because a short clip is not something to notice later.

Practically: **author spans at 46s or more.** 45 minus the 4s card is 41s of speech,
and the gap between 41 and 46 is the margin the silence pass eats.

## What the 2026 survey found, and what was NOT applied

Three research passes on 2026-08-22 (hook cards, cutaway transitions, platform
safe zones and caption conventions; sources in the session log). What they
agreed on drove the hook placement and animation and the b-roll zoom-through
above. What they recommended about the CAPTIONS was deliberately not applied,
because those are locked decisions in this file that nobody asked to reopen -
recorded here so the next person knows the trade was seen:

| finding | this pipeline | status |
| --- | --- | --- |
| safe top 290 (Meta ad spec 269, 4:5 feed crop 285) | hook prefers y300 | applied |
| TikTok top chrome ~140, Shorts ~288 | `HOOK_MIN_TOP` 140 | applied |
| hook 3 to 5s, filled card beats outline, never over the face | 3.0s, card, face-aware | applied |
| text arrives 150-400ms, no typewriter; one vocabulary | swipe 0.30s in / 0.233s out | applied |
| cutaway transition under ~8 frames, no whoosh, one direction | rise 7f in, swipe-left 6f out | applied |
| alternate framing at cuts (the retention edit's core move) | A/B punch 100/106% on the face, ladder above | applied |
| live word: colour shift + <=6% scale, no bounce | 1.05 (1.06 numbers) settling to 1.02 | applied |
| picture leads the word 80-150ms (video-leads-audio undetectable to 125ms) | 150ms | already so |
| consolidated safe bottom 520 (TikTok long description, Meta ads 672) | captions end y1430 | NOT applied: organic numbers hold, and the band is derived in code |
| caption size 72-76px, 3px stroke ("86px and 5px stroke read template-loud") | 86px, 5px | NOT applied: raised twice on evidence, see the top of this file |
| measure 720 (180px rail) | 740 | NOT applied; 20px inside the warn band |
| compliance plate on screen 3.5s | none | NOT applied: house rule against fine print on modules |
| X cashtags now render a price card (Apr 2026) | cashtags in X copy | worth knowing before posting |
