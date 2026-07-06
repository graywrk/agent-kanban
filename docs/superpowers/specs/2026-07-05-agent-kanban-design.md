# Agent Kanban — Design Spec

**Date:** 2026-07-05
**Status:** Approved (pending implementation)
**Author:** graywrk (with ZCode brainstorming)

---

## 1. Purpose

A self-hosted **kanban board for AI agents**. The board is a passive storage layer that agents read from and write to via the Model Context Protocol (MCP). Agents claim tasks, post progress, and complete them; the board never spawns processes, manages lifecycles, or controls agents.

The board serves two agent classes:
- **Coding agents** (Codex/ZCode) — work in a repo, optionally tied to a branch/PR.
- **General-purpose agents** (Hermes and similar) — research, documents, automation, etc.

Inspired by [BloopAI/vibe-kanban](https://github.com/BloopAI/vibe-kanban), but with a fundamentally different architecture: **pull-based (board = MCP server)** instead of push-based (orchestrator spawns agents). This drops most of vibe-kanban's complexity (worktree lifecycle, process management, preview proxy, terminal) in exchange for visibility limited to what agents self-report.

---

## 2. Non-goals

These are explicitly out of scope and distinguish this project from vibe-kanban:

- Spawning or managing agent processes.
- Git worktree creation/lifecycle. Agents create branches/worktrees themselves; the board only records the paths.
- Running setup/dev/cleanup scripts.
- Live stdout streaming from agents (no `<stdout>` block, no tool-call transcript mirroring).
- Preview browser or embedded terminal.
- PR polling/monitoring against GitHub.
- Auth and multi-user (single-user in scope; can be added later).
- Cloud sync, WebRTC, tunneling, relay.
- Analytics (PostHog/Sentry).

---

## 3. High-level architecture

```
┌──────────────────────────────────────────────────┐
│             Browser (React SPA)                   │
│   Board │ Card detail (progress feed) │ Comments │
└───────────────────┬──────────────────────────────┘
                    │ REST + WebSocket
                    ▼
┌──────────────────────────────────────────────────┐
│        Board Server (FastAPI, Python)             │
│                                                   │
│   ┌──────────────┐   ┌──────────────────────┐    │
│   │ REST/WS API  │   │  MCP server          │    │
│   │ (for UI)     │   │  (HTTP/SSE + stdio)  │    │
│   └──────────────┘   └──────────────────────┘    │
│              both read/write ↓                    │
│        ┌──────────────────────┐                   │
│        │  PostgreSQL          │                   │
│        └──────────────────────┘                   │
└──────────────────────────────────────────────────┘
                    ▲
                    │ MCP protocol (stdio or HTTP)
        ┌───────────┴───────────┐
        │                       │
   ┌────┴─────┐           ┌─────┴─────┐
   │  Codex   │           │  Hermes   │   ← user runs these manually,
   │ (MCP     │           │ (MCP      │     points them at the board's
   │  client) │           │  client)  │     MCP server in their config
   └──────────┘           └───────────┘
```

**Principles:**

1. **Board is passive.** No process spawning, no scheduling, no lifecycle control of agents. The board stores tasks, exposes an MCP interface, and serves a UI reading the same database.
2. **Two equal front-ends to the same database:**
   - **MCP server** — for agents (the tools defined in §5).
   - **REST/WS API** — for the web UI.
3. **Agents start work manually.** The user runs `codex`, `hermes`, etc., and instructs them to pull work from the board via `get_next_task`. There is no scheduler.
4. **Visibility is opt-in by the agent.** The board only knows what the agent reports through `post_progress`. There is no live stdout capture.
5. **Single board process, one database.** All agents talk to the same server (HTTP/SSE) or through the `kanban-mcp` stdio bridge that proxies to that server. PostgreSQL's MVCC handles concurrent agent writes without lock contention.

---

## 4. Data model (PostgreSQL + sqlmodel)

### 4.1 Tables

```sql
projects
  id              INTEGER PK
  name            TEXT
  repo_path       TEXT NULL          -- optional, for grouping coding tasks
  default_branch  TEXT NULL
  created_at      TIMESTAMP

tasks
  id              INTEGER PK
  project_id      INTEGER FK NULL
  title           TEXT
  description     TEXT                -- markdown
  status          TEXT                -- todo | ready | in_progress | review | done | blocked | cancelled
  tags            JSONB               -- array of strings, e.g. ["frontend","ui"]; GIN-indexable
  claimed_by      TEXT NULL           -- free-form agent identifier
  claimed_at      TIMESTAMP NULL
  sort_order      REAL
  repo_path       TEXT NULL           -- Phase 3: where the agent works
  base_branch     TEXT NULL           -- Phase 3: diff base; falls back to projects.default_branch
  branch          TEXT NULL           -- Phase 3: working branch (set by agent)
  pr_url          TEXT NULL           -- Phase 3
  pr_status       TEXT NULL           -- Phase 3: open | merged | closed
  created_at      TIMESTAMP
  updated_at      TIMESTAMP

progress_events
  id              INTEGER PK
  task_id         INTEGER FK
  agent           TEXT                -- who wrote it (= claimed_by at time of write)
  kind            TEXT                -- text | diff | artifact_ref | error | status_change
  payload         JSONB               -- {content, ...} shape depends on kind (see §4.3)
  created_at      TIMESTAMP

comments
  id              INTEGER PK
  task_id         INTEGER FK
  author          TEXT                -- "user" or an agent identifier
  content         TEXT                -- markdown
  seen_by_agent   BOOLEAN             -- read receipt for agents
  created_at      TIMESTAMP

artifacts
  id              INTEGER PK
  task_id         INTEGER FK
  path            TEXT                -- filesystem path (within an allow-listed root)
  kind            TEXT                -- diff.patch | log | screenshot | file | ...
  description     TEXT NULL
  created_at      TIMESTAMP
```

### 4.2 Status semantics

| Status | Meaning | Who can set |
|---|---|---|
| `todo` | Created, not ready for agents | user (via UI) |
| `ready` | Ready to be claimed via `get_next_task` | user (drag in UI), or board on reopen |
| `in_progress` | Agent has claimed it | agent (via `claim_task`) |
| `review` | Agent finished and requested review | agent (via `request_review`) |
| `done` | Completed | agent (via `complete_task`), or user |
| `blocked` | Agent reports being blocked, needs human | agent (via `post_progress` status_change), or user |
| `cancelled` | Abandoned | user |

`get_next_task` returns only `ready` tasks. The `todo → ready` transition is the user's signal that a task is fully specified and ready to be picked up.

### 4.3 `progress_events.payload` shapes by `kind`

- `text` — `{"content": "reading src/App.tsx"}`
- `diff` — `{"content": "<raw diff>", "files": ["src/App.tsx"], "stats": {"src/App.tsx": "+12 -3"}}`
- `artifact_ref` — `{"artifact_id": 17, "path": "...", "kind": "screenshot"}`
- `error` — `{"content": "permission denied: ..."}`
- `status_change` — `{"from": "in_progress", "to": "review", "note": "PR opened: #42"}`

### 4.4 Design decisions

1. **One task type.** No separate tables for coding vs general. The class of work is determined by which agent claims it and whether `repo_path`/`branch` are set.
2. **`claimed_by` is a free-form string.** Agents are external and not registered. Examples: `"codex"`, `"hermes"`, `"claude-sonnet-4.5"`. Used as a lightweight authorization (mutation requires `claimed_by == calling agent`).
3. **Comments and progress_events are separate.** Comments are a human↔agent dialogue (with read receipts); progress events are the agent's reported work stream. Mixing them complicates filtering and permissions.
4. **JSON payloads in `progress_events`.** PostgreSQL has native `JSONB` support; one table covers all event kinds without schema migration per new kind, and JSONB enables indexing on payload fields if needed later.
5. **No `runs` or `executors` table.** The board has no concept of a discrete run. A task transitions between statuses; each change writes a progress_event. If an agent crashes and restarts, it calls `get_next_task` again (if it had not claimed) or continues its claimed task. "Run history" is reconstructed from progress_events sharing the same `agent` value.
6. **No `unclaim_task`.** If an agent dies mid-task, the task stays `in_progress` and the user manually moves it back to `ready` or cancels it. The board cannot reliably detect agent death in a pull model, and automatic re-queueing causes race conditions and lost work.
7. **`get_next_task` and `claim_task` are separate.** Two-step model: an agent can inspect a task before committing to it. `get_next_task` does not claim; `claim_task` is the atomic claim.

---

## 5. MCP tools (board ← agent contract)

This is the agent-facing API. All tools are exposed via the MCP server. Tools that mutate task state require the calling agent to match the task's `claimed_by`.

### 5.1 Core tools (Phase 1)

```
CLAIMING & DISCOVERY
─────────────────────
get_next_task(
    tags_any?:    [str],   # filter: any of these tags
    tags_all?:    [str],   # filter: all of these tags
    exclude_tags?: [str],
) → Task | null
# Returns the first task in 'ready' status (ordered by sort_order, then created_at).
# Does NOT claim. Agent must call claim_task.

claim_task(task_id: str, agent: str) → {ok, task}
# Atomic: checks status == 'ready', sets 'in_progress', claimed_by=agent, claimed_at=now.
# Returns {ok: false, reason: "..."} if already claimed or status changed.
# Atomicity via SQL: UPDATE tasks SET ... WHERE id=$1 AND status='ready'.
# PostgreSQL's MVCC guarantees correctness under concurrent claim attempts.

list_tasks(status?: str, tags_any?: [str]) → [Task]
# Browse without claiming. Useful for seeing in_progress/review.

PROGRESS & LIFECYCLE
────────────────────
post_progress(
    task_id: str,
    agent: str,                # caller identity; must equal task.claimed_by
    kind: "text" | "diff" | "artifact_ref" | "error" | "status_change",
    content: str,
    artifact?: {path, kind},   # required when kind == "artifact_ref"
    status?: {from, to, note}, # required when kind == "status_change"
) → {ok}
# Appends to progress_events (agent stored as passed). Requires claimed_by == agent.
# For status_change, agent may move to 'blocked'. 'done'/'review' have dedicated tools.

complete_task(task_id: str, agent: str, summary?: str) → {ok}
# Status → 'done'. summary written as a text progress_event. Requires claimed_by == agent.

request_review(task_id: str, agent: str, summary?: str) → {ok}
# Status → 'review'. summary written as a text progress_event. Requires claimed_by == agent.
# In Phase 3, this also triggers a one-shot diff collection (see §6).

DIALOG (human ↔ agent)
──────────────────────
get_comments(task_id: str, since_id?: int) → [Comment]
# since_id = last comment id the agent has already seen. Returns comments with id > since_id,
# unseen first (ordered by id). Marks all returned comments as seen_by_agent=true.
# If since_id is omitted, returns all comments for the task.

post_comment(task_id: str, agent: str, content: str) → {ok}
# Author = agent. For questions/clarifications to the user.

ARTIFACTS
─────────
post_artifact(task_id: str, agent: str, kind: str, path: str, description?: str) → {artifact_id}
# Registers a file on disk. path must be inside an allow-listed root
# (project repo_path or ~/.agent-kanban/artifacts/<task_id>/). Otherwise rejected.
# Content is NOT uploaded; only the path is recorded. Requires claimed_by == agent.
```

### 5.2 Phase 3 tools (git/PR)

```
set_task_branch(task_id: str, agent: str, branch: str) → {ok}
# Updates tasks.branch. Requires claimed_by == agent. Optional convenience;
# agents may instead post a status_change via post_progress.

set_task_pr(task_id: str, agent: str, pr_url: str, status: "open" | "merged" | "closed") → {ok}
# Updates tasks.pr_url and tasks.pr_status. Requires claimed_by == agent.
```

### 5.3 Authorization model

- Single-user, no auth. The `agent` string passed to `claim_task` is used as a lightweight authorization for subsequent mutations: the board checks `tasks.claimed_by == calling_agent` before allowing `post_progress`, `complete_task`, `request_review`, `set_task_branch`, `set_task_pr`.
- Read tools (`get_next_task`, `list_tasks`, `get_comments`) are unrestricted.
- If multi-user is added later, a bearer token will gate the MCP endpoint; the per-agent authorization remains.

---

## 6. Git / PR integration (Phase 3)

This section applies only to coding tasks. It is opt-in per task and relies on **agent initiative**, not board automation.

### 6.1 Concept

A task may have `repo_path`, `branch`, `pr_url`, `pr_status` set. The board stores these as references; it does **not** create worktrees, branches, commits, or PRs. Agents do that through their own git/GitHub tools (Codex and Hermes both have git capabilities).

### 6.2 Workflow

1. On `claim_task`, the agent receives the task's `repo_path` and `branch` if set, otherwise null.
2. If `branch` is not set, the agent creates one and reports it (via `set_task_branch` or a `status_change` progress event).
3. The agent commits to that branch within `repo_path`. The board is unaware.
4. On `request_review` or `complete_task`, the agent opens a PR through its own tools and reports it via `set_task_pr` or a progress event.
5. **Diff auto-collection:** when a task transitions to `review`, the board runs `git -C <repo_path> diff <base>...<branch>` once and stores the result as a `progress_event` with `kind=diff`. This gives the user a ready diff in the UI without switching to GitHub. The base branch resolution: `tasks.base_branch` if set → else `projects.default_branch` for the task's project → else skip diff collection and log a warning. `tasks.base_branch` is an optional field the user can set when creating a coding task; if absent and the project has no default, no diff is collected. The diff is refreshed when the task re-enters `review`.

### 6.3 What the board does NOT do

- Create worktrees or branches.
- Run setup/dev/cleanup scripts.
- Poll GitHub for PR status. If the user wants updated PR status, the agent reports it via `set_task_pr`.
- Inline per-line code review (comments are flat, not anchored to diff lines).

### 6.4 Worktrees

Worktree creation is out of scope. If parallel isolated branches of one repo are needed, agents create worktrees themselves through git. The user specifies `repo_path` (a repo or an existing worktree) when creating a coding task; that is sufficient.

---

## 7. UI (React SPA)

### 7.1 Stack

- React + Vite + TypeScript
- shadcn/ui (component library)
- `@dnd-kit/core` for drag-and-drop
- `react-markdown` + `shiki` for markdown and code highlighting
- WebSocket for live updates
- Built into `web/dist/` and served as static from FastAPI in production; separate Vite dev server with a backend proxy during development

### 7.2 Screen 1 — Board

Classic kanban. Columns = statuses (`todo`, `ready`, `in_progress`, `review`, `done`, `blocked`, `cancelled`). Cards show title, tags, `claimed_by` badge, and a pulsing "live" indicator if a progress_event arrived in the last N seconds. Drag-and-drop between columns is the user's primary interaction. Dropping into `ready` makes the task available to agents.

### 7.3 Screen 2 — Card detail

Two-pane layout:

- **Left: progress feed** (live via WebSocket). Renders events by `kind`:
  - `text` — paragraph with timestamp + agent.
  - `diff` — syntax-highlighted diff, collapsed by default with an expand toggle.
  - `artifact_ref` — a link card with an icon based on `kind`.
  - `error` — red-highlighted block.
  - `status_change` — a horizontal separator (e.g. `── status → review ──`).
- **Right: details** — description (markdown), tags, branch/PR badges (Phase 3), action buttons (Reopen → ready, Cancel), metadata.
- **Comments** — below the progress feed. Each comment shows author and timestamp, with a `seen ✓` marker once `seen_by_agent` is true. An input box lets the user add a comment (a follow-up to the agent). Posting a comment can transition the task back to `in_progress` or `ready` so the agent picks it up.

### 7.4 Screen 3 — New / Edit task (modal)

Fields: title, description (markdown), tags (chip input), project (optional), `repo_path` and `branch` (optional, Phase 3). New tasks default to status `todo`.

### 7.5 Intentionally absent vs vibe-kanban

- No live terminal.
- No preview browser.
- No inline diff line-comments.
- No run history / execution log view.

---

## 8. Transport & deployment

### 8.1 Single server, two MCP transports

The board always runs as **one long-running HTTP server** (`kanban serve`) on a configurable port (default 7331). It exposes:

- `/api/*` — REST + WebSocket for the UI.
- `/mcp` — MCP-over-HTTP/SSE endpoint for agents that support HTTP transport.

A second CLI, `kanban-mcp`, is a thin **stdio↔HTTP bridge**: it speaks stdio-MCP with an agent and proxies to the running server over HTTP. This lets agents configured with `command: kanban-mcp` (stdio transport) share the same single board/database as agents configured with `url: http://...` (HTTP transport).

```
                         ┌──────────────────────┐
                         │  kanban serve         │
                         │  FastAPI :7331        │
                         │  ├─ /api (REST+WS UI) │
                         │  └─ /mcp (HTTP MCP)   │
                         │     reads/writes      │
                         │     PostgreSQL        │
                         └──────────────────────┘
                            ↑              ↑
              HTTP/SSE      │              │ stdio (via bridge)
                            │              │
              ┌─────────────┴──┐    ┌──────┴──────────┐
              │ hermes config  │    │ kanban-mcp CLI  │
              │ url: http://.. │    │ (proxy to HTTP) │
              └────────────────┘    └──────┬──────────┘
                                           │ stdio MCP
                                           ▼
                                    ┌──────────────┐
                                    │ codex / etc  │
                                    └──────────────┘
```

### 8.2 Project layout

```
agent-kanban/
├── pyproject.toml              # uv-managed, Python 3.11+
├── README.md
├── src/
│   └── agent_kanban/
│       ├── __init__.py
│       ├── server.py           # FastAPI app (REST + WS + MCP HTTP)
│       ├── mcp_server.py       # MCP tools implementation
│       ├── mcp_stdio_bridge.py # kanban-mcp CLI: stdio↔HTTP proxy
│       ├── db.py               # sqlmodel models + alembic migrations (asyncpg)
│       ├── git.py              # Phase 3: diff collection
│       ├── cli.py              # kanban serve / dev / migrate
│       └── config.py           # paths, ports, settings
├── web/                        # React SPA (Vite)
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── Board.tsx
│   │   ├── CardDetail.tsx
│   │   ├── api.ts              # REST + WS client
│   │   └── components/         # shadcn/ui based
│   └── vite.config.ts
├── Dockerfile
└── docker-compose.yml
```

### 8.3 Agent configuration

```toml
# Codex (~/.codex/config.toml) — or `codex mcp add kanban http://localhost:7331/mcp`
[mcp_servers.kanban]
url = "http://localhost:7331/mcp"
# or
[mcp_servers.kanban]
command = "kanban-mcp"
```

```yaml
# Hermes (~/.hermes/config.yaml)
mcp_servers:
  kanban:
    url: http://localhost:7331/mcp
```

### 8.4 Stack choices

| Component | Choice | Reason |
|---|---|---|
| Backend | FastAPI + uvicorn, Python 3.11+ | Async for WS; clean MCP-over-HTTP; sqlmodel integration |
| MCP library | official `mcp` Python SDK | Standard types; supports stdio and HTTP transports |
| Database | PostgreSQL + sqlmodel + alembic (async via asyncpg) | MVCC handles concurrent agent writes; JSONB for `payload`; typed models; migrations |
| WebSocket | FastAPI native | No extra dependencies |
| Auth | none (single-user) | Add bearer token later if multi-user is needed |
| UI | React + Vite + TypeScript | shadcn/ui, @dnd-kit, react-markdown, shiki |
| Packaging | uv; Dockerfile; `kanban` and `kanban-mcp` console scripts | One command to run |

### 8.5 Deployment

The board requires a PostgreSQL database. The connection string is read from the `DATABASE_URL` env var (e.g. `postgresql+asyncpg://kanban:kanban@localhost:5436/kanban`). Two services run together in development and production.

- **Local dev:**
  - `docker compose up -d postgres` (or any local Postgres) — PostgreSQL :5436 (host port).
  - `kanban migrate` — apply alembic migrations.
  - `kanban serve` — backend :7331.
  - Optionally `pnpm dev` in `web/` for hot-reload UI with a proxy to :7331.
- **Self-hosted:** `docker compose up -d` runs two containers — `kanban` (FastAPI :7331) and `postgres` (PostgreSQL :5436 (host port). — with a named volume for the database. `docker-compose.yml` sets `DATABASE_URL` for the app container and runs `kanban migrate` before `kanban serve`.

---

## 9. Phasing

This spec covers Phases 1–3. Each phase is independently useful.

| Phase | Scope | Useful outcome |
|---|---|---|
| **1 — MVP** | Board, data model, MCP core tools (§5.1), UI (board + card detail + comments), `kanban serve` + `kanban-mcp`, Docker compose | A working AI-native kanban usable with Codex and Hermes |
| **2 — Review loop** | Comments flow back to agents as follow-ups (status transitions on comment); progress feed polish (diff expand, artifact rendering) | Full human↔agent dialogue loop |
| **3 — Git/PR** | `repo_path`/`branch`/`pr_url` fields; `set_task_branch`, `set_task_pr` tools; diff auto-collection on `request_review`; branch/PR badges in UI | Coding-task pipeline including review diffs and PR links |

Phases 4+ (preview browser, terminal, inline diff comments, multi-user, cloud sync) are explicitly out of scope for this spec and would require separate specs.

---

## 10. Open questions to confirm during implementation

- Default port (7331 proposed) and config file location (`~/.agent-kanban/config.toml` proposed).
- `tags` representation: JSONB array column vs separate `task_tags` join table. JSONB array is simpler and supports GIN indexing for `tags_any`/`tags_all` filters; switch to a join table only if many-to-many tag metadata is needed.
- WebSocket event granularity: per-task channels vs single broadcast with client-side filter. Single broadcast is simpler for single-user; revisit if UI scales.
- `post_artifact` allow-listed roots: configurable per project, or a single global artifacts dir plus project `repo_path`. Proposed: both (project `repo_path` if set, plus `~/.agent-kanban/artifacts/<task_id>/`).
