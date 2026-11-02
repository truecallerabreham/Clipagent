# Screen Recorder

A coding-agent skill that records a speaker's screen and webcam, then uses the speaker's own materials to turn the raw recording into a finished, edited video.

## Language

**Session**:
One run of the skill from `/screen-record` to the finished video: one Take, its Context Pack, and the edit made from them.
_Avoid_: Project, job

**Take**:
The raw material captured between start and stop: screen, webcam, microphone, and input events. It is never modified.
_Avoid_: Raw video, clip, recording (when meaning the raw files)

**Context Pack**:
The materials the speaker gives the agent for a Session (repositories, documents, URLs, and whether web search is allowed). It is declared at start and can be amended after the Take ends.
_Avoid_: Context (alone), attachments, sources

**Insert**:
A generated visual tied to a moment in the Take that shows what the speaker is talking about: a diagram, code snippet, document excerpt, chart, number, whiteboard sketch or math animation.
_Avoid_: B-roll, motion graphic, animation (alone), overlay

**Look**:
The single production style of a whole Session's video: how Inserts look and move, how the screen recording is framed and annotated, plus transitions, chapter cards, captions and titles. Examples: Math Vector, Whiteboard SaaS, Neon Telestrator, Architecture Flow, Stickman Story.
_Avoid_: Theme, style preset, template

**Primitive**:
A pre-built, hand-tuned visual building block that a Look provides (e.g. a service card, packet stream, draw-on path, curly brace, number counter, hand-draw reveal). Inserts are composed only from Primitives.
_Avoid_: Component, widget, asset

**Beat**:
One step inside an Insert, tied to a specific spoken word so that it happens exactly when that word is said.
_Avoid_: Keyframe, cue, step

**Concept Color**:
The fixed color a concept (e.g. "JWT", "input vector") gets when it first appears. It holds for the whole Session across every Insert, caption and callout.
_Avoid_: Highlight color, accent

**Camera Source**:
Where the speaker's face comes from in a Take: none, a live webcam, or an external file (phone or DSLR) synced by audio afterwards.
_Avoid_: Webcam (when the source may be a phone)

**Scratch Marker**:
A point the speaker marks during a Take (by hotkey or by saying "cut that") meaning "discard what I just said back to the previous sentence".
_Avoid_: Bookmark, flag

**Mismatch**:
A moment where what the speaker says contradicts the Context Pack. The Insert follows the speech, and the Mismatch is reported.
_Avoid_: Error, conflict

**Deliverables**:
What a finished Session hands back: the main video, vertical shorts, a thumbnail, captions, chapters, publishing copy and a report.
_Avoid_: Content pack (too close to Context Pack), output, export, assets
