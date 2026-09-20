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
| `money-tree.html` | 2.80s | transition sting. The tree springs up, bills pop out of the canopy and flutter down, then it retracts. Bills are densest at 1.2–1.7s, so **put the hard cut 1.45s into the sting** and the join is hidden. |
| `title-card.html` | 3.20s | start of a product test. Gold `$1` badge, `PRODUCT TEST #n` kicker, product name. Anchored bottom-left — both subjects sit centre and centre-right in the living-room half, so a centred card lands on a face. |

To make a second title card, copy the file and change the `#name` and `#kicker`
lines. Everything else is measured from the text, so length changes are safe.

## Status — blocked on audio

**The uploaded file has no audio track at all** (`nb_streams=1`, no audio
stream). That blocks the parts of the brief that depend on content:

- Title cards can't name the products, because the product names are spoken.
- Scene boundaries can only be guessed from picture. Visual scene detection
  finds cuts at 18.7s, 48.8s, 69.7s, **169.8s** and 228.5s. Only 169.8s is a
  real location change (living room → bathroom); the others are camera or
  exposure shifts within the same setup.

So the placeholder card reads "Glue That Actually Sticks?" — invented, not from
the footage. Re-export with audio and the rest follows quickly.

## Also worth fixing

The living-room half (0–170s) is underexposed: mean luma 70/255 where 110–128
is normal. The bathroom half (170–233s) is fine at 116/255. A lift on the first
half would match them and would help a lot on phone screens, which is where
family viewers will watch it.

## Demo

`renders/demo-transition.mp4` (rebuild: see the ffmpeg command in the session
notes) shows both cards over the real footage across the 169.8s cut.
