---
name: screen-record
description: Record the screen, webcam and mic while the user talks freely, then turn the Take into a studio-quality edited video with animated Inserts (architecture diagrams, packet flows, code, docs, charts, math, whiteboard and stickman scenes) built from the user's own Context Pack (repo, docs, URLs, web search). Hands-off: cuts retakes and dead air, zooms on clicks, grades the webcam, denoises the voice, adds captions, sound design, shorts, thumbnail and publishing copy. Use when the user types /screen-record, asks to record their screen or a walkthrough/tutorial/demo, or hands over a raw recording to turn into a polished video.
---

# /screen-record

The user talks; you edit. The `clipagent` CLI does the mechanical work (capture, transcription, analysis, rendering). **You are the editor**: you read the transcript and the Context Pack, choose the Look, write the Inserts, and check your own output. The user never reviews anything in between, so the quality bar is yours to hold.

`CA` below means the `ca` launcher in this skill's folder (`<this skill's directory>/ca`; on Windows `ca.cmd`). It finds the engine and installs what it needs on first use. **You run every command; never ask the user to type one or show them flags.** Vocabulary: [GLOSSARY.md](../../GLOSSARY.md) (Session, Take, Context Pack, Insert, Beat, Primitive, Look, Concept Color, Scratch Marker, Mismatch, Deliverables).

Read before the editorial pass: [reference/edl.md](reference/edl.md) (the edit format), [reference/inserts.md](reference/inserts.md) (how to write Inserts), [reference/editing-guide.md](reference/editing-guide.md) (cuts, zooms, text, security). Each Look's scene vocabulary: `looks/<look>/PRIMITIVES.md` at the repo root.

## 1. Start (the user typed /screen-record)

Goal: recording within a minute, with at most three quick taps from the user. Nothing else.

1. **Warm up in the background, right away:** run `CA setup` in the background (instant once set up; the first time it installs the recorder and the render browser in parallel). Don't wait for it, go straight to step 2. If it later prints `FIX` (e.g. ffmpeg missing), tell the user the one command it names.
2. **Ask how they want it: multiple choice, one question per turn, nothing else in the message.** Use your question tool (Claude Code: `AskUserQuestion`; OpenCode: `question`); without one, send a short numbered list and accept a number. Skip any question the user's message already answers ("screen only", "make a short", "use the web", a file to edit).
   - Run `CA prefs`. If `"saved": true`, ask only: **Record with your usual setup?** → `Yes: <summary>` (first, recommended) · `Change setup`. On yes go to step 3.
   - Otherwise (first time, or "Change setup") ask, one at a time:
     1. **What are you making?** `Tutorial video (16:9)` · `Short / reel (9:16)` · `Edit a video I already have`
     2. **Camera?** `Webcam bubble` · `Screen only` · `Phone camera (I'll add the file after)`. Skip for "Edit a video".
     3. **What should the animations draw from?** `This repo` · `This repo + web search` · `Nothing, just my voice`
   - Save the answers: `CA prefs --make tutorial|short|import --camera webcam|none|external --context repo|repo+web|none` (add `--look ID` only if they named a Look). Next time, step 2 is one tap.
3. **Record:** `CA start`, adding only what the message gave: `--title "<topic>"`, `--context <extra paths or URLs>`, `--look ID`. The saved setup fills in the rest (the current repo, camera, 16:9 or 9:16, web). For "Edit a video I already have": ask for the file path if you don't have it, then `CA import <file> [--camera CAM.mp4]` and continue at section 2.
4. Tell the user in two lines: recording has started; stop with the floating bar's Stop button, **Ctrl+Alt+S** (⌘⌥S on macOS), or by asking you; **Ctrl+Alt+X** or saying "cut that" throws away the sentence they just said. Then tell them to talk naturally: mistakes get cut.
5. Run `CA wait` **in the background** so you are told when the Take ends. Don't poll. It also transcribes the mic *while they talk* (low priority, half the cores) and converts the media right after the stop, so when it returns the slow mechanical work is already done.

The user changes their mind later ("use the web this time", "make it a short")? Pass the flag for this run (`--web`, `--no-web`, `--format vertical`, `--camera none`) and offer to save it with `CA prefs`.

## 2. After stop: prepare (mechanical, ~15 s once `wait` has run)

- If they recorded their face on a phone/DSLR: `CA camera /path/to/file.mp4` first (synced by audio).
- Context added later ("also use this README"): `CA context add <path|url>`.
- `CA prepare`: analysis (voice SNR, screen activity, camera quality score) and a draft `work/edl.json` with dead air, fillers and Scratch Markers cut and zooms from clicks. The transcript (Whisper `large-v3-turbo`) and the converted media normally already exist from `wait`; if not (imports, `wait` not run), it does both, side by side. Misheard names: fix them with `glossary`/`caption_edits`; `--vocab "..." --retranscribe` re-runs Whisper with hints (minutes).

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

1. `CA inserts` renders every Insert (cached; only changed Inserts re-render; several browser processes, ~15-30 s per Insert). Start it **in the background** as soon as the Inserts are written and do the text work (titles, chapters, deliverables, copy) meanwhile. Read the warnings: Beats on cut words, overlaps.
2. `CA qa --stills` runs the automatic checks (clipped/overlapping text, blank frames, palette drift, Inserts over typing, camera rules) and writes `work/qa/<insert>.png` sheets: the Look's reference frame beside three frames of each Insert. **Open and look at every sheet and still.** Ask: does this look like a studio motion-graphics explainer? Is every label readable, aligned, unclipped? Does it say what the speaker says at that moment?
3. Fix and re-run `CA inserts --only <id>` and `CA qa`. **At most 2 retries per Insert**; if it still fails, delete it from `edl.json` and note it in the report. Never ship a broken Insert.
4. Composited stills of tricky moments: `CA render --still <source seconds> ...`, then look at them.

## 5. Render and deliver

- `CA render && CA deliver` together, in the background (roughly the video's length on a 4-core laptop; `--hq` for a slower, marginally cleaner encode).
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
