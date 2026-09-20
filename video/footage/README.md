# Where to put source material

One folder per project: `video/footage/<project-name>/`. Commit it and push.
Committing is the only way files on your machine reach a cloud session — I can't
see your disk, only what's in the repository.

```
cd C:\ConsensusData
mkdir video\footage\my-project          # pick a short lowercase name
copy <your files> video\footage\my-project\
git add video/footage/my-project
git commit -m "my-project: source material"
git push
```

Then tell me the folder name and what you want done with it.

## What travels in git automatically

Audio (`.mp3` `.wav` `.m4a`), decks (`.pptx`), documents (`.pdf` `.docx` `.txt`
`.md`), subtitles (`.srt` `.vtt`) and stills (`.png` `.jpg`). Drop them in and
`git add` works.

## Video needs one extra step

Video is ignored by default because GitHub hard-rejects anything over 100MB.

**Under 100MB** — force it in:

```
git add -f video/footage/my-project/clip.mp4
```

**Over 100MB** — shrink it first. This is visually lossless for screen
recordings and talking heads, and usually cuts the size by 3–5x:

```
ffmpeg -i big.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 160k small.mp4
```

Check the result is under 100MB, then `git add -f` it.

**Audio-only edits don't need the video at all.** If the job is cutting for
length, fillers, or mapping narration to slides, send just the audio — it's a
tenth the size and the edit decisions are identical:

```
ffmpeg -i clip.mp4 -vn -c:a libmp3lame -q:a 4 clip.mp3
```

The scifi episode worked this way. The actuary episode needed real video because
the screenshare is on camera.

## What never gets committed

`edit/`, `renders/` and `slidecut/` inside any project folder are working
directories — transcripts, intermediate cuts, ffmpeg scratch. They're ignored on
purpose and they live only in the session container.

## Where finished cuts go

`video/deliverables/`. That folder is tracked, so anything I put there shows up
in your clone after a pull. Working cuts stay in `edit/` and never reach you
unless you ask for them, so if you want a version, say so and I'll publish it
there.
