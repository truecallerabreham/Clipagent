#!/bin/sh
# Runs at session start (Claude Code plugin). Silent and non-blocking: if ClipAgent isn't set up yet,
# start `ca setup` in the background so the recorder and renderer are ready by the time /screen-record runs.
home="${CLIPAGENT_HOME:-$HOME/ClipAgent}"
grep -q '"ready": true' "$home/setup.json" 2>/dev/null && exit 0
command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ] || exit 0
[ -f "$home/setup.lock" ] && exit 0
mkdir -p "$home"
root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
nohup sh "$root/skills/screen-record/ca" setup >>"$home/setup.log" 2>&1 </dev/null &
exit 0
