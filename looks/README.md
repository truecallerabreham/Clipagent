# Looks

## The Looks

| Look | Feel | Scene vocabulary |
|---|---|---|
| `architecture-flow` | dark system-design explainer: service cards, packets, token pills | [PRIMITIVES.md](architecture-flow/PRIMITIVES.md) |
| `neon-telestrator` | black canvas, neon stylus ink over screenshots, 3D plots | [PRIMITIVES.md](neon-telestrator/PRIMITIVES.md) |
| `math-vector` | 3Blue1Brown style: LaTeX, draw-on, morphs, planes | [PRIMITIVES.md](math-vector/PRIMITIVES.md) |
| `whiteboard-saas` | white whiteboard, drawing hand, kinetic type, UI annotation | [PRIMITIVES.md](whiteboard-saas/PRIMITIVES.md) |
| `stickman-story` | line-art stickman scenes, macOS walkthroughs | [PRIMITIVES.md](stickman-story/PRIMITIVES.md) |

A **Look** is the single production style of a Session's video (see `GLOSSARY.md`): how Inserts look and move, plus how the screen recording is framed, the captions, chapter cards, transitions and sound. Each folder here is one Look. `_runtime/` is the shared HTML player every HTML Look runs in.

An Insert is a resolved spec (Contract 2 in `docs/design.md`): a `scene` built from the Look's **Primitives** and a list of **Beats** (`{at, action, target, args}`) timed to spoken words. The engine renders it frame by frame in headless Chromium.

## Folder contract

```
looks/<look-id>/
  look.json         id, name, description, best_for, dark, accent, canvas, concept_palette, semantic,
                    screen_treatment, captions, chapter_card, sfx, music (+ runtime keys below)
  look.css          tokens, @font-face for the vendored fonts, Primitive styles
  primitives.js     registers the Look's Primitives (and its layout) with the runtime
  PRIMITIVES.md     the scene vocabulary for the agent: props, Beat actions, defaults, examples
  examples/*.json   complete Insert specs (tests + reference frames)
  reference/*.png   frames rendered from the examples (the QA self-check compares against them)
  assets/           fonts (OFL only, with license files), icons/art (original or open-licensed, with license)
  sfx/              optional audio; the engine synthesizes the names used in look.json "sfx"
```

Runtime keys in `look.json` read by `_runtime/runtime.js`:

| key | meaning |
|---|---|
| `layout` | name passed to `CA.registerLayout` (places nodes by role) |
| `design_short_side` / `design_short_side_portrait` | design units: the canvas short side in design px (default 1080). Smaller = everything bigger |
| `scene_shortcuts` | e.g. `{"title": "SectionTitle", "hook": "HookQuestion"}`: `scene.title` becomes an element with id `title` |
| `tokens` | named colors usable in args (`"alert"`, `"ok"`, ...) |
| `semantic` | lowercase concept name -> Concept Color (spec `concepts` override it) |
| `runtime.scripts` | extra scripts loaded before `primitives.js` (paths relative to the Look) |
| `runtime.preload_fonts` | CSS font shorthands awaited before the scene is built |

## The HTML runtime (`_runtime/`)

`player.html?spec=<url>` loads the spec, then `../<look>/look.json`, `look.css`, the extra scripts, `primitives.js`, waits for fonts, builds the scene and exposes:

```js
window.clipagent = { ready: Promise<void>, duration: number, seek(t): void }
```

`seek(t)` is a pure function of `t`: all Beats are compiled into tracks at build time, so frames can be rendered in any order, in parallel, and backwards. No CSS animations or transitions (disabled globally), no `requestAnimationFrame` clocks, no unseeded randomness. Vendored libraries live in `_runtime/vendor/` with their licenses (flubber, MIT); nothing is fetched from the network at render time.

Preview in a browser (manual only): serve the repo root (`python -m http.server`) and open `/looks/_runtime/player.html?spec=/looks/architecture-flow/examples/jwt-auth-flow.json&t=5` (or `&play=1` for real-time playback).

### Shared helpers (`window.CA`)

Reuse these in every Look instead of re-implementing them:

| helper | signature | use |
|---|---|---|
| easing | `CA.ease.{smooth, inOut, out, in, outBack, linear}`, `CA.cubicBezier(x1,y1,x2,y2)`, `CA.getEase(nameOrFnOrArray)` | smooth = Manim-style ease-in-out |
| progress | `CA.prog(t, start, dur, ease) -> 0..1`, `CA.bump(t, start, dur) -> 0..1..0` | windows and pulses |
| keyframe track | `new CA.Track(initial).to(at, value, dur, ease).set(at, value)`, `.value(t)`, `.cancelAfter(t)` | numbers, arrays and `#hex` colors interpolate; transitions start from the live value, so interruptions are smooth |
| discrete events | `new CA.Events().add(at, data)`, `.last(t)` | screen states, text versions |
| seeded RNG | `CA.rng(seedOrString) -> () => [0,1)`, `CA.noise(seed, i)`, `CA.hashStr(s)` | flicker, jitter, LEDs (use `floor(t * rate)` as `i`) |
| DOM | `CA.el(tag, attrs, parent, html)`, `CA.svgEl(tag, attrs, parent)`, `CA.css(el, prop, v)`, `CA.attr(el, name, v)`, `CA.text(el, s)` | `css/attr/text` skip unchanged writes |
| colors | `CA.mixColor(a, b, p)`, `CA.rgba(hex, a)`, `CA.hexToRgb`, `CA.lerpValue` | |
| path LUT | `CA.PathLUT.fromPath(dOrPathEl, step)`, `.fromPoints(pts)`, `.at(s) -> {x,y,angle}`, `.atFrac(p)`, `.partialD(s0, s1)`, `.reversed()`, `.length` | moving things along paths; `partialD` draws dashed lines on |
| draw-on | `CA.drawOn(pathEl, p, len?)` | progressive stroke reveal (getTotalLength + dashoffset) |
| morph | `CA.morph(fromD, toD, opts) -> (p) => d` | flubber path interpolation (cached) |
| marching ants | `CA.marchingAnts(el, t, speed)` | animated dashed boxes |
| routing | `CA.route(boxA, boxB, {route: 'elbow'|'curve'|'straight', fromSide, toSide, offset, mid, radius}) -> {d, pts, p0, p1}`, `CA.roundedPolyline(pts, r)`, `CA.box(cx, cy, w, h)`, `CA.edgePoint(box, side, off)` | connectors |
| particles | `new CA.SpeedProfile(speed).change(at, speed, ramp)`, `.distance(t0, t1)`; `CA.streamPositions(D, Dstop, spacing, L) -> [{s, k}]` | dot streams whose speed changes stay continuous and seekable |
| text reveal | `CA.splitWords(el, text, {colorFor, emphasisColor}) -> spans`, `CA.revealWords(spans, localT, {stagger, wordDur, blur, rise, ease})`, `CA.revealDuration(n, opts)` | word-by-word blur reveal; `*emphasis*`, Concept Colors |
| counters | `CA.counter(from, to, p, {decimals, prefix, suffix, sep})`, `CA.formatNumber(v, opts)`, `CA.parseNumber("1,240 ms")` | |
| primitives | `class X extends CA.Primitive`, `CA.register(name, X)`, `CA.registerLayout(name, fn(scene))` | see below |

### Writing a Primitive

```js
class Gauge extends CA.Primitive {
  static isNode = true;                       // placed by the layout
  static defaults = { value: 0, label: '' };  // merged with def.props -> this.props
  static actions = { set: { dur: 0.8, ease: 'smooth' } };  // + inherited enter/exit/dim/highlight/...
  build() { /* create DOM under this.root (absolutely positioned) */ }
  afterLayout() { /* every node is placed: compute geometry that depends on other nodes */ }
  a_set(at, dur, ease, args) { this.valueT.to(at, args.value, dur, ease); }  // compile one Beat
  render(t) { super.render(t); /* write styles for time t only */ }
}
CA.register('Gauge', Gauge);
```

Build order: build -> measure -> layout -> afterLayout -> compile beats in time order (`a_<action>`) -> `seek`. Beats are dispatched in time order, so an action can query the state other elements will have at that time (e.g. `pill.posAt(at)`). Elements created during compile use `scene.spawn(def)`. Layers (bottom to top): `bg`, `links` (SVG), `nodes`, `fx` (SVG: boxes, glyphs, particles), `pills`, `text`. Design units: the canvas short side is `design_short_side` px; the stage is zoomed to the real size.

## Adding a Look

1. Copy `architecture-flow/` to `looks/<new-id>/`, keep the file names.
2. Rewrite `look.json` (all keys in the contract above), `look.css` and `primitives.js`. Reuse `CA` helpers; keep every animation a function of `t`.
3. Vendor fonts (OFL only) and art into `assets/` with license files. No network URLs.
4. Write `PRIMITIVES.md` for an AI author: every Primitive's props, actions with args and default durations, and two complete example specs.
5. Add at least three `examples/*.json` (one 9:16), render them, look at the frames, iterate, then save the best frames to `reference/`.

## Preview / render

From `engine/`:

```bash
# all frames (out/00001.png = t 0, 1-based, 5 digits), 2 parallel pages by default
uv run python -m clipagent.inserts.html_render ../looks/architecture-flow/examples/jwt-auth-flow.json /tmp/out --workers 4
# stills only (reference frames, QA)
uv run python -m clipagent.inserts.html_render ../looks/architecture-flow/examples/jwt-auth-flow.json /tmp/out --still 2.5 9.0
# to mp4
ffmpeg -framerate 30 -i /tmp/out/%05d.png -c:v libx264 -pix_fmt yuv420p -crf 18 /tmp/out.mp4
```

Python API (`clipagent.inserts.html_render`): `render_insert(spec_path, out_dir, workers=2)`, `render_stills(spec_path, times, out_dir)`, and `open_page(spec_path)` (context manager yielding a ready sync Playwright page; call `page.evaluate("t => window.clipagent.seek(t)", t)`). Set `CLIPAGENT_LOOKS_DIR` to render Looks from another folder. Chromium: Google Chrome if installed, else Playwright's bundled Chromium (`uv run playwright install chromium`). Rendering uses software-raster Chrome flags so a frame comes out the same whether it is reached forwards or backwards (in tests: byte-identical, apart from rare 1-level antialiasing differences on rotating spinners).
