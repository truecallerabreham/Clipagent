# math-vector: Primitives

Scene vocabulary for the **math-vector** Look (3Blue1Brown style programmatic math animation). You, the agent, write the `scene` and `beats` of an Insert spec (Contract 2 in `docs/design.md`); the runtime builds and animates them. The same spec renders with the HTML engine (default, `"engine": "html"`) or with ManimCE (`"engine": "manim"`, see the end of this file).

Use it for: vectors and linear algebra, matrices transforming space, function graphs, calculus, optimization / gradient descent, equations and derivations. Everything is on pure black with a muted cyan grid (#29ABCA at 40%); every label is LaTeX in Computer Modern.

## How it looks and moves (what the runtime guarantees)

- **TeX everywhere.** Every equation, label, axis number and counter is real LaTeX (KaTeX layout, Computer Modern glyph outlines). Write normal TeX: `\vec{v}`, `\hat{\imath}`, `\frac{a}{b}`, `\begin{bmatrix}..\end{bmatrix}`, `\sqrt{}`, `\sum`, `\int`. Macros: `\ihat`, `\jhat`, `\R`, `\N`.
- **Draw-on, never fades.** Entrances stroke the outline glyph by glyph, then fill (Manim `Write` / `DrawBorderThenFill`). Vectors grow from their tail (`GrowArrow`), shapes and graphs stroke on (`Create`), braces grow from their tip outwards, the grid draws on line by line from the axes outwards. `exit` plays the entrance backwards (`Uncreate`/`Unwrite`).
- **Morphs between ideas.** `transform` on a Tex is TransformMatchingTex: glyphs that exist in both versions slide to their new place, the remaining glyphs morph path-to-path into the new ones. `morph` turns any element into any other (equation into a circle, a graph into another graph, a vector into a brace...).
- **Easing** is Manim `smooth` (strong ease-in-out) for every movement.
- **Live geometry.** Braces, dashed projections, counters, labels and tangents track their targets every frame: move a vector or apply a matrix and everything attached follows.
- **Colour semantics.** Concept Colors persist across the Session. Defaults in `look.json`: input = `#FFFF00` (yellow), component A / horizontal / `i hat` = `#83C167` (green), component B / vertical / `j hat` = `#FC6255` (coral red), output / result / sum = `#FF862F` (orange). Put each variable in `concepts` once and colour its TeX substrings with the same name, so the symbol and its shape always match.

## Spec shape

```jsonc
{
  "look": "math-vector", "engine": "html", "size": [1920, 1080], "fps": 30, "duration": 12.0,
  "concepts": { "input vector": "#FFFF00", "sum": "#FF862F" },   // Concept Colors (merged over look.json "semantic")
  "scene": {
    "title": "Adding vectors",                                    // optional: Title (id "title"), top, with underline
    "elements": [ { "id": "plane", "primitive": "NumberPlane", "props": { } } ]
  },
  "beats": [ { "at": 1.2, "action": "enter", "target": "plane" } ]
}
```

- `at` is seconds from the Insert start (the engine resolves word ids to seconds). `target` is an id, a list of ids, or `"scene"` (`focus {ids, level}` / `unfocus`).
- `args.dur` overrides any duration; `args.ease` overrides easing (`smooth`, `inOut`, `out`, `in`, `linear`, `[x1,y1,x2,y2]`).
- **Colors** anywhere (props, args, `colors` maps, `\textcolor{...}` / `\color{...}` inside TeX) accept `#hex`, a concept name (`"sum"`, `"i hat"`), or a token: `input`/`yellow`, `a`/`green`, `b`/`red`, `output`/`orange`, `blue` (#58C4DD), `teal`, `purple`, `pink`, `gold`, `grid`, `white`, `grey`.
- **Entrances:** elements without an explicit `enter` / `write` / `create` beat auto-enter at 0.15 s, 0.14 s apart, in element order. Always time entrances to speech with explicit beats. `props.auto: false` keeps an element hidden until a beat shows it. Targets of `morph` never auto-enter (the morph reveals them).

### Coordinates and placement

- The first `NumberPlane`/`Axes` is the default **plane**. Points written as arrays (`[3, 1]`, `[1, 2, 0.5]`) are **math coordinates** on it. Give `"plane": "<id>"` to use another one.
- **Point references** (vector tails, brace ends, projections, `follow`, `move {to}`): `[x, y]` math coords, `{"x": 0.7, "y": 0.2}` canvas fractions, `"v"` (vector tip / dot centre / element centre), or `"v.tail"`, `"v.mid"`, `"v.tip"`, `"eq.left"`, `"eq.right"`, `"eq.top"`, `"eq.bottom"`, `"eq.ur"`..., `"plane.origin"`, `"brace.label"`.
- **Placing TeX, labels and counters** (pick one): `x`, `y` (canvas fractions of the element centre, default 0.5, 0.5); `pos: [mx, my]` (math coords on the plane); `next_to: {id, side: "right"|"left"|"up"|"down", buff: 30, part?, align?: "left"|"right"}`; `to_edge: "top"|"bottom"|"left"|"right"|"ul"|"ur"|"dl"|"dr"` with `buff` (64). Then `dx`, `dy` nudge in design px. Design units: the canvas short side is 1080 design px (16:9 is 1920 x 1080, 9:16 is 1080 x 1920).

## Generic actions (every Primitive)

| action | args | default dur | effect |
|---|---|---|---|
| `enter` / `write` / `create` | `dur` | 1.0 (Tex: 0.8-2.6 by glyph count; NumberPlane 1.8) | draw-on entrance |
| `exit` | `style: "fade"` | 0.7 | reverse draw (or fade out) |
| `fade_out` | | 0.6 | fade out |
| `move` | `to` (point ref) or `pos` (math) or `x`,`y` (fractions), `anchor` ("center"), `dx`,`dy` | 1.0 | smooth translate (Dot: `pos` or `x` on its graph) |
| `scale` | `by` (1.2) or `to` | 0.8 | scale about the element centre |
| `indicate` / `pulse` | `color` (yellow) | 0.9 | Manim `Indicate`: swell 1.2x and tint |
| `circumscribe` | `color`, `part` (TeX part), `col` (Matrix column), `buff` (14) | 1.5 | a rectangle draws around it and un-draws (passing flash) |
| `highlight` | `color`, `part`, `col`, `hold` (s, optional) | 0.8 | `SurroundingRectangle` draws on and stays |
| `unhighlight` | | 0.6 | rectangle un-draws |
| `dim` / `undim` | `level` (0.25) | 0.5 | |
| `morph` | `to` (element id) | 1.4 | path-interpolate this element into `to` (this one disappears, `to` remains) |

## Primitives

### NumberPlane
Muted cyan grid (#29ABCA, 40%) with fainter half-unit lines and white axes. By default it fills the whole frame (3B1B style) and extends beyond it, so linear maps never reveal an edge.
- props: `x_range` `[min, max, step]` (16:9 default `[-8, 8, 1]`, 9:16 `[-4.5, 4.5, 1]`), `y_range` (16:9 `[-4.5, 4.5, 1]`, 9:16 `[-8, 8, 1]`): the visible region; `x`, `y` (fraction where the centre of the ranges sits, default 0.5, 0.5); `unit` (design px per unit) or `width` / `height` (otherwise fitted); `full` (default true unless you place/size it; `true` forces full-frame); `subdivisions` (2), `opacity` (0.4), `color`, `axis_color`, `numbers` (false), `ticks`, `tips`, `x_label`, `y_label` (TeX), `view: {elev, azim}` (faux 3D, e.g. `{elev: 30, azim: -35}`; `z_range` adds a z axis).
- actions: `enter` (axes first, then grid lines from the centre outwards, 1.8 s), `apply_matrix {matrix: [[a,b],[c,d]] or 3x3, ghost: true, absolute: false}` (2.0 s: every point moves linearly from p to Mp; composes with earlier matrices; leaves a faint grey ghost of the original grid), `reset` (1.5), `orbit {elev, azim}` (2.0, faux-3D camera move), `exit`.
- Vectors, dots, shapes and projections on the plane move with `apply_matrix` (set `transform: false` on one to keep it fixed). Axis numbers hide while a matrix is applied.

### Axes
Same as NumberPlane but no grid, with ticks, numbers and arrow tips, sized to 80% of the canvas unless you give `unit` / `width` / `height` / `x` / `y`. props as NumberPlane plus `number_size` (30), `number_skip` (1), `label_size` (40). Graphs on Axes are clipped to its `y_range`.

### Tex (alias MathTex)
An equation or symbol, written on stroke by stroke.
- props: `tex`, `size` (56 px per em), `color` (white), `colors` (`{"\\vec{a}": "vector a", "x": "input"}`: Manim's `tex_to_color_map`; longest substrings first; control words are never split), `align` (`center`, `left`, `right`: which edge stays put through `transform`), `backdrop` (true: black rounded backing rectangle, use over a full-frame grid), `backdrop_opacity` (0.85), placement props.
- **Parts:** wrap pieces in double braces, `"{{a^2}} + {{b^2}} = {{c^2}}"`, to name them. Parts are matched first by `transform`, and can be addressed by `set_color {part}`, `circumscribe {part}`, `highlight {part}`, Brace `{target, part}`, `next_to {part}`.
- actions: generic +
  - `transform {tex, colors?, size?, align?, match: "none"?, morph: false?}` (1.4): TransformMatchingTex into new TeX at the same anchor. Shared glyphs (same part first, then same symbol in reading order) glide to their new position; the rest morph path to path (`morph: false`: fade out / write in instead). Chain as many as you like.
  - `set_color {part, color}` (0.6)
- Example: `{ "id": "eq", "primitive": "Tex", "props": { "tex": "\\vec{a} + \\vec{b} = \\vec{s}", "size": 64, "pos": [8, 4], "colors": { "\\vec{a}": "green", "\\vec{b}": "red", "\\vec{s}": "orange" } } }`

### Label
Plain text in Computer Modern (`\text{}`), with `$...$` for inline math: `"text": "learning rate $\\eta = 0.08$"`. props: `text` (or `tex`), `size` (42), `color`, `colors`, placement. Actions as Tex (`transform {text}`).

### Title (from `scene.title`, id `title`)
Label at the top edge (size 60) with a thin white underline that draws on from the centre. props: `text`, `size`, `underline` (true).

### Matrix
A bracketed matrix built from `rows`, entries tracked by row/column.
- props: `rows` (`[[1, 1], [0, 1]]`, numbers or TeX strings), `col_colors` (e.g. `["i hat", "j hat"]`: colour columns like the basis vectors they hold), `entry_colors` (2D), `bracket` (`b` square, `p` round, `v` bars), `prefix` (`"A = "`), `suffix`, `size` (52), `backdrop`, placement.
- actions: as Tex, plus `transform {rows, col_colors?}` (entries keep their identity), and `circumscribe {col}` / `highlight {col}` to frame a column.

### Vector (alias Arrow)
Arrow from a tail (default the origin) to tail + `coords`, on the plane.
- props: `coords` (`[3, 1]` or `[x, y, z]`), `from` (tail: math coords or a point ref such as `"a"`, i.e. tip-to-tail), `color` or `concept`, `stroke` (6), `tip` (30 px), `label` (TeX, written after the arrow grows), `label_pos` (`end` beyond the tip; `left` / `right` of the shaft middle, relative to its direction; `mid` above the middle), `label_size` (46), `label_color`, `label_colors`, `transform` (true: follows `apply_matrix`).
- actions: generic + `set {coords}` (1.2: tip moves; attached braces, projections and counters follow), `shift {from}` (1.2: slide the tail to a new point keeping the coords, e.g. `{"from": "a"}` for tip-to-tail addition; the tail then keeps following that point).
- Counter values (`track`): `x`, `y`, `z` (tip as displayed, after the plane's matrix), `dx`, `dy` (components), `length`, `angle` (degrees).

### Dot
- props: `pos` (math coords), or `on` (a graph Shape id) + `x` (rides the curve), or `follow` (point ref); `color`, `radius` (10), `label` (TeX), `label_dir` (`ur`, `ul`, `dr`, `dl`, `up`, `down`, `left`, `right`), `trace` (true: leaves a TracedPath), `trace_color`, `trace_width` (3), `trace_from` (s; default its entrance).
- actions: generic (enter grows from the centre) + `move {x}` (on a graph: slides along the curve) or `move {pos}`, `flash {color}` (0.7: Manim `Flash`, rays burst out).
- Counter values: `x`, `y` (= f(x) on a graph), `slope` (f'(x) on a graph).

### Shape
Geometry drawn on (stroke), then filled if `fill` is set. Coordinates are math coords on the plane (`"space": "screen"` for canvas fractions).
- `kind`:
  - `graph`: `fn` (JS/math expression in `x`: `"0.25*x^4 - 1.2*x^2"`, `sin(x)`, `exp(-x^2)`, `pi`, `e`, `ln`), `x_range` (default the plane's), `samples` (240), `y_clip`
  - `area`: region under `fn` between `x_range` (sweeps in left to right; `color`, `fill_opacity` 0.35)
  - `circle`: `center` (math or point ref), `radius` (math units); `arc`: + `start_angle`, `angle` (degrees)
  - `polygon`: `points`; `rect`: `center`, `width`, `height`; `line`: `from`, `to` (point refs); `curve`: `points` (smooth Catmull-Rom), `closed`
  - `tangent`: `graph` (id), `dot` (id, follows it) or `x`, `length` (3 math units): a live tangent line
- props: `color` (white), `stroke` (4), `fill` (color), `fill_opacity` (0.5), `dashed` (true or `[10, 8]`), `transform` (true).
- actions: generic (`create` = enter) + `set {fn | radius | points | center | ...}` (1.2: the shape interpolates point by point into the new one, e.g. one function graph becoming another).

### DashedProjection
Dashed lines from a point down to the axes (or to another point), drawn on from the point.
- props: `from` (point ref on the plane, e.g. `"v"` for a vector tip), `to` (`"both"`, `"x"`, `"y"`, or a point ref), `color` (white), `opacity` (0.8), `stroke` (2.5), `dash` (`[9, 7]`).

### Brace
Animated curly brace with a TeX label; grows from its tip outwards, then fills; the label writes on. Tracks its ends live.
- props: `from`, `to` (point refs: brace along that segment), `side` (`down` / `up` / `left` / `right`: which way it bulges; default down for horizontal, right for vertical), or `target` (element id) + `side` (`down` default) + `part` (a TeX part) to brace an element's edge; `label` (TeX), `label_size` (44), `label_color`, `color` (white), `buff` (12: gap from the segment), `depth` (26).
- Example: `{ "id": "bx", "primitive": "Brace", "props": { "from": [0, 0], "to": [4, 0], "side": "down", "label": "4" } }`

### NumberCounter (alias Counter)
A DecimalNumber in Computer Modern that counts or tracks a live value.
- props: `track` (`"d.slope"`, `"v.x"`, `"v.length"`, or `{target, value}`), or `value` (static start); `decimals` (2), `prefix` (TeX, e.g. `"x ="`), `suffix` (TeX), `color` / `concept`, `size` (48), `show_sign`; placement props, or `follow` (point ref: the counter rides next to it, e.g. a moving vector tip) with `side` (`ur`) and `offset`; `anchor` (`center`; `"eq"`: `x` is where the prefix ends, so stacked counters line up on their `=`; `"left"`).
- actions: generic + `set {value}` (1.0: counts to the value; only without `track`).

### Morph
The `morph` action as an element, for readability: `{ "id": "m1", "primitive": "Morph", "props": { "from": "eq", "to": "circle" } }` with a beat `{ "action": "play", "target": "m1" }` (1.4). Equivalent to `{ "action": "morph", "target": "eq", "args": { "to": "circle" } }`.

## Authoring rules of thumb (3Blue1Brown feel)

- One idea per Insert. Let things breathe: 1-1.5 s per entrance, 0.3 s between beats on the same element, a still second after the key reveal.
- Anchor beats to the spoken keyword: `enter` a vector when it is named, `apply_matrix` on "transform"/"apply", `transform` an equation on "which means"/"so", `indicate` / `circumscribe` on "this".
- Colour the symbol in the equation exactly like its shape (`concepts` + `colors`). Keep basis vectors green / red, inputs yellow, outputs orange.
- Transition with morphs, not cuts: `transform` the equation into its next form, `morph` the formula into the shape it describes.
- Over a full-frame grid, put equations on a `backdrop`, or on the empty side of the plane (shift the plane with `x`/`y` ranges).
- Prefer `Axes` for function graphs, `NumberPlane` for vectors and transformations.

## Example 1: vector addition with components and braces (16:9)

```json
{
  "id": "example-vector-addition", "look": "math-vector", "engine": "html", "mode": "full",
  "size": [1920, 1080], "transparent": false, "fps": 30, "duration": 13.0,
  "concepts": { "vector a": "#83C167", "vector b": "#FC6255", "sum": "#FF862F" },
  "scene": {
    "elements": [
      { "id": "plane", "primitive": "NumberPlane", "props": { "x_range": [-2.5, 10.5, 1], "y_range": [-1.6, 5.4, 1] } },
      { "id": "a", "primitive": "Vector", "props": { "coords": [3, 1], "concept": "vector a", "label": "\\vec{a}", "label_pos": "right" } },
      { "id": "b", "primitive": "Vector", "props": { "coords": [1, 2], "concept": "vector b", "label": "\\vec{b}", "label_pos": "left" } },
      { "id": "s", "primitive": "Vector", "props": { "coords": [4, 3], "concept": "sum", "label": "\\vec{a}+\\vec{b}", "label_pos": "left",
          "label_colors": { "\\vec{a}": "vector a", "\\vec{b}": "vector b" } } },
      { "id": "proj", "primitive": "DashedProjection", "props": { "from": "s", "to": "both" } },
      { "id": "bx", "primitive": "Brace", "props": { "from": [0, 0], "to": [4, 0], "side": "down", "label": "4" } },
      { "id": "by", "primitive": "Brace", "props": { "from": [0, 0], "to": [0, 3], "side": "left", "label": "3" } },
      { "id": "eq", "primitive": "Tex", "props": { "tex": "\\vec{a} + \\vec{b} = \\vec{s}", "size": 64, "pos": [8.0, 4.1],
          "colors": { "\\vec{a}": "vector a", "\\vec{b}": "vector b", "\\vec{s}": "sum" } } }
    ]
  },
  "beats": [
    { "at": 0.0, "action": "enter", "target": "plane" },
    { "at": 1.4, "action": "enter", "target": "a" },
    { "at": 2.6, "action": "enter", "target": "b" },
    { "at": 3.9, "action": "shift", "target": "b", "args": { "from": "a" } },
    { "at": 5.3, "action": "enter", "target": "s" },
    { "at": 5.6, "action": "write", "target": "eq" },
    { "at": 7.0, "action": "enter", "target": "proj" },
    { "at": 7.5, "action": "enter", "target": "bx" },
    { "at": 7.9, "action": "enter", "target": "by" },
    { "at": 9.4, "action": "transform", "target": "eq", "args": { "dur": 1.6,
        "tex": "\\textcolor{vector a}{\\begin{bmatrix} 3 \\\\ 1 \\end{bmatrix}} + \\textcolor{vector b}{\\begin{bmatrix} 1 \\\\ 2 \\end{bmatrix}} = \\textcolor{sum}{\\begin{bmatrix} 4 \\\\ 3 \\end{bmatrix}}" } },
    { "at": 11.6, "action": "circumscribe", "target": "eq" }
  ]
}
```

## Example 2: gradient descent with live counters (16:9)

```json
{
  "id": "example-gradient-descent", "look": "math-vector", "engine": "html", "mode": "full",
  "size": [1920, 1080], "transparent": false, "fps": 30, "duration": 13.5,
  "concepts": { "input": "#FFFF00", "slope": "#FC6255", "learning rate": "#83C167", "output": "#FF862F" },
  "scene": {
    "elements": [
      { "id": "ax", "primitive": "Axes", "props": { "x_range": [-3, 3, 1], "y_range": [-1, 4.5, 1], "unit": 148, "x": 0.31, "y": 0.52, "x_label": "x", "y_label": "f(x)" } },
      { "id": "f", "primitive": "Shape", "props": { "kind": "graph", "fn": "0.25*x^4 - 1.2*x^2 + 0.6*x + 2", "x_range": [-2.75, 2.42], "color": "blue", "stroke": 5 } },
      { "id": "d", "primitive": "Dot", "props": { "on": "f", "x": 2.3, "color": "input", "radius": 11, "trace": true } },
      { "id": "tan", "primitive": "Shape", "props": { "kind": "tangent", "graph": "f", "dot": "d", "length": 1.6, "color": "slope" } },
      { "id": "rule", "primitive": "Tex", "props": { "tex": "x_{n+1} = x_n - \\eta\\, f'(x_n)", "size": 60, "x": 0.775, "y": 0.22,
          "colors": { "x_{n+1}": "input", "x_n": "input", "\\eta": "learning rate", "f'": "slope" } } },
      { "id": "cx", "primitive": "NumberCounter", "props": { "prefix": "x =", "track": "d.x", "decimals": 3, "size": 52, "x": 0.765, "y": 0.43, "anchor": "eq", "color": "input" } },
      { "id": "cs", "primitive": "NumberCounter", "props": { "prefix": "f'(x) =", "track": "d.slope", "decimals": 3, "size": 52, "x": 0.765, "y": 0.53, "anchor": "eq", "color": "slope" } }
    ]
  },
  "beats": [
    { "at": 0.1, "action": "enter", "target": "ax" },
    { "at": 1.4, "action": "create", "target": "f", "args": { "dur": 1.6 } },
    { "at": 3.0, "action": "enter", "target": "d", "args": { "dur": 0.6 } },
    { "at": 3.3, "action": "write", "target": "rule" },
    { "at": 3.9, "action": "create", "target": "tan", "args": { "dur": 0.7 } },
    { "at": 4.2, "action": "write", "target": ["cx", "cs"] },
    { "at": 5.6, "action": "move", "target": "d", "args": { "x": 1.72, "dur": 1.0 } },
    { "at": 6.9, "action": "move", "target": "d", "args": { "x": 1.595, "dur": 0.8 } },
    { "at": 7.9, "action": "move", "target": "d", "args": { "x": 1.529, "dur": 0.7 } },
    { "at": 10.5, "action": "flash", "target": "d" },
    { "at": 11.2, "action": "transform", "target": "rule", "args": { "tex": "f'(x^*) = 0", "colors": { "x^*": "input", "f'": "slope" } } }
  ]
}
```

More in `examples/`: `vector-addition.json`, `linear-transformation-vertical.json` (9:16: a shear matrix moves the plane, î/ĵ/v ride along, the matrix column is circumscribed, the equation morphs into the column picture) and `gradient-descent.json`. Reference frames rendered from them are in `reference/`.

## Manim engine (optional)

Set `"engine": "manim"` to render the same spec with ManimCE (`looks/math-vector/manim/scene.py`, via `engine/clipagent/inserts/manim_render.py`). It supports the same Primitives and actions; HTML-only details (glyph-by-glyph morph pairing, `orbit`, `view`) degrade to Manim's nearest equivalent. Needs `uv sync --project engine --extra manim` (plus the system cairo/pango development packages to build `pycairo`/`manimpango`) and a LaTeX install for Tex; without LaTeX, TeX falls back to plain `Text`. The HTML engine is the default and needs nothing extra.
