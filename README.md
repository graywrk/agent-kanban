# Agent Kanban

An AI-native kanban board where agents (Codex, Hermes, etc.) pull tasks via
the Model Context Protocol. The board is passive — it never spawns or controls
agents. You point your agents at the board via MCP config, and they
self-serve tasks through `get_next_task` / `claim_task`.

## Architecture

See `docs/superpowers/specs/2026-07-05-agent-kanban-design.md` for the full
design. Phase 1 MVP scope is documented in
`docs/superpowers/plans/2026-07-06-agent-kanban-phase1-mvp.md`.

## Quickstart (local dev)

### Prerequisites
- Python 3.11+
- `uv` (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 20+ and `pnpm`
- PostgreSQL 16+ running locally

### 1. Database
```bash
createdb kanban  # or use docker: see docker-compose.yml
cp .env.example .env  # DATABASE_URL defaults to port 5436 (matches docker-compose ak-pg)
uv run kanban migrate
```

### 2. Backend
```bash
uv sync --extra dev
uv run kanban serve
```

### 3. Frontend (separate terminal)
```bash
cd web
pnpm install
pnpm dev   # http://localhost:5173, proxies to :7331
```

### 4. Point an agent at the board
Add to your agent's MCP config:

**Codex** (`~/.codex/config.toml`):
```toml
[mcp_servers.kanban]
url = "http://localhost:7331/mcp"
```

**Hermes** (`~/.hermes/config.yaml`):
```yaml
mcp_servers:
  kanban:
    url: http://localhost:7331/mcp
```

Then instruct your agent: "Check the kanban board for tasks via get_next_task."

## Docker
```bash
docker compose up -d
```
Runs the app on :7331 and Postgres on :5436 (host port).
