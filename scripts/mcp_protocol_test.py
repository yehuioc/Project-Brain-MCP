from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import Client
from project_brain.server import mcp

EXPECTED = {
    "list_workspaces",
    "list_workspace_areas",
    "get_workspace_overview",
    "find_workspace_files",
    "read_workspace_file",
    "search_workspace_text",
    "list_git_repositories",
    "get_git_repository_state",
    "get_git_history",
    "get_git_diff",
    "get_recent_errors",
    "get_test_results",
}


async def run() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        missing = EXPECTED - names
        if missing:
            raise AssertionError(f"Missing MCP tools: {sorted(missing)}")
        result = await client.call_tool("list_workspaces", {})
        if result.is_error:
            raise AssertionError(f"list_workspaces MCP call failed: {result.content}")
        print("MCP_PROTOCOL_TEST_PASS")
        print("protocol_version=", client.protocol_version)
        print("tools=", ", ".join(sorted(names)))


if __name__ == "__main__":
    asyncio.run(run())
