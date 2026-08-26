FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Note:
# ffmpeg should be installed at system level, such that av (pyav) can decode videos, sample frames and process images.
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install application dependencies
COPY . /app
WORKDIR /app
RUN uv sync --frozen --no-cache

# Run the FastMCP CLI
CMD ["/app/.venv/bin/python", "src/clipagent_mcp/server.py", "--port", "9090", "--host", "0.0.0.0", "--transport", "streamable-http"]
