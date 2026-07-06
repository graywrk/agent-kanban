"""End-to-end Phase 1 smoke: simulate the agent-side MCP calls + the UI-side REST calls.

Exercises the full user journey:
  create task (UI) -> ready (UI) -> get_next_task (agent) -> claim_task (agent)
  -> post_progress (agent) -> GET progress (UI) -> complete_task (agent)
  -> GET task -> status == done (UI).

Both the REST client and the in-process MCP tools resolve their DB sessions from
the same DATABASE_URL (pointed at the per-test throwaway DB by the `db_url`
fixture + `get_settings.cache_clear()`), so the two sides observe each other's
commits in real time — just like production, only without a network hop.

The agent side authenticates with a real bearer token minted by the admin via
``POST /api/tokens`` (agent_name="hermes"). Since the in-process MCP tools
bypass HTTP, we stub the verifiers to surface that Principal(agent_name="hermes")
for the test — exercising the real token-creation path while keeping the tool
calls deterministic.
"""
import json

import pytest

from agent_kanban.mcp_server import mcp


def _to_dict(result):
    """Decode the FastMCP-wrapped result of `call_tool` into a plain value.

    Same unwrapping logic as tests/test_mcp_server.py — handles the SDK's
    tuple-of-(unstructured, structured), list-of-TextContent, and empty-list
    return shapes for the pinned `mcp` version.
    """
    if isinstance(result, tuple) and len(result) == 2:
        structured = result[1]
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    if isinstance(result, list):
        if not result:
            return None
        if all(hasattr(block, "text") for block in result):
            decoded = []
            for block in result:
                try:
                    decoded.append(json.loads(block.text))
                except (ValueError, TypeError):
                    decoded.append(block.text)
            return decoded[0] if len(decoded) == 1 else decoded
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


@pytest.mark.asyncio
async def test_full_phase1_journey(authed_client, monkeypatch):
    # 0. Mint a real bearer token for the "hermes" agent via the admin UI, and
    #    stub the MCP verifiers to surface that Principal for in-process tool
    #    calls (call_tool bypasses HTTP, so MCPAuthMiddleware never runs).
    from agent_kanban import mcp_server
    from agent_kanban.auth import Principal

    r = await authed_client.post(
        "/api/tokens", json={"agent_name": "hermes", "description": "e2e"}
    )
    assert r.status_code == 201
    token = r.json()["token"]
    assert token

    async def _matching(agent):
        if agent != "hermes":
            raise PermissionError(f"agent {agent!r} != 'hermes'")
        return Principal(kind="token", agent_name="hermes")

    async def _any():
        return Principal(kind="token", agent_name="hermes")

    monkeypatch.setattr(mcp_server, "_require_matching_agent", _matching)
    monkeypatch.setattr(mcp_server, "_require_any_principal", _any)

    # 1. User creates a task via UI (status defaults to todo).
    r = await authed_client.post("/api/tasks", json={"title": "Write README", "tags": ["docs"]})
    assert r.status_code == 201
    task_id = r.json()["id"]
    assert r.json()["status"] == "todo"

    # 2. User moves it to ready (drag-and-drop in UI).
    r = await authed_client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})
    assert r.status_code == 200
    assert r.json()["status"] == "ready"

    # 3. Agent discovers and claims it via MCP.
    nxt = await mcp.call_tool("get_next_task", {"tags_any": ["docs"]})
    nxt_data = _to_dict(nxt)
    assert isinstance(nxt_data, dict)
    assert nxt_data["id"] == task_id

    claim = await mcp.call_tool("claim_task", {"task_id": task_id, "agent": "hermes"})
    claim_data = _to_dict(claim)
    assert claim_data["ok"] is True
    assert claim_data["task"]["claimed_by"] == "hermes"
    assert claim_data["task"]["status"] == "in_progress"

    # 4. Agent posts progress.
    await mcp.call_tool(
        "post_progress",
        {
            "task_id": task_id,
            "agent": "hermes",
            "kind": "text",
            "content": "starting on the README",
        },
    )

    # 5. UI sees the progress event.
    r = await authed_client.get(f"/api/tasks/{task_id}/progress")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    assert events[0]["agent"] == "hermes"
    assert events[0]["kind"] == "text"

    # 6. Agent completes.
    await mcp.call_tool(
        "complete_task", {"task_id": task_id, "agent": "hermes", "summary": "done"}
    )

    # 7. Board reflects done.
    r = await authed_client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"
