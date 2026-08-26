# Ask Anyone

A retrievable database of podcast interview questions, built so the questions
land on professionals in any industry — a nurse, a machinist, a bond trader, a
line cook, a county planner.

**378 questions.** 83 in the universal core, 128 across 21 industry packs, and 113
scoped to a *role* rather than a field — for middle managers, the AI leaders
driving adoption at them, the senior contributors now directing agents, and the
people who build the tools. Every question is tagged by theme, interview stage, and depth, carries a note on *why*
it works, and comes with follow-ups.

```
python3 scripts/query.py brief hospitality --role middle-manager
```

That prints a full interview brief: what earns status in that world, what makes
you sound like a tourist, the native vocabulary, and a running order of
questions with the vocabulary already substituted in.

Or open `docs/index.html` in a browser for the searchable version.

---

## The show

`data/series.json` is the bible: the promise, the register, and the spine.

**The promise to the listener.** They're a manager whose judgment has been
exercised constantly and solicited rarely. The claim the show makes is that the
tacit knowledge of how the work actually goes — never written down, never asked
for — is the scarce input, because the models are close to commodity and that
judgment is not. It works because it's true; inflating it past that costs more
than it buys.

**The spine.** Four themes every episode touches:

| Theme | The reframe |
| --- | --- |
| `natural-language-os` | Describing work precisely is now the act of configuring it. They've been writing specs for years and calling it explaining things to the new person. |
| `architecting-the-department` | Not using a tool — standing up specialised workers and teaching them the micro-judgments that live only in their head. Includes **control**: deterministic checks wrapped around the probabilistic part, reached through authorship rather than risk. |
| `customization-as-superpower` | Turnkey was never turnkey. Every workaround the team built is now a specification. |
| `management-redefined` | Agents as teammates you onboard, coach and performance-manage — not tools you install. A role is forming around that, and it reportedly fails when centralised in IT. |

Every arc beat declares what it `covers`, and **`validate.py` fails an arc that
can't deliver one of the four.** The requirement is enforced, not remembered.

**The register.** Warmth belongs in the *premise* of a question, never in its
content — that distinction is what separates an inviting question from a leading
one. `series.json` lists the invites and the avoids, and the avoids are
machine-checked: `validate.py` warns on any question containing deficit framing
("struggling with", "falling behind", "why haven't you"). A question that quotes
such a phrase in order to criticise it declares `voice_exempt`, so the exception
is visible in the data rather than hidden in the linter.

## The idea

A question lands when the guest recognizes their own working life in it. Most
interview question lists fail across industries because they smuggle in
assumptions — that the guest has customers, or a funding round, or creative
control, or a desk. This database is built on two mechanisms that survive the
jump between fields.

**A universal core built on structures, not content.** Every profession has
novices and masters, a gap between how it trains and how it operates, a payer
whose incentives distort the work, a shadow hierarchy, an error culture, and a
crunch season. The core questions ask about *those*, so they work on anyone.

**Vocabulary slots.** Universal questions contain placeholders like
`{work_unit}` and `{customer}`. Each industry profile supplies the native word,
so the same question reads as *"the first ten minutes of a case"* to a doctor,
*"a matter"* to a lawyer, *"a load"* to a freight broker, and *"a service"* to a
chef. Articles are corrected automatically — you get *"an outage"* and *"a
user"*, not *"a outage"*.

The industry profiles carry the rest: the status axis, what signals you did the
homework, and the landmines that make a guest close up.

### Two scoping axes

Industry is one axis. **Role** is the other, and it runs perpendicular: a middle
manager in a hospital and one in a warehouse face the same structure — a team
below, executives above, authority over the work but not over the constraints.
Questions scoped to a role stay industry-universal, so a brief can blend all
three sources at once:

```
python3 scripts/query.py brief healthcare --role middle-manager
```

That draws healthcare-specific questions, middle-manager questions, and the
unscoped core into one running order. Two properties are enforced by tests:
an AI-leader question never appears in a manager's brief, and the role packs —
several times larger than any industry pack — never crowd the industry material
out of the running order.

| Role | Questions | Packs |
| --- | --- | --- |
| `middle-manager` | 87 | AI & the Person in the Middle, From Chat to Workflow, Everyone Becomes a Manager, The Spine, Hard Boundaries, The Agent Manager |
| `ai-leader` | 32 | AI Leaders & Adoption Owners, plus the workflow, boundary and agent-manager packs |
| `individual-contributor` | 18 | Everyone Becomes a Manager, The Spine, Hard Boundaries |
| `builder` | 26 | The Builder, The Founder's View |

### A third axis: setting

Enterprise and entrepreneur are the same subject under opposite constraints.
Inside a large organization the binding constraint is almost never money or
capability — it's **permission**: procurement owns the purchase, IT owns the
configuration, legal owns the risk, and the manager owns the outcome anyway.
Running your own thing inverts all of it: you *are* procurement, IT and legal,
nobody has to approve anything, the money is yours, and the constraint is your
own hours.

Setting **narrows** rather than adding a third source — picking one excludes
questions written for the other and keeps the whole unscoped core.

Two mechanisms carry it. Questions that only make sense in one setting are
scoped there outright (a shadow org chart needs an org chart; *who pays for your
work* is sharpest solo). Questions that suit both but **word** badly in one
carry a `setting_text` variant — *"when you start work"* becomes *"when you boot
up in the morning"*. `validate.py` rejects a variant identical to its base, and
a floor check fails the build if either setting drops below **250** available
questions, so reassignment can't quietly hollow one side out.

```bash
python3 scripts/query.py brief finance --role middle-manager --setting entrepreneur
python3 scripts/query.py find --setting enterprise
```

### Aperture

Almost every question here is deliberately narrow — abstraction is where evasion
lives. The exception is the **Big Picture** bank, marked `aperture: "wide"`.
Those are the sweeping executive-level questions, and they have three real uses:
the pre-interview email, the open of a panel, and trailers.

They're kept out of briefs automatically, because they'd hollow out a running
order. And every one carries a **`narrow_to`** — the follow-up that drives the
answer down to one instance. `validate.py` refuses a wide question without one.
The wide question buys the frame; the `narrow_to` buys the episode.

```bash
python3 scripts/query.py find --aperture wide --industry healthcare
```

Wide questions can use `{industry}`, which fills from the profile's label.

## Arcs: themes with flavors

A brief is a good set of questions. An **arc** is a shaped episode: ordered
beats, each with a stated purpose, what the listener should take away, and a
tone note for keeping it approachable.

The reason arcs exist separately from the question corpus is **anchoring**. A
question rarely breaks because its topic is wrong — it breaks because it
presupposes something that turned out to be false. "What are you measured on?"
collapses if the guest left that job in March.

So every beat exists in four flavors, ordered by how much they assume:

| Level | Assumes | Reach for it when |
| --- | --- | --- |
| `current` | They're in the seat now and can speak freely | Confirmed, and they're candid |
| `experience` | Their own history, no current employer needed | **Default when anything is uncertain** |
| `observed` | Only that they've watched others | Consultants, advisors, someone who just left |
| `general` | Nothing | They can't discuss specifics at all |

```bash
python3 scripts/query.py arc                                    # what exists
python3 scripts/query.py arc ai-workflow-partner --industry healthcare
python3 scripts/query.py arc ai-workflow-partner --anchoring experience --format md
```

Omit `--anchoring` and all four flavors print per beat — that's the version to
hold during a recording, so you can read the room and pick live. Pass a level to
get a clean read-aloud script.

Tests enforce that every beat has all four flavors and that the `general` flavor
never says "your team" — a general question that assumes a current situation
defeats the point of the level.

### The skill

`.claude/skills/interview-arc/SKILL.md` wraps all of this. Ask Claude to prep an
interview and it establishes what's actually known about the guest, picks the
anchoring level to match that certainty, pulls the arc and supporting questions,
and assembles a prep sheet that opens with what to do if the premise turns out
to be wrong.

## Using it

Everything is Python 3 standard library. No install, no dependencies.

### Build a brief for one guest

```bash
python3 scripts/query.py brief healthcare
python3 scripts/query.py brief logistics --role middle-manager
python3 scripts/query.py brief skilled-trades --guest "Dana Reyes" --format md
python3 scripts/query.py brief finance --no-probing     # guarded or first-time guest
python3 scripts/query.py brief law --seed 3             # a different draw
```

The running order follows the arc — openers, warmup, core, deep, closers — and
prefers industry-specific questions where they exist, topping up from the
universal core. Pivots print at the end; keep them in view during the recording.

### Search the whole corpus

```bash
python3 scripts/query.py find --theme money --depth probing
python3 scripts/query.py find --industry law --search billable
python3 scripts/query.py find --role ai-leader --no-general         # role pack only
python3 scripts/query.py find --industry logistics --no-universal   # industry pack only
python3 scripts/query.py find --tag ai --depth probing
python3 scripts/query.py find --tag flagship --bare
```

### Read an industry profile on its own

```bash
python3 scripts/query.py profile agriculture
python3 scripts/query.py list industries
python3 scripts/query.py list tags
```

`--format md` and `--format json` work on every command. `--bare` drops the
notes and follow-ups when you just want the questions.

### The browser version

```bash
python3 scripts/build.py     # regenerate after editing any data file
open docs/index.html
```

Filter by depth, stage, and theme; search across text, notes, and tags; switch
to Brief mode for a running order; copy any question or the whole brief as
Markdown. The data is baked in, so it works offline and needs no server.

`docs/artifact.html` is the same page as a body fragment, for publishing as a
Claude Artifact.

## How a question is stored

```json
{
  "id": "u-craft-02",
  "text": "What can you tell in the first ten minutes of a {work_unit} that a novice could not tell in a week?",
  "theme": "craft",
  "arc": "core",
  "depth": "medium",
  "industries": ["universal"],
  "lands_because": "Rapid pattern recognition is the signature of expertise in every field.",
  "followups": ["What are you actually looking at when you make that read?"],
  "avoid_if": "…",
  "tags": ["pattern-recognition", "slotted", "flagship"]
}
```

| Field | Meaning |
| --- | --- |
| `arc` | Where it belongs: `opener`, `warmup`, `core`, `deep`, `pivot`, `closer` |
| `depth` | `light` (a sentence), `medium` (needs a story), `probing` (touches ego, money, or blame) |
| `theme` | `origin`, `craft`, `judgment`, `failure`, `people`, `money`, `change`, `ethics`, `myths`, `invisible`, `future`, `personal` |
| `industries` | `["universal"]` or specific slugs |
| `roles` | Optional. `middle-manager`, `ai-leader`. Absent means role-agnostic |
| `lands_because` | Why it works — read this when deciding whether to use it |
| `avoid_if` | When it will backfire |

Definitions for every value live in `data/taxonomy.json`.

### A note on sequence

Depth is not a difficulty rating, it is a *placement* instruction. The probing
questions mostly fail when asked cold and succeed once the guest has watched you
handle something smaller well. Several questions say so in `avoid_if` — the
failure question `u-fail-06` ("Is there one you are still carrying?") only works
as a follow-on, never as an opener.

## Layout

```
.claude/skills/
  interview-arc/SKILL.md the skill: prep an interview end to end
data/
  series.json            the bible: promise, register, spine
  taxonomy.json          controlled vocabularies for arc, depth, theme, industries, roles
  industries.json        20 profiles: vocabulary, status axis, trust signals, landmines
  arcs/
    ai-workflow-partner.json   17 beats, four flavors each, 11 carrying spine themes
  questions/
    00-openers.json      universal core, one file per pack
    …
    08-ai-and-management.json    AI and the person in the middle
    09-ai-leaders.json           for adoption owners and AI directors
    10-chat-to-workflow.json     embedded AI and process redesign
    11-agent-managers.json       contributors directing agents
    12-the-spine.json            the three required themes, standalone
    13-hard-boundaries.json      control: deterministic checks around probabilistic systems
    14-agent-manager.json        the management shift: agents as teammates, and who owns them
    15-the-builder.json          for founders and inventors, aimed away from the pitch
    16-big-picture.json          wide-aperture questions for emails, panels and trailers
    17-setting-split.json        the same subject for enterprise vs entrepreneur
    18-founder-wide.json         wide-aperture questions for someone who built a company here
    15-the-builder.json          interviewing the person who made the tool, without it becoming a demo
    industry/            one file per industry
scripts/
  corpus.py              loading, filtering, slot substitution, brief assembly
  query.py               the CLI
  validate.py            schema, vocabulary, and duplicate checks + coverage report
  build.py               bakes docs/index.html
  template.html          the page source
  test_corpus.py         unit tests
docs/
  index.html             generated - do not edit by hand
  artifact.html          generated
```

## Adding questions

Add to an existing pack file, or drop a new `.json` into `data/questions/` with
`{"pack": "...", "description": "...", "questions": [...]}`. The loader globs the
directory, so no registration step.

Then:

```bash
python3 scripts/validate.py                              # catches most mistakes
python3 -m unittest discover -s scripts -t scripts
python3 scripts/build.py
```

`make check` runs all three.

The validator enforces the controlled vocabularies, flags duplicate ids and
near-duplicate text, warns about slots no profile can fill, and prints a
coverage table by industry, stage, and theme so gaps are visible.

### Where new questions come from

Two questions in the corpus exist to restock it. `u-close-01` — "What is a
question you wish people asked you about your work?" — and `u-open-08` — "When
you meet someone else who does what you do, what do you ask them?" Whatever a
guest names in answer to those is, by definition, a question that lands on that
profession. Add it.

## Adding an arc or a beat

Drop a `.json` into `data/arcs/` with `arc`, `title`, `goal`, `house_rules`,
`anchoring`, and `beats`. Each beat needs `beat`, `title`, `theme`, `purpose`,
`listener_payoff`, `keep_it_approachable`, and all four `flavors`; `followups`
and `if_it_stalls` are optional.

Write all four flavors. A beat with three is a beat that will fail in the room.
Read the `general` one aloud as if to a stranger — if it contains "your team",
it isn't general.

`validate.py` enforces the four flavors, checks themes against the taxonomy,
and flags two flavors of a beat that are identical.

## Adding a role

1. Add the slug and description to `roles` in `data/taxonomy.json`.
2. Add a pack file whose questions carry `"roles": ["<slug>"]` and keep
   `"industries": ["universal"]` — a role exists in every field, and the
   validator warns if you scope a question on both axes at once.

## Adding an industry

1. Add the slug and a one-line description to `industries` in `data/taxonomy.json`.
2. Add a profile to `data/industries.json` with all six vocabulary slots,
   `status_axis`, `earns_trust`, and `landmines`.
3. Add `data/questions/industry/<slug>.json`.

`validate.py` will tell you if you miss a piece — it fails on an industry with
no profile and warns on a profile with no questions.
