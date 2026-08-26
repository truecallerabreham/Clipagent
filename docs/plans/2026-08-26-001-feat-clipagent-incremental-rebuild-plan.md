---
title: "feat: clipagent — Incremental Product Rebuild from Kubrick Course"
type: feat
status: active
date: 2026-08-26
origin: docs/brainstorms/2026-08-26-clipagent-rebuild-requirements.md
---

# clipagent — Incremental Product Rebuild

## Summary

Rebuild the multimodal-agents-course (Kubrick) as a standalone product called **clipagent**. Same codebase, same tech stack, restructured into 6 architectural layers with 63 micro-milestones. Each milestone produces a verifiable, demoable state for social/portfolio recording. The plan clones the source repo, rebrands it, and builds incrementally from the video processing pipeline up through observability.

---

## Problem Frame

The Kubrick course repo contains a fully functional Video-RAG system but is structured for learning (notebooks, tutorial comments, modular separation). The goal is to repackage this as a product called clipagent, built incrementally so each milestone produces something recordable. This is an exploratory product bet — the video search/clip extraction space has established players but no user pain was validated.

(see origin: `docs/brainstorms/2026-08-26-clipagent-rebuild-requirements.md`)

---

## Requirements

- R1. Project named "clipagent" with its own identity (see origin: R1)
- R2. 63 micro-milestones organized into 6 architectural layers (see origin: R2)
- R3. Each micro-milestone has clear "what was added" and "what's demoable now" (see origin: R3)
- R4. Layer 1: Video processing pipeline (15 milestones) (see origin: R4)
- R5. Layer 2: MCP server (13 milestones) (see origin: R5)
- R6. Layer 3: Agent (10 milestones) (see origin: R6)
- R7. Layer 4: FastAPI API (5 milestones) (see origin: R7)
- R8. Layer 5: React UI (13 milestones) (see origin: R8)
- R9. Layer 6: Observability + polish (6 milestones + 1 prep = 7) (see origin: R9)
- R10-R18. Tech stack: Python 3.12, uv, Pixeltable, FastMCP, FastAPI, Groq, OpenAI, Opik, React, Docker (see origin: R10-R18)
- R19-R21. Each milestone demoable; early layers front-loaded; final state end-to-end (see origin: R19-R21)
- R22-R25. Same code, local Docker only, desktop web, single-user (see origin: R22-R25)

**Origin actors:** A1 (Developer), A2 (End user — future, not validated)
**Origin flows:** F1 (Milestone build + demo record), F2 (Video search + clip extraction)
**Origin acceptance examples:** AE1-AE7

---

## Scope Boundaries

### Deferred for later

- Monetization, pricing, or business model
- Cloud deployment or hosted version
- Multi-user / multi-tenant support
- Mobile app
- User research or validation interviews
- Competitive analysis against Descript, Opus Clip, Recall.ai
- CI/CD pipeline
- Automated test suite (unit, integration, e2e)
- Performance optimization or caching
- Internationalization / localization

### Outside this product's identity

- Not a course or educational product — no notebooks, no tutorials
- Not a SaaS platform — no auth, no billing, no tenant isolation
- Not a developer SDK/API product — API is internal
- Not a video editing tool — searches and clips only

### Deferred to Follow-Up Work

- Groq model migration: source uses deprecated llama-4-scout/maverick; plan uses current models with config-layer abstraction for future swaps

---

## Context & Research

### Relevant Code and Patterns

- **Source repo:** `https://github.com/the-ai-merge/multimodal-agents-course` — 3-service architecture (kubrick-mcp, kubrick-api, kubrick-ui)
- **MCP server pattern:** FastMCP with 4 tools, 1 resource, 3 prompts; streamable-http transport on port 9090
- **Agent pattern:** Abstract BaseAgent → GroqAgent; tool-use loop with routing → tool selection → execution → response
- **API pattern:** FastAPI with /chat, /process-video, /upload-video, /reset-memory, /task-status, /media endpoints on port 8080
- **UI pattern:** React + Vite + Tailwind + shadcn/ui; HAL 9000 dark theme; nginx reverse proxy on port 3000
- **Docker pattern:** 3 containers, shared_network, shared_media volume, health checks

### Institutional Learnings

- No local learnings (greenfield project)

### External References

- FastMCP v2.5+ patterns: tools as primitives, rich outputs, prompt versioning
- Pixeltable: FrameIterator for frame sampling, embedding indexes for multimodal search
- Groq model deprecation: llama-4-scout (shut down Jul 17, 2026) — use openai/gpt-oss-120b or qwen/qwen3.6-27b instead
- HAL 9000 UI: monochromatic red-on-black, CRT scanlines, minimal chrome

---

## Key Technical Decisions

- **Clone + rebrand over rewrite:** Clone the source repo, rename all `kubrick` references to `clipagent`, keep all code intact. Minimizes risk and maximizes speed.
- **Groq model config abstraction:** Source uses deprecated models. Create a config layer that maps model roles (routing, tool-use, general) to model IDs, so models can be swapped without code changes. Default to current stable models.
- **Architecture-first build order:** Pipeline → MCP → Agent → API → UI → Observability. Each layer depends on the previous. This is the natural dependency chain.
- **63 micro-milestones with verification:** Each milestone is a single step with a clear demo output. The plan organizes these into 6 phases (one per layer).
- **Shared Docker volume:** All services share a `shared_media` volume for video files and processed clips, matching the source architecture.

---

## Open Questions

### Resolved During Planning

- **Groq model selection:** Source uses deprecated llama-4-scout/maverick. Resolution: Use config abstraction with current stable models (openai/gpt-oss-120b for tool-use, qwen/qwen3.6-27b for general). Swap is config-only.
- **Project structure:** Source has kubrick-mcp/, kubrick-api/, kubrick-ui/. Resolution: Rename to clipagent-mcp/, clipagent-api/, clipagent-ui/ to match product identity.
- **Docker Compose ports:** MCP on 9090, API on 8080, UI on 3000. Keep same ports for compatibility.

### Deferred to Implementation

- Exact Pixeltable table schemas — will be copied from source during clone
- Exact MCP tool input/output formats — will be copied from source during clone
- React component details — will be copied from source during clone

---

## High-Level Technical Design

> *This illustrates the intended architecture and is directional guidance for review, not implementation specification.*

```
┌─────────────────────────────────────────────────────────────────┐
│                        clipagent-ui                             │
│                    React + Vite + Tailwind                      │
│                    HAL 9000 dark theme                          │
│                    Port 3000 (nginx)                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP REST
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       clipagent-api                             │
│                  FastAPI + Custom Agent                         │
│              Groq LLM (tool-use loop)                          │
│              Memory (Pixeltable)                                │
│              Port 8080                                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MCP (streamable-http)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      clipagent-mcp                              │
│                 FastMCP Server                                  │
│            4 Tools + 1 Resource + 3 Prompts                    │
│         Video Processing Pipeline                               │
│         Pixeltable (indexes)                                    │
│              Port 9090                                          │
└─────────────────────────────────────────────────────────────────┘
                           │
                    shared_media volume
                  (video files + clips)
```

**Data flow:**
1. User uploads video via UI → API receives → background task processes via MCP
2. MCP processes: extract audio → transcribe → sample frames → caption → embed → index in Pixeltable
3. User asks question / provides image → API agent routes → selects MCP tool → tool searches Pixeltable → returns clip or answer
4. Agent generates natural language response → returned to UI

---

## Screenshot Policy

Each milestone is classified as either requiring a screenshot or not:

- **SCREENSHOT** — Milestone produces visible output that demonstrates progress (terminal output, file creation, UI state, API response). Save to `docs/screenshots/M{N}-{description}.png`
- **NO SCREENSHOT** — Milestone is structural/boilerplate only (init files, directory creation, config changes with no visible output)

| Layer | Milestones needing screenshots |
|-------|-------------------------------|
| Layer 1 (Pipeline) | M1 (imports), M3 (Pixeltable init), M4 (upload), M5 (audio), M6 (transcription), M7 (frames), M8 (captions), M11 (schema), M13 (full pipeline), M15 (docs) |
| Layer 2 (MCP) | M17 (server start), M19 (process_video), M22 (text search), M24 (image search), M26 (Q&A), M28 (full MCP test) |
| Layer 3 (Agent) | M30 (tool-use loop), M34 (Groq integration), M38 (agent end-to-end) |
| Layer 4 (API) | M39 (FastAPI + Swagger), M43 (full API test) |
| Layer 5 (UI) | M44 (React dev server), M53 (frontend↔API), M56 (full user flow) |
| Layer 6 (Polish) | M57 (Opik traces), M60 (Docker Compose), M62 (final integration) |

---

## Implementation Units

### U1. Layer 1 — Video Processing Pipeline (Milestones 1-15)

**Goal:** Set up the project skeleton and build a complete video processing pipeline that can upload, transcribe, sample, caption, embed, and index videos.

**Requirements:** R1, R2, R3, R4, R10, R11, R15

**Dependencies:** None (first layer)

**Files:**
- Create: `clipagent-mcp/` (cloned from `kubrick-mcp/`)
- Create: `clipagent-api/` (cloned from `kubrick-api/`)
- Create: `clipagent-ui/` (cloned from `kubrick-ui/`)
- Modify: All `pyproject.toml` files (rename kubrick → clipagent)
- Modify: All Python source files (rename kubrick_mcp → clipagent_mcp, kubrick_api → clipagent_api)
- Create: `README.md`, `docker-compose.yml`, `Makefile`, `.env.example`

**Approach:**
1. Clone the source repo into the clipagent workspace
2. Rename all `kubrick` references to `clipagent` (package names, imports, Docker service names, config keys)
3. Strip educational scaffolding (notebooks, tutorial comments, learning-oriented docs)
4. Build the video processing pipeline step by step, verifying each micro-milestone

**Micro-milestones (15 steps):**

| # | Milestone | What's demoable | Screenshot |
|---|-----------|-----------------|------------|
| 1 | Initialize Python project (pyproject.toml, directory structure) | `uv sync` succeeds, project imports | YES |
| 2 | Add Docker config (Dockerfile, docker-compose) | `docker build` succeeds for MCP service | NO |
| 3 | Install + configure Pixeltable | `import pixeltable` works, DB initializes | YES |
| 4 | Create video upload function | Upload a video file, confirm stored on disk | YES |
| 5 | Create audio extraction (ffmpeg) | Video in → audio file out | YES |
| 6 | Create audio transcription (Groq Whisper) | Audio in → text transcript out | YES |
| 7 | Create frame sampling (Pixeltable FrameIterator) | Video in → key frames extracted | YES |
| 8 | Create frame captioning (gpt-4o-mini) | Frame in → text description out | YES |
| 9 | Create CLIP embedding for frames | Frame in → vector out | NO |
| 10 | Create text embedding for captions | Caption in → vector out | NO |
| 11 | Create Pixeltable table schema | Tables created with correct columns | YES |
| 12 | Create pipeline orchestration | One function runs all steps end-to-end | NO |
| 13 | Pipeline test with sample video | Upload video → see full output in Pixeltable | YES |
| 14 | Error handling | Graceful failures on bad input (corrupt file, missing audio) | NO |
| 15 | Pipeline documentation | README with usage examples | YES |

**Patterns to follow:**
- Source: `kubrick-mcp/src/kubrick_mcp/video/ingestion/video_processor.py` — VideoProcessor class
- Source: `kubrick-mcp/src/kubrick_mcp/video/ingestion/constants.py` — embedding model configs
- Source: `kubrick-mcp/src/kubrick_mcp/config.py` — pydantic-settings pattern

**Test scenarios:**
- Happy path: Upload a 30-second MP4 → audio extracted, transcription returned, 5-10 frames sampled, each captioned, embeddings created, all stored in Pixeltable
- Edge case: Upload a video with no audio track → pipeline completes without audio transcription step
- Edge case: Upload a very short video (<2 seconds) → pipeline handles minimal frame count
- Error path: Upload a corrupt file → pipeline returns meaningful error, no partial state
- Integration: Pipeline orchestration runs all steps in sequence, each step's output feeds the next

**Verification:**
- `uv sync` succeeds in clipagent-mcp/
- `docker build -t clipagent-mcp .` succeeds
- Running the pipeline on a sample video produces transcribed text, sampled frames, captions, and embeddings visible in Pixeltable

---

### U2. Layer 2 — MCP Server (Milestones 16-28)

**Goal:** Wrap the video processing pipeline in an MCP server with 4 tools, 1 resource, and 3 prompts, all discoverable via MCP Inspector.

**Requirements:** R5, R12

**Dependencies:** U1

**Files:**
- Modify: `clipagent-mcp/src/clipagent_mcp/server.py` — FastMCP entry point
- Modify: `clipagent-mcp/src/clipagent_mcp/tools.py` — 4 MCP tools
- Modify: `clipagent-mcp/src/clipagent_mcp/resources.py` — list_tables resource
- Modify: `clipagent-mcp/src/clipagent_mcp/prompts.py` — 3 prompts with Opik versioning
- Modify: `clipagent-mcp/src/clipagent_mcp/config.py` — settings

**Approach:**
1. Set up FastMCP server skeleton on port 9090
2. Implement each tool one at a time: process_video → get_clip_from_text → get_clip_from_image → ask_about_video
3. Add resources and prompts
4. Test each tool with MCP Inspector

**Micro-milestones (13 steps):**

| # | Milestone | What's demoable | Screenshot |
|---|-----------|-----------------|------------|
| 16 | FastMCP install | `import fastmcp` works | NO |
| 17 | Server skeleton | Server starts, responds to MCP ping | YES |
| 18 | `process_video` tool schema | Tool appears in MCP Inspector | NO |
| 19 | `process_video` handler | Call tool → video processes | YES |
| 20 | Video metadata resource | List processed videos from registry | NO |
| 21 | `get_clip_from_text` schema | Tool appears in Inspector | NO |
| 22 | `get_clip_from_text` handler | Text in → clip out | YES |
| 23 | `get_clip_from_image` schema | Tool appears in Inspector | NO |
| 24 | `get_clip_from_image` handler | Image in → clip out | YES |
| 25 | `ask_about_video` schema | Tool appears in Inspector | NO |
| 26 | `ask_about_video` handler | Question in → answer with timestamps out | YES |
| 27 | Opik prompt versioning | Prompts stored and versioned in Opik | NO |
| 28 | MCP Inspector full test | All 4 tools work from Inspector | YES |

**Patterns to follow:**
- Source: `kubrick-mcp/src/kubrick_mcp/server.py` — FastMCP server setup
- Source: `kubrick-mcp/src/kubrick_mcp/tools.py` — tool implementations
- Source: `kubrick-mcp/src/kubrick_mcp/resources.py` — resource pattern
- Source: `kubrick-mcp/src/kubrick_mcp/prompts.py` — Opik versioning pattern

**Test scenarios:**
- Happy path: Start server → MCP Inspector shows 4 tools, 1 resource, 3 prompts
- Happy path: Call `process_video` with a video path → video processed, tables populated
- Happy path: Call `get_clip_from_user_query` with "the car scene" → returns 5-10 second clip
- Happy path: Call `get_clip_from_image` with a reference image → returns matching clip
- Happy path: Call `ask_question_about_video` with "What color is the shirt?" → returns answer with timestamps
- Edge case: Call tool with unprocessed video → error message indicating video not indexed
- Integration: All tools share the same Pixeltable database and video registry

**Verification:**
- MCP Inspector at `npx @modelcontextprotocol/inspector` shows all tools/resources/prompts
- Each tool returns correct results for a sample video
- Opik dashboard shows versioned prompts

---

### U3. Layer 3 — Agent (Milestones 29-38)

**Goal:** Build a custom agent with tool-use loop, MCP client, Groq LLM integration, and conversation memory.

**Requirements:** R6, R14

**Dependencies:** U2

**Files:**
- Create: `clipagent-api/src/clipagent_api/agent/base_agent.py` — abstract agent
- Create: `clipagent-api/src/clipagent_api/agent/groq/groq_agent.py` — Groq implementation
- Create: `clipagent-api/src/clipagent_api/agent/groq/groq_tool.py` — MCP→Groq tool translation
- Create: `clipagent-api/src/clipagent_api/agent/memory.py` — Pixeltable memory
- Create: `clipagent-api/src/clipagent_api/config.py` — agent config

**Approach:**
1. Create BaseAgent abstract class with MCP client setup
2. Implement tool-use loop (observe → decide → act)
3. Connect to MCP server, discover tools, translate to Groq format
4. Add Groq LLM integration with conversation history
5. Add Pixeltable-backed memory persistence

**Micro-milestones (10 steps):**

| # | Milestone | What's demoable | Screenshot |
|---|-----------|-----------------|------------|
| 29 | BaseAgent class skeleton | Instantiate, see basic loop structure | NO |
| 30 | Tool-use loop (observe→decide→act) | Agent picks a tool based on input | YES |
| 31 | MCP client class | Connects to MCP server at port 9090 | NO |
| 32 | Tool discovery | Agent lists available MCP tools | NO |
| 33 | GroqTool converter | MCP tools become Groq-compatible format | NO |
| 34 | Groq LLM integration | Agent generates responses via Groq | YES |
| 35 | Conversation history | Multi-turn conversation works | NO |
| 36 | Pixeltable memory table | Memory table created with schema | NO |
| 37 | Memory persistence | Conversation survives restart | NO |
| 38 | Agent end-to-end test | Ask about video → get answer with timestamps | YES |

**Patterns to follow:**
- Source: `kubrick-api/src/kubrick_api/agent/base_agent.py` — abstract agent pattern
- Source: `kubrick-api/src/kubrick_api/agent/groq/groq_agent.py` — routing/tool-use/general modes
- Source: `kubrick-api/src/kubrick_api/agent/groq/groq_tool.py` — MCP→Groq translation
- Source: `kubrick-api/src/kubrick_api/agent/memory.py` — Pixeltable memory

**Test scenarios:**
- Happy path: Agent receives "What color is the car?" → routes to tool-use → calls ask_about_video → returns answer
- Happy path: Agent receives "Hello" → routes to general chat → returns conversational response
- Happy path: Multi-turn conversation → agent remembers previous context
- Edge case: MCP server unavailable → agent returns graceful error
- Edge case: Tool returns empty results → agent generates "no results found" response
- Integration: Agent ↔ MCP server connection established, tools discovered, calls succeed

**Verification:**
- Agent can chat conversationally
- Agent can answer questions about processed videos
- Conversation history persists across restarts
- Memory table exists in Pixeltable with correct schema

---

### U4. Layer 4 — FastAPI API (Milestones 39-43)

**Goal:** Expose the agent over HTTP with a clean API surface and interactive docs.

**Requirements:** R7, R13

**Dependencies:** U3

**Files:**
- Create: `clipagent-api/src/clipagent_api/api.py` — FastAPI app
- Create: `clipagent-api/src/clipagent_api/models.py` — Pydantic models

**Approach:**
1. Initialize FastAPI app with lifespan management
2. Create /chat endpoint (main agent interaction)
3. Create /videos endpoint (list processed videos)
4. Create /upload endpoint (upload video)
5. Add Swagger UI configuration

**Micro-milestones (5 steps):**

| # | Milestone | What's demoable | Screenshot |
|---|-----------|-----------------|------------|
| 39 | FastAPI app init | Server starts, Swagger at `/docs` | YES |
| 40 | `/chat` endpoint | Send message → get agent response | NO |
| 41 | `/videos` endpoint | List processed videos as JSON | NO |
| 42 | `/upload` endpoint | Upload video via multipart form | NO |
| 43 | API test with curl | All endpoints respond correctly | YES |

**Patterns to follow:**
- Source: `kubrick-api/src/kubrick_api/api.py` — FastAPI endpoints, background tasks, task status tracking

**Test scenarios:**
- Happy path: POST /chat with {"message": "What color is the car?"} → agent response with answer
- Happy path: GET /videos → JSON list of processed videos
- Happy path: POST /upload with video file → upload confirmed, processing starts
- Edge case: POST /chat with empty message → 422 validation error
- Edge case: POST /upload with non-video file → 400 bad request
- Integration: /chat endpoint triggers agent which calls MCP tools

**Verification:**
- `curl http://localhost:8080/docs` shows Swagger UI
- All endpoints return correct responses
- /chat triggers full agent → MCP → pipeline flow

---

### U5. Layer 5 — React UI (Milestones 44-56)

**Goal:** Build a complete React frontend with upload, chat, video player, clip preview, and HAL 9000 theme.

**Requirements:** R8, R17

**Dependencies:** U4

**Files:**
- Create: `clipagent-ui/src/` — React application
- Create: `clipagent-ui/src/components/` — UI components
- Create: `clipagent-ui/src/styles/` — HAL 9000 theme CSS
- Create: `clipagent-ui/Dockerfile` — multi-stage build
- Create: `clipagent-ui/nginx.conf` — reverse proxy

**Approach:**
1. Initialize React project with Vite + Tailwind
2. Build core components: upload, chat, video player, clip preview
3. Connect to API backend
4. Apply HAL 9000 dark theme
5. Test full user flow

**Micro-milestones (13 steps):**

| # | Milestone | What's demoable | Screenshot |
|---|-----------|-----------------|------------|
| 44 | React project init | Dev server starts at localhost:5173 | YES |
| 45 | App layout | Basic page structure renders (header, sidebar, main) | NO |
| 46 | Video upload (drag-and-drop) | Drag video file → upload starts | NO |
| 47 | Upload progress bar | Progress indicator shows during upload | NO |
| 48 | Chat message component | Messages render in chat bubbles | NO |
| 49 | Chat input component | Type and send messages | NO |
| 50 | Video player | Play uploaded video in browser | NO |
| 51 | Clip preview + download | See and save extracted clips | NO |
| 52 | Video library sidebar | List of processed videos in sidebar | NO |
| 53 | Frontend↔API connection | Chat works end-to-end through API | YES |
| 54 | HAL 9000 theme | Dark UI, red accents, monospace fonts | YES |
| 55 | Responsive layout | Works on different screen sizes | NO |
| 56 | Full user flow test | Upload → process → search → clip in browser | YES |

**Patterns to follow:**
- Source: `kubrick-ui/src/` — React components, hooks, pages
- HAL 9000 theme: `#ff1a1a` red on `#0a0a0a` black, Share Tech Mono font, CRT scanline overlay

**Test scenarios:**
- Happy path: Upload video → progress bar → video appears in library
- Happy path: Type question → see response with clip preview
- Happy path: Click video in sidebar → video plays in player
- Happy path: Click clip → preview plays → download button works
- Edge case: Upload fails → error message displayed
- Edge case: API unavailable → connection error message
- Integration: Full flow upload → process → search → clip → download

**Verification:**
- Dev server starts and renders UI
- All components render correctly with HAL 9000 theme
- Full user flow works end-to-end in browser
- `docker compose up` serves the UI at localhost:3000

---

### U6. Layer 6 — Observability + Polish (Milestones 57-63)

**Goal:** Add observability, error logging, Docker Compose orchestration, documentation, and final integration testing.

**Requirements:** R9, R16, R18

**Dependencies:** U5

**Files:**
- Modify: All services — add Opik tracing
- Create: `docker-compose.yml` — full stack orchestration
- Create: `README.md` — project documentation
- Create: `.env.example` — environment variable template

**Approach:**
1. Integrate Opik SDK across all services
2. Add custom trace spans for tool calls
3. Add error logging
4. Set up Docker Compose for full stack
5. Write setup documentation
6. Final integration test
7. Demo recording preparation

**Micro-milestones (7 steps):**

| # | Milestone | What's demoable | Screenshot |
|---|-----------|-----------------|------------|
| 57 | Opik SDK integration | Traces appear in Opik dashboard | YES |
| 58 | Custom trace spans | Each MCP tool call is traced | NO |
| 59 | Error logging | Errors captured and displayed in logs | NO |
| 60 | Docker Compose full stack | `docker compose up` runs all 3 services | YES |
| 61 | Setup documentation | Another developer can run from README | NO |
| 62 | Final integration test | Full system works from clean state | YES |
| 63 | Demo recording prep | Clean state ready for screen recording | NO |

**Patterns to follow:**
- Source: `kubrick-api/src/kubrick_api/opik_utils.py` — Opik tracing helpers
- Source: `docker-compose.yml` — 3-service orchestration with shared volumes

**Test scenarios:**
- Happy path: `docker compose up` → all 3 services start, health checks pass
- Happy path: Upload video through UI → traces appear in Opik
- Happy path: Full flow → all steps traced in Opik dashboard
- Error path: Service crashes → error logged, other services remain healthy
- Integration: Clean clone → `docker compose up` → upload → search → clip → all works

**Verification:**
- `docker compose up` starts all services without errors
- Opik dashboard shows traces for agent interactions
- README contains complete setup instructions
- Full flow works from a clean state

---

## System-Wide Impact

- **Interaction graph:** UI → API (HTTP) → MCP (streamable-http) → Pixeltable (local DB). All three services must be running for full functionality.
- **Error propagation:** MCP errors bubble through agent to API to UI. Each layer should handle upstream failures gracefully.
- **State lifecycle risks:** Pixeltable DB is shared between MCP and API via Docker volume. Race conditions possible if both write simultaneously (unlikely in single-user mode).
- **API surface parity:** UI is the only consumer; no external API consumers to maintain parity with.
- **Integration coverage:** Full flow (upload → process → search → clip) requires all 3 services + shared volume. Unit tests alone won't prove this.
- **Unchanged invariants:** The source code's functional behavior is preserved. Only names, structure, and educational scaffolding change.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Groq model deprecation (llama-4-scout shut down Jul 17, 2026) | Config-layer abstraction; default to current stable models (openai/gpt-oss-120b, qwen/qwen3.6-27b) |
| Source repo may have hidden bugs or missing features | Test each milestone independently; verify against source behavior |
| Docker resource limits (MCP needs 4GB RAM for video processing) | Document in README; set resource limits in docker-compose.yml |
| Pixeltable version compatibility | Pin versions in pyproject.toml; test with source repo's versions first |
| OpenAI API costs for captioning/embedding | Use sample videos only; document cost estimates in README |

---

## Documentation / Operational Notes

- **README.md:** Setup instructions, environment variables, Docker usage, architecture overview
- **.env.example:** Template for required API keys (OPENAI_API_KEY, GROQ_API_KEY, OPIK_API_KEY, OPIK_WORKSPACE, OPIK_PROJECT)
- **Makefile:** build, start, stop commands (matching source pattern)
- **Each milestone:** Committed with descriptive message noting which milestone was completed

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-08-26-clipagent-rebuild-requirements.md`
- **Source repo:** `https://github.com/the-ai-merge/multimodal-agents-course`
- **FastMCP docs:** `https://github.com/jlowin/fastmcp`
- **Pixeltable docs:** `https://github.com/pixeltable/pixeltable`
- **Groq models:** `https://console.groq.com/docs/models` (check current stable models)
- **Opik docs:** `https://www.comet.com/docs/opik/`
