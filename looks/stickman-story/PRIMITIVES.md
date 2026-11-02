# stickman-story: Primitives

Scene vocabulary for the **stickman-story** Look (minimalist monochrome stickman storytelling + clean UI walkthrough). You, the agent, write the `scene` and `beats` of an Insert spec (Contract 2 in `docs/design.md`); the runtime builds and animates them. Unknown primitives, actions, props, moods, poses, symbols or icons raise an error that lists the valid choices.

Use it for: relatable stories and emotional beats (stress, relief, victory, surprise), productivity/habit/dev-life explainers, before/after, and simple product walkthroughs (clicks, zooms on stats, tab switches).

## How an Insert is structured

An Insert is a sequence of **shots**. Each shot is one element: a `Scene` (stickman on white) or a `Walkthrough` (UI in a macOS window on black). The first shot in `elements` is on screen at t = 0; a `cut` beat on another shot replaces it instantly (hard cut). Write one shot per 4-6 s emotional beat (1-2 sentences) and put each `cut` on the first word of the next sentence.

```jsonc
{
  "look": "stickman-story", "engine": "html", "size": [1920, 1080], "fps": 30, "duration": 10.0,
  "scene": {
    "elements": [
      { "id": "s1", "primitive": "Scene", "props": { "caption": "It's 11 pm…", "props": ["laptop"], "mood": "stressed", "arms": "type" } },
      { "id": "s2", "primitive": "Scene", "props": { "caption": "Then it *worked*.", "layout": "center", "mood": "happy" } }
    ]
  },
  "beats": [
    { "at": 1.2, "action": "symbol", "target": "s1", "args": { "kind": "sweat" } },
    { "at": 5.0, "action": "cut", "target": "s2" },
    { "at": 5.4, "action": "victory", "target": "s2" }
  ]
}
```

- `at` is seconds from the Insert start (the engine resolves word ids to seconds). Beats may be in any order.
- Every beat targets a shot id. All character, prop and symbol actions are sent to the Scene that contains them (there is exactly one character per Scene).
- `args.dur` overrides any action's duration; `args.ease` overrides easing (`smooth`, `inOut`, `out`, `in`, `outBack`, `linear`, or `[x1,y1,x2,y2]`).
- Beats on a shot that is not on screen still compile (its state is ready when you cut to it), but the viewer only sees the shot that is active.
- 16:9 and 9:16 both work. In 9:16, thought bubbles and the first floating prop (checklist, timer, clock) stack above the character instead of beside it.

### Style rules (already enforced)

Pure white canvas, uniform 5 px black ink, round caps, no shading or color. The character is always the same rig: round head, exactly three hair strands, cartoon eyes with pupils, eyebrows, mouth, tubular torso, stick limbs with round hands. Furniture and the base posture never move within a shot; only face, head, arms, symbols, clock hands, screens, steam and checkmarks animate. Blinks happen automatically (seeded, every 2.3-4.9 s, occasional double blink).

## Scene

One shot: the character + 1-2 props + a handwritten caption (Patrick Hand) at the top. The composition auto-fits and centers itself; you never give pixel positions.

### Props (`props` of the element)

| prop | default | meaning |
|---|---|---|
| `caption` | `""` | handwritten text at the top. `*word*` underlines a word (5 px ink). Words pop in quickly at the cut. |
| `props` | `[]` | 0-2 props: strings (`"laptop"`) or objects (`{ "kind": "clock", "time": "10:52" }`). See Props below. |
| `layout` | `auto` | `desk` (seated at a desk, chair added), `stand` (standing, props beside), `center` (character alone, centered). `auto`: `desk` if a laptop/monitor/desk is listed, `stand` if other props, else `center`. |
| `pose` | by layout | `sit` or `stand` |
| `side` | `right` | which side the props/desk go on (`left`/`right`). The character faces them. |
| `facing` | toward props | `left`, `right`, `front` (3/4 turn of the face; the body is always the same tube) |
| `mood` | `neutral` | starting face: see Moods |
| `arms` | `rest` | starting arm pose: see Arm poses (loops like `type` and `scroll` run from the first frame) |
| `look` | toward screen / slightly forward | starting gaze: see Look directions |
| `symbols` | `[]` | symbols visible from the cut, e.g. `["zzz"]` or `[{ "kind": "bubble", "text": "hmm", "delay": 0.4 }]` (pop in `delay` s after the cut, default 0.35) |
| `bubbleSide` | away from props | `left`/`right`: side for thought bubbles and `!`/`?` |
| `floor` | `true` | the ground line |

### Prop kinds

| kind | where | props | actions |
|---|---|---|---|
| `desk`, `chair` | desk layout (always added there) | | |
| `laptop` | on the desk, 3/4 view, screen visible | `screen`: `code` (default; lines type in while the character types), `error`, `success`, `chart` (line draws on), `blank`, `text` | `screen` |
| `monitor` | on the desk with a keyboard | `screen` as laptop | `screen` |
| `mug` (alias `coffee`) | on the desk, animated steam | | |
| `clock` | wall (desk layout: above the desk; stand/center: on the wall) | `time` (`"10:52"`), `speed` (clock-minutes per second of ambient drift, default 0). The second hand ticks every second. | `clock` |
| `checklist` | clipboard beside the character (desk: on the wall) | `title`, `items` (strings), `checked` (indices already ticked) | `check` |
| `timer` | stopwatch with progress ring and `m:ss` | `seconds` (1500), `mode` (`down` default, or `up` = elapsed), `running`, `rate` (displayed seconds per real second, default 60) | `timer` |
| `door` | beside the character | `open` (false) | `door` |
| `phone` | in the hand (no prop needed: use `arms: "scroll"` / `"phone"`) | | |

Put a desk prop (laptop/monitor/mug) only in a desk layout; a mug needs a desk.

### Moods (`mood` prop, `mood` action)

`neutral`, `smile`, `happy` (big open grin), `confident` (smirk + one raised brow), `focused`, `thinking`, `stressed` (worried brows + wobbly mouth), `sad`, `surprised` (wide eyes, O mouth), `angry`, `sleepy` (half-closed eyes).

Eyebrow states (`brows`): `neutral`, `stressed`/`worried`, `confident`, `raised`, `angry`, `sad`, `focused`, `happy`.
Mouth shapes (`mouth`): `neutral`, `smile`, `grin`, `frown`, `open`, `o`, `flat`, `smirk`, `wobble`, `small`.

### Arm poses (`arms` prop, `arms {pose}` action, or the alias actions)

`rest`, `hips` (hands on hips), `victory` (both arms up, pumping), `wave` (loop), `shrug`, `think` (fist under chin), `facepalm`, `type` (typing loop on the laptop/monitor keyboard), `scroll` (phone in hand, thumb-scroll loop, content scrolls), `phone` (holding phone, no scrolling), `point {at}` (index finger), `present {at}` (open hand toward something), `press {at}` (reaches and presses: laptop key, timer button, door handle), `clap` (loop).

### Look directions / targets

`camera` (or `center`, `front`), `left`, `right`, `up`, `down`, `up-left`, `up-right`, `down-left`, `down-right`, `phone`, `screen` (laptop/monitor), `prop` (first prop), `clock`, `checklist`, `timer`, `door`, `mug`, or `[x, y]` (-1..1 pupil offset). `point`/`press` accept the same names plus `button`, and `item` (checklist row index).

### Actions (target = the Scene id)

| action | args | default dur | effect |
|---|---|---|---|
| `cut` (alias `enter`) | | 0 | hard cut to this shot |
| `exit` | | 0 | blank white if this shot is on screen |
| `mood` (alias `face`) | `mood` | 0.3 | brows, mouth and eyelids blend to the mood |
| `brows` | `state` | 0.25 | eyebrows only |
| `mouth` | `shape` | 0.2 | mouth only |
| `talk` | `dur` | 2.0 | lip-flap loop on top of the current mouth for `dur` s (sync to a quoted line) |
| `blink` | | 0.2 | an extra blink |
| `look` | `dir` (or `at`) | 0.22 | pupils move |
| `turn` | `to`: `left`/`right`/`front` or -1..1 | 0.3 | face features shift (3/4 head turn) |
| `nod` | `times` (2) | 0.75 | nod (yes) |
| `shake` | `times` (2) | 0.8 | head shake (no) |
| `tilt` | `angle` (deg, -25..25, 8) | 0.4 | head tilt (holds; `angle: 0` to undo) |
| `arms` | `pose`, `at`, `item`, `arm` (`left`/`right`) | 0.45 | change arm pose (loops start/stop smoothly) |
| `type` | `look` (true) | 0.45 | arms to keyboard + typing loop; eyes to screen |
| `scroll` | `look` (true) | 0.45 | phone in hand + thumb-scroll loop; eyes to phone |
| `point` | `at`, `item`, `arm`, `look` (true) | 0.4 | point at a target; eyes follow |
| `press` | `at` (`button`) | 0.45 | reach and press (a short push at the end) |
| `wave`, `think`, `shrug`, `rest`, `hips`, `clap` | | 0.35-0.5 | arm pose aliases |
| `facepalm` | `mood` (`stressed`, or `false`) | 0.45 | hand to forehead + mood |
| `victory` | `mood` (`happy`), `sparkles` (true), `hold` | 0.4 (outBack) | arms up + happy face + sparkles + eyes to camera |
| `symbol` | `kind`, `hold` (s, optional), `side`, `dx`, `dy`, kind-specific args | 0.3 | pop a comic symbol in (bounce). Stays until `clear`, `hold` or the next cut away. |
| `bubble` | `text` (`\n` for 2 lines) or `icon`, `hold` | 0.35 | thought bubble (alias of `symbol {kind: "bubble"}`) |
| `clear` | `kind` (all if omitted) | 0.2 | pop symbols out |
| `check` | `item` (next unchecked if omitted), `strike` (false) | 0.35 | checklist: the ✓ draws on (optional strike-through). Without a checklist: a big circled ✓ pops near the head. |
| `clock` | `to` (`"11:00"`) or `add` (minutes, 60) | 1.6 | hands spin forward to the time (time passing) |
| `timer` | `run` (true/false), `rate` | 0 | start/stop the stopwatch |
| `door` | `open` (true/false) | 0.6 | door swings open (light rays) or closed |
| `screen` | `state`, `text` | 0 | laptop/monitor screen content |
| `caption` | `text` | 0 | replace the caption (new words pop in) |

### Comic symbols (`symbol {kind}`)

| kind | placement | animation |
|---|---|---|
| `bubble` | thought cloud above the head on the open side, with two trailing circles; `text` (single short phrase) or `icon` | gentle bob |
| `stress` | scribble cloud over the head | boils (re-drawn every 0.11 s) |
| `sweat` | two drops beside the head, away from the props | drops slide and re-form |
| `exclaim`, `question` | big `!` / `?` beside the head | pop + wobble |
| `zzz` | z's rising from the head | loop |
| `idea` | light bulb with rays above the head | pulse |
| `heart`, `music` | beside the head | float |
| `check` | big circled ✓ beside the head (or `at`: a target name) | draw-on |
| `sparkles` | five 4-point stars around the head (added by `victory`) | twinkle |

Bubble icons (Lucide, ISC): alarm-clock, battery-low, bed, bell, book-open, brain, briefcase, bug, calendar, car, chart-line, check, clock, cloud, code, coffee, dollar-sign, dumbbell, file-text, flame, gift, graduation-cap, heart, house, key-round, laptop, lightbulb, lock, mail, message-circle, moon, music, pizza, plane, rocket, search, shopping-cart, smartphone, star, sun, target, thumbs-down, thumbs-up, trending-down, trending-up, trophy, umbrella, user, users, utensils, wifi, x, zap.

## Walkthrough

A browser capture framed in a rounded macOS window (16 px radius, traffic lights, tab strip, address bar) centered over pure black. Clicks show a cursor that glides to the spot and a 40 px translucent grey ripple; zooms are smooth 1.8x pan-and-zoom keyframes; tab switches use a 0.25 s radial zoom-blur.

### Props

| prop | default | meaning |
|---|---|---|
| `tabs` | | `[{ "src": "media/page.png", "title": "Overview · Pulse", "url": "app.pulse.dev" }]`. `src` is relative to the spec file (or `look:<path>` inside the Look, or a data: URL). Use full-width page screenshots; taller images can be scrolled. |
| `active` | 0 | starting tab |
| `aspect` | 1.6 | width/height of the visible page area (match your screenshots, e.g. 1.6 for 1600x1000) |
| `caption` | `""` | optional white handwritten line above the window |
| `width` | 0.84 (9:16: 0.92) | max window width as a fraction of the canvas |
| `cursor` | true | show the pointer |
| `cursorAt` | `[0.62, 0.7]` | cursor start (0-1 of the page) |

All coordinates are fractions of the visible page area: `x` 0 = left edge, 1 = right; `y` 0 = top of the page area (under the address bar), 1 = bottom. They stay attached to the content while zoomed.

### Actions

| action | args | default dur | effect |
|---|---|---|---|
| `cut` | | 0 | hard cut to the walkthrough |
| `click` | `x`, `y`, `travel` (s, = dur) | 0.45 | cursor glides there during `travel` *before* `at`; the press + ripple land exactly at `at` (anchor `at` to the spoken word) |
| `move` | `x`, `y` | 0.5 | cursor glides without clicking |
| `zoom` | `x`, `y`, `scale` (1.8) | 1.1 | smooth pan-and-zoom centered on the point (clamped to the page edges) |
| `unzoom` | | 0.9 | back to the full page |
| `tab` | `index` or `to` (tab title substring), `keepZoom` (false) | 0.25 | radial zoom-blur to that tab; zoom resets at the midpoint |
| `scroll` | `to` (0-1 of the overflow) | 0.9 | scroll a tall screenshot |
| `highlight` | `x`, `y`, `w`, `h`, `hold` (optional) | 0.35 | dashed marching-ants box around a region |
| `unhighlight` | | 0.25 | remove highlight boxes |
| `caption` | `text` | 0 | replace the caption |

## Authoring rules of thumb

- One sentence (or two short ones) per Scene, 4-6 s each; `cut` on the first word of the next sentence. 3-5 Scenes per Insert is plenty.
- Give every Scene one clear emotion: set `mood` in props, then change it once on the key word (`mood`, `victory`, `facepalm`, `symbol`).
- 1-2 props per Scene. Desk scenes: laptop or monitor (+ mug or clock). Standing scenes: checklist, timer, clock or door.
- Time `check` to each item being said, `clock` to "hours later", `symbol: stress` to "panic"/"stuck", `victory` to "it worked", `bubble` to "I thought…".
- Keep captions short (≤ 8 words in 16:9, ≤ 6 per line in 9:16). They are a headline, not a transcript (the video has its own captions).
- Walkthrough: start the `click` a beat early is unnecessary (the cursor travels before `at`); `zoom` 0.3-0.5 s after the click; leave ≥ 1.2 s on a zoom so text can be read; `unzoom` before a `tab`.

## Example 1: late-night bug (16:9, three Scenes)

```json
{
  "id": "example-late-night-bug",
  "look": "stickman-story",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 15.0,
  "concepts": {},
  "scene": {
    "elements": [
      { "id": "s1", "primitive": "Scene", "props": {
          "caption": "It's 11 pm and the bug is *still* there.",
          "props": ["laptop", { "kind": "clock", "time": "10:52" }],
          "mood": "stressed", "arms": "type" } },
      { "id": "s2", "primitive": "Scene", "props": {
          "caption": "So I wrote down every step, one by one.",
          "props": [{ "kind": "checklist", "title": "Debug plan", "items": ["Reproduce it", "Add a test", "Fix the cause"] }],
          "mood": "focused", "arms": "rest" } },
      { "id": "s3", "primitive": "Scene", "props": {
          "caption": "Twenty minutes later: *green*.",
          "props": [{ "kind": "laptop", "screen": "success" }],
          "mood": "happy", "arms": "rest" } }
    ]
  },
  "beats": [
    { "at": 0.6, "action": "symbol", "target": "s1", "args": { "kind": "sweat" } },
    { "at": 1.6, "action": "clock", "target": "s1", "args": { "to": "11:00", "dur": 2.0 } },
    { "at": 2.4, "action": "look", "target": "s1", "args": { "dir": "clock" } },
    { "at": 3.0, "action": "symbol", "target": "s1", "args": { "kind": "stress" } },
    { "at": 3.6, "action": "look", "target": "s1", "args": { "dir": "screen" } },

    { "at": 5.0, "action": "cut", "target": "s2" },
    { "at": 5.4, "action": "point", "target": "s2", "args": { "at": "checklist" } },
    { "at": 6.2, "action": "check", "target": "s2", "args": { "item": 0 } },
    { "at": 7.2, "action": "check", "target": "s2", "args": { "item": 1 } },
    { "at": 7.6, "action": "nod", "target": "s2" },
    { "at": 8.3, "action": "check", "target": "s2", "args": { "item": 2 } },
    { "at": 8.6, "action": "mood", "target": "s2", "args": { "mood": "confident" } },
    { "at": 8.8, "action": "look", "target": "s2", "args": { "dir": "camera" } },

    { "at": 10.0, "action": "cut", "target": "s3" },
    { "at": 10.6, "action": "victory", "target": "s3" },
    { "at": 11.0, "action": "talk", "target": "s3", "args": { "dur": 1.4 } }
  ]
}
```

## Example 2: stickman intro + UI walkthrough (16:9)

```json
{
  "id": "example-dashboard-walkthrough",
  "look": "stickman-story",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 14.0,
  "concepts": {},
  "scene": {
    "elements": [
      { "id": "intro", "primitive": "Scene", "props": {
          "caption": "Let me show you where the numbers live.",
          "props": [{ "kind": "monitor", "screen": "chart" }, "mug"],
          "mood": "smile", "arms": "rest", "look": "camera" } },
      { "id": "ui", "primitive": "Walkthrough", "props": {
          "tabs": [
            { "src": "media/dashboard.png", "title": "Overview · Pulse", "url": "app.pulse.dev/overview" },
            { "src": "media/billing.png", "title": "Billing · Pulse", "url": "app.pulse.dev/billing" }
          ],
          "aspect": 1.6 } }
    ]
  },
  "beats": [
    { "at": 0.8, "action": "point", "target": "intro", "args": { "at": "screen" } },
    { "at": 1.0, "action": "talk", "target": "intro", "args": { "dur": 1.8 } },
    { "at": 2.2, "action": "look", "target": "intro", "args": { "dir": "camera" } },

    { "at": 3.5, "action": "cut", "target": "ui" },
    { "at": 4.6, "action": "click", "target": "ui", "args": { "x": 0.30, "y": 0.20 } },
    { "at": 5.0, "action": "zoom", "target": "ui", "args": { "x": 0.30, "y": 0.22, "scale": 1.8 } },
    { "at": 6.4, "action": "highlight", "target": "ui", "args": { "x": 0.18, "y": 0.128, "w": 0.25, "h": 0.135, "hold": 1.2 } },
    { "at": 8.0, "action": "unzoom", "target": "ui" },
    { "at": 9.0, "action": "click", "target": "ui", "args": { "x": 0.17, "y": 0.04 } },
    { "at": 9.05, "action": "tab", "target": "ui", "args": { "index": 1 } },
    { "at": 10.6, "action": "click", "target": "ui", "args": { "x": 0.915, "y": 0.37 } },
    { "at": 11.3, "action": "move", "target": "ui", "args": { "x": 0.6, "y": 0.33, "dur": 0.6 } },
    { "at": 11.4, "action": "zoom", "target": "ui", "args": { "x": 0.6, "y": 0.3, "scale": 1.8 } }
  ]
}
```

More in `examples/`: `morning-routine-vertical.json` (9:16: Zzz + alarm clock, phone scrolling with a thought bubble, stopwatch counting up, facepalm, wave) and `deadline-panic.json` (monitor typing + spinning clock + error screen, door opening, idea bubble with an icon, shrug + question mark, victory). Reference frames rendered from all four are in `reference/`.
