# Running the studio locally

The studio was built in a Claude Code web container (Debian). This is what
changes when you run it on your own machine instead — which is what you want
for anything with real footage: multi-GB sources never move, and ffmpeg and
headless Chrome render on hardware you control.

## Windows: use WSL, not native

`setup.sh` is bash and its package step is apt. Native Windows gives you no
ffmpeg, no cmake/gcc for whisper.cpp, and symlink steps that silently no-op.

```bash
wsl --install -d Ubuntu          # PowerShell, once, then reopen as Ubuntu
```

Work from the WSL filesystem (`~/repos/...`), **not** `/mnt/c/...`. Building
whisper.cpp and rendering across the 9p mount is several times slower, and
ffmpeg writing large intermediates to `/mnt/c` is the single biggest avoidable
cost in a long edit.

## Bootstrap

```bash
git clone https://github.com/beachbum37/ConsensusData
cd ConsensusData
git checkout claude/sleepy-clarke-6phtej
bash video/setup.sh
```

`setup.sh` is idempotent — re-run it any time. It clones the two tool repos,
installs the HyperFrames skills into `~/.claude/skills/` (so they load
automatically in a local session), and ensures the render browser.

whisper.cpp is **not** built by setup — it builds itself on the first
`hyperframes transcribe`, and that first run takes a few minutes. Do it once up
front rather than discovering it mid-edit.

## Where footage goes

`video/footage/` is gitignored, as are `edit/`, `**/renders/` and loose
`.mp4`/`.mov`/`.wav`. So you can point the studio at a working folder that sits
inside the repo without any of it reaching git. Only `video/deliverables/*.mp4`
is committed, and only for a final cut under GitHub's 100MB limit.

For a source folder you keep outside the repo, pass absolute paths — nothing in
`video/tools/` assumes the file lives under `video/footage/`.

## A new project

Copy the shape of `video-projects/dollar-tree-vs-walmart/` — `hyperframes.json`,
`compositions/`, `assets/brand-tokens.css`, `meta.json`, `index.html`. Run the
HyperFrames CLI **from inside the project folder**; it resolves `assets/`,
`compositions/` and `renders/` relative to cwd and does the wrong thing from the
repo root.

Everything else — the pipeline, the four cut rules, the transcription routes,
and the gotchas that cost real time — is in `video/README.md`. Read that first;
this file only covers what differs off the container.
