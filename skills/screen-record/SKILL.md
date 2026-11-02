---
name: screen-record
description: Record the screen, webcam and mic while the user talks freely, then turn the Take into a studio-quality edited video with animated Inserts (architecture diagrams, packet flows, code, docs, charts, math, whiteboard and stickman scenes) built from the user's own Context Pack (repo, docs, URLs, web search). Hands-off: cuts retakes and dead air, zooms on clicks, grades the webcam, denoises the voice, adds captions, sound design, shorts, thumbnail and publishing copy. Use when the user types /screen-record, asks to record their screen or a walkthrough/tutorial/demo, or hands over a raw recording to turn into a polished video.
---

# /screen-record

The user talks; you edit. The `clipagent` CLI does the mechanical work (capture, transcription, analysis, rendering). **You are the editor**: you read the transcript and the Context Pack, choose the Look, write the Inserts, and check your own output. The user never reviews anything in between, so the quality bar is yours to hold.

`CA` below means `uv run --project <this skill's directory>/../../engine clipagent`. Vocabulary: [GLOSSARY.md](../../GLOSSARY.md) (Session, Take, Context Pack, Insert, Beat, Primitive, Look, Concept Color, Scratch Marker, Mismatch, Deliverables).

Read before the editorial pass: [reference/edl.md](reference/edl.md) (the edit format), [reference/inserts.md](reference/inserts.md) (how to write Inserts), [reference/editing-guide.md](reference/editing-guide.md) (cuts, zooms, text, security). Each Look's scene vocabulary: `looks/<look>/PRIMITIVES.md` at the repo root.

## 1. Start (the user typed /screen-record)

1. First run only: `CA doctor`. Fix what it marks FIX (`! sudo apt install ffmpeg`, `CA install-recorder`, `uv run --project ... playwright install chromium`). Input-group access on Wayland is optional.
2. Work out the Context Pack from the user's message: paths (default: the current repo), URLs, and whether web search is allowed (only if they said so). Camera: `webcam` (default), `none` (screen only), or `external` (they'll add a phone/DSLR file afterwards). A Look only if they named one.
3. `CA start --context <paths/urls> [--web] [--camera webcam|none|external] [--look ID] [--title "<topic>"]`.
4. Tell the user in two lines: recording has started; stop with the floating bar's Stop button, **Ctrl+Alt+S** (⌘⌥S on macOS), or by asking you; **Ctrl+Alt+X** or saying "cut that" throws away the sentence they just said. Then tell them to talk naturally: mistakes get cut.
5. Run `CA wait` **in the background** so you are told when the Take ends. Don't poll.

If the user hands you an existing video instead: `CA import SCREEN.mp4 [--camera CAM.mp4] --context ...` and continue at step 2.

## 2. After stop: prepare (mechanical, takes minutes; run in the background)

- If they recorded their face on a phone/DSLR: `CA camera /path/to/file.mp4` first (synced by audio).
- Context added later ("also use this README"): `CA context add <path|url>`.
- `CA prepare [--vocab "names, libraries, product terms"]`: ingest, local transcription (Whisper `large-v3-turbo`), analysis (voice SNR, screen activity, camera quality score), and a draft `work/edl.json` with dead air, fillers and Scratch Markers cut and zooms from clicks.

## 3. The editorial pass (the actual work: take your time)

Read in this order:
1. `work/transcript.txt` end to end, then `work/words.txt` (the same words with ids `w123`; you anchor Beats to these).
2. The Context Pack: `CA status` lists it. Skim the repo structure and open the files the speaker talks about; read the docs they gave; fetch the URLs. With `web: true`, search the web to get facts right (versions, benchmarks, definitions), and you may capture page screenshots for telestration Inserts (reference/inserts.md).
3. Contact sheets: `CA frames --every 20`, then look at them.

Then edit `work/edl.json`:
- **Cuts:** retakes (keep the last take), false starts, tangents. The draft already cut dead air, fillers and Scratch Markers.
- **Look:** pick one Look for the whole video from `CA looks`, by topic and audience (reference/inserts.md has the decision table). Set `"look"`; the renderer applies its screen treatment, captions, transitions and sound.
- **Inserts:** where an Insert makes the explanation clearer, write it from the Look's Primitives with Beats anchored to the spoken words. Typical density: one every 30–90 s during screen work, never over code being typed. While the speaker explains without touching the screen, you may run long animated stretches (Stickman Story / Whiteboard scenes every 4–6 s). A Take with no screen action (voice only) becomes a fully animated video.
- **Concept Colors:** list every concept that appears in more than one Insert in `"concepts"`; it keeps one color for the whole video.
- **Mismatches:** when the speaker says something that contradicts the Context Pack, the Insert shows what they *said*, and you add `{"at": "w412", "said": "...", "context": "..."}` to `"mismatches"`.
- **Screen annotations:** `annotations` (marching-ants boxes, curved arrows, chevrons, pill labels, red pointers) where the speaker refers to something on screen.
- **Zooms:** confirm or fix every suggested zoom with `CA frames --at T --rect x,y,w,h` and look at the image.
- **Camera:** layouts per reference/editing-guide.md. If `camera.allow_full` is false (poor camera), never use `full`; keep the bubble.
- **Titles, chapters, callouts, glossary/caption fixes, redactions** per the editing guide. **Never skip the secrets hunt.**
- **Deliverables:** 1–3 `shorts` (the strongest self-contained 30–60 s moments), a `thumbnail` (`at` + a ≤ 5-word headline), and `publish` (title, YouTube description, tags, a LinkedIn post, an X post) written in the speaker's voice from what they actually said.

## 4. Render the Inserts and check your own work

1. `CA inserts` renders every Insert (cached; only changed Inserts re-render). Read the warnings: Beats on cut words, overlaps.
2. `CA qa --stills` runs the automatic checks (clipped/overlapping text, blank frames, palette drift, Inserts over typing, camera rules) and writes `work/qa/<insert>.png` sheets: the Look's reference frame beside three frames of each Insert. **Open and look at every sheet and still.** Ask: does this look like a studio motion-graphics explainer? Is every label readable, aligned, unclipped? Does it say what the speaker says at that moment?
3. Fix and re-run `CA inserts --only <id>` and `CA qa`. **At most 2 retries per Insert**; if it still fails, delete it from `edl.json` and note it in the report. Never ship a broken Insert.
4. Composited stills of tricky moments: `CA render --still <source seconds> ...`, then look at them.

## 5. Render and deliver

- `CA render` (in the background; roughly 1–2× the video length on a laptop, plus Insert frames).
- `CA deliver`: `deliverables/final.mp4`, `shorts/`, `thumbnail.png`, `captions.srt`, `chapters.txt`, `copy.md`, `report.md`.
- Look at the thumbnail and one frame of each short.

## 6. Report to the user

Short: the path of `deliverables/`, raw → final length, the Look and why, the Inserts made (one line each), Mismatches, what you redacted, words you couldn't resolve, anything dropped by QA. Tell them how to tweak ("change anything in plain words; I edit `edl.json` and re-render, and only the changed parts are redone").

## Rules

- Times in `edl.json` are source seconds or word ids, never output seconds. The engine remaps through the cuts.
- Don't invent content: Inserts, titles and copy restate what the speaker said, made concrete with their Context Pack.
- Keep the speaker's words: cut, don't rewrite. Captions come from the transcript plus glossary fixes.
- Plain typing is never shown or logged as text. Only shortcuts get badges.
- If a step fails, read the error, fix it, re-run. Don't hand back a half-finished video.
