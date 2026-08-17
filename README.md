# Ask Anyone

A retrievable database of podcast interview questions, built so the questions
land on professionals in any industry — a nurse, a machinist, a bond trader, a
line cook, a county planner.

**263 questions.** 83 in the universal core, 120 across 20 industry packs, and 60
scoped to a *role* rather than a field — for middle managers, the AI leaders
driving adoption at them, and the senior contributors now directing agents. Every
question is tagged by theme, interview stage, and depth, carries a note on *why*
it works, and comes with follow-ups.

```
python3 scripts/query.py brief hospitality --role middle-manager
```

That prints a full interview brief: what earns status in that world, what makes
you sound like a tourist, the native vocabulary, and a running order of
questions with the vocabulary already substituted in.

Or open `docs/index.html` in a browser for the searchable version.

---

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
| `middle-manager` | 48 | AI & the Person in the Middle, From Chat to Workflow, Everyone Becomes a Manager |
| `ai-leader` | 21 | AI Leaders & Adoption Owners, plus the workflow and agent packs |
| `individual-contributor` | 7 | Everyone Becomes a Manager |

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
data/
  taxonomy.json          controlled vocabularies for arc, depth, theme, industries
  industries.json        20 profiles: vocabulary, status axis, trust signals, landmines
  questions/
    00-openers.json      universal core, one file per pack
    …
    08-ai-and-management.json    AI and the person in the middle
    09-ai-leaders.json           for adoption owners and AI directors
    10-chat-to-workflow.json     embedded AI and process redesign
    11-agent-managers.json       contributors directing agents
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
