# Video Editing Studio

A working video pipeline: **raw footage in → filler words cut → motion graphics on
top → rendered MP4 out.** Everything runs locally except one optional API call.

Two toolchains, each doing the half it's good at:

| Tool | Repo | Owns |
|---|---|---|
| **video-use** | [browser-use/video-use](https://github.com/browser-use/video-use) | The **cut**. Transcribe, remove fillers and dead air, color grade, burn subtitles, assemble. |
| **HyperFrames** | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | The **graphics**. Motion graphics, overlay cards, kinetic type, lower-thirds — authored as plain HTML + GSAP, rendered through headless Chrome. |

They compose cleanly: video-use produces the cut and calls out to HyperFrames for
each animation slot, so you get one `final.mp4` with the graphics baked in.

---

## Give me a video

Drop it in `video/footage/` and say what you want:

> "cut the fillers out of footage/talk.mp4 and add a title card and lower-third"

That's enough. I'll inventory it, transcribe it, show you a plain-English plan,
and wait for your OK before touching the cut.

`video/footage/` is gitignored — footage never lands in the repo.

---

## The pipeline

```
footage/raw.mp4
   │
   ├─1─ ffprobe            duration / resolution / fps
   ├─2─ transcribe         word-level timestamps  ──┐
   ├─3─ pack_transcripts   takes_packed.md          │ the LLM reads text,
   │                                                │ not pixels
   ├─4─ [you confirm the strategy] ─────────────────┘
   ├─5─ edl.json           cut decisions, snapped to word boundaries
   ├─6─ animations/        HyperFrames slots, rendered in parallel
   ├─7─ render.py          extract → concat → overlays → subtitles LAST
   ├─8─ self-eval          frames checked at every cut before you see it
   └──> edit/final.mp4
```

Everything derived lands in `edit/` next to your footage. Sources are never
modified in place.

### How filler removal actually works

The model never watches the video — it *reads* it. Transcription gives every word
a start and end timestamp. Fillers (`um`, `uh`, false starts, restarts) and
silence gaps become cut candidates as text. The cut list is then applied with
ffmpeg at word boundaries.

Four rules make the difference between a clean cut and an obviously-edited one,
and they're enforced, not optional:

- **Never cut inside a word.** Every edge snaps to a word boundary.
- **Pad every edge**, 30–200ms. ASR timestamps drift 50–100ms; padding absorbs it.
- **30ms audio fades at every boundary**, or you hear a click at each cut.
- **Per-segment extract then lossless concat** — never one giant filtergraph, or
  every segment gets double-encoded once overlays are added.

---

## Transcription: two routes

Filler removal needs word-level timestamps. There are two ways to get them, and
the studio has both wired up.

**Local Whisper (default, no API key, free).** whisper.cpp, built and cached on
this machine. Good word timings, no cost, no network.

```bash
npx hyperframes transcribe footage/raw.mp4 --model small.en --json
```

**ElevenLabs Scribe (optional, needs a key, costs credits).** What video-use uses
natively. Adds **speaker diarization** and **audio-event tags** (`(laughter)`,
`(applause)`, `(sigh)`) — worth it for multi-speaker interviews and podcasts,
overkill for a single talking head.

```bash
printf 'ELEVENLABS_API_KEY=%s\n' "$KEY" > ~/browser-use/video-use/.env
chmod 600 ~/browser-use/video-use/.env
```

Get a key at [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys).
**Single speaker → local Whisper is fine, skip the key.** Multi-speaker → the key
pays for itself in not hand-labelling who said what.

---

## Motion graphics

Compositions are plain HTML files with a paused GSAP timeline registered on
`window.__timelines`. Not Remotion, not React — a composition is a file you can
open in a browser.

```bash
cd video/video-projects/<project>
npx hyperframes lint                                    # always before rendering
npx hyperframes preview                                 # localhost:3002, hot reload
npx hyperframes render --quality draft  --output renders/draft.mp4
npx hyperframes render --quality standard --output renders/final.mp4
```

The eleven **render-contract** rules that a composition must obey (timeline
registration, `class="clip"`, `data-start`/`data-duration`, no `Date.now()`, …)
are in the `hyperframes-core` skill. `npx hyperframes lint` catches violations —
run it before every render.

Two ways to get graphics onto a talking head:

- **Overlay cards on a clip that plays underneath** → the `talking-head-recut`
  skill. Titles, lower-thirds, data callouts, quotes, PiP.
- **Plain subtitles** → the `embedded-captions` skill. Not the same thing; don't
  reach for recut when you just want captions.

---

## What's installed

Run `bash video/setup.sh` to rebuild all of it. It's idempotent — re-running is
safe and it only acts on what's actually missing.

**Skills** (in `~/.claude/skills/`, so they load automatically):

`video-use` · `hyperframes` · `hyperframes-cli` · `hyperframes-core` ·
`hyperframes-animation` · `hyperframes-keyframes` · `hyperframes-audio` ·
`hyperframes-creative` · `hyperframes-registry` · `motion-graphics` ·
`talking-head-recut` · `embedded-captions` · `general-video` · `media-use`

**Binaries:** ffmpeg + ffprobe, cmake/gcc, Node 22+, headless Chrome (render),
whisper.cpp (transcription).

**Not installed** (lazy, only if a job needs them): Remotion, Manim, yt-dlp,
Kokoro TTS, MusicGen.

---

## Reference projects

`video-projects/dollar-tree-vs-walmart/` — a complete worked example built here.
9:16, 33s, data-driven: `data/items.json` → `scripts/build-video.mjs` →
compositions. See its own README for the pattern.

The upstream student kit has 12 more finished projects worth reading:

```bash
git clone https://github.com/nateherkai/hyperframes-student-kit
```

`may-shorts-19` is the most polished vertical talking-head build; `claude-edit-intro`
is the cleanest minimal starting template.

---

## Gotchas that cost real time

- **Run the HyperFrames CLI from inside the project folder.** It resolves
  `assets/`, `compositions/`, `renders/` relative to cwd. From the repo root it
  scans the wrong files or fails outright.
- **Asset paths in sub-compositions are root-relative**, not relative to
  `compositions/`. Write `assets/x.css`, never `../assets/x.css` — the second
  lints clean in some tools but 404s in Studio preview.
- **Never add `class="clip"` to a `<video>`.** It breaks playback. Videos get the
  `data-*` timing attributes but not the class.
- **Never animate width/height/top/left on a `<video>`** — the browser freezes
  frames. Wrap it in a div and animate the wrapper.
- **Subtitles go last in the ffmpeg filter chain.** Any overlay applied after
  them covers them, and it fails silently.
- **Don't re-transcribe.** Transcripts are cached per source; re-running burns
  time (and Scribe credits) for an identical result.
