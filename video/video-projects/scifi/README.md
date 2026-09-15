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

### v3 — fewer, longer takes

v2 cut on every sentence (23 cuts in 96s) and read as choppy. v3 keeps the light
conversational glue (*Exactly. Totally. Not yet, anyway.*) inside long runs and
cuts only at slide boundaries and around genuinely off-content material:
7 continuous takes, 6 cuts. Where consecutive takes are adjacent in the source,
the audio runs unbroken and the slide changes underneath — the tail of `(3)`
plays 21s straight across slides 5, 6 and 9. The Stradivarius passage is out
in both tellings by request; the "six skills" line stays.

### v4 — the "Personal AI OS" chapter appended

A second deck, `The_Personal_AI_OS.pptx` (five image-only slides, kept in
`personal-ai-os/`), re-issues the OS chapter: 01 Relative Expert, 02 Curate your
taste, 03 Prompt engineering is dying → Contextual AI OS, 04 The Chef's Loop,
05 Build your Jarvis (vending vs slot machine). 01/02/03/05 are redesigns of the
original slides 7/8/9/11; 04 is new.

Every transcript variant was searched for the five slides' material (degree,
Friday update, workflow, taste, em-dash, dictate, metric, vending, slot machine,
deterministic, Jarvis, prompt, context, intern…). Only slide 03 has narration:
the summer-intern / business-context take in `(3)` 33.4–42.1s. It now closes the
video under the new slide 03 instead of sitting under old slide 9 mid-run; the
`(3)` take therefore ends on slide 6 ("…your own projects.") and the cut lands in
the 130ms gap before "Like the summer intern" — no word is clipped. Slides 01,
02, 04 and 05 have **no audio anywhere in the three recordings** and are not in
the cut. The build takes them through `plan["slide_files"]`, a name → PNG map,
so a second deck does not need to be renumbered into the first.

## What the audio covers

3.7 min of source narrates **7 of the 13 original slides** (2, 3, 4, 5, 6, 9, 10)
and **1 of the 5 Personal-AI-OS slides** (03, which is old slide 9 redesigned).
Original slides 1, 7, 8, 11, 12, 13 and OS slides 01, 02, 04, 05 have nothing in
the recordings that serves them. 98.3s kept, 127.5s discarded — see the log.

### v5 — the second recording (`take2.mp3`), original deck only

A new 20.6-minute recording (`take2.mp3`, the Audiomass export) walks the whole
deck in order: history → velvet rope → six skills → wrap-up. v5 is built from
this recording alone, against the 13 original slides, in slide order.

**Pipeline for a new recording** (all from `video/footage/scifi/`):

```
whisper-cli -m ggml-small.en.bin -f take2.wav --dtw small.en -ml 1 -oj -of take2.dtw
python3 ../../tools/dtw_to_words.py take2.dtw.json -o edit/transcripts/take2.json
python3 ../../tools/sentence_table.py edit/transcripts/take2.json take2.mp3 --src take2 -o edit/sentences.json --append
python3 ../../tools/filler_pass.py take2.mp3 --context edit/transcripts/take2.json   # 1 filler: a deliberate "Ah" — kept
python3 ../../tools/build_slide_cut.py edit/plan.json -o edit/scifi-cut-v5.mp4
```

**Mapping.** The recording's running order differs from the deck's in two places,
so the plan reorders: the "wrong questions" passage (bar exam, Model T in a
vacuum, engineers 10% faster) is spoken *after* the velvet-rope history but sits
on slide 3, *before* it; and the six-skills recap from the wrap-up is used as the
overview on slide 6, ahead of the skills themselves. Everything else runs in
source order. 12 of 13 slides have narration:

| Slide | Source | What |
|---|---|---|
| 1 | 0:26–1:00 | hype cycle vs the bigger picture of history |
| 3 | 4:00–4:38 | bar exam / Model T in a vacuum; the enterprise trap |
| 4 | 1:06–3:52 | velvet rope, domino effect, printing press, automobile, luxury phase |
| 5 | 4:39–5:17 | expertise made accessible; the kitchen-table builder |
| 6 | 18:44–19:11 | the six skills named in one breath |
| 7 | 5:23–6:33 | relative expert, Friday update, ROI, task force |
| 8 | 6:34–9:07 | taste: email joke, em dashes, signature, library |
| 9 | 9:07–10:54 | prompt vs context, the intern, AIOS, amnesia |
| 10 | 10:54–11:38 | persistent context: your transcripts, SOPs, walled garden |
| 11 | 13:25–15:10 | Jarvis; vending machine vs slot machine |
| 12 | 15:10–15:28 | cloned output, five-person team |
| 13 | 19:11–20:35 | don't quit your job; the provocative send-off |

**Slide 2 (The Plumber's Hedge) has no narration in this recording** — nothing
mentions trades, plumbers or a hedge. The only take that serves it is the old
`Note.mp3` opener used in v1–v4.

**Attribution lines removed** (the brief: no "the sources" / "the research"):
six occurrences. Three were whole sentences and are cut at sentence boundaries;
three were trimmed *inside* a sentence with a tight join — `"gap_before"` on a
segment overrides the default pause, so "…prompt engineering, but [the research
suggests] that's actually a dying art" plays with a 0.08s join instead of a
0.4s pause. Also out: the Stradivarius line and its musicians/garages follow-up
(violin, by request), and the hosts' bridges that only made sense in the
original order.

**Unmapped and logged** (`discards.md`): skill four *iteration speed* (1:47),
skill six *job stacking* (1:43), *building in public* (1:00), and the history
half of the wrap-up. None has a slide in the original deck; the first is slide
04 of the Personal AI OS deck.

Result: 14:22, 15 audio spans, 12 slides, no silence over 1s, levels −19 dB mean.
Every slide transition was frame-checked against the slide PNGs.
`edit/scifi-cut-v5.mp4` is the 1080p master; `-preview.mp4` is the 720p copy.
