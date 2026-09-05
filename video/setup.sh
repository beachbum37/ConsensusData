#!/usr/bin/env bash
# Video editing studio — idempotent setup.
#
# Rebuilds the whole toolchain from scratch. Safe to re-run; every step checks
# before it acts. Written for Debian/Ubuntu (which is what the Claude Code web
# container runs); the apt block is the only OS-specific part.
#
#   bash video/setup.sh
#
set -uo pipefail

# Reuse a clone that already exists rather than making a second copy — $HOME
# is not the same directory on every host this runs on (it is /root in the
# Claude Code web container but the checkout may live under /home/user).
find_clone() {  # <owner/repo> -> prints path if a git clone is already there
  local sub="$1" base
  for base in "$HOME" /home/user "$PWD"; do
    [ -d "$base/$sub/.git" ] && { printf '%s\n' "$base/$sub"; return 0; }
  done
  return 1
}
HYPERFRAMES_DIR="${HYPERFRAMES_DIR:-$(find_clone heygen-com/hyperframes || echo "$HOME/heygen-com/hyperframes")}"
VIDEOUSE_DIR="${VIDEOUSE_DIR:-$(find_clone browser-use/video-use || echo "$HOME/browser-use/video-use")}"
SKILLS_DIR="${SKILLS_DIR:-$HOME/.claude/skills}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$1"; }

# --- 1. System packages ------------------------------------------------------
step "System packages (ffmpeg, build toolchain)"
missing=()
for b in ffmpeg ffprobe cmake gcc git; do
  command -v "$b" >/dev/null || missing+=("$b")
done
if [ ${#missing[@]} -gt 0 ]; then
  warn "missing: ${missing[*]} — installing"
  if command -v apt-get >/dev/null; then
    apt-get update -qq && apt-get install -y -qq ffmpeg cmake build-essential git
  else
    warn "no apt-get. Install manually: ${missing[*]}"
  fi
fi
for b in ffmpeg ffprobe cmake gcc git; do
  command -v "$b" >/dev/null && ok "$b $(command -v "$b")" || warn "$b STILL MISSING"
done

# --- 2. Node ------------------------------------------------------------------
step "Node (HyperFrames needs 22+)"
if command -v node >/dev/null; then
  ok "node $(node --version)"
  case "$(node --version)" in
    v1[0-9].*|v2[01].*) warn "Node is older than 22 — HyperFrames render may fail" ;;
  esac
else
  warn "node not found — install Node 22+ before rendering"
fi

# --- 3. Source repos ----------------------------------------------------------
step "Source repos"
clone_or_pull() {  # <url> <dir>
  if [ -d "$2/.git" ]; then
    git -C "$2" pull --ff-only -q 2>/dev/null && ok "updated $2" || ok "$2 (kept as-is)"
  else
    mkdir -p "$(dirname "$2")"
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 -q "$1" "$2" && ok "cloned $2"
  fi
}
clone_or_pull https://github.com/heygen-com/hyperframes "$HYPERFRAMES_DIR"
clone_or_pull https://github.com/browser-use/video-use  "$VIDEOUSE_DIR"

# --- 4. video-use Python deps -------------------------------------------------
step "video-use Python deps"
if python3 -c 'import librosa, matplotlib, PIL, numpy, requests' 2>/dev/null; then
  ok "deps already importable"
else
  ( cd "$VIDEOUSE_DIR" && { command -v uv >/dev/null && uv sync || pip install -e . ; } ) \
    && ok "installed" || warn "dep install failed — run manually in $VIDEOUSE_DIR"
fi

# --- 5. Skills ----------------------------------------------------------------
step "HyperFrames skills"
npx --yes hyperframes@latest skills update \
  talking-head-recut embedded-captions motion-graphics general-video \
  hyperframes-animation hyperframes-keyframes hyperframes-audio \
  hyperframes-creative media-use >/dev/null 2>&1 \
  && ok "installed to $SKILLS_DIR" || warn "skills install failed — run it manually"

step "video-use skill"
mkdir -p "$SKILLS_DIR"
ln -sfn "$VIDEOUSE_DIR" "$SKILLS_DIR/video-use" && ok "$SKILLS_DIR/video-use -> $VIDEOUSE_DIR"

# --- 6. Render browser --------------------------------------------------------
step "Headless Chrome for rendering"
npx --yes hyperframes@latest browser ensure >/dev/null 2>&1 \
  && ok "ready" || warn "browser ensure failed"

# --- 7. Local transcription (no API key needed) -------------------------------
step "Local Whisper (whisper.cpp)"
if [ -x "$HOME/.cache/hyperframes/whisper/whisper.cpp/build/bin/whisper-cli" ]; then
  ok "already built"
else
  warn "not built yet — it builds itself on first \`hyperframes transcribe\` (a few minutes)"
fi

# --- 8. ElevenLabs key (optional; only for the video-use Scribe route) --------
step "ElevenLabs API key (optional)"
if [ -n "${ELEVENLABS_API_KEY:-}" ]; then
  ok "found in environment"
elif grep -q '^ELEVENLABS_API_KEY=..' "$VIDEOUSE_DIR/.env" 2>/dev/null; then
  ok "found in $VIDEOUSE_DIR/.env"
else
  warn "not set. Only needed for the video-use/Scribe route (adds speaker"
  warn "diarization + audio-event tags). The local Whisper route works without it."
  warn "To set:  printf 'ELEVENLABS_API_KEY=%s\\n' \"\$KEY\" > $VIDEOUSE_DIR/.env && chmod 600 $VIDEOUSE_DIR/.env"
fi

step "Done"
echo "    Drop footage in video/footage/ and tell Claude what you want."
