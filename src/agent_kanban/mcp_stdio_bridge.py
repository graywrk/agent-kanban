"""stdio ↔ HTTP MCP bridge.

Lets an agent configured with `command: kanban-mcp` connect to the single
running board server over stdio, while the bridge forwards every message to
the board's /mcp HTTP endpoint. This keeps one shared DB across all agents.
"""
import asyncio
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client


async def _proxy(server_url: str) -> None:
    async with streamablehttp_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Loop forever: read JSON-RPC from stdin, forward, write reply.
            # The MCP stdio client + session handle the framing for us when
            # we let the session run its own message pump. For a generic
            # proxy we use the lower-level approach: pipe bytes through.
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await asyncio.get_event_loop().connect_read_pipe(
                lambda: protocol, sys.stdin
            )

            while True:
                line = await reader.readline()
                if not line:
                    break
                # Forward raw JSON-RPC line to the HTTP server session and
                # echo back whatever comes back. The simplest reliable
                # approach is to delegate tool calls to the session object.
                # This implementation focuses on the common path: tools/list
                # and tools/call. For full proxy semantics, extend here.
                import json

                try:
                    req = json.loads(line)
                except json.JSONDecodeError:
                    continue
                method = req.get("method")
                if method == "tools/list":
                    tools = await session.list_tools()
                    sys.stdout.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": req.get("id"),
                                "result": {
                                    "tools": [
                                        {
                                            "name": t.name,
                                            "description": t.description,
                                            "inputSchema": t.inputSchema,
                                        }
                                        for t in tools.tools
                                    ]
                                },
                            }
                        )
                        + "\n"
                    )
                    sys.stdout.flush()
                elif method == "tools/call":
                    params = req.get("params", {})
                    result = await session.call_tool(
                        params["name"], params.get("arguments", {})
                    )
                    # CallToolResult is a pydantic model; model_dump() yields a
                    # JSON-serializable dict (with by_alias to match the MCP wire
                    # shape, e.g. content / isError / structuredContent).
                    sys.stdout.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": req.get("id"),
                                "result": result.model_dump(by_alias=True, mode="json"),
                            }
                        )
                        + "\n"
                    )
                    sys.stdout.flush()
                elif method == "initialize":
                    sys.stdout.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": req.get("id"),
                                "result": {
                                    "protocolVersion": "2024-11-05",
                                    "capabilities": {},
                                    "serverInfo": {"name": "kanban-mcp", "version": "0.1"},
                                },
                            }
                        )
                        + "\n"
                    )
                    sys.stdout.flush()


def main() -> None:
    url = os.environ.get("AGENT_KANBAN_URL", "http://localhost:7331/mcp")
    asyncio.run(_proxy(url))


if __name__ == "__main__":
    main()
