#!/usr/bin/env bash
# ClipAgent installer for Claude Code and Codex (macOS / Linux).
#   curl -fsSL https://raw.githubusercontent.com/truecallerabreham/Clipagent/main/install.sh | bash
set -euo pipefail
DIR="${CLIPAGENT_DIR:-$HOME/.clipagent/Clipagent}"
say() { printf '\033[1;38;5;81m▸\033[0m %s\n' "$*"; }

command -v git >/dev/null || { echo "git is required"; exit 1; }
command -v ffmpeg >/dev/null || echo "! ffmpeg not found: install it (apt install ffmpeg / brew install ffmpeg)"
if ! command -v uv >/dev/null; then
  say "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if [ -d "$DIR/.git" ]; then say "updating $DIR"; git -C "$DIR" pull --ff-only
else say "cloning into $DIR"; mkdir -p "$(dirname "$DIR")"; git clone --depth 1 https://github.com/truecallerabreham/Clipagent.git "$DIR"; fi

say "installing the engine (Python deps + headless Chromium)"
uv sync --project "$DIR/engine" --quiet
uv run --project "$DIR/engine" playwright install chromium >/dev/null 2>&1 || true

for agent_dir in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  parent="$(dirname "$agent_dir")"
  [ -d "$parent" ] || continue
  mkdir -p "$agent_dir"
  ln -sfn "$DIR/skills/screen-record" "$agent_dir/screen-record"
  say "skill linked: $agent_dir/screen-record"
done

say "installing the recorder app"
uv run --project "$DIR/engine" clipagent install-recorder || echo "! recorder download failed; dev fallback: cd $DIR/recorder && npm install"
uv run --project "$DIR/engine" clipagent doctor || true
say "done. In Claude Code or Codex, type: /screen-record"
