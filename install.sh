#!/usr/bin/env bash
# ClipAgent: one line, every agent (Claude Code, Codex, OpenCode, Antigravity), macOS / Linux.
#   curl -fsSL https://raw.githubusercontent.com/truecallerabreham/Clipagent/main/install.sh | bash
# Takes seconds: the skill is linked right away; the heavy parts (Python deps, recorder, render browser)
# finish in the background and /screen-record waits for them if you're quicker.
set -euo pipefail
DIR="${CLIPAGENT_DIR:-$HOME/.clipagent/Clipagent}"
REPO="${CLIPAGENT_REPO:-https://github.com/truecallerabreham/Clipagent.git}"
HOME_DIR="${CLIPAGENT_HOME:-$HOME/ClipAgent}"
say() { printf '\033[1;38;5;81m▸\033[0m %s\n' "$*"; }

command -v git >/dev/null || { echo "git is required"; exit 1; }
if ! command -v uv >/dev/null; then
  say "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
fi

if [ -d "$DIR/.git" ]; then
  say "updating ClipAgent"; git -C "$DIR" pull --ff-only --quiet
else
  say "downloading ClipAgent (code only, no demo videos)"
  mkdir -p "$(dirname "$DIR")"
  git clone --quiet --depth 1 --filter=blob:none --sparse "$REPO" "$DIR"
  git -C "$DIR" sparse-checkout set skills engine looks recorder hooks .claude-plugin
fi

say "adding /screen-record to your coding agents"
PYTHONPATH="$DIR/engine" uv run --no-project --quiet python -m clipagent.setup link

mkdir -p "$HOME_DIR"
nohup sh "$DIR/skills/screen-record/ca" setup >>"$HOME_DIR/setup.log" 2>&1 </dev/null &
command -v ffmpeg >/dev/null || say "one thing to do yourself: install ffmpeg (sudo apt install ffmpeg / brew install ffmpeg)"
say "done. Open your agent and type: /screen-record   (setup finishes in the background)"
