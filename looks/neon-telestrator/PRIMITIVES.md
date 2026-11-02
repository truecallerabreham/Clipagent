# neon-telestrator: Primitives

Scene vocabulary for the **neon-telestrator** Look: a dark-mode technical telestrator. Everything is drawn on a pure black canvas with a pressure-sensitive neon stylus stroke (3-5 px, tapered, slightly textured, no hand), handwritten labels write on glyph by glyph, screenshots get telestrated, charts are sketched, the 3D module is real three.js, and bold red pointers land on the exact thing being said. You, the agent, write the `scene` and `beats` of an Insert spec (Contract 2 in `docs/design.md`); the runtime builds and animates them. Unknown primitives, actions, ids, rows or series raise an error that names the valid choices.

Use it for: AI/ML explainers, benchmark and leaderboard breakdowns, pricing and cost drops, reacting to a news chart or screenshot, multi-variable trade-offs (3D), code walk-throughs with handwritten highlights.

## Spec shape

```jsonc
{
  "look": "neon-telestrator", "engine": "html", "size": [1920, 1080], "fps": 30, "duration": 10.0,
  "concepts": {},                                    // optional Concept Colors (color names usable in "color")
  "scene": {
    "title": "Inference got 15x cheaper",            // optional: Title (id "title"), big handwriting + yellow underline
    "elements": [ { "id": "shot", "primitive": "Screenshot", "props": { "src": "/abs/path/chart.png", "source": "example.com" } } ]
  },
  "beats": [ { "at": 1.2, "action": "draw", "target": "loop1" } ]
}
```

- `at` is seconds from the Insert start. Beats may be in any order. `target` is an id, a list of ids, or `"scene"` (`focus {ids, level}` / `unfocus`).
- `args.dur` overrides any duration; `args.ease` overrides easing (`smooth`, `inOut`, `out`, `in`, `outBack`, `linear`, `[x1,y1,x2,y2]`).
- **Coordinates are canvas fractions** (0-1 of width / height) for `x`, `y`, `box: [x, y, w, h]` (top-left + size) and `at: [x, y]`. Sizes (`size`, `width`, `gap`, `pad`, font sizes) are design px: the canvas short side is 1080 design px in both 16:9 (1920x1080) and 9:16 (1080x1920).

## Semantic ink rules (follow them strictly)

| meaning | color | token(s) | default on |
|---|---|---|---|
| base diagrams, icons, text, axes | Pure White #FFFFFF | `white`, `ink` | InkStroke, InkText, Icon, Panel, charts, Title text |
| positive metrics, price drops, money flows | Neon Green #2ECC71 | `green`, `gain`, `money` | Metric `tone: "gain"`, Metric `strike` new value, `dollar` icon |
| price cross-outs (X), inefficiency zones (hatch), attention pointers | Bright Red #FF2A2A | `red`, `alert`, `loss` | CrossOut, HatchZone, RedPointer, Metric strike line |
| grouping loops, brackets, trade-off side A | Neon Purple/Pink #D946EF | `purple`, `pink` | Loop, Underline, Bracket `kind: "tradeoff"`, notes on screenshots |
| trade-off side B | Cyan/Blue #3B82F6 | `blue`, `cyan` | Bracket `kind: "tradeoff-b"` |
| high-level category brackets, cross-panel connectors | Warm Yellow #FACC15 | `yellow`, `category` | Bracket `kind: "category"`, Arrow, Title underline |

Any `color` prop/arg accepts a token above, a `#hex`, or a Concept Color name. Do not invent other ink colors; data series in charts may use the same palette (purple, blue, green, yellow, white).

## References (`ref`): pointing at things

Telestration primitives (Loop, Underline, Bracket, CrossOut, HatchZone, Arrow `from`/`to`, RedPointer, anchored InkText) take a **ref**, written as props on the element itself (or as an object for Arrow `from`/`to`):

| ref | meaning |
|---|---|
| `"target": "id"` | the element's box (InkText: its text, Icon: the icon square, Metric: the value, HatchZone: the zone, Screenshot: the image) |
| `+ "region": [x, y, w, h]` | a sub-box in fractions **of the target** (for Screenshot: fractions of the image: `[0.33, 0.45, 0.2, 0.06]`) |
| `+ "line": 2` / `[2, 3]` / `"text"` | CodeSnippet line(s) (1-based, or the first line containing the text); indentation is ignored |
| `+ "bar": 1` / `"2026"` (+ `"part": "value"\|"label"`) | BarChart bar (live height), its value or x label |
| `+ "series": 0, "index": 3` / `[2, 3]` | LineChart point or point range; Chart3D vertex |
| `+ "part": "label", "index": 3` | LineChart x label |
| `+ "point": [x, y, z]` | Chart3D data coordinates (projected with the camera at that time; RedPointer tracks it live during orbits) |
| `+ "part": "label"\|"new"\|"source"\|"all"` | Icon/HatchZone/Metric label, Metric struck-to value, Screenshot source line, Icon incl. label |
| `"box": [x, y, w, h]` | a canvas box (fractions) |
| `"at": [x, y]` | a canvas point (fractions) |
| `"pad"`, `"dx"`, `"dy"` | grow the box / nudge it (design px) |

Telestration geometry is resolved at the moment the mark is drawn, so it follows a Chart3D camera or a BarChart `set`.

## Timing: drawing is a Beat

Every ink element draws on with the pen when it gets a `draw` (alias `enter`, `write`) beat. **Default duration follows the ink length** (pen speed 1500 design px/s, handwriting 0.045 s per glyph, strokes drawn one after another), clamped to 0.25-2.6 s (Icon 2.2 s, BarChart 3.2 s, LineChart 3.4 s). Pass `args.dur` to fit a spoken phrase.

Elements without a draw/enter/write/point beat **auto-draw** early (0.15 s + 0.14 s per element, in element order; Title at 0.05 s). Always give important marks an explicit beat on the spoken keyword. Set `props.auto: false` to keep an element hidden until a beat. RedPointer never auto-enters.

### Actions every ink element supports

| action | args | default dur | effect |
|---|---|---|---|
| `draw` / `enter` / `write` | `dur` | from ink length | pen draws the strokes / writes the text in order |
| `erase` | | 0.45 | un-draws everything, then hides |
| `exit` | | 0.4 | fades out |
| `dim` / `undim` | `level` (0.25) | 0.5 | dim instead of deleting |
| `pulse` | `color` | 0.7 | one neon glow flash |

## Primitives

### Title (from `scene.title`, id `title`)
Large bold handwriting at the top (y 0.095 landscape, 0.075 portrait) with a yellow underline drawn after the words.
- props: `text`, `size` (64), `underline` (true), `underlineColor` (`yellow`), `y`, `rotate` (-0.8)

### InkText (handwritten label)
- props: `text` (`\n` for lines), `x`, `y` (0.5, 0.5: anchor point), `size` (44), `color` (`white`), `font` (`hand` = Kalam, `script` = Caveat, casual notes like "yay"), `bold`, `align` (`center`), `valign` (`middle`), `rotate` (seeded ±1.6°), `speed` (1)
- anchored to a ref instead of x/y: `target` (+ any ref keys) + `side` (`right` default, `left`, `top`, `bottom`, `center`) + `gap` (18) + `dx`/`dy`
- notes over a screenshot: use `color: "purple"`, `font: "script"`, size 44-56

### InkStroke (alias Sketch): free stroke
- props: `points` ([[x, y], ...] canvas fractions, smoothed through), or `d` (SVG path in design px), or `strokes` (list of either, drawn in order); `closed`, `smooth` (true), `width` (4), `wobble` (1 = hand jitter), `color`

### Icon (sketched icons)
- props: `icon`, `x`, `y` (center), `size` (150), `color` (white; `dollar` defaults green), `accent` (color for accent strokes: output neurons, server LEDs, GPU text), `width` (4), `label`, `labelSize` (34), `labelColor`, `labelSide` (`bottom`, `top`, `left`, `right`)
- icons: `neural-net` (alias `nn`, `brain`, `model`), `server` (`servers`, `server-stack`), `user` (`avatar`, `person`), `database` (`db`), `gpu` (`chip`, `cpu`), `dollar` (`money`, `coin`), `cloud`, `document` (`doc`, `file`), `bolt` (`fast`), `lock`, `clock` (`latency`, `time`), `chat` (`prompt`, `message`)
- refs: icon square; `part: "label"`, `part: "all"`

### Loop (circle-around)
Overshooting hand-drawn ellipse around a ref (starts upper-left, goes ~1.1 turns, slight spiral).
- props: ref, `pad` (12), `turns` (1.1), `shape` (`ellipse`, or `box` = rounded rectangle), `color` (`purple`), `width` (4)

### Underline
- props: ref, `style` (`single`, `double`, `wavy`), `offset` (8 px below), `extend` (0.05 of width past each end), `color` (`purple`), `width`

### Bracket
Curly (or square) bracket along one side of a ref, with an optional handwritten label beyond its tip.
- props: ref, `side` (`left`, `right`, `top`, `bottom`), `kind` (`category` = yellow, `tradeoff` = purple, `tradeoff-b` = blue), `color` (overrides kind), `style` (`curly`, `square`), `depth` (28), `gap` (16), `overhang` (4), `label` (`\n` allowed), `labelSize` (36), `labelColor`
- trade-offs: put a `tradeoff` (purple) bracket on one side of the comparison and a `tradeoff-b` (blue) on the other.

### CrossOut (red)
- props: ref, `style` (`x` default, `strike` = one slanted line, `double`, `scribble`), `pad` (6), `width` (5), `color` (`red`)

### HatchZone (red diagonal hatch = inefficiency / waste)
- props: ref or `box`, `spacing` (18), `angle` (45), `outline` (true), `fill` (0.07 opacity tint), `label`, `labelSide` (`top`, `bottom`, `center`), `labelSize` (34), `width` (3.5 outline), `hatchWidth` (2.4), `pad` (0)
- refs: the zone; `part: "label"`

### Arrow (hand-drawn connector, yellow = cross-panel)
- props: `from`, `to` (refs: id string, `[x, y]`, or `{target, region|line|bar|series|index|point|part}`), `fromSide`/`toSide` (`left`, `right`, `top`, `bottom`: leave/enter from that edge's middle; default: the edge facing the curve), `bend` (0.18; negative bends the other way), `head` (22), `gap` (14 px off the boxes), `fromGap`, `double` (head at both ends), `label`, `labelSize` (32), `labelColor`, `color` (`yellow`; use `white` for flow arrows inside one diagram)

### Panel (hand-drawn frame)
- props: `box` ([x, y, w, h]), `radius` (18), `title` (handwritten, top-left inside), `titleSize` (34), `titleColor`, `width` (3.4), `color` (`white`)

### RedPointer (bold solid red arrow)
A thick solid #FF2A2A vector arrow that snaps in toward a target (overshoot), pokes twice, holds, and retreats.
- props: ref (including Chart3D `point: [x, y, z]`, tracked live), `from` (`auto`, `left`, `right`, `top`, `bottom`, `top-left`, `top-right`, `bottom-left`, `bottom-right`, or degrees: the side the tail sits on), `length` (150), `size` (1), `hold` (1.2, clamped 0.8-1.5), `gap` (6), `label` (white handwriting at the tail), `labelSize` (32)
- actions: `point {hold?, from?, + ref keys to aim somewhere else}` (0.28 s snap; total = 0.28 + hold + 0.26 out). Use one `point` per mention; a pointer can point several times. `exit` (0.25) cuts a hold short.
- never auto-enters: always give it a `point` beat at the exact word.

### Metric (handwritten number)
- props: `value` ("$15", "120 ms", "89.4%"), `label` (small caption under the value), `x`, `y` (center), `size` (120), `tone` (`gain` = green, `loss` = red, default white), `color`, `labelSize` (34), `align` (`center`), `strikeSide` (`right`)
- actions: `write`/`draw` (writes value then label), `set {value, tone?|color?, dur: 1.0}` (counts when both are numbers with the same unit, flashes), `strike {to, side: right|below|left, tone?, color?, size?, dur: 0.9}` (red strike through the current value, old value greys, the new value is written in green beside it: the canonical "price drop")
- refs: the value; `part: "label"`, `part: "new"` (the struck-to value)
- leave room on the `strikeSide` for the new value (about 0.35 x size gap + its width).

### BarChart (hand-drawn)
- props: `box` ([0.12, 0.2, 0.76, 0.66]), `bars` ([{`label`, `value`, `display`? (text shown instead of the formatted value), `tone`? (`gain`/`loss`), `color`?}]), `max` (auto), `prefix`, `suffix`, `decimals`, `title`, `titleSize` (40), `labelSize` (30), `valueSize` (32), `values` (true), `fill` (0.16 tint), `axisColor`
- actions: `draw` (axes, then each bar outline rises with its fill, label, value), `set {bar, value, tone?|color?, dur: 0.9}` (bar grows/shrinks, value counts)
- refs: `bar` (+ `part: "value"|"label"`), `region` of the box

### LineChart (hand-drawn)
- props: `box`, `series` ([{`name`, `color`, `values`: [y, ...] or [[xIndex, y], ...], `width`}]), `labels` (x labels), `yMin`, `yMax` (auto), `prefix`, `suffix`, `decimals`, `title`, `titleSize` (40), `labelSize` (26), `smooth` (true), `dots` (true), `yTicks` (3; 0 = none), `endLabels` (true: series name at the line end; space is reserved automatically)
- actions: `draw` (axes, tick labels, then each series line with dots popping as the pen passes, then its name)
- refs: `series` (+ `index` n or [a, b]), `part: "label", index: n` (x label), `region` (plot area)

### Screenshot (external chart / news / benchmark image + telestration)
- props: `src` (an **absolute local path** to a .png/.jpg/.webp/.gif, served by the renderer's `/@file/` route; a path relative to the spec file or an http(s)/data URL also works), `source` (shown as "source: ..." under the image), `mode` (`full` = fills the canvas, `dock` = lower half so you can draw graphs above it), `box` (custom placement, image is fitted inside), `radius` (10)
- actions: `enter` (0.7 rise + de-blur), `exit` (0.45), `spotlight {region: [x, y, w, h] of the image, level: 0.62}` (0.5: darkens everything else, so neon ink pops), `unspotlight` (0.45), `dim`, `undim`, `pulse`
- refs: `region` in image fractions; `part: "source"`
- Telestration recipe: `spotlight` the part being discussed, `Loop` it (purple), write a `script` note next to it, `Underline` the numbers, `RedPointer` the exact cell, `CrossOut` the old value, green `Loop` + note on the better one. In `dock` mode, draw a BarChart/LineChart/Metric above and connect with yellow `Arrow`s from image regions to the drawn graph.

### CodeSnippet (dark panel, handwritten highlights)
- props: `code` (string with `\n`, or array of lines), `title` (file name), `box` ([x, y, w] or [x, y, w, minH]; height follows the lines), `fontSize` (26), `lineNumbers` (true), `startLine` (1)
- actions: `enter` (panel fades in, lines wipe in one by one; `lineDur` 0.16, `stagger` 0.1), `mark {line, style, color?, note?, noteSide?, noteGap?, noteSize?, noteColor?, dur?}` draws ink on a line: `style` = `underline` (default), `box` (tight rounded box), `loop`, `bracket` (`side`, `kind`), `cross` (red); `note` writes a handwritten comment beside it (`noteSide` `right`). `exit`, `dim`, `pulse`.
- refs: `line`

### Chart3D (three.js wireframe 3D data module)
Dark wireframe cube (#222222 grid walls that always sit behind the data, white handwritten axis labels), glowing 3D polylines (hot core + two additive halos) with sphere or cross vertex markers, camera orbits, and a seamless dolly-zoom from perspective into a true orthographic top/front/side projection.
- props: `box` ([0.06, 0.1, 0.88, 0.84]), `axes` ({`x`|`y`|`z`: {`label`, `min`, `max`, `ticks` (5), `prefix`, `suffix`, `decimals`}}; y is vertical, z is depth), `series` ([{`name`, `color`, `points`: [[x, y, z], ...] in data units, `marker`: `sphere`|`cross`, `width`}]), `camera` ({`azimuth` (35), `elevation` (22), `ortho`}), `zoom` (1), `grid` (5), `fov` (32), `autoDraw` (true), `thickness` (1)
- actions:
  - `enter` (1.0: fade in, grid reveals; with `autoDraw` and no `drawSeries` beats, the series draw one after another)
  - `drawSeries {series: index|name|"all", stagger: 0.5}` (1.4 per series: the line grows, markers pop as it passes, the name appears at its end)
  - `orbit {azimuth?, elevation?, zoom?, perspective?}` (1.8: smooth camera interpolation)
  - `view {mode: "top"|"front"|"side"|"perspective", azimuth?, elevation?, zoom?, ortho?: true}` (1.6: rotates to the preset while dolly-zooming into an orthographic projection; `perspective` goes back)
  - `highlightSeries {series, level: 0.18}` / `unhighlightSeries` (0.5), `exit`, `dim`
- refs: `point: [x, y, z]`, `series` + `index`, `region`
- Camera tip: azimuth is the camera's angle around the vertical axis (0 = looking from +z, 90 = from +x). If two variables rise together (e.g. cost and latency), view from an azimuth where that diagonal runs across the screen (e.g. -40), not toward the camera. `front` shows x/y, `side` shows z/y, `top` shows x/z.

## Authoring rules of thumb

- One idea per Insert; 3-8 ink marks. Time every `draw` to its spoken keyword; give long marks a `dur` that ends with the phrase.
- Over screenshots: `spotlight` first (level 0.6-0.75) so neon ink reads; keep notes in purple `script`, numbers struck in red, the better number in green.
- Layout in fractions: keep a ~0.05 margin; Title occupies the top 0.15 (landscape) / 0.1 (portrait); in 9:16 keep the bottom ~0.15 free for captions.
- Pointers last 0.8-1.5 s: one `point` per mention, never a pointer that stays.
- Never mix meanings: green only for gains/money, red only for cross-outs/waste/pointers, yellow only for categories and cross-panel connectors.

## Example 1: telestrating a benchmark screenshot (16:9)

```json
{
  "id": "example-benchmark-telestration",
  "look": "neon-telestrator",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 11.0,
  "concepts": {},
  "scene": {
    "elements": [
      {"id": "shot", "primitive": "Screenshot", "props": {"src": "media/benchmark-leaderboard.png", "source": "evalboard.example", "mode": "full"}},
      {"id": "loopNew", "primitive": "Loop", "props": {"target": "shot", "region": [0.085, 0.44, 0.115, 0.095]}},
      {"id": "noteNew", "primitive": "InkText", "props": {"text": "new model", "target": "loopNew", "side": "right", "gap": 8, "dy": -2, "size": 44, "color": "purple", "font": "script"}},
      {"id": "ulScores", "primitive": "Underline", "props": {"target": "shot", "region": [0.33, 0.455, 0.215, 0.055], "style": "single"}},
      {"id": "yay", "primitive": "InkText", "props": {"text": "yay!", "target": "shot", "region": [0.33, 0.455, 0.215, 0.055], "side": "right", "gap": 26, "dy": 46, "size": 52, "color": "purple", "font": "script"}},
      {"id": "ptr", "primitive": "RedPointer", "props": {"target": "shot", "region": [0.333, 0.455, 0.03, 0.055], "from": "bottom-left", "hold": 1.2}},
      {"id": "xOld", "primitive": "CrossOut", "props": {"target": "shot", "region": [0.762, 0.575, 0.048, 0.055], "style": "x"}},
      {"id": "loopPrice", "primitive": "Loop", "props": {"target": "shot", "region": [0.762, 0.458, 0.042, 0.05], "color": "green", "pad": 6}},
      {"id": "cheaper", "primitive": "InkText", "props": {"text": "6x cheaper", "target": "shot", "region": [0.762, 0.458, 0.042, 0.05], "side": "right", "gap": 50, "size": 46, "color": "green", "font": "script"}},
      {"id": "cat", "primitive": "Bracket", "props": {"target": "shot", "region": [0.325, 0.36, 0.38, 0.04], "side": "top", "kind": "category", "label": "accuracy", "gap": 10, "depth": 22}}
    ]
  },
  "beats": [
    {"at": 0.2, "action": "enter", "target": "shot"},
    {"at": 1.1, "action": "spotlight", "target": "shot", "args": {"region": [0.02, 0.36, 0.96, 0.27], "level": 0.74}},
    {"at": 1.4, "action": "draw", "target": "loopNew"},
    {"at": 2.1, "action": "write", "target": "noteNew"},
    {"at": 3.3, "action": "draw", "target": "cat"},
    {"at": 4.3, "action": "draw", "target": "ulScores"},
    {"at": 5.0, "action": "write", "target": "yay"},
    {"at": 5.4, "action": "point", "target": "ptr"},
    {"at": 7.2, "action": "draw", "target": "xOld"},
    {"at": 7.9, "action": "draw", "target": "loopPrice"},
    {"at": 8.6, "action": "write", "target": "cheaper"}
  ]
}
```

## Example 2: 3D trade-off with orbit, pointer and orthographic front view (16:9)

```json
{
  "id": "example-model-tradeoff-3d",
  "look": "neon-telestrator",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 13.0,
  "concepts": {},
  "scene": {
    "title": "Cost vs accuracy vs latency",
    "elements": [
      { "id": "chart", "primitive": "Chart3D", "props": {
          "box": [0.04, 0.15, 0.92, 0.83],
          "axes": {
            "x": { "label": "cost ($/1M)", "min": 0, "max": 20, "ticks": 4, "prefix": "$" },
            "y": { "label": "accuracy", "min": 60, "max": 95, "ticks": 5, "suffix": "%" },
            "z": { "label": "latency (s)", "min": 0, "max": 10, "ticks": 5, "suffix": "s" }
          },
          "series": [
            { "name": "Orion family", "color": "purple", "marker": "sphere", "points": [[1, 68, 1.0], [3, 79, 2.6], [6, 86, 4.4], [10, 89.4, 6.5]] },
            { "name": "Kestrel family", "color": "blue", "marker": "cross", "points": [[4, 70, 2.0], [9, 77, 4.5], [14, 82, 7.0], [19, 84.7, 9.5]] }
          ],
          "camera": { "azimuth": -40, "elevation": 18 }
      } },
      { "id": "ptr", "primitive": "RedPointer", "props": { "target": "chart", "point": [10, 89.4, 6.5], "from": "top-left", "label": "89.4%" } },
      { "id": "sweet", "primitive": "Loop", "props": { "target": "chart", "point": [3, 79, 2.6], "pad": 30, "color": "green" } },
      { "id": "sweetNote", "primitive": "InkText", "props": { "text": "sweet spot", "target": "chart", "point": [3, 79, 2.6], "side": "left", "gap": 64, "size": 44, "color": "green", "font": "script" } }
    ]
  },
  "beats": [
    { "at": 0.4, "action": "enter", "target": "chart" },
    { "at": 1.2, "action": "drawSeries", "target": "chart", "args": { "series": 0, "dur": 1.6 } },
    { "at": 2.6, "action": "drawSeries", "target": "chart", "args": { "series": 1, "dur": 1.6 } },
    { "at": 4.4, "action": "orbit", "target": "chart", "args": { "azimuth": -62, "elevation": 26, "dur": 2.2 } },
    { "at": 5.2, "action": "point", "target": "ptr", "args": { "hold": 1.4 } },
    { "at": 7.4, "action": "view", "target": "chart", "args": { "mode": "front", "dur": 1.8 } },
    { "at": 9.6, "action": "draw", "target": "sweet" },
    { "at": 10.3, "action": "write", "target": "sweetNote" }
  ]
}
```

More in `examples/`: `price-drop-docked.json` (docked news chart, hand-drawn bars, struck price, yellow cross-panel arrows), `gpu-cost-vertical.json` (9:16: icons, hatch zone, pointer, code fix, price strike) and `batching-tradeoff-code.json` (code marks, line chart, purple/blue trade-off brackets). Reference frames rendered from them are in `reference/`.
