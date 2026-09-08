# Deliverables

Finished episodes, committed so they are actually retrievable. Everything else
under `video/` that is video — footage, working renders, previews — stays
gitignored and lives only on the machine that made it.

| File | Episode | Length |
|---|---|---|
| `one-human-department-1080p.mp4` | One Human Department | 10:51 |

1920×1080, H.264 CRF 23, AAC 128k, `+faststart`. Re-encoded from the render
master purely to fit under GitHub's 100MB file limit — 115MB to 75MB, with a
mean pixel difference of 0.13 on a 1:1 crop of on-screen text, so the screen
recordings stay legible.

Keep a final cut here only. Working renders belong in `footage/edit/`, which is
ignored — committing those would grow the repository without bound.
