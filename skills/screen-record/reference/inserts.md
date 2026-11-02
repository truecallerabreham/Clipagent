# Writing Inserts

An Insert is a generated visual tied to a moment of the Take that shows what the speaker is talking about. You build it from the Look's **Primitives** (pre-built, hand-tuned pieces) and drive it with **Beats** anchored to spoken words. You never write HTML, CSS or Manim code: if no Primitive fits, use a simpler Insert or none.

## 1. Pick the Look (once per Session)

| Look | Pick it when the video is about | Feel |
|---|---|---|
| `architecture-flow` | system design, backends, auth/tokens, APIs, caching, queues, latency, security attacks | dark, charcoal service cards, packets and token pills flowing between nodes |
| `neon-telestrator` | AI/ML news, model launches, benchmarks, pricing, comparisons, "what changed" analysis | black canvas, hand-drawn neon ink over screenshots and charts, 3D data plots |
| `math-vector` | algorithms, math, ML theory, vectors/matrices, complexity, anything with equations | 3Blue1Brown style: black, LaTeX, draw-on strokes, morphing, persistent colors |
| `whiteboard-saas` | product demos, SaaS walkthroughs, onboarding, business/marketing explainers, non-technical audiences | white whiteboard, hand drawing with a marker, purple keywords, annotated UI |
| `stickman-story` | stories, career/productivity/process topics, "why" videos, beginner explainers, clean UI walkthroughs | white, black 5 px line-art stickman with micro-animations, macOS window framing |

If the user named a Look, use it. Otherwise decide from the transcript's main topic, not from one passage. Run `clipagent looks` for the installed list, then read `looks/<look>/PRIMITIVES.md` fully before writing a scene.

## 2. Decide where Inserts go

Make an Insert when the speaker:
- explains structure or flow that isn't visible on screen ("the request goes to the gateway, then...")
- names numbers, comparisons, trade-offs, steps or a sequence
- refers to code or docs in the Context Pack that aren't on screen right now (show the snippet or excerpt)
- tells a story or explains *why* with no screen action

Don't make one when the speaker is showing something on screen the viewer must see (typing code, clicking through UI), during `typing` spans, or just to fill time. Typical density during screen work: one every 30–90 s, 6–20 s long. During long explanations with nothing happening on screen, Inserts may follow each other (Stickman/Whiteboard: a new scene every 4–6 s, cut at sentence boundaries).

**Mode:**
- `full`: the concept *is* the content (architecture, story scenes, math). The camera bubble stays on top.
- `split`: the screen still matters (the code they're explaining on the left, the diagram on the right).
- `overlay`: a small transparent addition over the live screen: a number, a snippet, a token pill, a short label. Set `rect` away from what they're pointing at.

## 3. Anchor every Beat to a word

`words.txt` gives every word an id: `[01:12.4] w310:the w311:gateway w312:checks w313:the w314:token`.

- `start` / `end` of the Insert: the first and last word it illustrates. The engine adds 0.25 s before and 0.45 s after.
- Each Beat fires on the word that names the thing: the packet starts moving on "sends", the checkmark appears on "valid", the brace draws on "both". Use `"lead": -0.15` to land an entrance slightly before the word (it reads as "in sync" to the eye).
- First Beat within ~0.5 s of the Insert start, so the frame is never empty. Leave ≥ 0.6 s between Beats on the same element.
- If a Beat's word was cut, the engine warns and moves it to the next kept word: re-anchor it.

## 4. Concept Colors

Every concept that appears in more than one Insert (or in an Insert and a callout) goes in the top-level `"concepts"` and in the Insert's `"concepts"`. The Look's semantic colors win (in `architecture-flow`, JWT/access token is always cyan, session id orange, refresh token purple). Never use a concept's color for anything else.

## 5. Content from the Context Pack

- **Code:** quote the real lines from the repo (5–12 lines max, trimmed to what they talk about), with the real file path as the title. Never invent code.
- **Docs:** short excerpts (≤ 2 sentences) with the source name; highlight the phrase the speaker reads out.
- **Numbers:** only numbers the speaker said or that the Context Pack or web sources state; put the source in a small label.
- **Web screenshots** (only when the Context Pack has `web: true`): `clipagent snap <url> [--name chart] [--selector CSS]` saves `work/assets/<name>.png`; use it in the Look's screenshot Primitive (`neon-telestrator`: telestrate it) with a source label.
- **Mismatch:** speech and Context Pack disagree → follow the speech, add a `mismatches` entry.

## 6. Quality bar (what QA and you check)

- Every label readable at 1080p (≥ 28 px), inside the safe margin, nothing overlapping or clipped.
- One idea per Insert; ≤ 7 nodes in a diagram, ≤ 12 words of on-screen text per element.
- The Insert says the same thing as the voice at the same moment.
- It looks like the Look's reference frame: same palette, stroke, type. If the QA sheet shows otherwise, fix the scene (positions, fewer elements, shorter labels), up to 2 retries, then drop it.

## Example (architecture-flow, full mode)

```jsonc
{ "id": "ins-02", "start": "w42", "end": "w118", "mode": "full", "concepts": ["access token", "refresh token"],
  "scene": { "title": "LOGIN FLOW",
             "elements": [ { "id": "phone", "primitive": "Device", "props": { "place": "client", "label": "Phone app" } },
                           { "id": "gw", "primitive": "ServiceCard", "props": { "place": "server", "title": "API Gateway" } },
                           { "id": "db", "primitive": "Database", "props": { "place": "store-right", "title": "Sessions" } } ] },
  "beats": [ { "word": "w44", "action": "enter", "target": "phone", "lead": -0.15 },
             { "word": "w51", "action": "enter", "target": "gw" },
             { "word": "w60", "action": "send", "target": "phone", "args": { "to": "gw", "pill": "access token" } },
             { "word": "w73", "action": "validate", "target": "db", "args": { "pill": "access token", "row": 0 } } ] }
```
The exact element props and Beat actions differ per Look: `looks/<look>/PRIMITIVES.md` is the source of truth.
