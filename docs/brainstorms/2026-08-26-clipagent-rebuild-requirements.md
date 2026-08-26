---
date: 2026-08-26
topic: clipagent-rebuild
---

# clipagent — Incremental Rebuild as Product

## Summary

Rebuild the multimodal-agents-course (Kubrick) as a standalone product called **clipagent** — a video search and clip extraction tool. Same codebase, same tech stack, restructured as 63 architecture-layer micro-milestones where each step produces a visible, demoable state for social/portfolio recording.

---

## Problem Frame

The Kubrick course repo contains a fully functional Video-RAG system (video processing, MCP server, agent, API, UI, observability) but is structured for learning — notebooks, step-by-step comments, modular separation. The goal is to repackage this as a product called clipagent, built incrementally so each milestone produces something recordable (screenshot, screen recording, demo video) for social media and portfolio content.

The video search/clip extraction space has established players (Descript, Opus Clip, Recall.ai) but no user pain was validated in this brainstorm — this is an exploratory product bet driven by portfolio impact.

---

## Actors

- A1. **Developer (you)**: Builds the project milestone by milestone, records demos at each step
- A2. **End user**: Content creator, editor, or researcher who uploads videos and searches/clips moments (future user, not yet validated)

---

## Key Flows

- F1. **Milestone build + demo record**
  - **Trigger:** Developer starts a new micro-milestone
  - **Actors:** A1
  - **Steps:** Pull previous milestone state → implement single step → verify it works → record screenshot or screen recording → commit
  - **Outcome:** One working, demoable increment added to the project
  - **Covered by:** R1, R2, R3

- F2. **Video search + clip extraction (product flow)**
  - **Trigger:** End user uploads a video
  - **Actors:** A2
  - **Steps:** Upload video → system processes (transcribe, sample, embed, index) → user asks question or provides image → system returns matching clip or answer
  - **Outcome:** User gets a video clip or answer grounded in video content
  - **Covered by:** R4, R5, R6

---

## Requirements

**Project structure & identity**

- R1. Project named "clipagent" with its own repo, README, and identity — not a fork or derivative labeling of Kubrick
- R2. 63 micro-milestones organized into 6 architectural layers, each producing a verifiable, demoable state
- R3. Each micro-milestone has a clear "what was added" and "what's demoable now" description

**Architecture layers (build order)**

- R4. Layer 1: Video processing pipeline — upload, transcribe, sample frames, caption, embed, index (15 micro-milestones)
- R5. Layer 2: MCP server — expose pipeline capabilities as MCP tools with FastMCP (13 micro-milestones)
- R6. Layer 3: Agent — custom agent with tool-use loop, MCP client, Groq LLM, memory (10 micro-milestones)
- R7. Layer 4: FastAPI API — expose agent over HTTP with Swagger docs (5 micro-milestones)
- R8. Layer 5: React UI — upload, chat, video player, clip preview, HAL 9000 theme (13 micro-milestones)
- R9. Layer 6: Observability + polish — Opik tracing, error logging, Docker Compose, docs (6 micro-milestones)

**Tech stack (inherited from source)**

- R10. Python 3.12.8, uv package manager
- R11. Pixeltable for video processing and multimodal indexing
- R12. FastMCP for MCP server
- R13. FastAPI for HTTP API
- R14. Groq (Llama 4 Scout/Maverick) for LLM inference
- R15. OpenAI CLIP for visual embeddings, gpt-4o-mini for captioning, gpt-4o-mini-transcribe for audio
- R16. Opik for observability and prompt versioning
- R17. React for frontend with HAL 9000-inspired dark theme
- R18. Docker + Docker Compose for containerization

**Demo & recording**

- R19. Each micro-milestone produces a state that can be verified via command, screenshot, or screen recording
- R20. Early milestones (Layer 1-2) should be front-loaded with the most visually compelling demo moments
- R21. Final state should be demoable as a complete end-to-end flow: upload → process → search → clip

**Scope constraints**

- R22. Same code as source repo — no rewrite, rebrand and restructure only
- R23. Local Docker deployment only — no cloud, no multi-tenant
- R24. Desktop web only — no mobile
- R25. Single-user — no auth, no multi-user support

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given a fresh clone of clipagent, when the developer reads the README, they see 63 numbered milestones with clear "what was added" and "what's demoable" for each.
- AE2. **Covers R4.** Given a sample video file, when the developer completes milestone 13 (pipeline test), they can upload the video and see transcribed text, sampled frames, captions, and embeddings in Pixeltable.
- AE3. **Covers R5.** Given a processed video, when the developer completes milestone 28 (MCP Inspector test), they can call all 4 MCP tools from MCP Inspector and get correct results.
- AE4. **Covers R6.** Given a running MCP server, when the developer completes milestone 38 (agent test), they can ask "What color is the car?" about a processed video and get an answer with timestamps.
- AE5. **Covers R7.** Given a running agent, when the developer completes milestone 43 (API test), they can send a chat message via curl and get a response.
- AE6. **Covers R8.** Given a running API, when the developer completes milestone 56 (full user flow test), they can upload a video through the UI, ask a question, and see a clip extracted — all in the browser with the HAL 9000 theme.
- AE7. **Covers R9.** Given the full stack running, when the developer completes milestone 62 (final integration test), `docker compose up` starts everything and the system works from a clean state.

---

## Success Criteria

- Every one of the 63 milestones can be independently verified (run, screenshot, or record)
- The final product is functionally identical to the source Kubrick repo but under the clipagent identity
- Each milestone commit produces a working state — no broken intermediate states
- The full 63-milestone journey can be recorded as a series of demo videos for social/portfolio

---

## Scope Boundaries

### Deferred for later

- Monetization, pricing, or business model
- Cloud deployment or hosted version
- Multi-user / multi-tenant support
- Mobile app or responsive mobile-first design
- User research or validation interviews
- Competitive analysis against Descript, Opus Clip, Recall.ai
- CI/CD pipeline
- Automated test suite (unit, integration, e2e)
- Performance optimization or caching
- Internationalization / localization

### Outside this product's identity

- This is not a course or educational product — no notebooks, no step-by-step tutorials, no learning-oriented comments
- This is not a SaaS platform — no auth, no billing, no tenant isolation
- This is not a developer SDK/API product — the API is internal to the product, not exposed for third-party integration
- This is not a video editing tool — it searches and clips, not edits or renders

---

## Key Decisions

- **Same code, new identity**: The entire Kubrick codebase is kept intact. clipagent is a rebrand + restructure, not a rewrite.
- **Architecture-first build order**: Pipeline → MCP → Agent → API → UI → Observability. Each layer depends on the previous.
- **63 micro-milestones**: Every single step is its own milestone with a clear demo output.
- **Demo-first, user-second**: Primary goal is portfolio/social content. Product-market fit is not yet validated.
- **HAL 9000 theme retained**: The distinctive dark UI with red accents is a brand differentiator.

---

## Dependencies / Assumptions

- The source Kubrick repo code is functional and complete
- Groq API access is available for LLM inference
- OpenAI API access is available for CLIP embeddings, captioning, and transcription
- Opik account is available for observability
- Local machine can run Docker + Python 3.12.8 + Node.js for React
- FFmpeg is available for audio extraction

---

## Outstanding Questions

### Deferred to Planning

- [Needs research] Exact Pixeltable table schemas and column types from source repo
- [Needs research] Exact MCP tool schemas (input/output formats) from source repo
- [Needs research] Groq model configuration (which Llama 4 variant for which task)
- [Technical] Docker Compose service dependencies and port mapping
- [Technical] React build toolchain (Vite vs CRA) and dependency versions
