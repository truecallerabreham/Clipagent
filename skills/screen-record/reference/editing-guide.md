# Editing guide: the editorial pass

The draft only knows silence and pixels. You know what the video is *about*. These are the calls that make it watchable.

## Cuts

- **Already cut by the draft:** dead air, filler words, and every Scratch Marker (hotkey or a spoken "cut that"): the sentence before it is gone. Check `_draft_scratched` in the EDL to see what went.
- **Retakes:** when the speaker restarts a sentence ("let me say that again", "actually, wait", or simply says nearly the same sentence twice), keep the **last** take and cut the earlier ones whole, from the start of the failed take to the start of the good one.
- **False starts and trailing-off:** a half-sentence abandoned mid-way goes.
- **Tangents and dead ends:** cut a debugging detour only if the fix isn't shown later; viewers of a from-scratch tutorial often *want* to see an error and its fix. When in doubt, keep it and speed it up.
- **Cut at word boundaries.** Segment edges sit about 0.1s before the first word and 0.2s after the last; never inside a word.
- **Silent work goes faster, it doesn't disappear:** typing, installs, builds and waiting on Claude Code to respond become `speed` 2-8 segments, not cuts, or the screen jumps. Aim for any silent stretch to last 2-4s on screen.
- **Pacing target:** most raw tutorial footage loses 25-45%. If you cut less than 15%, look again; if more than 60%, check you didn't cut the work.

## Opening (the first 5 seconds decide everything)

- Start on the strongest line: the result or the promise ("In ten minutes we'll have an agent that reviews its own PRs"). Segments always play in source order (the renderer sorts them), so you can't move a later line to the front: cut any warm-up before the first strong sentence instead.
- `layouts`: start `full` (face fills frame) for the hook, switch to `bubble` when the screen work begins.
- One `title` over the first 3s: short punchy headline (≤ 7 words) + `sub` line.

## Zooms

- Zoom when the speaker points at something small: "this function", "here in the terminal", a line of output, a config value, a Claude Code permission prompt.
- Hold ≥ 2.5s; the renderer eases in/out over 0.75s. Back-to-back zooms within 1.2s pan straight across without zooming out.
- Typical rect width 0.35-0.6. Narrower than 0.3 on 1080p source looks soft.
- Never zoom during fast scrolling or window switching; it reads as shaky.
- Verify **every** zoom by eye: `clipagent frames --at <mid-zoom time> --rect x,y,w,h` and look at the picture. Auto suggestions are often off.
- Density: roughly one zoom per 15-40s of screen work. More in vertical format (the screen is small there).

## Text

- **Chapters** at real topic shifts (new file, new concept, "now let's..."): 3-8 for a 10-minute video, 2-4 words each.
- **Callouts** for the one sentence a viewer must not miss (a definition, a gotcha, a security point). 3-7 words. Add `rect` when the thing is on screen; it spotlights it.
- **Captions**: always on for social. Fix technical terms via `glossary`: read `transcript.txt` for misheard names (Claude, Claude Code, MCP, Anthropic, library and CLI names, the speaker's own name and handle).
- **Outro**: "Made with ClipAgent" (or the user's own line) + their handle. Keep 3-5s.

## Security: redact before anything is published

A leaked key in a published video is the worst possible outcome, and the speaker was told to talk without worrying. Before the final render:

1. Scan contact sheets (`clipagent frames --every 20`) and every frame around `.env`, `export`, `config`, `credentials`, `token`, `key`, `secret`, `password`, `Authorization`, `ssh`, `login`, terminal history and browser tabs (emails, account names, internal URLs).
2. `grep -iE "key|token|secret|password|env|credential|bearer"` over `transcript.txt` for moments they mention one.
3. Add `redact` rects generously (pad 20%) for the full span the value is visible, then check a still inside the span.
4. If something can't be cleanly redacted (it scrolls), cut that stretch instead.
5. List what you redacted in your final report so the user can double-check.

## Camera

- The analysis scores the camera (`analysis.json` → `camera_look.quality`): **good** cameras may go `full` for the hook; **poor** ones stay a small bubble (`camera.allow_full: false`): never `full`, never `side`.
- No camera (`--camera none`): no layouts needed; Inserts carry the visual variety.

- `grade: "auto"` is right most of the time. Look at a still: if the face is too dark, raise `target_luma` to 130-140; orange/blue cast left over → `white_balance: 0.85`; grainy → `denoise: 5`.
- `side` layout for long talking explanations where the screen isn't changing; `hidden` when the screen needs every pixel (dense diffs, big terminal output) and the speaker is quiet.

## Platform presets

| Platform | format | notes |
|---|---|---|
| YouTube / LinkedIn long-form | landscape | chapters on, badge `intro` |
| X / LinkedIn feed clip (≤ 2 min) | landscape | tighter cuts, more callouts, badge `always` |
| Shorts / Reels / TikTok (≤ 60s) | vertical | zoom most of the time, captions essential, `words_per_line: 3` |

Shorts come from `"shorts"` in the EDL: `clipagent deliver` cuts each range out of the final video and reframes it to 9:16 with a title. Pick moments that stand alone: a complete idea in 30-60 s, with an Insert in it if possible. For a native vertical edit of the whole Take, start the Session with `--format vertical`.
