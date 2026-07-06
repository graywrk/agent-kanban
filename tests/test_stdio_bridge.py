"""Smoke test for the stdio bridge: it should at least import and parse args."""

from agent_kanban.mcp_stdio_bridge import main


def test_bridge_importable():
    # The bridge main() runs an asyncio loop; we only verify import + structure.
    assert callable(main)
