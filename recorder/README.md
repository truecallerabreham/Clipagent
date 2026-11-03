# ClipAgent Recorder

The Electron companion app that captures a **Take**: screen, webcam, microphone and input events, written into `<SESSION>/take/` exactly as described in [Contract 1 of `docs/design.md`](../docs/design.md#contract-1-the-take-recorder--engine). The `clipagent` engine launches it (`/screen-record`), but it also runs on its own.

## Usage

```
clipagent-recorder --session <DIR> [--camera <deviceId>|none|default] [--no-mic] [--display <id>]
clipagent-recorder --stop <DIR> [--no-wait] [--timeout <seconds>]
clipagent-recorder --list-devices
```

| option | meaning |
|---|---|
| `--session <DIR>` | record into `<DIR>/take/`. Refuses to run if that folder already holds a Take (`take.json` or `screen.webm`) |
| `--camera <deviceId>` | webcam to record (ids from `--list-devices`). `default` = system default camera (error if there is none), `none` = no camera. Omitted = default camera if one exists, otherwise no camera |
| `--no-mic` | do not record the microphone |
| `--display <id>` | display to capture (ids from `--list-devices`). Ignored on Wayland, where the system portal dialog chooses. On macOS 15+ without `--display`, the system picker is shown |
| `--stop <DIR>` | creates `<DIR>/take/stop` (the running recorder polls it every 250 ms), then waits until `state.json` says `done` or `error` (`--no-wait` to return at once) |
| `--list-devices` | prints `{"displays": [...], "cameras": [...], "mics": [...]}` as JSON and exits |

Hotkeys: stop `Ctrl+Alt+S` (`Cmd+Option+S` on macOS), pause/resume `Ctrl+Alt+P`, Scratch Marker `Ctrl+Alt+X`. On Linux/macOS, `SIGTERM`/`SIGINT` stop gracefully, `SIGUSR1` toggles pause and `SIGUSR2` drops a Scratch Marker.

Exit codes: `0` finished (`state.status = "done"`), `1` runtime error, `2` usage error (or the session already has a Take), `3` permission or device error (screen share refused, camera missing or busy, mic denied). Every failure after the take folder is created is also written to `state.json` as `{"status": "error", "error": "<message>"}`.

## How it works

```
main process (src/main/main.js)
 ├─ hidden capture window (src/renderer/capture.js)
 │    getDisplayMedia → MediaRecorder → screen.webm   (VP9, falls back to VP8)
 │    getUserMedia    → MediaRecorder → camera.webm   (VP9/VP8, no audio)
 │    getUserMedia    → MediaRecorder → mic.webm      (Opus; no echo cancel / noise suppression / AGC)
 │    each recorder emits a chunk every second; the main process appends it to disk at once
 ├─ floating control bar (src/renderer/bar.*)  timer, pause/resume, stop, mic level, red dot
 ├─ input (src/main/input.js)  uiohook-napi, or the evdev worker (src/main/evdev-worker.js), or none
 └─ events.jsonl / state.json / take.json      (src/lib/*.js: pure, unit-tested modules)
```

- **Timing.** Take t=0 is the earliest MediaRecorder `start` event; each stream's `start_offset` is its own `start` event minus t=0. A single clock (`src/lib/clock.js`) maps wall time to recorded time, excluding pauses; events, `duration` and `pauses` all use it. Pause/resume pauses all recorders together (Chromium's WebM muxer also drops paused time, so file timelines match recorded time).
- **Crash safety.** Chunks are on disk within about a second; `events.jsonl` is appended line by line; `state.json` and `take.json` are written atomically (temp file + rename).
- **Privacy.** A plain keystroke is stored as `{"type": "typing"}` and nothing else. Only combos with Ctrl/Alt/Cmd/Super, or F1-F24/Esc/Enter/Tab, are stored as `shortcut` with key names. Shift alone does not make a shortcut (Shift+A is a capital A). The recorder's own hotkeys are not recorded as shortcuts.
- **Pointer.** Moves are sampled at most 20 Hz, coordinates are 0-1 of the captured display, events on other displays are dropped. With evdev the mouse only reports relative motion, so clicks and scrolls carry `"x": null, "y": null` and no moves are written; the engine estimates the position from the video.
- **The bar.** `setContentProtection(true)` hides it from the capture on macOS and Windows. Linux has no equivalent, so the bar is pinned top-right (not draggable) and `take.json.overlay_rect` records where it was, for the engine to blur.
- **Ending.** The bar's Stop button, the stop hotkey, `--stop`, a signal, or the system "stop sharing" control all finalize the recorders, write `take.json`, set `state.status = "done"` and exit 0. A stop requested before recording begins cancels with an error.

## Permissions

### macOS
- **Screen Recording**: System Settings > Privacy & Security > Screen Recording. Enable *ClipAgent Recorder* (in dev: the terminal app that launches Electron). Restart the recorder after granting.
- **Camera** and **Microphone**: asked on first use.
- **Accessibility** (and **Input Monitoring** on recent macOS) for clicks and shortcuts: System Settings > Privacy & Security > Accessibility. Without it the Take is still recorded with `input.source = "none"` and a warning.
- The bar is excluded through `NSWindowSharingNone`. Some macOS 15+ capture paths have been reported to ignore it; if the bar shows up in `screen.webm`, report it.

### Linux (Wayland: GNOME, KDE, ...)
- **Screen**: captured through the xdg-desktop-portal / PipeWire (`WebRTCPipeWireCapturer`). The portal asks you to pick a screen each time; the recorder waits up to 180 s (`CLIPAGENT_START_TIMEOUT`) and records `state.status = "starting"` meanwhile. Needs `xdg-desktop-portal` plus your desktop's backend (`-gnome`, `-kde`, `-wlr`) and PipeWire.
- **Windows run under XWayland** (`--ozone-platform=x11`): native Wayland allows neither always-on-top nor placing the bar, and the bar's position must be known for `overlay_rect`. The dev launcher passes the flag; a packaged binary re-executes itself once with it. Set `CLIPAGENT_NATIVE_WAYLAND=1` to opt out.
- **Input events**: global hooks do not exist on Wayland, so the recorder reads `/dev/input/event*` directly (keyboards and mice). That requires membership of the `input` group:
  ```
  sudo usermod -aG input $USER     # then log out and back in
  ```
  Without it the Take is recorded with `input.source = "none"` and a warning explaining this. Touchpad tap-to-click and two-finger scrolling are gestures interpreted by libinput, not kernel button events, so only physical clicks are seen.
- **Hotkeys** on Wayland: `globalShortcut` only fires while an XWayland window has focus, so the hotkeys are detected from the evdev stream (needs the `input` group). Without it, use the bar, `--stop`, or signals.
- **Sandbox**: Electron's `chrome-sandbox` from npm is not setuid root, and Ubuntu 24.04+ restricts unprivileged user namespaces. The dev launcher adds `--no-sandbox` when needed. For the AppImage, run it with `--no-sandbox` if it aborts with a sandbox error.

### Linux (X11)
Screen capture needs no permission. Input comes from uiohook-napi (falls back to evdev if it cannot load).

### Windows
No permission prompts for the screen. Camera and microphone follow Settings > Privacy & security > Camera / Microphone ("Let desktop apps access..."). Input comes from uiohook-napi. The bar is excluded from capture with `WDA_EXCLUDEFROMCAPTURE` (Windows 10 2004+).

## Development

```bash
cd recorder
npm install                 # installs Electron (binary downloaded on first run) and uiohook-napi (optional)
npm test                    # unit tests, plain Node, no display needed

# run from the checkout (either form)
bin/clipagent-recorder --list-devices
bin/clipagent-recorder --session /tmp/s1 --camera none
bin/clipagent-recorder --stop /tmp/s1

npx electron . -- --list-devices                       # from recorder/
npx electron recorder/ -- --session /tmp/s1            # from the repo root
# On Linux add Chromium switches before the app dir when needed:
npx electron --no-sandbox --ozone-platform=x11 recorder/ -- --session /tmp/s1
```

`bin/clipagent-recorder` is what the engine uses in a dev checkout. It handles `--stop` in plain Node and starts Electron for everything else, adding `--no-sandbox` / `--ozone-platform=x11` on Linux when needed and forwarding signals.

Environment variables for testing and tuning:

| variable | effect |
|---|---|
| `CLIPAGENT_FAKE_SCREEN=1` | record a generated test pattern instead of the screen (no portal / permission): exercises the whole pipeline |
| `CLIPAGENT_INPUT=uiohook\|evdev\|none` | force the input source |
| `CLIPAGENT_EVDEV_PATHS=/path:keyboard,/path:mouse` | evdev worker reads these files instead of discovering devices (tests) |
| `CLIPAGENT_SCREEN_CODEC=vp8` | screen codec (default `vp9`) |
| `CLIPAGENT_SCREEN_BITRATE=8000000` | screen bitrate in bit/s |
| `CLIPAGENT_START_TIMEOUT=180` | seconds to wait for the screen-share grant |
| `CLIPAGENT_NATIVE_WAYLAND=1` | do not switch to XWayland on Wayland |

### Packaging

```bash
npm run dist:linux     # release/ClipAgent-Recorder-linux-x86_64.AppImage
npm run dist:mac       # release/ClipAgent-Recorder-mac-universal.dmg
npm run dist:win       # release/ClipAgent-Recorder-win-x64.exe and .zip
```

Releases: push a tag `recorder-v<version>` matching `package.json`; `.github/workflows/release-recorder.yml` builds all three on GitHub runners and attaches them to the release. Signing is optional (`CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` secrets).

## Files

```
bin/clipagent-recorder     dev launcher (Node)
src/main/main.js           Electron main: CLI modes, Recorder state machine, bar, hotkeys, take.json
src/main/input.js          input source selection (uiohook / evdev / none)
src/main/evdev-worker.js   child process reading /dev/input/event*
src/main/preload-*.js      context bridges for the two windows
src/renderer/capture.*     hidden window: getDisplayMedia / getUserMedia / MediaRecorder
src/renderer/bar.*         floating control bar
src/lib/                   pure modules: cli, clock, keys, events, evdev, geometry, take, stopper
test/                      node --test unit tests
```

## End-to-end test without your devices

`test/e2e/run.sh PAGE.html VOICE.wav [SECONDS]` runs the real recorder against a separate X display (`:99`, Xvfb or rootful Xwayland) showing a scripted page, with `--camera none --no-mic`. It drives real X input (clicks and a shortcut via XTest) so the input hook is tested, adds the voice track, and runs `prepare → inserts → qa → render → deliver` on the resulting Take. Your own screen, camera and microphone are never opened.
