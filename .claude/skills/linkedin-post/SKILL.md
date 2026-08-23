---
name: linkedin-post
description: Run the LinkedIn content machine - pick and publish this week's post, scour news sources for novel AI use cases in the workplace, or write new posts from an article. Use when the user wants a LinkedIn post, asks what to post this week, wants a posting schedule or queue, asks to find or research new material about AI at work, or drops an article to be turned into posts.
---

# LinkedIn content machine

This account posts one to two times a week to the same person the podcast talks
to: a manager or senior practitioner responsible for delivery, scrolling between
meetings, deciding in two seconds whether to tap "see more".

Three jobs live here. Work out which one is being asked for before doing
anything else.

| Ask | Job |
| --- | --- |
| "what should I post", "give me this week's post" | **Publish from the queue** |
| "find something", "what's new in AI at work" | **Run a scouring pass** |
| "turn this article into posts", "here's a doc" | **Write new posts** |

## Read these first, every time

```bash
python3 scripts/linkedin.py channel          # the channel bible
python3 scripts/linkedin.py nuggets          # the claims this account makes
```

`data/series.json` governs the register here as much as it does the podcast -
same account, same person, different door. Warmth belongs in the premise, never
in the content. No deficit framing, no catch-up urgency, no tech as the hero.
`validate.py` lints post copy against that list *and* against a feed-specific
one: engagement bait, hook formulas, vendor register.

The spine is the same four themes: `natural-language-os`,
`architecting-the-department`, `customization-as-superpower`,
`management-redefined`. Every post declares which it `covers`, and validation
fails if the feed as a whole stops carrying one of them.

---

## Job 1: publish from the queue

```bash
python3 scripts/linkedin.py queue --weeks 4 --per-week 1
python3 scripts/linkedin.py post li-onboard-01            # with notes
python3 scripts/linkedin.py post li-onboard-01 --bare     # paste-ready
```

The queue orders posts so no two in a row carry the same spine theme or come
from the same source article. Hand over the `--bare` text, plus the "careful"
note if the post has one.

**An empty slot is information.** It means the queue is short, not that a post
should be recycled or padded. Offer job 2 or job 3 instead.

Cadence starts at one a week. Move to two only when at least four ready posts
are banked, so a thin week never forces a weak post.

## Job 2: run a scouring pass

```bash
python3 scripts/linkedin.py scan --format md
```

That prints the whole brief: the novelty test, the disqualifiers, where to
look, the queries, the scoring rubric, and the nugget claims to match against.

The order matters and it is not the obvious one. **Read the nuggets before
searching.** You are not looking for interesting AI news; you are looking for a
concrete instance of a claim this account already makes, or a genuine
counterexample to one. Searching first produces product news dressed as
insight.

Then:

1. Run two or three queries with WebSearch, **including one counterexample
   query**. A find that contradicts a nugget is worth more than a fifth
   confirmation of one.
2. Apply the novelty test before reading anything closely. All five conditions
   have to hold - a named function, the work itself changed, a person made a
   scope call, one checkable detail, and a structure that transfers to another
   industry. Most items die in a sentence.
3. Score what survives, 0-3 on each of the five dimensions. Six or better is
   worth drafting. A zero on specificity is a drop regardless of total.
4. Report the candidates with their scores and a one-line verdict, and say
   plainly when nothing cleared the bar. **A week with no publishable find is a
   normal outcome.** Manufacturing one is how the account turns into slop.
5. Fetch the primary source before writing anything, never an aggregator's
   rewrite of it.

**Numbers.** No figure goes in a post unless you have opened the primary source
yourself, in which case the nugget behind it gets `citation_status: verified`.
The structural arguments do not need the number, and a wrong one is the single
mistake this audience remembers. `nug-deployment-bottleneck` carries a
`verify_before_use` note for exactly this reason - the survey figure in the
source transcript is unattributed and stays out of the copy.

## Job 3: write new posts

From a find, or from an article the user drops in.

**Distil nuggets first.** Before writing copy, add what the source actually
claims to `data/linkedin/nuggets.json`: the claim, which spine theme it carries,
the vocabulary worth reusing, when to reach for it, its `citation_status`, and
**a counterpoint**. The counterpoint is required. A nugget with nothing to say
against it is a slogan, and posts built from slogans are the ones this audience
discounts.

**Then write the post** into a pack under `data/linkedin/posts/`. Shape:

- **hook** - one or two lines, under 210 characters so it survives the fold.
  Name a situation the reader has been in, or state the claim flat. Never tease
  the payoff.
- **body** - short paragraphs, one to three lines each. At least one concrete,
  checkable specific: a threshold, a sentence somebody would actually say, a
  step in a process. `nug-threshold-example` travels well across industries.
- **close** - a real question, answerable from their own week, that you would
  genuinely want the answer to. Not "thoughts?".
- **hashtags** - two to five, at the end.
- **why_it_lands**, and **risk** when the post has a failure mode.

Target 900-1800 characters. Longer reads as an essay, shorter as a slogan.

Two rules that do most of the work:

**Put the cost in.** Every post carries the trade honestly somewhere: what you
build you maintain; escalation thresholds are easy to state and hard to set;
naming an agent invites the anthropomorphising it is meant to prevent. A post a
sceptic cannot finish and disagree with something specific in is an
advertisement.

**Lead with the reader, not the technology.** The first line should be
recognisable to someone who has never touched an agent.

Then:

```bash
python3 scripts/validate.py                    # fold, limits, register, references
python3 -m unittest discover -s scripts -t scripts
```

Validation catches a hook past the fold, a post over the platform limit, an
unknown format or status, a dangling nugget reference, a link in the body, a
figure with no verified source behind it, and any phrase from either avoid list.

## Publishing

Nothing here posts to LinkedIn. The output is copy to paste, on purpose - a
human reads it once more before it goes out, which is the same rule this
account argues for everywhere else.

Put links in the first comment, never in the body, and say so in the post.
