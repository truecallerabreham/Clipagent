# whiteboard-saas: Primitives

Scene vocabulary for the **whiteboard-saas** Look (whiteboard sketch and annotated SaaS explainer). You, the agent, write the `scene` and `beats` of an Insert spec (Contract 2 in `docs/design.md`); the runtime builds and animates them. Unknown primitives, actions, parts or art names raise an error that lists the valid choices.

Use it for: SaaS walkthroughs, pricing and onboarding, startup/business ideas, growth and marketing concepts, simple flows and checklists, non-technical audiences.

The look in one paragraph: a pure white board. A cutout hand holding a marker draws line-art illustrations, diagrams and handwritten notes stroke by stroke (its tip is locked to the leading edge of the active stroke), then colors them in with an angled wipe. Takeaways are bold geometric sans (#111111) with one operative keyword in electric purple (#5E17EB) or semantic red/green. Product UI is shown as clean SaaS cards, annotated with marching-ants boxes, dashed hand-drawn arrows, pulsing `>>>` chevrons, dark pill badges and an oversized pointing hand. Chapters are 2 s black cards.

## Spec shape

```jsonc
{
  "look": "whiteboard-saas", "engine": "html", "size": [1920, 1080], "fps": 30, "duration": 10.0,
  "concepts": { "pro plan": "#5E17EB" },        // Concept Colors (text matching a concept is colored)
  "scene": {
    "title": "From *idea* to launch",           // optional: SketchText (id "title"), handwritten, top center, underlined
    "hand": { "skin": "light", "sleeve": "#2A2A31", "cuff": "#5E17EB", "scale": 1.0 },   // optional, see "The hand"
    "elements": [ { "id": "bulb", "primitive": "HandDraw", "props": { "art": "lightbulb", "x": 0.25, "y": 0.55 } } ]
  },
  "beats": [ { "at": 1.2, "action": "draw", "target": "bulb", "args": { "dur": 1.6 } } ]
}
```

- `at` is seconds from the Insert start (the engine resolves word ids to seconds). Beats may be in any order.
- `target` is an element id, a list of ids, or `"scene"` (`focus {ids, level}` / `unfocus`).
- `args.dur` overrides any action's duration; `args.ease` overrides easing (`smooth`, `inOut`, `out`, `in`, `outBack`, `linear`, or `[x1,y1,x2,y2]`).
- `*word*` in any text marks the operative keyword (accent purple, or the element's `emphasis` color).
- Colors accept `#hex`, a concept name, or a token: `accent`/`purple` #5E17EB, `ink`/`black` #111111, `red`/`alert` #EF4444, `green`/`ok` #16A34A, `yellow` #FACC15, `blue` #3B82F6, `orange` #F97316, `gray`, `white`, `dark` #1E1E1E.
- Sizes: numbers between -1 and 1 are fractions of the canvas (width for x/width, height for y/height); larger numbers are design px. The canvas short side is 1080 design px (16:9 = 1920x1080, 9:16 = 1080x1920).

### Placement

Placed elements (HandDraw, Icon, HandPlace, SketchText, KineticText, UIMock, Checklist, Diagram) take one of:
- `"x": 0.25, "y": 0.55`: center of the element as canvas fractions (only one given = the other is centered).
- `"place"`: `center`, `left`, `right`, `far-left`, `far-right`, `top`, `bottom`, `top-left`, `top-right`, `bottom-left`, `bottom-right`.
- nothing: auto flow. 16:9 lays unplaced elements out in a centered row, 9:16 in a centered column, below the title.
- `"dx"`, `"dy"`: nudge in design px after placement.

Annotations (Arrow, Chevrons, MarchingBox, PillLabel, PointerHand) attach to **references** instead:
- `"pro"`: an element's box; `"pro.button"`: a named **part** of an element (see UIMock, Diagram, Checklist);
- `[0.5, 0.4]` or `{"x": 0.5, "y": 0.4}`: a point; `{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.25}`: a region (x/y = top-left).

### Entrances (auto-enter)

An element without an entrance beat (`enter`, `draw`, `write`, `place`, `reveal`) enters automatically, **one after another in element order**, each starting when the previous one has finished (the title first). Annotations also wait for their targets. Set `props.enterAt` to pin an auto entrance, or `props.auto: false` to keep an element hidden until a beat enters it. For narration sync, write explicit entrance beats on the spoken keyword and give them a `dur` that fits the sentence.

### The hand

One shared marker hand draws everything that is drawn (HandDraw, Icon, SketchText, Checklist, Diagram, UIMock `draw` entrance, and Arrow/MarchingBox with `hand: true`). Its tip follows the active stroke, it glides between drawings that are less than ~1.1 s apart, and slides off-screen to the lower right otherwise. The marker tip takes the current ink color (including fill colors during the color wipe). Two things are drawn at once only if you overlap their beats; the hand follows the most recent one, so keep drawing beats sequential.
- `scene.hand`: `skin` (`light` default, `medium`, `tan`, `deep`), `sleeve` (#2A2A31), `cuff` (accent), `scale` (1.0), `enabled` (false = no hand anywhere; strokes still draw on).
- Per element: `"hand": false` draws without the hand.

## Generic actions (all placed elements)

| action | args | default dur | effect |
|---|---|---|---|
| `enter` | | per primitive | the element's entrance (draw / write / pop) |
| `exit` | | 0.4 | fade out |
| `dim` / `undim` | `level` (0.25) | 0.5 | fade to 25% / back (compare options without deleting) |
| `highlight` | `color` (accent), `hold` (s) | 0.35 | marching-ants dashed box around the element |
| `alert` | `hold` | 0.35 | red dashed box |
| `unhighlight` | | 0.3 | remove the box |
| `pop` / `pulse` | | 0.5 | quick 1.0 -> 1.08 -> 1.0 scale bounce |

## Primitives

### HandDraw (any SVG illustration, drawn by hand then colored in)
Strokes are drawn in document order with pen lifts between them, then every filled shape is revealed by one angled (24 deg) color wipe while the hand "colors in".
- props: `art` (kit name, see Art kit), or `svg` (a full `<svg viewBox=...>` string; fills/strokes as in any SVG), or `paths` (`[{ "d": "M...", "fill": "yellow", "stroke": "ink", "width": 6 }]` with `viewBox` default `"0 0 200 200"`); `size` (300 design px wide), `label` (handwritten caption written under the art after drawing), `labelSize` (46), `labelColor`, `accent` (recolors the accent slots), `colors` (`{"Y": "#F97316"}` per slot), `ink` (outline color), `strokeWidth` (in viewBox units; default ~3.4% of the size, 4.2-10 px), `fill` (true; false = outline only, color later with `fill`), `angle` (wipe angle, 24), `drawn` (true = appears already drawn, fading in), `hand` (true)
- actions: generic + `draw` / `enter` `{dur}` (auto: ~1.0-2.2 s from stroke length; the last ~26% is the color wipe, then the label), `fill` `{dur: 0.6}` (color wipe now, for `fill: false`)

### Icon (HandDraw preset: smaller, for diagrams and lists)
Same props/actions as HandDraw with `size` 180 and `labelSize` 40. Use any art kit name.

### Art kit (`assets/art/art.js`, original line art, 200x200)
`lightbulb`, `rocket`, `chart`, `user`, `team`, `gear`, `money`, `coins`, `clock`, `cloud`, `database`, `server`, `check`, `cross`, `laptop`, `phone`, `browser`, `target`, `shield`, `lock`, `mail`, `chat`, `star`, `heart`, `document`, `calendar`, `cart`, `megaphone`, `puzzle`, `arrowRight`.
Color slots (override with `colors`): `INK` outline, `A` accent, `A2` accent tint, `Y`/`Y2` yellow, `G`/`G2` green, `R`/`R2` red, `B`/`B2` blue, `GR` light gray, `W` white. A custom `svg` may use the same `{{SLOT}}` placeholders.

### SketchText (handwritten text, written on by the hand)
Caveat handwriting. Words are revealed left to right with the marker riding the reveal edge.
- props: `text` (`\n` = new line, `*keyword*` = accent), `size` (64; title 76), `color` (ink), `weight` (700), `align` (center), `width` (max width, wraps), `emphasis` (accent), `underline` (false; title true: a hand-drawn underline after writing), `underlineColor`, `charTime` (0.055 s per character), `hand`
- actions: generic + `write` / `enter` `{dur}` (auto 0.055 s/char), `underline {word?, color?}` (0.5), `circle {word?, color?}` (0.75: hand-drawn loop around the text or a word), `strike {word?, color: red}` (0.45)

### KineticText (key takeaway, bold geometric sans)
Poppins ExtraBold #111111 on white; words pop in one by one (scale 0.5 -> 1 with overshoot, rise, fade); the `*keyword*` is colored and then highlighted.
- props: `text` (`*keyword*`, `\n` = line break), `size` (92), `emphasis` (`accent` default, or `red` / `green` for semantics, or any color), `highlight` (`underline` default: a swoosh under the keyword; `marker`: highlighter band behind it; `circle`; `none`), `width` (max width; default canvas width minus margins), `align`, `stagger` (0.12 s per word), `weight` (800), `uppercase`
- actions: generic + `reveal` / `enter` `{dur}` (dur spreads the words over that many seconds; time it to the spoken sentence), `emphasize` (0.6: keyword bounces)

### ChapterCard (2 s black chapter card)
Full-canvas #000000 card, centered all-caps Poppins with 0.3em tracking, slow 1.0 -> 1.08 scale-up, small accent rule. When the card spans the whole Insert it is opaque from frame 0 and never fades (the engine's transition handles the cut); otherwise it fades in and out around its `duration`.
- props: `text`, `kicker` (small line above, e.g. "Chapter 2"), `duration` (look.json `chapter_card.duration`, 2.0), `rule` (true), `ruleColor` (accent), `hold` (keep it after `duration`)
- actions: `enter` (0.3), `exit` (0.3). Make a chapter Insert 2.0 s long with one ChapterCard and no beats.

### Arrow (hand-drawn curved arrow, solid or dashed `--->`)
- props: `from`, `to` (references), `bend` (0.22: curvature as a fraction of length; negative bends the other way), `dashed` (false), `color` (ink; accent on transparent overlays), `width` (6), `head` (`end`, `start`, `both`, `none`), `gap` (18 px from the targets), `label` (handwritten text beside the curve), `labelSize` (40), `labelSide` (1 or -1), `hand` (false)
- actions: `enter` / `draw` (0.7: shaft draws on, then the head), `exit`, `pulse` (glow), `dim`

### Chevrons (pulsing `>>>` pointer)
Three chevrons whose brightness wave travels toward the target, with a small nudge.
- props: `target` (reference) + `side` (`left` default: sits left of the target pointing right; `right`, `top`, `bottom`) + `gap` (26), or `x`, `y` + `dir` (`right`, `left`, `up`, `down` or degrees); `count` (3), `size` (46), `color` (accent), `speed` (1.6 pulses/s)
- actions: `enter` (0.35 pop), `exit`

### MarchingBox (dashed marching-ants box around a region)
- props: `target` (reference) + `pad` (14), or `region` `{x, y, w, h}` (fractions, top-left); `radius` (16), `color` (accent), `width` (4.5), `dash` ("16 11"), `speed` (38 px/s), `label` (pill tag on the box), `labelSide` (`top` = top-left, `top-right`, `bottom`, `bottom-right`), `hand` (false)
- actions: `enter` / `draw` (0.6: the box draws on, then marches), `exit`, `pulse` (thicker stroke)

### PillLabel (dark pill badge, optional bi-directional arrows)
#1E1E1E pill, white Poppins text. With `arrows` it becomes a dimension label for an interface zone: `|<--- Sidebar --->|`.
- props: `text`, `target` + `side` (`top`, `bottom`, `left`, `right`, `center`) + `gap` (22), or `x`, `y`; `arrows` (`none`, `both`, `left`, `right`, `vertical`), `span` (arrow extent; default = the target's width, or height for `vertical`), `ticks` (true: end bars), `color` (#1E1E1E), `textColor` (#FFFFFF), `size` (26), `dot` (colored dot before the text), `dx`, `dy`
- actions: `enter` (0.6: pill pops, arrows extend outward), `exit`, `set {text}` (0.4 blur swap), `pulse`

### PointerHand (oversized vector pointing hand)
Slides in from off-screen with the fingertip on the target; `click` scales it to 0.85x and back (fingertip stays put) with a purple ripple.
- props: `target` (reference; fingertip goes to its center) or `x`, `y`; `angle` (-24: degrees, 0 = pointing straight up with the arm going down; negative = arm toward the lower right), `size` (1.25), `skin`, `sleeve`, `ripple` (true), `color` (ripple, accent)
- actions: `enter` (0.6), `move {target | x, y}` (0.6), `click` / `tap` (0.36), `exit` (0.5)
- Pair `click` on the hand with `click {part}` on the UIMock at the same `at` so the button presses too.

### UIMock (clean SaaS UI sketch that can be annotated)
White card, ink outline, hard offset shadow, Poppins. Entrance `draw`: the hand draws the outline, then the content is revealed by the angled wipe.
- props (all variants): `variant`, `width` (440; slider 520), `height` (min height; equal heights for side-by-side cards), `accent`, `entrance` (`draw` default, `pop`), `shadow` (true), `hand`
- variants and their props:
  - `card`: `title`, `subtitle`, `lines` (count of skeleton lines, or an array of strings), `badge`, `button`, `ghost`
  - `pricing`: `plan`, `price`, `period`, `features` [..], `badge`, `button`, `ghost` (outlined button)
  - `slider`: `label`, `value` (0-1), `min`, `max`, `format` ("{v} seats")
  - `button`: `button` (text), `ghost`
  - `browser`: `url`, `items` (sidebar), `active` (index), `title`, `stat`, `bars` (0-1 heights; last is highlighted)
  - `form`: `title`, `fields` [{`label`, `value`}], `button`
- parts (for references like `"pro.button"`): card `title`, `subtitle`, `badge`, `line0..`, `button`; pricing `badge`, `plan`, `price`, `features`, `feature0..`, `button`; slider `label`, `value`, `slider`, `knob`; button `button`; browser `url`, `sidebar`, `item0..`, `main`, `stat`, `chart`; form `title`, `field0..`, `button`
- actions: generic + `enter` / `draw` `{dur: 1.4}`, `click {part: "button"}` (0.4 press), `set {value}` (0.8: slider moves, value counts), `type {field, text}` (0.06 s/char), `select` (0.45: lifts, accent outline), `deselect` (0.35)

### HandPlace (a hand slides in and drops an asset in place)
The asset comes in from off-screen held by an open hand (fingers behind, thumb in front), settles with a small drop, and the hand retracts.
- props: one of `art` / `svg` / `paths` (static art, as HandDraw), `mock` (UIMock props object, e.g. `{"variant": "pricing", ...}`), `note` (sticky note text, `\n` allowed); `size` (320), `from` (`bottom` default, `left`, `right`, `top`), `rotate` (final tilt in degrees), `noteColor` (#FDE68A), `noteSize` (52), `colors`, `accent`
- actions: generic + `place` / `enter` (1.4), `take` (1.1: the hand comes back and carries it off)

### Checklist (items written by hand, ticked on cue)
- props: `items` [..], `title` (optional handwritten heading), `size` (50), `gap` (24), `checkColor` (green), `checked` (indices ticked at the end of the entrance), `strike` (false: strike through items when checked), `dimDone` (false: checked items turn gray), `titleSize`, `hand`
- parts: `item0..`
- actions: generic + `write` / `enter` `{dur}` (auto: box + text per item), `check {item}` (0.45; item = index or text), `checkAll {gap: 0.12}` (0.45 each), `strike {item}` (0.4)

### Diagram (boxes + arrows flow, drawn on)
Each node: hand-drawn rounded box, tint color wipe, optional icon (art kit), handwritten label. Edges are hand-drawn arrows with optional handwritten labels.
- props: `nodes` [`"Label"` or `{id, label, icon, color}`], `edges` (default: a chain in node order; or `[["a","b","label"], ...]` / `[{from, to, label, dashed, color, bend}]`), `direction` (`row` in 16:9, `column` in 9:16, or `grid` with `cols`), `boxW` (270), `boxH` (196), `gap` (140), `labelSize` (42), `iconSize` (100), `color` (box tint base, accent), `fill` (true), `dashed` (false), `bend` (0.12), `hand`
- parts: node ids
- actions: generic + `draw` / `enter` `{dur}` (auto ~1.5 s per node: incoming edge, box, fill, icon, label), `step {node, dur?}` (1.3: draw just that node and its incoming edges; nodes with a `step` beat are skipped by the entrance), `fill {node, color}` (0.5: stronger color wipe to mark the active step), `highlight {node, color, hold}` / `unhighlight {node}` (dashed box on one node; without `node` it boxes the whole diagram)

## Authoring rules of thumb

- One idea per Insert: 1-4 drawn things plus annotations. Leave white space; the board should breathe.
- Anchor every drawing beat to the spoken keyword and give it a `dur` that ends with the phrase. Typical: icon 1.2-1.8 s, title 1-1.5 s, Diagram node 1.2-1.6 s.
- Keep drawing beats sequential (the single hand can only draw one thing). Annotations without the hand (KineticText, PillLabel, Chevrons, MarchingBox, PointerHand, HandPlace) can overlap a drawing.
- Takeaway sentences: KineticText, one `*keyword*`, max ~8 words per line; `emphasis: "red"` for a problem/cost, `"green"` for a win.
- UI walkthroughs: UIMock (or a screen recording in overlay mode) + MarchingBox on the zone being discussed, PillLabel to name zones, Chevrons/Arrow to direct the eye, PointerHand `click` synced to the spoken "click".
- Chapters: a separate 2.0 s Insert with one ChapterCard.
- Transparent overlays (`"transparent": true`, `mode: "overlay"`) work for the annotation primitives over the screen recording; Arrow then defaults to the accent color.

## Example 1: idea to launch (16:9)

```json
{
  "id": "example-idea-to-launch",
  "look": "whiteboard-saas",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 12.0,
  "concepts": {},
  "scene": {
    "title": "From *idea* to launch",
    "elements": [
      { "id": "idea", "primitive": "HandDraw", "props": { "art": "lightbulb", "size": 260, "label": "Idea", "x": 0.2, "y": 0.53 } },
      { "id": "build", "primitive": "HandDraw", "props": { "art": "gear", "size": 260, "label": "Build", "x": 0.5, "y": 0.53 } },
      { "id": "launch", "primitive": "HandDraw", "props": { "art": "rocket", "size": 260, "label": "Launch", "x": 0.8, "y": 0.53 } },
      { "id": "a1", "primitive": "Arrow", "props": { "from": "idea", "to": "build", "bend": -0.25 } },
      { "id": "a2", "primitive": "Arrow", "props": { "from": "build", "to": "launch", "bend": -0.25, "dashed": true } },
      { "id": "note", "primitive": "SketchText", "props": { "text": "ship in weeks, not months", "size": 50, "color": "accent", "x": 0.5, "y": 0.86, "auto": false } }
    ]
  },
  "beats": [
    { "at": 9.4, "action": "write", "target": "note" },
    { "at": 11.0, "action": "underline", "target": "note", "args": { "word": "weeks" } },
    { "at": 11.0, "action": "pop", "target": "launch" }
  ]
}
```

## Example 2: annotated pricing (16:9)

```json
{
  "id": "example-pricing-annotated",
  "look": "whiteboard-saas",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 13.0,
  "concepts": {},
  "scene": {
    "title": "Pick the plan that *scales*",
    "elements": [
      { "id": "starter", "primitive": "UIMock", "props": { "variant": "pricing", "plan": "Starter", "price": "$0", "period": "/month",
          "features": ["1 project", "Community support", "Basic analytics"], "button": "Get started", "ghost": true, "x": 0.25, "y": 0.565, "width": 420, "height": 0.47 } },
      { "id": "pro", "primitive": "UIMock", "props": { "variant": "pricing", "badge": "Most popular", "plan": "Pro", "price": "$29", "period": "/month",
          "features": ["Unlimited projects", "Priority support", "Advanced analytics"], "button": "Start free trial", "x": 0.52, "y": 0.565, "width": 420, "height": 0.47 } },
      { "id": "note", "primitive": "SketchText", "props": { "text": "best value!", "size": 64, "color": "accent", "x": 0.82, "y": 0.36, "auto": false } },
      { "id": "arrow", "primitive": "Arrow", "props": { "from": "note", "to": "pro", "bend": 0.3, "dashed": true, "color": "accent", "auto": false } },
      { "id": "box", "primitive": "MarchingBox", "props": { "target": "pro", "pad": 22, "radius": 30, "auto": false } },
      { "id": "chev", "primitive": "Chevrons", "props": { "target": "pro.button", "side": "right", "gap": 84, "auto": false } },
      { "id": "cursor", "primitive": "PointerHand", "props": { "target": "pro.button", "auto": false } }
    ]
  },
  "beats": [
    { "at": 5.6, "action": "enter", "target": "box" },
    { "at": 5.9, "action": "select", "target": "pro" },
    { "at": 6.6, "action": "write", "target": "note" },
    { "at": 7.6, "action": "enter", "target": "arrow", "args": { "dur": 0.8 } },
    { "at": 8.8, "action": "enter", "target": "chev" },
    { "at": 10.0, "action": "enter", "target": "cursor" },
    { "at": 10.8, "action": "click", "target": "cursor" },
    { "at": 10.85, "action": "click", "target": "pro", "args": { "part": "button" } }
  ]
}
```

More in `examples/`: `launch-checklist-vertical.json` (9:16: Icon, Checklist with ticks, KineticText), `signup-flow-diagram.json` (Diagram with icons and edge labels, node highlight, HandPlace sticky note), `dashboard-tour.json` (browser UIMock with PillLabel zone arrows, labeled MarchingBox, Chevrons, dashed Arrow, PointerHand click), `takeaway-kinetic.json` (KineticText with marker highlight + HandPlace), `chapter-card.json` (2 s chapter card). Reference frames rendered from them are in `reference/`.
