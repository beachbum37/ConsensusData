# scifi — "Jobs and AI: Science Fiction or Fact?"

A slide-driven cut. The deck is the spine; the narration is NotebookLM audio
(two hosts plus the listener interjecting in interactive mode) captured as
three Otter voice notes. Audio is conformed to the slides, not the other way
round.

| File | What |
|---|---|
| `slides.json` | the 13 slides as read from the image-only deck — titles, themes, keyword hints. The PPTX has no text layer. |
| `plan.json` | kept sentences (anchored by phrase, keyed to a slide) — `"discards": "auto"` makes the log the full complement of what is kept, with `discard_notes` for human reasons on specific ranges |
| `sentences.json` | every sentence in the source with its measured loudness, longest internal dead air, and a banter/content label — the table the mapping was made from |
| `timeline.json` | resolved output timeline — where every segment and slide lands |
| `discards.md` | **the record of removed audio**, with source timestamps and transcript |

Build: `python3 video/tools/build_slide_cut.py edit/plan.json -o edit/scifi-cut.mp4`
from `video/footage/scifi/` (source audio lives there, un-ignored for mp3/pptx).

## Transcript alignment — use DTW, not the default

The default whisper word timestamps were **3.3s wrong** on one file (`Note_otter_ai (3)`):
they placed the first content word at 15.95s where the waveform is flat −91 dB; the
speech actually starts at 19.25s. whisper.cpp's `--dtw small.en` token timestamps were
right on all three files. The transcripts in this folder are the DTW pass; the default
pass is kept alongside as `*.heur.json` for comparison.

Every cut edge was then verified against the waveform (150ms inside vs outside), not
trusted from the transcript. `build_slide_cut.py` also merges segments that are
contiguous in the source so a slide change is a cue over continuous audio, never an
artificial pause with a double fade mid-sentence.

## Method — sentence-level, not file-level

v1 mapped each recording to one slide and shipped 10s of near-silence inside a
kept span (word timestamps smeared a short sentence across a long gap) followed
by host banter. v2 works a sentence at a time:

1. **Sentence table** — split on terminal punctuation, then measure each
   sentence's mean level and longest internal silence from the waveform, and
   label host glue (*Exactly. Totally. It really is. That is such a brilliant
   way to frame it.*) as banter.
2. **Map sentences to slides by the deck's own text** — a sentence can land on
   any slide, in any order; slide order is the spine. Sub-sentence anchors trim
   glue prefixes at word level (*"What is fascinating here is"* → gone).
3. **Snap every span to its voiced bounds** before cutting, and refuse any span
   with ≥1.5s of dead air inside it.
4. **Normalise each span** (loudnorm −16 LUFS) — one file was 10 dB quieter.
5. **The discard log is the complement of what is kept**, tiled against each
   source to 100%, so nothing is removed unlogged.

## What the audio covers

3.7 min of source narrates **7 of the 13 slides**: 2, 3, 4, 5, 6, 9, 10. Slides
1, 7, 8, 11, 12, 13 have nothing in the recordings that serves them. 95.6s kept,
135.3s discarded — see the log.
