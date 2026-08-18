---
name: interview-arc
description: Build a podcast interview prep sheet - a themed arc of questions for a specific guest, robust to uncertainty about their current role or employer. Use when planning or prepping an interview, drafting questions for a guest, building a running order, writing a pre-interview email, or when the guest's situation is unconfirmed ("she may have left", "not sure if he's still there"). Also for adding new arcs, beats, or questions to the database.
---

# Interview arc

Build a prep sheet for one guest from this repository's question database.

The output is a document the host holds during a recording. It has to survive
contact with a real conversation: a guest whose situation turned out to be
different from the booking email, an answer that goes somewhere better than
planned, a stretch that dies and needs rescuing.

## Read the series bible first

`data/series.json` holds the show's promise, its register, and its spine. Read
it before writing a single question — it is the thing that makes episodes sound
like one show rather than a stack of interviews.

**The promise.** The listener is a manager whose judgment has been exercised
constantly and solicited rarely. The claim the show makes to them is that the
tacit knowledge of how the work actually goes — never written down, never asked
for — is the scarce input, because the models are close to commodity and that
judgment is not. Every question should be consistent with that claim.

It only works because it's true. Do not inflate it. The listener has a working
detector for flattery and using it costs more than it buys.

**The spine.** Four themes every episode touches:
`natural-language-os`, `architecting-the-department`,
`customization-as-superpower`, `management-redefined`. Each arc beat declares what it `covers`, and
`validate.py` **fails** an arc that cannot deliver one of them. When you build a
prep sheet, confirm all four are represented before you hand it over.

**The register.** Warmth belongs in the *premise* of a question, never in its
content. "How did you decide where to draw that line" assumes they drew it —
that is inviting. "How can managers introduce this so teams feel supported"
contains its own answer — that is leading, and no amount of warmth rescues it.
The two are easy to confuse; the test is whether the guest could disagree with
the premise and still have something to say.

`series.json` carries `voice.avoid_patterns`, and `validate.py` warns on any
question text containing one. If a question quotes a phrase in order to
criticise it, declare `voice_exempt` on that question so the exception is
visible in the data.

## The core idea: anchoring

A question breaks not because its topic is wrong but because it **presupposes
something that turned out to be false**. "What are you measured on?" collapses
if the guest left that job in March.

So every beat of an arc exists in four flavors, ordered by how much they assume:

| Level | Assumes | Reach for it when |
| --- | --- | --- |
| `current` | They are in the seat now and can speak freely | Confirmed, and they are candid |
| `experience` | Their own history, no current employer needed | **Default when anything is uncertain** |
| `observed` | Only that they have watched others | Consultants, vendors, advisors, someone who just left |
| `general` | Nothing | They cannot discuss specifics at all |

`experience` is the workhorse. It is personal and specific enough to produce
real stories, and it survives every situation except a guest who has never done
the work. When you do not know, start there.

Never run a whole episode at `general` - it produces a panel discussion.

## Steps

**1. Establish what you actually know.** Ask the user for anything missing:
guest name, their field, their role, and how confident they are that the role
is current. Do not guess at an employer. If the user has already said the
situation is uncertain, do not ask again - go to `experience` and say so.

**2. Map the guest onto the database's two axes.**

```bash
python3 scripts/query.py list industries
python3 scripts/query.py list roles
```

Industry is their field. Role is `middle-manager`, `ai-leader`, or
`individual-contributor` - or none, if they are simply a practitioner. Pick the
closest industry even when the fit is loose; it supplies the vocabulary that
makes universal questions sound native.

**3. Pull the arc.**

```bash
python3 scripts/query.py arc                                    # what exists
python3 scripts/query.py arc ai-workflow-partner --industry <slug> --format md
```

Omit `--anchoring` to print all four flavors per beat. That is usually what you
want on the page - the host reads the room and picks live. Pass
`--anchoring experience` only when the user wants a clean read-aloud script.

**4. Pull supporting questions** for anything the arc does not cover.

```bash
python3 scripts/query.py brief <industry> --role <role> --format md
python3 scripts/query.py find --tag workflow --format md
```

**5. Assemble the prep sheet** in this order:

1. **If the situation changes** - one short block naming what to do if the
   premise is wrong. This goes first because it is the thing they need at
   minute two, not minute forty.
2. **The promise and the voice** - a compressed version of the series register,
   so the host holds the tone in their head while reading.
3. **The guest's world** - status axis, what earns trust, landmines, from the
   industry profile.
4. **The running order** - beats in sequence, each with its flavors, purpose,
   what the listener takes away, follow-ups, and the rescue prompt. Mark which
   beats carry a spine theme; those are the ones that cannot be cut for time.
5. **Pivots** - kept visible, for when an answer dies.

**6. Offer to publish it as an artifact** so the host can open it on a phone
or second screen during the recording.

## Writing new material

When adding a beat or an arc, write all four flavors. A beat with three is a
beat that will fail in the room.

Test the `general` flavor by reading it aloud as if to a stranger. If it
contains "your team" or "your company", it is not general - rewrite it.

Then:

```bash
python3 scripts/validate.py                              # schema, vocabulary, ASCII
python3 -m unittest discover -s scripts -t scripts
python3 scripts/build.py                                 # regenerate docs/
```

`validate.py` enforces that every beat has all four flavors, that themes come
from the taxonomy, and that no two flavors of a beat are identical.

New questions go in `data/questions/`, new arcs in `data/arcs/`. Both
directories are globbed - no registration step. See README.md for the schema.

## House rules

Every arc carries its own `house_rules`. Put them at the top of the prep sheet
and follow them - they encode what the arc is for. The general ones:

- **Ask for the specific instance.** Abstraction is where evasion lives. "Walk
  me through last week" beats "what is a typical week."
- **Do not write leading questions.** If the question contains its own answer,
  the guest will read it back to you. "How can managers introduce AI so teams
  feel supported?" produces a change-management answer; "when you brought this
  to your team, what did they actually say?" produces the truth.
- **Ask about their work, not about their category.** A guest asked to
  generalize about their profession gives you a talking point. A guest asked
  what they did on Tuesday gives you an episode.
- **Depth is placement, not difficulty.** Probing questions fail cold and land
  once the guest has watched you handle something smaller well. Respect the
  `avoid_if` notes.

## Pre-interview emails

Questions sent in advance get prepared answers. That helps for some questions
and ruins others.

Send the ones where preparation makes the answer **better** - where you want
the guest arriving with real examples, numbers, or a specific story they had to
go look up. Hold the ones that reward spontaneity, and anything sharp: a
probing question sent by email arrives as an accusation and gets a lawyered
response.

Two or three in the email is enough. It signals seriousness without spending
your material.
