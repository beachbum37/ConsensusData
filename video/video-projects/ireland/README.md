# Ireland — monastic reading to the AI revolution

Three narrated slide segments from a Gemini Notebook deck, joined into one cut.
Same treatment as `scifi/`: attribution phrases out, levels matched, dead
picture fixed, no re-narration.

| Source | Length | Covers |
|---|---|---|
| `irelandA.mp4` | 1:14 | monastic vs scholastic reading — the book as sacred object, then the reader mastering the text |
| `irelandB1.mp4` | 1:54 | the thesis question, the velvet rope, information as exclusive luxury, Irish monasteries, the scriptorium |
| `irelandB2.mp4` | 2:27 | printing press, internet, smartphones, the real question about AI, the close |

Build:

```
cd video/footage/ireland
python3 ../../tools/build_ireland_cut.py --order B1 A B2 -o edit/ireland-cut-recommended.mp4
python3 ../../tools/build_ireland_cut.py --order A B1 B2 -o edit/ireland-cut-as-listed.mp4
```

Both run 5:36. `ireland-trims.json` records every change.

## Running order — B1, A, B2 is recommended

The segments were listed A, B1, B2, and that version is built too. But the
content argues for B1 first:

- **A opens mid-sentence.** Its first words are *"literally change the nature
  of human thought and intellectual freedom"* — no subject, nothing before it.
  As a cold open it sounds like the viewer missed something. Its title slide
  ("When did we stop revering and start using books?") carries it visually,
  but the audio does not.
- **B1 opens with the actual thesis:** *"How do we define success in the age of
  AI?"* — a question that frames all three segments.
- **A's last line hands straight to B2's first.** A ends *"…precipitates the
  very next wave of innovation"*; B2 begins *"the printing press completely
  revolutionized…"*. Putting A second makes that a single thought.
- **B1's last line hands to A.** B1 ends on a scribe managing three or four
  pages a day; A picks up with how those books were then read.

So B1 → A → B2 reads: thesis → information as luxury → the reader takes
control → printing press, internet, AI → close. A → B1 → B2 works, but opens
on a half-sentence and splits the scriptorium from the reading it describes.

## Changes made

**Attribution removed.** One occurrence, in A at 33.92–35.02s: *"But I
absolutely love this analogy **from our source material**, because…"* → the
phrase is trimmed mid-sentence, leaving *"But I absolutely love this analogy,
because it hits the nail right on the head."* Both cut edges sit in measured
silence (−43 dB and −82 dB), not on transcript word boundaries, which drift.

**Picture dropout fixed.** In B1 at 65.5–70.5s the slide transition renders as
a **blank white frame for 5.0 seconds** while the narrator says *"Information
as trapped luxury."* Cutting it would have clipped the line, so the incoming
"Information as Luxury — A Trapped Resource" slide is held across the gap
instead. Audio is untouched, so sync and duration never move, and the words now
land on the slide that states them. No blank run of 1s or more remains.

**Levels matched.** Sources differed (A −22.5, B1 −24.4, B2 −23.3 dB mean).
Each segment is normalised whole, before slicing, so a trim inside it cannot
shift level across the join. Finished cut sits at −19.5 dB mean, −1.2 dB peak.

**Breaths between segments.** 0.30s of held last frame plus silence, so the
three land as chapters rather than colliding. The joins themselves are slide
changes, which is what the rest of the deck does anyway.

**No fillers found** in any segment — the narration is synthetic, so there are
none to remove.

## Left alone

The slow delivery of some slide titles (two to three seconds between words) is
how the source is narrated throughout, not a defect. Only the 5-second blank
was treated.
