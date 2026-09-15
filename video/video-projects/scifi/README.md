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

## What the audio covers

3.7 min of source narrates **4 of the 13 slides**: 2, 4, 5, 9. The other nine
have no audio at all. See the discard log for what was cut and why.
