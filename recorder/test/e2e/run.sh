#!/usr/bin/env bash
# End-to-end check of the real recorder that never touches your screen, camera or mic.
#
# A separate X display (:99) shows a scripted page; the real recorder captures that display
# with --camera none --no-mic; real X input (XTest) clicks and presses a shortcut so the input
# hook is exercised too. Then a voice track is added and the whole engine runs on the Take.
#
# usage: recorder/test/e2e/run.sh PAGE.html VOICE.wav [SECONDS]
#   e.g. recorder/test/e2e/run.sh demo/source/terminal.html narration.wav 51
# needs: Xvfb or Xwayland (Linux), Google Chrome, ffmpeg, uv
set -euo pipefail
PAGE=$1; VOICE=$2; SECS=${3:-50}
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(mktemp -d); export CLIPAGENT_HOME=$OUT/home
CA="uv run --project $ROOT/engine clipagent"

if command -v Xvfb >/dev/null; then Xvfb :99 -screen 0 1920x1080x24 & else Xwayland :99 -geometry 1920x1080 -decorate & fi
XPID=$!; trap 'kill $XPID 2>/dev/null' EXIT; sleep 2

env -u WAYLAND_DISPLAY DISPLAY=:99 XDG_SESSION_TYPE=x11 $CA start --camera none --no-mic --look architecture-flow --context "$ROOT" --title "virtual e2e"
env -u WAYLAND_DISPLAY DISPLAY=:99 uv run --project "$ROOT/engine" --with python-xlib python "$ROOT/recorder/test/e2e/drive.py" "$PAGE" "$OUT/drive.json" "$SECS"
$CA stop

TAKE=$(ls -d "$CLIPAGENT_HOME"/sessions/*/take)
python3 - "$TAKE" "$OUT/drive.json" "$VOICE" <<'PY'
import json, sys, datetime, subprocess
take, drive, voice = sys.argv[1:]
tk = json.load(open(f"{take}/take.json"))
t0 = datetime.datetime.fromisoformat(tk["started_at"].replace("Z", "+00:00")).timestamp()
ms = int((json.load(open(drive))["page_loaded_epoch"] - t0) * 1000)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", voice, "-af", f"adelay={ms},apad", "-t", str(tk["duration"]),
                "-c:a", "libopus", f"{take}/mic.webm"], check=True)
tk["streams"]["mic"] = {"file": "mic.webm", "start_offset": 0.0, "label": "test voice"}
json.dump(tk, open(f"{take}/take.json", "w"), indent=2)
PY
$CA prepare
$CA inserts && $CA qa && $CA render && $CA deliver
echo "deliverables: $(ls -d "$CLIPAGENT_HOME"/sessions/*/deliverables)"
