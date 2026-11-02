# architecture-flow: Primitives

Scene vocabulary for the **architecture-flow** Look (dark-mode system architecture and packet-flow explainer). You, the agent, write the `scene` and `beats` of an Insert spec (Contract 2 in `docs/design.md`); the runtime builds and animates them. Everything not listed here is ignored or raises an error that names the valid choices.

Use it for: auth and tokens (JWT, sessions, refresh), request flows, caches and databases, latency and bottlenecks, attacks (replay, interception).

## Spec shape

```jsonc
{
  "look": "architecture-flow", "engine": "html", "size": [1920, 1080], "fps": 30, "duration": 10.0,
  "concepts": { "access token": "#38BDF8" },          // Concept Colors for the Session (merged over look.json "semantic")
  "scene": {
    "title": "How JWT login works",                   // optional: SectionTitle (id "title"), marker font, top
    "hook": "So why does the server never *store* it?",// optional: HookQuestion (id "hook"), bottom, word-by-word blur
    "elements": [ { "id": "phone", "primitive": "Device", "props": { "place": "client" } } ]
  },
  "beats": [ { "at": 1.2, "action": "send", "target": "token", "args": { "to": "api" } } ]
}
```

- `at` is seconds from the Insert start (the engine resolves word ids to seconds). Beats may be in any order.
- `target` is an element id, a list of ids (the beat applies to each), or `"scene"` for scene actions.
- `args.dur` overrides any action's duration; `args.ease` overrides easing (`smooth`, `inOut`, `out`, `in`, `outBack`, `linear`, or `[x1,y1,x2,y2]`).
- Concept Colors: any text (titles, hooks, row values, pill labels, callouts) that matches a concept name gets that color automatically. Pills colour themselves from `concept` or `label`.
- Colors in args/props accept `#hex`, a concept name (`"access token"`), or a token: `alert` (#F43F5E), `ok` (#22C55E), `link`, `white`, `warn`. `"red"` means alert.

### Entrances (auto-enter)

Every element without an explicit `enter` beat enters automatically: the title at 0.05 s, nodes one after another from 0.15 s (0.14 s apart, in element order), Links 0.25 s after both endpoints, Callouts 0.25 s after their target, the hook at 0.6 s. Set `props.enterAt` to move an auto entrance, or `props.auto: false` to keep an element hidden until you `enter` it. TokenPill, PacketStream and Hacker copies never auto-enter. Time entrances to speech by writing explicit `enter` beats.

### Layout: `place` instead of pixels

Nodes (Device, ServiceCard, Database, Hacker, Metric) are placed by role. 16:9 uses three columns (client left third, center, servers right third); 9:16 stacks rows top to bottom (clients, center, servers, stores). Elements sharing a role stack in element order; stores sit at the bottom of their column (lower-left / lower-right corners).

| `place` | 16:9 | 9:16 |
|---|---|---|
| `client`, `client-top`, `client-bottom`, `left` | left column | first row |
| `center`, `gateway`, `middle`, `center-top`, `center-bottom` | middle column | second row |
| `server`, `server-top`, `server-bottom`, `service`, `right` | right column | third row |
| `store`, `store-right` | bottom of right column | last row |
| `store-left` | bottom of left column | last row |
| `store-center`, `attacker` | bottom of middle column | last row (`attacker` alone sits right of center) |

Explicit position instead: `"x": 0.8, "y": 0.3` (fractions of the canvas, element center). Nudge any node with `"dx"`, `"dy"` (design px; the canvas short side is 960 design px). Keep roles simple: a client, one to three servers, one or two stores, optionally a gateway or attacker in the middle. If a column overflows, stores slide sideways next to it rather than overlapping.

## Generic actions (all node Primitives)

| action | args | default dur | effect |
|---|---|---|---|
| `enter` | | 0.6-0.9 | fade + rise + de-blur (Link: stroke draw-on; Hacker: neon flicker) |
| `exit` | | 0.4 | fade out |
| `dim` | `level` (0.25) | 0.5 | dim to 25% opacity instead of deleting (compare workflows) |
| `undim` | | 0.5 | back to full opacity |
| `highlight` | `color` (`white`), `hold` (s, optional auto-off) | 0.35 | marching-ants dashed box around the node |
| `alert` | `hold` | 0.35 | red dashed box + red flash (security alerts, breaches) |
| `unhighlight` | | 0.3 | remove the dashed box |
| `pulse` | `color` | 0.6 | one glow flash |

Scene actions (`"target": "scene"`): `focus` `{ids: [...], level: 0.25}` dims everything except those ids (Links stay lit when both ends are kept; pills are never dimmed); `unfocus` restores all.

## Primitives

### SectionTitle (from `scene.title`, id `title`)
All-caps marker-font title, top center, with a hand-drawn underline (in the title's first Concept Color, else the accent).
- props: `text`, `color` (underline)
- actions: `enter` (0.9: words blur in, underline draws on), `set {text}` (0.8: crossfade to a new title), `exit`

### HookQuestion (from `scene.hook`, id `hook`)
Bottom-center question revealed word by word with a blur. Wrap words in `*asterisks*` to emphasise them (accent color); concept names color automatically.
- props: `text`, `stagger` (0.11 s per word)
- actions: `reveal` / `enter` `{dur}` (dur spreads the words over that many seconds; time it to the spoken sentence), `set {text, dur}`, `exit` (0.45)

### Device (smartphone wireframe; `place` default `client`)
- props: `label` ("Client", shown under the phone), `screen` (initial screen), `app` ("Acme"), `user` (login email), `accent`, `storageLabel` ("Secure storage")
- screens: `login`, `home` (alias `app`), `loading`, `success`, `error` (401), `locked` (session expired), or custom `{ "state": "custom", "title", "subtitle", "lines": [..], "button", "icon", "color" }`. `title`/`subtitle` also override the built-in screens' text.
- actions: generic + `screen {state, title?, subtitle?, lines?, button?, icon?}` (0.45 crossfade), `tap {x?, y?}` (0.55 ripple; defaults to the screen's button; x/y are 0-1 of the screen), `receive {color}` (glow)
- Tokens sent to a Device dock in a "secure storage" tray that slides up inside the screen.

### ServiceCard (`place` default `server`)
Charcoal card (#161618, 12px radius): header icon, marker-font uppercase title, optional subtitle, then key-value rows or server blades.
- props: `title`, `subtitle`, `icon` (see Icons), `accent` (icon tint), `width` (360), `rows`: `[{"k": "alg", "v": "RS256", "color"?}]` or `[["alg","RS256"]]` or `["alg: RS256"]`, `blades` (count of server blades with blinking LEDs), `bladeLabel` ("node")
- actions: generic +
  - `receive {color}` (0.6) glow pulse (sends flash the receiver automatically)
  - `latency {factor: 0.3, spinner: true, streams: true, dependents: [ids]}` (0.6): red outline + glow, spinner in the header, PacketStreams on Links touching this card slow to `factor` (70% slower), `dependents` get spinners too
  - `recover {dependents}` (0.6): undo latency, streams back to full speed
  - `spinner {on: true|false}` (0.3)
  - `setRow {row, value, color?}` (0.6): change a value (numbers count up/down, text blur-swaps), row flashes
  - `highlightRow {row, color?, hold?}` (0.35) / `unhighlightRow {row}`: dashed box on one row
  - `validate` (see Database)
- `row` is a 0-based index or text matching any cell of the row (e.g. `"alice@acme.io"`, `"alg"`).

### Database (`place` default `store`)
Same card style with a table. Rows can be looked up and validated against.
- props: `title`, `subtitle`, `icon` ("database"), `columns` (["key", "user"]), `rows` ([["sid_7f3e", "alice"], ...]), `flex` (column widths, e.g. [1.6, 1]), `width` (auto from column count)
- actions: everything ServiceCard has, plus
  - `lookup {row, color?, hold: 1.4}` (1.0): a scan bar sweeps down to the row, then a dashed box holds on it
  - `insertRow {values: [..]}` (0.6): a new row slides in (space is reserved at build time)
  - `validate {pill, row, result: "match"|"mismatch", hold: 1.6, travel: 0.8, after: "fade"|"stay", side?}`: the pill travels (via a Link from where it is, if one exists) to sit beside the row, an `=` appears, the row gets a dashed box, then `=` morphs into a green check circle (#22C55E) or a red X (mismatch: the pill shakes). Total ≈ travel + 0.45 + 0.45 + hold. With `after: "fade"` the pill then disappears into the store; `"stay"` leaves it there.

### Link (thin #4B5563 line between two nodes)
- props: `from`, `to` (ids), `route` (`elbow` default: orthogonal with rounded corners, straightened automatically when the nodes overlap; `curve`; `straight`), `fromSide`/`toSide` (`left|right|top|bottom`), `offset` (px, parallel lanes, e.g. -14 / 14 for request and response), `mid` (x or y of the elbow), `label` (small mono text), `labelAt` (0-1), `dashed`, `color`, `arrow` (`end|start|both`)
- actions: `enter` (0.6 stroke draw-on from `from`), `exit`, `dim`, `undim`, `highlight {color}` (brighter, thicker, glow), `alert` (red), `unhighlight`, `pulse`
- TokenPills and PacketStreams travel along Links; create one for every hop you want animated.

### PacketStream (bulk traffic: continuous 4px glowing dots along a Link)
- props: `link` (id), `color` (default ice white) or `concept`, `speed` (380 px/s), `spacing` (34 px between dots), `size` (4), `reverse` (flow `to` -> `from`)
- actions: `start` (dots begin to emit at `from`), `stop` (emission stops; dots in flight finish), `slow {factor: 0.3}` (ramps over `dur` 0.8), `speed {factor}`, `resume` (back to 1x), `exit`, `dim`
- Never auto-starts: add a `start` beat. ServiceCard/Database `latency` slows streams on adjacent Links for you.

### TokenPill (a specific API call or token: color-coded rounded pill)
Session ID = orange #F59E0B, access token / JWT = cyan #38BDF8, refresh token = purple #A855F7 (from look.json `semantic`, overridable via spec `concepts`). Unknown labels are neutral white pills.
- props: `label`, `concept` (color + key icon from this concept, e.g. label "sid_7f3e", concept "session id"), `color`, `icon` (icon name, or `false`), `from` (node id where it starts)
- actions:
  - `show {at?: nodeId, dock?: true, x?, y?}` (0.45 pop): appear docked at a node (in a Device's storage tray) or above it
  - `send {to, via?: linkId, then?: "dock"|"absorb"|"stay", dur?}`: travel from its current place along the Link to `to`. Duration defaults to path length / 650 px/s (0.7-1.8 s). `then` defaults to `dock` for a Device (stored in the tray) and `absorb` elsewhere (shrinks into the card, which glows). `stay` parks it on the Link next to the target. A hidden pill pops out at its node when sent.
  - `hide` (0.3), `expire` (0.5: greys out with strikethrough), `pulse`, `highlight`, `alert`, `dim`
- A pill is one object: send it again later and it leaves from where it is.

### Hacker (neon red hooded attacker with laptop; `place` default `attacker`)
- props: `label` ("Attacker"), `color` (#F43F5E)
- actions: generic (enter has a glitch flicker) +
  - `intercept {pill, link?, point?: 0.5, as?, hold: 2.4}` (1.2): a dashed red line shoots to the pill (its live position if it is moving at `at`, else the point on `link`), a copy of the pill appears (red dashed ring) and is pulled back beside the hacker. The copy's id is `as` or `<pill>-copy`; use it in later beats (e.g. `validate` it).
  - `replay {to, pill?: copyId, then: "absorb", hold: 2.0}` (1.3): a dashed red line to `to` and the copy travels along it.
- Pair with `alert` on the victim node and a Callout to land the point.

### Callout and Label
- Callout: dark bubble with a colored dot and a dotted connector to its target. props: `text`, `target` (id), `row` (anchor to a card/table row), `side` (`top` default, `bottom`, `left`, `right`), `gap` (34), `color` (dot; defaults to the text's concept or accent), `dx`, `dy`, or `x`,`y` without target. Variants via `variant`: `callout`, `label` (small caps grey text), `marker` (marker font).
- Label: same with `variant: "label"`, `side: "bottom"`, `gap: 16` (a caption under a node).
- actions: `enter` (0.5 slide from its side + de-blur), `exit`, `set {text}` (blur swap), `dim`, `pulse`

### Metric (big number with a counter; `place` default `center`)
- props: `value` ("120 ms"), `label` ("p99 latency"), `color`
- actions: generic + `set {value, color?, dur: 1.0}`: counts from the old number to the new one when both are numbers with the same unit, else blur-swaps; `color: "red"` turns it alert red.

### Icons
Lucide (ISC): smartphone, server, database, shield-check, shield-alert, key-round, lock, lock-open, globe, cpu, user, laptop, zap, hard-drive, cloud, network, fingerprint, gauge, router, layers, box, cog, mail, credit-card, monitor, timer, activity, scan, user-check, file-key, message-square, hourglass, refresh-cw, boxes, container, workflow, list-ordered, binary, terminal, check, x, wifi, radio-tower, webhook, split, ticket, clock, bell, search. To add more, extend `assets/icons/lucide-subset.js` from the `lucide-static` package.

## Authoring rules of thumb

- One idea per Insert, 3-6 nodes. Anchor every important Beat to the spoken keyword: `send` when the token is named, `validate` when "checks"/"looks up" is said, `latency` on "slow"/"bottleneck", `intercept` on "steals".
- Leave about 0.3 s between a `send` finishing and the next Beat on the same pill. A new movement starting earlier wins, cleanly.
- Reveal the hook in the last 2-3 s; give `reveal` a `dur` matching the spoken sentence.
- Dim, don't delete: when comparing two flows, `dim` (or `focus`) the unused path.
- Use `concepts` so the same token keeps its color in every Insert, caption and callout of the Session.

## Example 1: latency / bottleneck (16:9)

```json
{
  "id": "example-latency-bottleneck",
  "look": "architecture-flow",
  "engine": "html",
  "mode": "full",
  "size": [1920, 1080],
  "transparent": false,
  "fps": 30,
  "duration": 11.0,
  "concepts": {},
  "scene": {
    "title": "Where is the bottleneck?",
    "hook": "One slow query can stall *every* request upstream.",
    "elements": [
      { "id": "phone", "primitive": "Device", "props": { "place": "client", "label": "10k users", "screen": "home" } },
      { "id": "gw", "primitive": "ServiceCard", "props": { "place": "center", "title": "Gateway", "subtitle": "rate limit · auth", "icon": "router", "width": 300 } },
      { "id": "api", "primitive": "ServiceCard", "props": { "place": "server-top", "title": "Orders API", "subtitle": "3 replicas", "icon": "server", "blades": 3, "bladeLabel": "orders" } },
      { "id": "db", "primitive": "Database", "props": { "place": "store-right", "title": "Orders DB", "subtitle": "single primary", "columns": ["query", "time"], "flex": [1.6, 1],
          "rows": [ ["SELECT by id", "2 ms"], ["SELECT by email", "4 ms"], ["SELECT * WHERE note", "18 ms"] ] } },
      { "id": "p99", "primitive": "Metric", "props": { "place": "center-bottom", "label": "p99 latency", "value": "120 ms" } },
      { "id": "l1", "primitive": "Link", "props": { "from": "phone", "to": "gw" } },
      { "id": "l2", "primitive": "Link", "props": { "from": "gw", "to": "api" } },
      { "id": "l3", "primitive": "Link", "props": { "from": "api", "to": "db" } },
      { "id": "s1", "primitive": "PacketStream", "props": { "link": "l1" } },
      { "id": "s2", "primitive": "PacketStream", "props": { "link": "l2" } },
      { "id": "s3", "primitive": "PacketStream", "props": { "link": "l3" } },
      { "id": "note", "primitive": "Callout", "props": { "text": "full table scan", "target": "db", "row": 2, "side": "left", "color": "#F43F5E" } }
    ]
  },
  "beats": [
    { "at": 1.4, "action": "start", "target": "s1" },
    { "at": 1.7, "action": "start", "target": "s2" },
    { "at": 2.0, "action": "start", "target": "s3" },
    { "at": 4.0, "action": "highlightRow", "target": "db", "args": { "row": 2, "color": "red" } },
    { "at": 4.0, "action": "latency", "target": "db", "args": { "dependents": ["api"] } },
    { "at": 4.3, "action": "setRow", "target": "db", "args": { "row": 2, "value": "2,400 ms", "color": "#F43F5E" } },
    { "at": 4.3, "action": "set", "target": "p99", "args": { "value": "2,400 ms", "color": "#F43F5E", "dur": 1.4 } },
    { "at": 4.6, "action": "slow", "target": ["s1", "s2"], "args": { "factor": 0.3 } },
    { "at": 4.8, "action": "latency", "target": "gw", "args": { "streams": false } },
    { "at": 5.2, "action": "enter", "target": "note" },
    { "at": 8.0, "action": "reveal", "target": "hook" }
  ]
}
```

## Example 2: session lookup and validation (9:16)

```json
{
  "id": "example-session-lookup-vertical",
  "look": "architecture-flow",
  "engine": "html",
  "mode": "full",
  "size": [1080, 1920],
  "transparent": false,
  "fps": 30,
  "duration": 9.0,
  "concepts": { "session id": "#F59E0B" },
  "scene": {
    "title": "Sessions, explained",
    "hook": "Every request costs one *lookup*. That's the trade-off.",
    "elements": [
      { "id": "phone", "primitive": "Device", "props": { "place": "client", "label": "Browser", "screen": "home" } },
      { "id": "api", "primitive": "ServiceCard", "props": { "place": "server", "title": "Web Server", "subtitle": "stateless", "icon": "server", "blades": 2, "bladeLabel": "web" } },
      { "id": "cache", "primitive": "Database", "props": { "place": "store", "title": "Session store", "subtitle": "redis", "icon": "database", "columns": ["session id", "user"],
          "rows": [ ["sid_19ac", "bob"], ["sid_7f3e", "alice"], ["sid_c201", "carol"] ] } },
      { "id": "l1", "primitive": "Link", "props": { "from": "phone", "to": "api" } },
      { "id": "l2", "primitive": "Link", "props": { "from": "api", "to": "cache" } },
      { "id": "s1", "primitive": "PacketStream", "props": { "link": "l1", "speed": 300 } },
      { "id": "sid", "primitive": "TokenPill", "props": { "label": "sid_7f3e", "concept": "session id", "from": "phone" } }
    ]
  },
  "beats": [
    { "at": 1.2, "action": "show", "target": "sid", "args": { "at": "phone" } },
    { "at": 1.3, "action": "start", "target": "s1" },
    { "at": 2.0, "action": "send", "target": "sid", "args": { "to": "api" } },
    { "at": 3.3, "action": "lookup", "target": "cache", "args": { "row": "sid_7f3e" } },
    { "at": 3.6, "action": "validate", "target": "cache", "args": { "pill": "sid", "row": "sid_7f3e", "hold": 1.6 } },
    { "at": 5.8, "action": "screen", "target": "phone", "args": { "state": "success", "title": "Welcome, Alice" } },
    { "at": 6.4, "action": "reveal", "target": "hook" }
  ]
}
```

More in `examples/`: `jwt-auth-flow.json` (login, access + refresh tokens, credential validation) and `token-replay-attack.json` (intercept, replay, validate the copy). Reference frames rendered from them are in `reference/`.
