# clipagent

A video search and clip extraction tool. Upload videos, ask questions in natural language, and extract clips by text or image similarity.

## Architecture

```
clipagent-ui (React) → clipagent-api (FastAPI) → clipagent-mcp (FastMCP) → Pixeltable
```

## Tech Stack

- **Backend:** Python 3.12, FastMCP, Pixeltable, FastAPI
- **LLM:** Groq (Llama 4), OpenAI (CLIP, captioning, transcription)
- **Frontend:** React, Vite, Tailwind CSS
- **Observability:** Opik
- **Deployment:** Docker Compose

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in API keys
3. Run `docker compose up`
4. Open `http://localhost:3000`

## Development

See `docs/plans/` for the full implementation plan with 63 micro-milestones.

## License

Apache-2.0
