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

## Agent workflow

1. Create a task in the UI. It starts in `todo`.
2. Drag it to the `READY` column. It's now available to agents via `get_next_task`.
3. Instruct your agent (e.g. Codex, Hermes) to check the board:
   - Call `get_next_task` to discover work.
   - Call `claim_task` to take it.
   - Call `post_progress` to report what it's doing.
   - Call `request_review` when ready for your review, or `complete_task` when done.
4. Watch progress events stream into the card detail view in real time.
5. Add comments to give the agent follow-up instructions; the agent reads them via `get_comments`.

Agents must pass their identifier as the `agent` argument to mutation tools
(`claim_task`, `post_progress`, `complete_task`, `request_review`, `post_comment`,
`post_artifact`, `set_task_branch`, `set_task_pr`). The board authorizes mutations
by checking `claimed_by == agent`.

## Coding tasks (git/PR)

For tasks that touch a git repo, set `repo_path` and `base_branch` when creating
the task. The board does NOT create branches or PRs — your agent does that with
its own git tools. The board records what the agent reports and renders a review
diff.

Agent workflow for a coding task:
1. `claim_task` — receives `repo_path` and (if set) `base_branch`.
2. Create a branch in `repo_path` with the agent's git tool.
3. `set_task_branch(task_id, agent, branch)` — record it so the UI shows it and
   the diff can be collected.
4. Commit work on that branch.
5. `request_review(task_id, agent, summary)` — the board runs
   `git -C <repo_path> diff <base>...<branch>` once and stores the result as a
   diff event visible in the card's progress feed.
6. Open a PR with the agent's GitHub tool, then
   `set_task_pr(task_id, agent, pr_url, "open")`.
7. When merged, `set_task_pr(task_id, agent, pr_url, "merged")` then
   `complete_task`.

If `repo_path`, `base_branch` (or the project's `default_branch`), or `branch` is
missing, diff collection is skipped silently. If `git diff` fails, an error event
is recorded instead, but the review request itself still succeeds.

## Authentication

The board requires authentication. Two kinds of principals:

- **Users** (humans): log in with username + password via the web UI. Sessions are signed cookies.
- **Tokens** (agents): opaque bearer tokens, managed in the Admin panel. Each token is bound to an `agent_name`.

### First run

On first startup with an empty database, the board auto-creates an `admin` user and prints a random password to stdout once. Set `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` to choose it yourself. Log in, then go to Admin → Users to add more users, and Admin → Tokens to mint tokens for your agents.

### Pointing an agent at the board

Agents authenticate via a bearer token. In your agent's MCP config:

**Codex** (`~/.codex/config.toml`):
```toml
[mcp_servers.kanban]
url = "http://your-host:7331/mcp"
# Codex reads headers from config in newer versions; otherwise set the auth via env.
headers = { Authorization = "Bearer <your-token>" }
```

**Hermes** (`~/.hermes/config.yaml`):
```yaml
mcp_servers:
  kanban:
    url: http://your-host:7331/mcp
    headers:
      Authorization: Bearer <your-token>
```

The token's `agent_name` MUST match the `agent` argument you pass to MCP tools. A token minted with `agent_name=codex` can call `claim_task(agent="codex")` but NOT `claim_task(agent="hermes")`.

### Production env vars

- `SESSION_SECRET` — signing key for session cookies. REQUIRED in production; set a long random string.
- `PUBLIC_URL` — the public base URL (e.g. `https://kanban.example.com`). Controls cookie `Secure` flag.
- `AGENT_KANBAN_BOOTSTRAP_ADMIN_PASSWORD` — first-run admin password (optional; auto-generated if unset).

## Docker
```bash
docker compose up -d
```
Runs the app on :7331 with Postgres in an internal-only container (not exposed to
the host). The app connects to it over the compose network as `postgres:5432`.
For local dev against a host-visible Postgres, see the standalone container note
in "Database" above (port 5436).
