# Agent Kanban — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the review loop, pay down Phase 1 tech debt, and upgrade the diff viewer and artifact rendering so the card detail view is genuinely usable for reviewing agent work.

**Architecture:** Frontend-focused changes plus small backend additions. No data model changes. The review loop closes the human→agent feedback path: when a user comments on a card in `review` status, the card moves back to `in_progress` so the agent picks up the comment on its next `get_comments` call. Tech debt fixes (WS reconnect, error handling, dead deps, datetime) harden the existing stack.

**Tech Stack:** Python 3.11 + FastAPI + sqlmodel (backend); React + Vite + TypeScript + shiki (frontend, new dep). Existing: `@dnd-kit` (to be removed), `react-markdown`.

**Spec:** `docs/superpowers/specs/2026-07-05-agent-kanban-design.md` — Phase 2 scope (§7.3 review loop, §7.5 polish). Phase 3 (git/PR) is a separate plan.

## Global Constraints

- All existing Phase 1 constraints still apply (Python 3.11+, PostgreSQL on host port **5436**, MCP SDK `mcp>=1.27,<2.0`, etc.).
- No breaking changes to the MCP tool contract — agents that work against Phase 1 must keep working.
- No DB migrations in this plan (no schema changes). If a task appears to need one, escalate.
- Frontend served from FastAPI as static in production; Vite dev server with proxy during development.
- Default port 7331. Postgres `ak-pg` container on host 5436.
- `agent` is a free-form string; mutation tools require `claimed_by == agent` (no change).
- TDD where there is testable logic (backend). Frontend changes are verified by `pnpm build` + manual smoke; no JS test framework is being introduced in Phase 2.

---

## File Structure

Phase 2 touches existing files. No new modules; one new dependency (`shiki`) and one removal (`@dnd-kit/*`).

```
src/agent_kanban/
├── services.py          # MODIFY: extract _set_status helper; comment-post status side-effect (Task 1)
├── routes/
│   └── comments.py      # MODIFY: optional status query param on POST comment (Task 1)
web/
├── package.json         # MODIFY: add shiki, remove @dnd-kit/* (Task 5)
├── src/
│   ├── api.ts           # MODIFY: WS reconnect w/ backoff + error handling (Task 4)
│   ├── components/
│   │   ├── ProgressFeed.tsx   # MODIFY: shiki diff highlighting, expand-all (Task 3)
│   │   ├── ArtifactCard.tsx   # CREATE: link-card with thumbnail/icon (Task 6)
│   │   ├── CommentList.tsx    # MODIFY: status selector on post, pending state, error toast (Task 2)
│   │   └── TaskCard.tsx       # MODIFY: live indicator from last progress event (Task 7)
│   ├── pages/
│   │   └── CardDetail.tsx     # MODIFY: error handling on Reopen/Cancel; pass last-progress timestamp (Task 2, 7)
│   └── types.ts         # MODIFY: add ArtifactMeta type, WS reconnect options (Tasks 4, 6)
src/agent_kanban/
├── services.py          # MODIFY (Task 8): datetime.utcnow() → datetime.now(UTC)
└── models.py            # MODIFY (Task 8): default_factory uses UTC now
```

**Decomposition rationale:** Tasks 1–2 form the review-loop pair (backend side-effect + frontend UX). Tasks 3 and 6 are independent visual upgrades (diff / artifact). Task 4 (WS resilience) and Task 5 (dep cleanup) are infrastructure. Tasks 7 and 8 finish the deferred-issues list. Each task ends with a green build/test run and its own commit.

---

## Task 1: Review-loop status side-effect (backend)

When a user posts a comment on a task in `review` status, the task should move back to `in_progress` so the agent re-engages. The user can override this with an explicit status choice.

**Files:**
- Modify: `src/agent_kanban/routes/comments.py`
- Modify: `src/agent_kanban/services.py`
- Test: `tests/test_routes_comments.py`

**Interfaces:**
- Consumes: `agent_kanban.services.{list_comments, post_comment, get_task, update_task}`, `agent_kanban.models.TaskStatus`
- Produces: `POST /api/tasks/{task_id}/comments` now accepts an optional `status` query param (`in_progress` or `ready`). When omitted and the task is in `review`, the task auto-transitions to `in_progress`. The response body is the created Comment (unchanged shape); the status side-effect is observable via the task.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_routes_comments.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient

from agent_kanban.server import create_app


@pytest.fixture
async def client(db_url):
    from agent_kanban.config import get_settings
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_comment_on_review_task_moves_to_in_progress(client):
    # Create a task and move it to review directly.
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    await client.patch(f"/api/tasks/{task_id}", json={"status": "review"})

    # Post a comment with no explicit status.
    r = await client.post(
        f"/api/tasks/{task_id}/comments",
        json={"author": "user", "content": "please also handle the empty case"},
    )
    assert r.status_code == 201

    # Task should now be in_progress.
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_comment_with_explicit_ready_status(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    await client.patch(f"/api/tasks/{task_id}", json={"status": "review"})

    r = await client.post(
        f"/api/tasks/{task_id}/comments?status=ready",
        json={"author": "user", "content": "redo it"},
    )
    assert r.status_code == 201
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_comment_on_non_review_task_does_not_change_status(client):
    r = await client.post("/api/tasks", json={"title": "t"})
    task_id = r.json()["id"]
    # Task is in 'todo'.
    r = await client.post(
        f"/api/tasks/{task_id}/comments",
        json={"author": "user", "content": "hi"},
    )
    assert r.status_code == 201
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "todo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_routes_comments.py -v`
Expected: the first new test FAILs — posting a comment does not change the task status (it stays `review`).

- [ ] **Step 3: Implement the side-effect in `routes/comments.py`**

Open `src/agent_kanban/routes/comments.py`. The current `add_comment` handler creates the comment via `post_comment` and returns it. Add a `status: Optional[str] = None` query parameter and apply the status transition after the comment is created.

Replace the `add_comment` function with:
```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.db import get_session
from agent_kanban.models import TaskStatus
from agent_kanban.schemas import CommentCreate, CommentRead, TaskUpdate
from agent_kanban.services import get_task, list_comments, post_comment, update_task

router = APIRouter(prefix="/api/tasks/{task_id}/comments", tags=["comments"])


@router.get("", response_model=list[CommentRead])
async def get_comments(
    task_id: int,
    since_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    return await list_comments(session, task_id, since_id, mark_seen_by=None)


@router.post("", response_model=CommentRead, status_code=201)
async def add_comment(
    task_id: int,
    data: CommentCreate,
    status: Optional[str] = Query(
        None, description="Override task status after comment. If omitted, review→in_progress."
    ),
    session: AsyncSession = Depends(get_session),
):
    if data.author == "":
        data.author = "user"
    comment = await post_comment(session, task_id, data.author, data.content)

    # Resolve the target status: explicit query param wins; else auto review→in_progress.
    if status is not None:
        target = TaskStatus(status)
    else:
        task = await get_task(session, task_id)
        target = TaskStatus.IN_PROGRESS if task.status == TaskStatus.REVIEW else None

    if target is not None:
        await update_task(session, task_id, TaskUpdate(status=target))
    return comment
```

(Keep the existing module-level imports that are still used; remove the now-unused old imports.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_comments.py -v`
Expected: PASS (all comment tests including the 3 new ones).

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `uv run pytest -v`
Expected: 40 prior + 3 new = 43 passing.

- [ ] **Step 6: Commit**

```bash
git add src/agent_kanban/routes/comments.py tests/test_routes_comments.py
git commit -m "feat(routes): comment on review task auto-transitions to in_progress"
```

---

## Task 2: Review-loop UX (frontend)

Wire the backend side-effect into the UI: the comment input shows a status selector (`Re-engage → in_progress` default, or `→ ready`), disables while pending, and surfaces errors. CardDetail's Reopen/Cancel buttons get error handling.

**Files:**
- Modify: `web/src/components/CommentList.tsx`
- Modify: `web/src/pages/CardDetail.tsx`
- Modify: `web/src/api.ts` (only the `postComment` signature)

**Interfaces:**
- Consumes: `api.postComment` (extended), `Task` type
- Produces: `CommentList` accepts an optional `taskStatus` prop and renders a small status selector next to the Send button.

- [ ] **Step 1: Extend `postComment` in `api.ts`**

Open `web/src/api.ts`. Find the `postComment` method and change its signature to accept an optional `status`:
```typescript
  async postComment(
    taskId: number,
    content: string,
    author = "user",
    status?: "in_progress" | "ready"
  ): Promise<Comment> {
    const q = status ? `?status=${status}` : "";
    return j(
      await fetch(`${BASE}/tasks/${taskId}/comments${q}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author, content }),
      })
    );
  },
```

- [ ] **Step 2: Rewrite `CommentList.tsx` with selector, pending state, error toast**

Replace the entire contents of `web/src/components/CommentList.tsx`:
```typescript
import { useState } from "react";
import { api } from "../api";
import type { Comment, TaskStatus } from "../types";

type ReengageStatus = "in_progress" | "ready";

export function CommentList({
  taskId,
  comments,
  taskStatus,
  onPosted,
}: {
  taskId: number;
  comments: Comment[];
  taskStatus: TaskStatus;
  onPosted: () => void;
}) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Show the status selector only when the user's comment will re-engage the agent.
  const showSelector = taskStatus === "review";
  const [reengage, setReengage] = useState<ReengageStatus>("in_progress");

  async function send() {
    if (!text.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      await api.postComment(taskId, text, "user", showSelector ? reengage : undefined);
      setText("");
      onPosted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to post comment");
    } finally {
      setPending(false);
    }
  }

  return (
    <div style={{ marginTop: 16, borderTop: "1px solid #ddd", paddingTop: 12 }}>
      <h4>Comments</h4>
      {comments.map((c) => (
        <div key={c.id} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: "#666" }}>
            {new Date(c.created_at).toLocaleString()} · <strong>{c.author}</strong>
            {c.author !== "user" && (c.seen_by_agent ? " ✓ seen" : " ⏳ not seen by agent")}
          </div>
          <div>{c.content}</div>
        </div>
      ))}
      {error && (
        <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 8 }}>{error}</div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !pending && send()}
          placeholder="Add a comment for the agent..."
          style={{ flex: 1 }}
          disabled={pending}
        />
        {showSelector && (
          <select
            value={reengage}
            onChange={(e) => setReengage(e.target.value as ReengageStatus)}
            disabled={pending}
            title="Status after posting"
          >
            <option value="in_progress">→ in_progress</option>
            <option value="ready">→ ready</option>
          </select>
        )}
        <button onClick={send} disabled={pending || !text.trim()}>
          {pending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Update `CardDetail.tsx` — pass taskStatus, add error handling on Reopen/Cancel**

Open `web/src/pages/CardDetail.tsx`. Three changes:

a) Pass `taskStatus={task.status}` to `<CommentList>`:
```typescript
<CommentList
  taskId={taskId}
  comments={comments}
  taskStatus={task.status}
  onPosted={refresh}
/>
```

b) Add a small error state at the top of the component (after `const [comments, setComments] = ...`):
```typescript
const [actionError, setActionError] = useState<string | null>(null);
```

c) Replace the Reopen/Cancel buttons block with error-handling versions:
```typescript
<div style={{ marginTop: 12 }}>
  {actionError && (
    <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 8 }}>{actionError}</div>
  )}
  <button
    onClick={async () => {
      setActionError(null);
      try {
        await api.updateTask(taskId, { status: "ready" });
        refresh();
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Failed to update task");
      }
    }}
  >
    Reopen → ready
  </button>{" "}
  <button
    onClick={async () => {
      setActionError(null);
      try {
        await api.updateTask(taskId, { status: "cancelled" });
        refresh();
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Failed to update task");
      }
    }}
  >
    Cancel
  </button>
</div>
```

- [ ] **Step 4: Verify the frontend builds**

Run: `cd web && pnpm build`
Expected: build succeeds with no TypeScript errors. (Watch for the `taskStatus` prop being required now — `CommentList` must always receive it.)

- [ ] **Step 5: Manual smoke (documented)**

With backend on :7331 and frontend on :5173:
1. Create a task, drag to ready, then (via curl or the API) move it to review.
2. Open the card — the comment input shows a "→ in_progress / → ready" selector.
3. Post a comment — the task status flips per the selector.
4. Trigger a network error (e.g. stop the backend) and click Send — the error appears inline; the input is not cleared.

- [ ] **Step 6: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/src/components/CommentList.tsx web/src/pages/CardDetail.tsx web/src/api.ts
git commit -m "feat(web): review-loop UX with status selector and error handling"
```

---

## Task 3: Diff viewer with syntax highlighting + expand/collapse all

Replace the plain `<pre>` diff rendering with shiki-highlighted output, add an "Expand all / Collapse all" toggle, and show per-file diff stats.

**Files:**
- Modify: `web/src/components/ProgressFeed.tsx`
- Modify: `web/package.json` (add `shiki`)
- Modify: `web/src/types.ts` (extend `ProgressEvent.payload` doc; no runtime change required)

**Interfaces:**
- Consumes: shiki highlighter (created once, memoized)
- Produces: `ProgressFeed` accepts an optional `defaultExpanded` prop. Diff items render with syntax highlighting when a language can be inferred from the filename, fall back to plain monospace otherwise.

- [ ] **Step 1: Add shiki as a dependency**

Run:
```bash
cd web
pnpm add shiki
```
Expected: `shiki` appears in `web/package.json` dependencies, lockfile updated.

- [ ] **Step 2: Rewrite `ProgressFeed.tsx`**

Replace the entire contents of `web/src/components/ProgressFeed.tsx`:
```typescript
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ProgressEvent } from "../types";

// Shiki is loaded once for the whole feed.
import type { Highlighter } from "shiki";

let highlighterPromise: Promise<Highlighter> | null = null;

async function getHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = (async () => {
      const { createHighlighter } = await import("shiki");
      return createHighlighter({
        themes: ["github-light", "github-dark"],
        langs: ["diff", "typescript", "javascript", "python", "bash", "json"],
      });
    })();
  }
  return highlighterPromise;
}

const EXT_LANG: Record<string, string> = {
  ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  py: "python", sh: "bash", bash: "bash", json: "json",
};

function langFromDiff(content: string): string {
  // Try to read a filename from a +++ b/... or diff --git a/... line.
  const m = content.match(/^(?:\+\+\+ b\/|diff --git a\/)([^\n]+)/m);
  if (m) {
    const ext = m[1].split(".").pop()?.toLowerCase() ?? "";
    if (ext && EXT_LANG[ext]) return EXT_LANG[ext];
  }
  return "diff";
}

export function ProgressFeed({
  events,
  defaultExpanded = false,
}: {
  events: ProgressEvent[];
  defaultExpanded?: boolean;
}) {
  const [expandAll, setExpandAll] = useState(defaultExpanded);
  const hasDiff = events.some((e) => e.kind === "diff");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {hasDiff && (
        <div style={{ marginBottom: 4 }}>
          <button onClick={() => setExpandAll((v) => !v)}>
            {expandAll ? "Collapse all diffs" : "Expand all diffs"}
          </button>
        </div>
      )}
      {events.map((e) => (
        <ProgressItem key={e.id} event={e} forceExpanded={expandAll} />
      ))}
    </div>
  );
}

function ProgressItem({
  event,
  forceExpanded,
}: {
  event: ProgressEvent;
  forceExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const effectiveExpanded = forceExpanded || expanded;
  const ts = new Date(event.created_at).toLocaleTimeString();
  const content = (event.payload.content as string) || "";

  if (event.kind === "status_change") {
    return (
      <div style={{ borderTop: "1px dashed #aaa", margin: "8px 0", paddingTop: 4, fontSize: 12, color: "#666", textAlign: "center" }}>
        ── {content} ──
      </div>
    );
  }
  if (event.kind === "error") {
    return (
      <div style={{ background: "#fee2e2", borderLeft: "3px solid #ef4444", padding: 8, borderRadius: 4 }}>
        <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>{ts} · {event.agent}</div>
        <pre style={{ margin: 0, fontFamily: "monospace", color: "#991b1b", whiteSpace: "pre-wrap" }}>{content}</pre>
      </div>
    );
  }
  if (event.kind === "diff") {
    return <DiffItem content={content} ts={ts} agent={event.agent} expanded={effectiveExpanded} onToggle={() => setExpanded((v) => !v)} />;
  }
  if (event.kind === "artifact_ref") {
    return <ArtifactTextItem ts={ts} agent={event.agent} content={content} payload={event.payload} />;
  }
  // plain text
  return (
    <div style={{ background: "#fff", border: "1px solid #eee", padding: 8, borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>{ts} · <strong>{event.agent}</strong></div>
      <div style={{ fontSize: 14 }}>
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}

function DiffItem({
  content,
  ts,
  agent,
  expanded,
  onToggle,
}: {
  content: string;
  ts: string;
  agent: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const lang = useMemo(() => langFromDiff(content), [content]);
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    getHighlighter().then((h) => {
      if (cancelled) return;
      const out = h.codeToHtml(content, { lang, theme: "github-light" });
      setHtml(out);
    });
    return () => { cancelled = true; };
  }, [expanded, content, lang]);

  const stats = content.match(/@@.*@@/g)?.length ?? 0;
  return (
    <div style={{ background: "#f8f8f8", border: "1px solid #ddd", borderRadius: 4 }}>
      <button
        onClick={onToggle}
        style={{ width: "100%", textAlign: "left", padding: 6, background: "none", border: "none", cursor: "pointer" }}
      >
        {expanded ? "▼" : "▶"} diff · {ts} · {agent} · {lang}{stats > 0 ? ` · ${stats} hunk(s)` : ""}
      </button>
      {expanded && (
        html ? (
          <div
            style={{ padding: 8, margin: 0, overflowX: "auto", fontSize: 12 }}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre style={{ padding: 8, margin: 0, overflowX: "auto", fontSize: 12 }}>{content}</pre>
        )
      )}
    </div>
  );
}

// ArtifactTextItem is a placeholder until Task 6 swaps in the full ArtifactCard.
function ArtifactTextItem({
  ts,
  agent,
  content,
  payload,
}: {
  ts: string;
  agent: string;
  content: string;
  payload: { [k: string]: unknown };
}) {
  return (
    <div style={{ background: "#fff", border: "1px solid #eee", padding: 8, borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>
        {ts} · <strong>{agent}</strong> · 📎 artifact
      </div>
      <div style={{ fontSize: 14 }}>
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
      <div style={{ fontSize: 11, color: "#999" }}>{JSON.stringify(payload.artifact ?? {})}</div>
    </div>
  );
}
```

- [ ] **Step 3: Verify the build**

Run: `cd web && pnpm build`
Expected: build succeeds. If shiki's types complain about the dynamic import or `Highlighter`, use `import("shiki").Highlighter` for the type or `any` with a comment — but try the typed import first.

- [ ] **Step 4: Manual smoke**

With backend running, post a diff progress event via curl:
```bash
TASK_ID=1  # adjust
curl -X POST http://localhost:7331/mcp/ -H 'Content-Type: application/json' -d '...'
# (or directly insert via psql / a small script)
```
Open the card — the diff shows a chevron, language hint, hunk count, and on expand renders syntax-highlighted HTML. "Expand all diffs" toggles every diff at once.

- [ ] **Step 5: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/src/components/ProgressFeed.tsx web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): shiki-highlighted diff viewer with expand-all toggle"
```

---

## Task 4: WebSocket reconnect with backoff

The current `subscribeWebSocket` opens a socket once and silently dies on disconnect. Add exponential backoff reconnection and an `onerror` log, gated behind an options object so existing call sites compile.

**Files:**
- Modify: `web/src/api.ts`
- Modify: `web/src/pages/Board.tsx` (passes no options — uses defaults)
- Modify: `web/src/pages/CardDetail.tsx` (passes no options — uses defaults)

**Interfaces:**
- Produces: `subscribeWebSocket(taskId, onMessage, options?)` where `options = { maxRetries?: number; baseDelayMs?: number }`. Returns an object `{ close(): void }` instead of a raw `WebSocket` (call sites updated to call `.close()` on cleanup).

- [ ] **Step 1: Replace `subscribeWebSocket` in `api.ts`**

Open `web/src/api.ts`. Replace the existing `subscribeWebSocket` function (the one returning a raw `WebSocket`) with:
```typescript
export interface WSOptions {
  maxRetries?: number;
  baseDelayMs?: number;
}

export interface WSSubscription {
  close: () => void;
}

export function subscribeWebSocket(
  taskId: number | null,
  onMessage: (evt: { type: string; [k: string]: unknown }) => void,
  options: WSOptions = {}
): WSSubscription {
  const maxRetries = options.maxRetries ?? 5;
  const baseDelayMs = options.baseDelayMs ?? 500;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const q = taskId ? `?task_id=${taskId}` : "";
  const url = `${proto}//${location.host}/ws${q}`;

  let retryCount = 0;
  let closedByCaller = false;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function open() {
    ws = new WebSocket(url);
    ws.onopen = () => {
      retryCount = 0;
    };
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch (err) {
        console.error("kanban: bad WS message", err);
      }
    };
    ws.onerror = (err) => {
      console.error("kanban: WS error", err);
    };
    ws.onclose = () => {
      if (closedByCaller) return;
      if (retryCount >= maxRetries) {
        console.error(`kanban: WS giving up after ${maxRetries} retries`);
        return;
      }
      const delay = baseDelayMs * Math.pow(2, retryCount);
      retryCount += 1;
      reconnectTimer = setTimeout(open, delay);
    };
  }

  open();

  return {
    close: () => {
      closedByCaller = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    },
  };
}
```

- [ ] **Step 2: Update call sites to use `.close()` (they already do)**

`Board.tsx` and `CardDetail.tsx` both have `const ws = subscribeWebSocket(...)` and `return () => ws.close()`. The new return type's `.close()` is callable the same way — verify both files still compile.

Open `web/src/pages/Board.tsx` — confirm the cleanup line reads `return () => ws.close();` (no change needed, but verify).
Open `web/src/pages/CardDetail.tsx` — same check.

- [ ] **Step 3: Verify the build**

Run: `cd web && pnpm build`
Expected: succeeds. TypeScript should accept the new return type at both call sites since both only call `.close()`.

- [ ] **Step 4: Manual smoke**

With the backend running, open the board, then kill the backend (`Ctrl+C` or `docker compose stop app`). The browser console should log a WS error and retry with exponential backoff, then give up after 5 attempts. Restart the backend — note that the subscription does NOT auto-resume after giving up (acceptable for Phase 2; the user can refresh). Verify the board still works on a clean refresh.

- [ ] **Step 5: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/src/api.ts web/src/pages/Board.tsx web/src/pages/CardDetail.tsx
git commit -m "feat(web): WebSocket reconnect with exponential backoff"
```

---

## Task 5: Remove dead `@dnd-kit` dependencies

The board uses native HTML5 drag-and-drop; `@dnd-kit/core` and `@dnd-kit/sortable` are installed but never imported.

**Files:**
- Modify: `web/package.json`
- Modify: `web/pnpm-lock.yaml` (regenerated)

- [ ] **Step 1: Verify no imports of @dnd-kit exist**

Run: `cd web && grep -rn "@dnd-kit" src/ || echo "no imports found"`
Expected: `no imports found`. If any import exists, STOP — do not remove the deps; escalate.

- [ ] **Step 2: Remove the deps**

Run:
```bash
cd web
pnpm remove @dnd-kit/core @dnd-kit/sortable
```
Expected: both packages removed from `package.json` `dependencies`; lockfile updated; `node_modules` pruned.

- [ ] **Step 3: Verify the build**

Run: `cd web && pnpm build`
Expected: succeeds (no missing-import errors).

- [ ] **Step 4: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/package.json web/pnpm-lock.yaml
git commit -m "chore(web): remove unused @dnd-kit dependencies"
```

---

## Task 6: Artifact rendering with link cards

`artifact_ref` progress events currently render as plain text with an emoji. Render them as proper link cards: thumbnail for images, icon + size for other files.

**Files:**
- Create: `web/src/components/ArtifactCard.tsx`
- Modify: `web/src/components/ProgressFeed.tsx` (use `ArtifactCard` instead of `ArtifactTextItem`)
- Modify: `web/src/types.ts` (add `ArtifactMeta`)

**Interfaces:**
- Consumes: `ProgressEvent.payload.artifact` (an object `{ path, kind }` per the spec)
- Produces: `ArtifactCard` component rendered inside `ProgressFeed` for `kind === "artifact_ref"` events.

- [ ] **Step 1: Add `ArtifactMeta` to `types.ts`**

Open `web/src/types.ts`. Append:
```typescript
export interface ArtifactMeta {
  path: string;
  kind: string; // "screenshot" | "log" | "diff.patch" | "file" | ...
}
```

- [ ] **Step 2: Create `ArtifactCard.tsx`**

Create `web/src/components/ArtifactCard.tsx`:
```typescript
import { useEffect, useState } from "react";
import type { ArtifactMeta } from "../types";

const IMAGE_KINDS = new Set(["screenshot", "image", "png", "jpg", "jpeg", "gif", "webp"]);

function iconFor(kind: string): string {
  if (IMAGE_KINDS.has(kind.toLowerCase())) return "🖼";
  if (kind.includes("log")) return "📜";
  if (kind.includes("diff") || kind.includes("patch")) return "🔧";
  return "📎";
}

export function ArtifactCard({
  artifact,
  description,
}: {
  artifact: ArtifactMeta;
  description?: string;
}) {
  const [size, setSize] = useState<string | null>(null);
  const isImage = IMAGE_KINDS.has(artifact.kind.toLowerCase());

  useEffect(() => {
    // Best-effort size fetch; ignore failures (path may not be HTTP-served).
    if (isImage) return;
    fetch(`file:///${artifact.path}`, { method: "HEAD" })
      .then((r) => {
        const len = r.headers.get("content-length");
        if (len) setSize(formatBytes(Number(len)));
      })
      .catch(() => {});
  }, [artifact.path, isImage]);

  return (
    <a
      href={`file:///${artifact.path}`}
      onClick={(e) => e.preventDefault()}
      title={artifact.path}
      style={{
        display: "flex",
        gap: 10,
        padding: 8,
        border: "1px solid #ddd",
        borderRadius: 6,
        background: "#fafafa",
        textDecoration: "none",
        color: "inherit",
        alignItems: "center",
      }}
    >
      {isImage ? (
        <img
          src={`file:///${artifact.path}`}
          alt={description ?? artifact.path}
          style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4 }}
          onError={(e) => { (e.currentTarget.style.display = "none"); }}
        />
      ) : (
        <span style={{ fontSize: 24 }}>{iconFor(artifact.kind)}</span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {description ?? artifact.path.split("/").pop() ?? artifact.path}
        </div>
        <div style={{ fontSize: 11, color: "#666" }}>
          {artifact.kind}{size ? ` · ${size}` : ""}
        </div>
      </div>
    </a>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
```

> **Note for the implementer:** `file:///` URLs won't resolve in a browser for arbitrary filesystem paths — this is expected. The card is a visual anchor; in Phase 1/2 the path is informational. A future task can serve artifacts via a dedicated `/api/artifacts/{id}/content` endpoint. The `onClick preventDefault` keeps the link from navigating; the user copies the path from the `title` tooltip.

- [ ] **Step 3: Wire `ArtifactCard` into `ProgressFeed.tsx`**

In `web/src/components/ProgressFeed.tsx`:

a) Add the import at the top:
```typescript
import { ArtifactCard } from "./ArtifactCard";
import type { ArtifactMeta } from "../types";
```

b) Replace the `ArtifactTextItem` function with one that renders an `ArtifactCard`:
```typescript
function ArtifactTextItem({
  ts,
  agent,
  content,
  payload,
}: {
  ts: string;
  agent: string;
  content: string;
  payload: { [k: string]: unknown };
}) {
  const artifact = (payload.artifact as ArtifactMeta | undefined) ?? { path: content, kind: "file" };
  return (
    <div style={{ background: "#fff", border: "1px solid #eee", padding: 8, borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>
        {ts} · <strong>{agent}</strong>
      </div>
      <ArtifactCard artifact={artifact} description={content} />
    </div>
  );
}
```

- [ ] **Step 4: Verify the build**

Run: `cd web && pnpm build`
Expected: succeeds.

- [ ] **Step 5: Manual smoke**

Post an `artifact_ref` progress event via curl/psql with `payload = {"content": "screenshot of dark mode", "artifact": {"path": "/tmp/x.png", "kind": "screenshot"}}`. Open the card — the event renders as a card with an image thumbnail placeholder (image won't load from `file:///`, which is fine) and the description text.

- [ ] **Step 6: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add web/src/components/ArtifactCard.tsx web/src/components/ProgressFeed.tsx web/src/types.ts
git commit -m "feat(web): artifact link-cards with thumbnails and kind icons"
```

---

## Task 7: Live indicator from last progress event

`TaskCard.isFresh` currently keys off `task.created_at`, so it glows for 30s after creation regardless of agent activity. Glow when the most recent progress event is recent instead.

**Files:**
- Modify: `web/src/components/TaskCard.tsx`
- Modify: `web/src/components/Column.tsx` (passes `lastProgressAt`)
- Modify: `web/src/pages/Board.tsx` (fetches and passes last-progress timestamps)
- Modify: `web/src/api.ts` (add `listLastProgressTimestamps`)

**Interfaces:**
- Produces: `api.listLastProgressTimestamps(): Promise<Record<number, string>>` — a map of task_id → ISO timestamp of its most recent progress_event. `TaskCard` accepts an optional `lastProgressAt?: string`; if it's within 30s of now, the card glows.

- [ ] **Step 1: Add the backend endpoint**

The map of "task_id → last progress timestamp" is best computed in one query. Add a route.

Create the route by editing `src/agent_kanban/routes/progress.py`. Add this endpoint:
```python
from collections import OrderedDict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban.db import get_session
from agent_kanban.models import ProgressEvent, Task

router = APIRouter(tags=["progress"])


@router.get("/api/tasks/{task_id}/progress")
async def list_progress(task_id: int, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(ProgressEvent)
        .where(ProgressEvent.task_id == task_id)
        .order_by(ProgressEvent.created_at)
    )
    result = await session.execute(stmt)
    return [
        {
            "id": e.id,
            "task_id": e.task_id,
            "agent": e.agent,
            "kind": e.kind.value if hasattr(e.kind, "value") else e.kind,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
        }
        for e in result.scalars()
    ]


@router.get("/api/progress/last")
async def last_progress_timestamps(session: AsyncSession = Depends(get_session)):
    """Map task_id → ISO timestamp of its most recent progress_event (for live indicators)."""
    stmt = (
        select(
            ProgressEvent.task_id,
            func.max(ProgressEvent.created_at).label("last_at"),
        )
        .group_by(ProgressEvent.task_id)
    )
    result = await session.execute(stmt)
    return {row.task_id: row.last_at.isoformat() for row in result.all()}
```

(Replace the existing `routes/progress.py` content entirely with the above — it preserves the existing `list_progress` behavior and adds the new endpoint.)

- [ ] **Step 2: Add `listLastProgressTimestamps` to `api.ts`**

In `web/src/api.ts`, add to the `api` object:
```typescript
  async listLastProgressTimestamps(): Promise<Record<number, string>> {
    return j(await fetch(`${BASE}/progress/last`));
  },
```

- [ ] **Step 3: Rewrite `TaskCard.tsx` to use `lastProgressAt`**

Replace the contents of `web/src/components/TaskCard.tsx`:
```typescript
import type { Task } from "../types";

const LIVE_WINDOW_MS = 30_000;

export function TaskCard({
  task,
  lastProgressAt,
}: {
  task: Task;
  lastProgressAt?: string;
}) {
  const isLive = lastProgressAt
    ? Date.now() - new Date(lastProgressAt).getTime() < LIVE_WINDOW_MS
    : false;
  return (
    <div
      style={{
        border: "1px solid #ddd",
        borderRadius: 6,
        padding: 10,
        background: "#fff",
        boxShadow: isLive ? "0 0 0 2px #22c55e" : "none",
        transition: "box-shadow 200ms",
      }}
    >
      <div style={{ fontWeight: 600 }}>
        #{task.id} {task.title}
        {isLive && <span style={{ marginLeft: 6, fontSize: 11, color: "#22c55e" }}>● live</span>}
      </div>
      {task.tags.length > 0 && (
        <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}>
          {task.tags.map((t) => (
            <span key={t} style={{ background: "#eee", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>
              {t}
            </span>
          ))}
        </div>
      )}
      {task.claimed_by && (
        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>claimed by {task.claimed_by}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Thread `lastProgressAt` through `Column.tsx` and `Board.tsx`**

In `web/src/components/Column.tsx`, accept a `lastProgress: Record<number, string>` prop and pass `lastProgressAt={lastProgress[t.id]}` to each `TaskCard`. The `Column` props become:
```typescript
interface Props {
  status: TaskStatus;
  tasks: Task[];
  lastProgress: Record<number, string>;
  onDrop: (taskId: number, status: TaskStatus) => void;
  onOpen: (taskId: number) => void;
}
```
And the card wrapper becomes:
```typescript
<TaskCard task={t} lastProgressAt={lastProgress[t.id]} />
```

In `web/src/pages/Board.tsx`:
```typescript
const [lastProgress, setLastProgress] = useState<Record<number, string>>({});

async function refresh() {
  const [tasks, lp] = await Promise.all([api.listTasks(), api.listLastProgressTimestamps()]);
  setTasks(tasks);
  setLastProgress(lp);
}
```
And pass `lastProgress={lastProgress}` to each `<Column>`.

- [ ] **Step 5: Add a tick state so the live indicator fades without a refresh**

In `Board.tsx`, add a `tick` state that bumps every 5s so `Date.now()` re-evaluates:
```typescript
const [, setTick] = useState(0);
useEffect(() => {
  const id = setInterval(() => setTick((t) => t + 1), 5000);
  return () => clearInterval(id);
}, []);
```

- [ ] **Step 6: Verify the build**

Run: `cd web && pnpm build`
Expected: succeeds.

- [ ] **Step 7: Manual smoke**

Post a progress event for a task. The card in the `in_progress` column should glow green and show "● live" for ~30 seconds, then fade (the 5s tick forces re-render). Cards with no recent progress do not glow.

- [ ] **Step 8: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add src/agent_kanban/routes/progress.py web/src/api.ts web/src/components/TaskCard.tsx web/src/components/Column.tsx web/src/pages/Board.tsx
git commit -m "feat: live card indicator keyed off last progress event"
```

---

## Task 8: Replace deprecated `datetime.utcnow()` with `datetime.now(UTC)`

`datetime.utcnow()` is deprecated in Python 3.12+ and emits 130 warnings per test run. Switch all 12 call sites to `datetime.now(timezone.utc)`.

**Files:**
- Modify: `src/agent_kanban/models.py`
- Modify: `src/agent_kanban/services.py`

- [ ] **Step 1: Find all call sites**

Run: `grep -rn "datetime.utcnow" src/`
Expected: ~12 hits across `models.py` (default factories) and `services.py` (mutation timestamps).

- [ ] **Step 2: Update `models.py`**

Open `src/agent_kanban/models.py`. Change the import line:
```python
from datetime import datetime
```
to:
```python
from datetime import UTC, datetime
```
Then replace every `default_factory=datetime.utcnow` with `default_factory=lambda: datetime.now(UTC)`.

- [ ] **Step 3: Update `services.py`**

Open `src/agent_kanban/services.py`. Change the import:
```python
from datetime import datetime
```
to:
```python
from datetime import UTC, datetime
```
Then replace every `datetime.utcnow()` call with `datetime.now(UTC)`. There are ~7 occurrences in `update_task`, `claim_task`, `post_progress`, `complete_task`, `request_review`.

- [ ] **Step 4: Run the test suite — confirm green AND warning-free**

Run: `uv run pytest -W error::DeprecationWarning -v 2>&1 | tail -20`

The `-W error::DeprecationWarning` flag turns deprecation warnings into errors. If any `utcnow` calls remain (or any other deprecation), tests will FAIL. Expected: all 43 tests pass with no warnings.

If other unrelated DeprecationWarnings surface, do NOT chase them in this task — note them in the report and relax the flag back to default. The goal is the `utcnow` sweep.

- [ ] **Step 5: Run the suite normally to confirm**

Run: `uv run pytest -v`
Expected: 43 passing. The 130-warning count from before should drop to near zero.

- [ ] **Step 6: Commit**

```bash
cd /Users/graywrk/src/graywrk_agents_canban
git add src/agent_kanban/models.py src/agent_kanban/services.py
git commit -m "chore: replace deprecated datetime.utcnow() with datetime.now(UTC)"
```

---

## Phase 2 Acceptance Criteria

Phase 2 is complete when all of the following hold:

- [ ] `uv run pytest -v` passes (43+ tests, no `utcnow` deprecation warnings).
- [ ] `cd web && pnpm build` succeeds with no TypeScript errors.
- [ ] Posting a comment on a `review`-status task moves it to `in_progress` (or to `ready` if the user picks that option); posting on a non-review task leaves the status unchanged.
- [ ] The comment input shows a pending state and surfaces network errors inline.
- [ ] Reopen/Cancel buttons on CardDetail surface errors instead of failing silently.
- [ ] Diff progress events render with shiki syntax highlighting and an expand-all toggle.
- [ ] Artifact progress events render as link cards with thumbnails (images) or kind-based icons.
- [ ] The WebSocket reconnects with exponential backoff (visible in the browser console after killing the backend).
- [ ] `@dnd-kit/*` is no longer in `web/package.json`.
- [ ] TaskCard glows when its most recent progress event is within 30s, not on creation.

---

## Notes for the implementer

- No DB migrations in this plan. If a task seems to need one, escalate rather than adding a migration.
- `file:///` artifact URLs are intentional placeholders — they will not resolve in a browser. The card is a visual anchor; Phase 3+ may add a real artifact-serving endpoint.
- The shiki highlighter is loaded lazily and cached module-level; the first diff expand pays the load cost, subsequent ones are instant.
- The WS reconnect caps at 5 retries then gives up; the user must refresh. Auto-resume after give-up is intentionally out of scope (would need a health-check + reconnect UI).
- Task 8's `-W error::DeprecationWarning` run may surface unrelated warnings (e.g. from third-party deps). Do not fix those here — note them and move on.
