# The ClipAgent demo

[`clipagent-demo.mp4`](clipagent-demo.mp4) was edited by ClipAgent itself, and that is the point of it.

How it was made:

1. **The take.** The narration (`source/narration.txt`) was voiced with an open-source TTS voice (Piper, `en_US-ryan-high`), and the "screen" is a terminal session (`source/terminal.html`) recorded with `source/record_terminal.py`.
2. **Import and prepare.** `clipagent import raw.mp4 --context . --look architecture-flow`, then `clipagent prepare` ran the local Whisper transcription (`source/transcript.txt`), analysis and the draft cut.
3. **The editorial pass.** The agent wrote [`source/edl.json`](source/edl.json): two Architecture Flow Inserts anchored to spoken words, zooms, three annotation boxes, caption fixes ("chip" → "ship"), sound design, the outro, a short, a thumbnail and the publishing copy.
4. **Render.** `clipagent inserts`, `qa` (both Inserts passed), `render` and `deliver`. The 6-second montage of the five Looks was then laid over the "five studio looks" sentence from each Look's own example renders.

The self-check report is in [`source/report.md`](source/report.md).

## One video per Look

[`looks/`](looks) holds a full end-to-end edit for each of the other four Looks, made the same way (Piper voice over a recorded HTML screen, then `import`, `prepare`, the agent's `edl.json`, `inserts`, `qa`, `render`, `deliver`):

| Look | Video | Topic |
|---|---|---|
| Neon Telestrator | [video.mp4](looks/neon-telestrator/video.mp4) | a fictional model launch and its pricing |
| Math Vector | [video.mp4](looks/math-vector/video.mp4) | what a matrix does to space, and gradient descent |
| Whiteboard SaaS | [video.mp4](looks/whiteboard-saas/video.mp4) | onboarding for a fictional analytics SaaS |
| Stickman Story | [video.mp4](looks/stickman-story/video.mp4) | why I test before Friday deploys |

Each `source/` folder has the narration, the screen page, the `edl.json` and the self-check report.
