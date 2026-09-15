# scifi — "Jobs and AI: Science Fiction or Fact?"

A slide-driven cut. The deck is the spine; the narration is NotebookLM audio
(two hosts plus the listener interjecting in interactive mode) captured as
three Otter voice notes. Audio is conformed to the slides, not the other way
round.

| File | What |
|---|---|
| `slides.json` | the 13 slides as read from the image-only deck — titles, themes, keyword hints. The PPTX has no text layer. |
| `plan.json` | kept segments (anchored by phrase, keyed to a slide) and discards with reasons |
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

## What the audio covers

3.7 min of source narrates **4 of the 13 slides**: 2, 4, 5, 9. The other nine
have no audio at all. See the discard log for what was cut and why.
