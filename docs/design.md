# ClipAgent: design and contracts

ClipAgent is a coding-agent skill: the user types `/screen-record` in Claude Code (or Codex), talks freely while the screen, webcam, mic and input events are captured, hits stop, and gets a studio-quality edited video back, with Inserts (animated diagrams, code, docs, charts, math) generated from their own Context Pack. Vocabulary is in [`GLOSSARY.md`](../GLOSSARY.md); decisions are in [`adr/`](adr/).

## Pipeline

```
/screen-record ──► recorder/ (Electron)          writes  SESSION/take/
        stop  ──► engine: clipagent ingest        Take → CFR mp4s + events
                  clipagent transcribe            word-level transcript (faster-whisper, local)
                  clipagent analyze               activity, SNR, sync offset, camera look/quality score
                  clipagent draft                 first edl.json (cuts, retakes, Scratch Markers, zooms from clicks)
           agent  ── editorial pass ──            reads transcript + Context Pack, writes Inserts + Look choice into edl.json
                  clipagent inserts               resolve Beats → render each Insert (HTML/Playwright or Manim) → frames
                  clipagent qa                    automatic checks + stills for the agent to compare with Look reference frames
                  clipagent render                pass 1 (cut, grade, voice master) + pass 2 (composite, Inserts, captions, SFX, music)
                  clipagent deliver               shorts, thumbnail, srt, chapters, publishing copy, report.md
```

The coding agent is the editor: the `clipagent` CLI does the mechanical work, the agent makes editorial calls by writing `edl.json` (see `skills/screen-record/SKILL.md`).

## Repository layout

```
.claude-plugin/        Claude Code plugin manifest (+ marketplace.json)
skills/screen-record/  SKILL.md (works for Claude Code and Codex) + reference/
engine/                Python package `clipagent` (uv project). CLI entry point: `clipagent`
looks/                 one folder per Look + _runtime/ (shared HTML player)
recorder/              Electron companion app
demo/                  the README demo video and the script that produced it
docs/                  design, ADRs, and project history (brainstorms/plans from Aug 2026)
```

## Contract 1: the Take (recorder → engine)

The recorder is launched as:

```
clipagent-recorder --session <SESSION_DIR> [--camera <deviceId>|none] [--no-mic] [--display <id>]
```

It writes everything into `<SESSION_DIR>/take/`:

| file | content |
|---|---|
| `screen.webm` | screen video (no audio), MediaRecorder VP9/VP8 |
| `camera.webm` | webcam video (no audio), absent when camera is `none` |
| `mic.webm` | microphone audio (Opus), absent with `--no-mic` |
| `events.jsonl` | one JSON object per line, see below |
| `state.json` | `{"status": "starting|recording|paused|stopping|done|error", "error": null, "elapsed": 12.3}` rewritten on each change |
| `take.json` | manifest, written once on stop |

`take.json`:
```jsonc
{
  "version": 1,
  "app": "clipagent-recorder 0.1.0",
  "platform": "linux|darwin|win32",
  "started_at": "2026-11-02T20:31:07.120Z",
  "duration": 312.4,                       // recorded seconds, pauses excluded
  "display": { "width": 2560, "height": 1440, "scale": 1.0 },   // physical px of the captured display
  "streams": {
    "screen": { "file": "screen.webm", "start_offset": 0.000 },  // seconds after take t=0 that the stream's first frame belongs to
    "camera": { "file": "camera.webm", "start_offset": 0.031, "label": "HD Webcam" },
    "mic":    { "file": "mic.webm",    "start_offset": 0.012, "label": "Built-in mic" }
  },
  "input": { "source": "uiohook|evdev|none", "warning": null },
  "overlay_rect": [0.80, 0.02, 0.18, 0.05],  // floating bar position (0-1 of display) when it could not be excluded from capture, else null
  "pauses": [[120.5, 120.5]]                // positions in recorded time where a pause happened
}
```

`events.jsonl` (times are seconds of recorded time since take t=0; pauses excluded; coordinates 0-1 of the captured display):
```jsonc
{"t": 3.21, "type": "click", "x": 0.41, "y": 0.62, "button": "left"}
{"t": 3.30, "type": "move", "x": 0.42, "y": 0.61}                 // sampled ≤ 20 Hz
{"t": 5.02, "type": "scroll", "x": 0.5, "y": 0.5, "dy": -3}
{"t": 7.80, "type": "shortcut", "keys": ["Ctrl", "Shift", "P"]}    // only combos with a modifier, or F-keys/Esc/Enter/Tab
{"t": 7.90, "type": "typing"}                                      // a plain keystroke: NO character is ever stored
{"t": 9.00, "type": "marker", "kind": "scratch"}                   // Scratch Marker hotkey
{"t": 60.1, "type": "pause"} {"t": 60.1, "type": "resume"}
```

Stop paths: the floating bar's Stop button, the global stop hotkey, or `clipagent-recorder --stop <SESSION_DIR>` (creates `take/stop`, which the app polls). The app finalizes files, writes `take.json`, sets `state.status = "done"` and exits 0.

Hotkeys (defaults): stop `Ctrl+Alt+S` (`Cmd+Option+S` on macOS), pause/resume `Ctrl+Alt+P`, Scratch Marker `Ctrl+Alt+X`.

## Contract 2: Insert specs (engine ↔ Look runtime)

The agent writes Inserts into `edl.json` with Beats anchored to **word ids** (`w123`, from `transcript.json`). The engine resolves them to seconds relative to the Insert start in the edited timeline and writes a resolved spec:

```jsonc
{
  "id": "ins-03",
  "look": "architecture-flow",
  "engine": "html",                // html | manim
  "mode": "full",                  // full | split | overlay
  "size": [1920, 1080],            // pixel size of the Insert's own canvas
  "transparent": false,            // true for overlay mode: background must be transparent
  "fps": 30,
  "duration": 9.4,                 // seconds
  "concepts": { "JWT": "#38BDF8", "session id": "#F59E0B" },   // Concept Colors for the whole Session
  "scene": { ... },                // Look-specific; documented in looks/<look>/PRIMITIVES.md
  "beats": [ { "at": 1.20, "action": "...", "target": "...", "args": { } } ]
}
```

HTML runtime contract (`looks/_runtime/player.html?spec=<file URL of resolved spec>`): the page builds the scene and exposes

```js
window.clipagent = {
  ready: Promise<void>,          // resolves when fonts/assets are loaded and the scene is built
  duration: number,
  seek(t: number): void | Promise<void>   // render the exact state at time t. Pure function of t: no CSS animations,
                                          // no requestAnimationFrame clocks, no Math.random without a seed.
}
```

The engine's frame grabber (`engine/clipagent/inserts/html_render.py`) opens the page in headless Chromium at `size`, calls `seek(i / fps)` for each frame, and screenshots (with `omitBackground` when transparent) into `frames/%05d.png`.

Manim contract: `looks/math-vector/manim/` provides a scene that reads the same resolved spec (env var `CLIPAGENT_SPEC`) and renders a video of exactly `duration` seconds, with each Beat played at its `at` time.

## Contract 3: Look folders

```
looks/<look-id>/
  look.json         id, name, description, best_for, canvas background, palette, fonts, concept_palette,
                    semantic colors, screen_treatment (frame, zoom feel, click effect, annotations, transitions),
                    captions style, chapter card style, sfx map (primitive/action → file)
  look.css          tokens + styles for the HTML runtime
  primitives.js     registers this Look's Primitives with the runtime
  PRIMITIVES.md     the scene vocabulary the agent writes (each Primitive: props, Beat actions, example)
  examples/*.json   example Insert specs (used for tests and reference frames)
  reference/*.png   reference frames rendered from the examples (the self-check compares against them)
  assets/           SVG art kit (open-licensed or original), fonts (OFL)
  sfx/              short royalty-free / synthesized sound effects
```

The five v1 Looks: `math-vector`, `whiteboard-saas`, `neon-telestrator`, `architecture-flow`, `stickman-story`.
