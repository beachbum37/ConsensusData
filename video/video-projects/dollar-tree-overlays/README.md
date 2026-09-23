# Dollar Tree product test — playful overlay cards

Overlay cards for `video/footage/dollar-tree/doltree.mp4` (1920x1080, 30fps,
3:53). Same pattern as `actuary-overlays`: each card is an independent
composition rendered to ProRes 4444 with alpha, then composited onto the cut.

```
npx hyperframes render -c compositions/<name>.html --format mov \
    --output renders/<name>.mov
```

`renders/` is gitignored — rebuild from the HTML. The lint error about
`index.html` having no renderable content is expected for this multi-card
layout and matches `actuary-overlays`; render each card explicitly with `-c`.

## Cards

| Card | Duration | Where it goes |
|---|---|---|
| `money-tree.html` | 3.60s | transition sting. Bare branches spring up, leaf out **in dollar bills**, then shed them — the canopy empties from the crown down and the tree is left bare but for three bills still clinging, holds and sways for a beat, then retracts. Bills are densest at 1.3–1.9s, so **put the hard cut 1.6s into the sting**. |
| `title-card.html` | 3.20s | start of a product test. Gold `$1` badge, `PRODUCT TEST #n` kicker, product name. Anchored bottom-left — both subjects sit centre and centre-right in the living-room half, so a centred card lands on a face. |

To make a second title card, copy the file and change the `#name` and `#kicker`
lines. Everything else is measured from the text, so length changes are safe.

## The cut

Source is three 55.8s clips at 1280x720/30 with stereo audio: `dtree1.mp4`
(intro + the format + the toothpaste reveal), `dtree2.mp4` (smell test),
`dtree3.mp4` (taste test). They join end to end for 2:47.

| Overlay | At | Why there |
|---|---|---|
| `money-tree` | 0:27.2 | **the product reveal** — "who looked at toothpaste and thought…" at 31.2s. The tree is reserved for a genuinely new product, and this video has exactly one. |
| `card-product` | 0:31.0 | names it: Ice Cream Toothpaste |
| `bill-wipe` | 0:55.2 | join 1 at 55.77s — same product, so the light wipe, not the tree. Peaks at 0.55s, so the sting starts 0.55s before the cut. |
| `card-smell` | 0:56.8 | clip 2 opens "What does it smell like?" |
| `bill-wipe` | 1:51.0 | join 2 at 111.58s, same reasoning |
| `card-taste` | 1:52.6 | clip 3 is the tasting |

**Transition grammar.** Two weights, and which one fires carries meaning:
the money tree (3.6s, full frame, tree sheds its bills) means *a new product
starts here*; the bill wipe (1.3s, a flurry sweeping across, no tree) means
*same product, new segment*. Don't spend the tree on an ordinary cut — it
stops meaning anything.

## Grade

The living room runs across **clips 1 and 2**, not just clip 1 — clip 3 is the
only bathroom footage. Both living-room clips are lifted so the room doesn't
step in brightness at the join:

| Clip | Room | Ungraded luma | Grade | After |
|---|---|---|---|---|
| dtree1 | living room | 63–85 | `eq=gamma=1.45:saturation=1.06` | 95–117 |
| dtree2 | living room | 73–88 | `eq=gamma=1.35:saturation=1.05` | 97–112 |
| dtree3 | bathroom | 107–127 | none | unchanged |

Gamma rather than a curve or a brightness offset: it lifts shadows and mids
while leaving the white point alone, and the window behind them is already
blown. Clipped-white pixels go from 6,006 to 6,863 out of 2.7M, so the window
is no worse. Measured across the finished cut, luma now holds 100–115
throughout.

Build (one pass, no intermediate encode):

```
ffmpeg -i dtree1.mp4 -i dtree2.mp4 -i dtree3.mp4 \
       -i money-tree.mov -i card-product.mov -i card-smell.mov -i card-taste.mov \
       -filter_complex "…concat=n=3:v=1:a=1… scale=1280:720 … setpts+offset … overlay" \
       -c:v libx264 -crf 20 -c:a aac -b:a 192k out.mp4
```

Overlays render at 1920x1080 and are scaled to 1280x720 in the composite, so
the compositions stay resolution-independent. The full command is in the
session notes; `edit/dollar-tree-cut.mp4` is the working master and
`video/deliverables/dollar-tree-ice-cream-toothpaste-720p.mp4` the tracked copy.

The earlier 4-minute upload was unusable: it held only **7 unique frames**
across 3:53 and carried no audio track — a broken export, not a real recording.
These three clips replaced it.

## Also worth fixing

**The uploaded file has no audio track at all** (`nb_streams=1`, no audio
stream). That blocks the parts of the brief that depend on content:

- Title cards can't name the products, because the product names are spoken.
- Scene boundaries can only be guessed from picture. Visual scene detection
  finds cuts at 18.7s, 48.8s, 69.7s, **169.8s** and 228.5s. Only 169.8s is a
  real location change (living room → bathroom); the others are camera or
  exposure shifts within the same setup.

So the placeholder card reads "Glue That Actually Sticks?" — invented, not from
the footage. Re-export with audio and the rest follows quickly.

The green wash behind the tree is deliberately weak (0.22 alpha) and clears at
1.95s, before the bare beat — the bare tree is the payoff, so it plays against
clean picture rather than through a tint.

## Also worth fixing

The living-room footage is underexposed: mean luma 81/255 at 0:30 and 0:60,
where 110–128 is normal. The bathroom footage is fine at 115/255. Lifting the
first 56 seconds would match the two and would help a lot on phone screens,
which is where family viewers will watch. Not applied — the cut ships ungraded
until asked.
