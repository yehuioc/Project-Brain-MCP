from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import Client
from project_brain.server import mcp

EXPECTED = {
    "list_projects",
    "get_project_files",
    "read_file",
    "read_project_snapshot",
    "get_local_git_status",
    "get_local_diff",
    "get_local_commits",
}


async def run() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        missing = EXPECTED - names
        extra = names - EXPECTED
        if missing:
            raise AssertionError(f"Missing MCP tools: {sorted(missing)}")
        if extra:
            raise AssertionError(f"Unexpected legacy MCP tools remain: {sorted(extra)}")
        result = await client.call_tool("list_projects", {})
        if result.is_error:
            raise AssertionError(f"list_projects MCP call failed: {result.content}")
        print("MCP_PROTOCOL_TEST_PASS")
        print("protocol_version=", client.protocol_version)
        print("tools=", ", ".join(sorted(names)))


if __name__ == "__main__":
    asyncio.run(run())
