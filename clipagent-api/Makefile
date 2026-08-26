CHECK_DIRS := .

# --- Ruff ---

format-fix:
	uv run ruff format $(CHECK_DIRS) 
	uv run ruff check --select I --fix

lint-fix:
	uv run ruff check --fix

format-check:
	uv run ruff format --check $(CHECK_DIRS) 
	uv run ruff check -e
	uv run ruff check --select I -e

lint-check:
	uv run ruff check $(CHECK_DIRS)

# --- MCP Server ---

start-clipagent-api: stop-clipagent-api
	docker build -t clipagent-api . && \
	docker run -d -p 8080:8080 --name clipagent-api --env-file .env clipagent-api

stop-clipagent-api:
	docker stop clipagent-api || true && \
	docker rm clipagent-api || true
