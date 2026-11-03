# edl.json reference

The EDL (edit decision list) is the whole edit. `clipagent prepare` writes a draft to `work/edl.json`; you refine it; `clipagent inserts` + `clipagent render` execute it.

**Every time in the EDL is in SOURCE seconds** (the clock of `transcript.txt` and `clipagent frames`), **or a word id** (`"w412"`, from `words.txt`) where noted. Never convert to output time yourself; the renderer maps through the cuts. An event whose span was cut away entirely is dropped.

**Every rect is `[x, y, w, h]` as 0-1 fractions of the raw screen frame**, read straight off the `clipagent frames` grid.

```jsonc
{
  "version": 1,
  "inputs": {
    "screen": "/abs/raw/screen.mp4",
    "camera": "/abs/raw/cam.mp4",      // null if no separate webcam file
    "camera_offset": -1.84,            // camera_time = screen_time + offset (analyze.py measures it)
    "camera_rect": null,               // [x,y,w,h] if the webcam is baked INTO the screen recording (graded in place)
    "audio": "screen"                  // which file carries the good mic: "screen" | "camera"
  },
  "output": { "path": "/abs/out/final.mp4", "format": "landscape", "fps": 30 },   // format: landscape 1920x1080 | vertical 1080x1920

  "style": {
    "accent": "#D97757",                       // highlights, rings, bars, karaoke word
    "background": ["#14141f", "#2b1d3a"],      // gradient behind the inset screen
    "screen_inset": 0.035,                     // margin around the screen, fraction of height
    "radius": 18,                              // screen corner radius at 1080p
    "font": "Inter",
    "captions": { "enabled": true, "words_per_line": 4, "highlight": "#D97757" },
    "badge": "Made with ClipAgent",            // small pill top-right; null to disable
    "badge_mode": "intro"                      // "intro" (first 6s) | "always"
  },

  "voice": {
    "denoise": "normal",      // light | normal | strong (analyze.py recommends one from the measured noise floor)
    "mic": "earphones"        // earphones | phone | laptop | studio: EQ profile for that mic
  },

  "camera": {
    "source": "phone",        // phone (gentle grade, no re-sharpening) | webcam (stronger cleanup)
    "grade": "auto",          // "auto" | "off" | { overrides, see below }
    "shape": "circle",        // "circle" | "rounded"
    "size": 0.23,             // bubble diameter, fraction of height (landscape)
    "size_vertical": 0.42,    // bubble diameter, fraction of width (vertical)
    "corner": "br",           // br | bl | tr | tl
    "mirror": false
  },

  "glossary": { "cloud code": "Claude Code" },   // caption fixes for RECURRING mishearings; multi-word keys OK, case-insensitive
  "caption_edits": [                               // one-off fixes: words spoken in start..end are shown as `text`
    { "start": 84.1, "end": 85.0, "text": "LangGraph" }
  ],

  "segments": [                          // what is KEPT, in order. Everything else is cut.
    { "start": 0.42, "end": 14.9, "speed": 1 },
    { "start": 15.1, "end": 41.0, "speed": 4, "note": "npm install" }   // speed: integer 1-8; audio ducked, "4x speed" badge shown
  ],

  "layouts": [                           // camera layout changes; default "bubble" from t=0
    { "at": 0.4,  "camera": "full" },    // talking-head intro, fills the frame
    { "at": 6.2,  "camera": "bubble" },  // shrinks into the corner (animated)
    { "at": 120,  "camera": "side" },    // screen left 2/3, camera right: explanations
    { "at": 300,  "camera": "hidden" }
  ],

  "zooms": [                             // smooth zoom/pan into a screen region; slow push-in while held
    { "start": 22.0, "end": 31.5, "rect": [0.05, 0.55, 0.5, 0.5], "note": "terminal output" }
  ],

  "titles": [ { "at": 0.6, "duration": 3.2, "text": "Build an MCP server in 10 minutes", "sub": "from scratch, with Claude Code" } ],
  "chapters": [ { "at": 48.0, "text": "Defining the tools" } ],          // numbered label slides in top-left + punch-in
  "callouts": [                                                          // pill at top; with rect also spotlights that region
    { "start": 70.2, "end": 74.0, "text": "This is the agent loop", "rect": [0.12, 0.30, 0.40, 0.18] }
  ],
  "redact": [ { "start": 90.0, "end": 140.0, "rect": [0.30, 0.42, 0.45, 0.04], "note": "ANTHROPIC_API_KEY in .env" } ],  // pixelated; omit start/end = whole video

  "outro": { "text": "Made with ClipAgent", "sub": "@yourhandle", "duration": 4 }
}
```

Keys starting with `_` (e.g. `_draft_removed_gaps`, `_draft_scratched`) are notes; the renderer ignores them.

`style` is filled from the Look (`clipagent prepare --look` / changing `"look"` and re-running `prepare` re-applies it). You rarely edit it by hand.

## ClipAgent fields

```jsonc
{
  "look": "architecture-flow",            // one Look for the whole video (`clipagent looks`)
  "concepts": { "JWT": "#38BDF8" },        // Concept Colors; the Look's semantic colors win, the rest come from its palette

  "inserts": [                             // see reference/inserts.md
    { "id": "ins-01", "start": "w120", "end": "w161",           // word ids (or source seconds)
      "mode": "full",                                           // full | split | overlay
      "rect": [0.56, 0.1, 0.4, 0.42],                           // overlay only: canvas fractions
      "engine": "html",                                         // html | manim (math-vector)
      "concepts": ["JWT", "refresh token"],
      "transition": null,                                       // override the Look's transition (crossfade | diagonal_wipe | radial_blur | cut)
      "scene": { },                                             // the Look's scene vocabulary: looks/<look>/PRIMITIVES.md
      "beats": [ { "word": "w131", "action": "send", "target": "jwt", "args": {}, "lead": -0.1 } ] }
  ],

  "annotations": [                         // drawn on the screen recording, follow zooms
    { "type": "box",     "start": 41.0, "end": 45.5, "rect": [0.2, 0.3, 0.3, 0.1], "label": "pricing card", "label_pos": "below" },  // marching ants; label_pos optional: right/left/below/above
    { "type": "arrow",   "start": 47.0, "end": 50.0, "to": [0.62, 0.41], "from": [0.4, 0.2], "label": "click here" },
    { "type": "chevron", "start": 52.0, "end": 54.0, "at": [0.7, 0.55], "dir": "right" },              // pulsing >>>
    { "type": "pill",    "start": 55.0, "end": 58.0, "at": [0.5, 0.12], "text": "Sidebar", "arrows": true },
    { "type": "pointer", "start": 60.0, "end": 61.2, "at": [0.33, 0.7], "color": "#FF2A2A" }          // red arrow callout
  ],
  "clicks":    [ { "t": 12.4, "x": 0.41, "y": 0.62 } ],      // from the input log; the Look's click effect is drawn on each
  "shortcuts": [ { "at": 30.1, "keys": ["Ctrl", "Shift", "P"] } ],   // keycap badges; delete entries you don't want shown
  "typing":    [ [62.0, 75.5] ],                               // typing stretches: keep Inserts off these

  "sound": { "sfx": true, "music": false, "music_db": -20 },   // music: true (the Look's bed) or a style: dark-pulse | bright-pluck | ambient-pad

  "shorts":    [ { "start": "w300", "end": "w402", "title": "Why refresh tokens exist" } ],
  "thumbnail": { "at": "w140", "text": "JWT in 60 seconds" },
  "publish":   { "title": "...", "description": "...", "tags": ["..."], "linkedin": "...", "x": "..." },
  "mismatches": [ { "at": "w412", "said": "we cache users in Redis", "context": "src/cache.ts uses an in-memory LRU" } ],

  "camera": { "quality": "fair", "allow_full": true }          // set by analysis; poor cameras: allow_full false → never layout "full"
}
```

## voice.denoise levels

All levels: rumble filter, click removal, mic EQ, de-esser, compressor, loudness to -14 LUFS.

| level | adds | use when |
|---|---|---|
| `light` | gentle spectral denoise | quiet room, SNR > 38 dB |
| `normal` | RNNoise neural denoiser (80% mix) + spectral | typical room, fan, light hiss |
| `strong` | RNNoise 100% + heavier spectral + soft gate between words | earphone mic hiss, street noise, SNR < 24 dB |

`strong` can make soft word endings sound clipped; listen-test isn't possible for Claude, so it trusts the SNR numbers and tells the user which level it picked.

## camera.grade overrides

HDR phone footage (iPhone default, many Androids) is detected and tone-mapped to normal video first. `"auto"` measures the camera (`analysis.json` → `camera_look`) and builds: denoise → white balance → exposure (gamma) → contrast/saturation → film S-curve → warmth → sharpen. Override any piece:

| key | default | effect |
|---|---|---|
| `target_luma` | 118 | brightness the auto exposure aims for (0-255); raise for a dark room |
| `gamma` | auto | force exposure (>1 brighter) |
| `white_balance` | 0.6 | 0 keep the color cast, 1 fully neutralize |
| `contrast` | 1.06 | |
| `saturation` | 1.12 | |
| `warmth` | 1 | 0 neutral, 2 warmer skin |
| `denoise` | 3 (phone 1.5) | 0-8; webcams in low light want 5-6 |
| `sharpen` | 0.5 (phone 0.15) | 0-1 (CAS) |

Changing anything under `inputs`, `segments`, `voice` or `camera` re-runs pass 1 (slow). Everything else (zooms, text, layouts, style) only re-runs pass 2.
