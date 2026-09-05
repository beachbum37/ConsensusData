# Dollar Tree vs Walmart — Unit Price Showdown

A 33s vertical (1080×1920, 30fps) price comparison. Built as the worked example
for this studio: it exercises the whole HyperFrames path — sub-compositions,
generated markup, count-up animations, whip transitions, render contract — with
no footage required.

## ⚠️ The prices are placeholders

Every item in `data/items.json` has `"verified": false`. The numbers are
plausible-shaped stand-ins so the pipeline renders end to end. **They are not
researched prices and must not be published as fact.**

While any item is unverified, the build stamps a `SAMPLE DATA · NOT REAL PRICES`
badge on every frame. To make it real: replace the entries with numbers off your
own receipts, set `"verified": true`, fill in `"source"` (store number + date, or
a product URL), and the badge disappears on the next build.

## Build it

```bash
cd video/video-projects/dollar-tree-vs-walmart
node scripts/build-video.mjs                                   # data → compositions
npx hyperframes lint                                           # must be 0 errors
npx hyperframes preview                                        # localhost:3002
npx hyperframes render --quality draft --output renders/draft.mp4
```

## How it's wired

```
data/items.json  ──scripts/build-video.mjs──>  compositions/02-items.html
                                               compositions/03-tally.html
index.html  (hand-authored)  ──data-composition-src──>  all three compositions
```

`index.html` and `compositions/01-hook.html` are hand-authored. The other two are
**generated** — edit the data or the generator, never those files directly.

Scene timings in `index.html` depend on the item count. The build script does not
rewrite `index.html`; it **verifies** it and exits non-zero printing the exact
attributes to change. Change the item count → run the build → paste in what it
tells you.

## The argument the video makes

Sticker totals are not comparable when package sizes differ — Walmart's total is
bigger largely because its packages are bigger. So the script computes the honest
number: take the Dollar Tree *quantity* of each item and price it at Walmart's
*unit* price. With the placeholder data that produces a genuine upset — Walmart
wins 4 of 6 items on unit price, yet the Dollar Tree basket still comes out
cheaper, because one item (greeting cards) swings the whole basket.

That tension is the point of the edit. If your real numbers don't produce it, the
payoff line adapts — see `upsetLine` in the generator.

## Structure

```
index.html                  root composition, hand-authored
compositions/01-hook.html   hand-authored — the matchup title
compositions/02-items.html  GENERATED — one card per item
compositions/03-tally.html  GENERATED — totals + payoff number
assets/brand-tokens.css     palette; swap the hexes, everything follows
data/items.json             the only file you need to touch for new data
scripts/build-video.mjs     generator + timing verifier
meta.json                   id / name / 1080×1920 / 30fps
hyperframes.json            CLI config
```

The palette is deliberately generic — "side A" green and "side B" blue are
editorial colors for a two-column comparison, not either retailer's brand system.
No logos, no trade dress.
