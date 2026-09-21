from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from .core import ProjectBridge


def default_config_path() -> Path:
    env = os.environ.get("PROJECT_BRAIN_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "data" / "projects.json").resolve()


bridge = ProjectBridge(default_config_path())
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False,
    idempotent_hint=True, open_world_hint=False,
)

mcp = MCPServer(
    "Project Brain MCP - Full Project Bridge",
    instructions=(
        "Read-only bridge to explicitly registered local Git projects and directory sources. "
        "First use list_projects and select a source by name. Never read unrelated sources. "
        "Git sources expose the complete Git-defined project surface. For directory sources, get_project_files lists immediate children with path/cursor/limit; it does not consult Git. "
        "Inspect file listings first, then choose original files or scopes needed for the user's current task. "
        "Keep full access available: do not automatically exclude docs, vendor or historical evidence, and do not require a Codex pre-summary or semantic filter. "
        "Use read_file for selected Git files; path-scoped snapshots are only supported for directory sources. "
        "Read a full snapshot when the user requests it or the task needs the entire scope, rather than loading every source for every task. "
        "Use read_project_snapshot repeatedly with the same project, path and snapshot_id until complete=true for all text in a selected scope. "
        "Pagination and hashes demonstrate complete transfer, not simultaneous model context capacity or understanding. State the scope actually read and material unread gaps; never claim full understanding from complete=true alone. "
        "Directory sources have no Git tools and never expose ancestor repository history. "
        "The server does not search, summarize, rank importance, write files, run arbitrary shell commands, commit, push, fetch, deploy, or mutate projects."
    ),
)


def call_bridge(method, *args):
    try:
        return method(*args)
    except (ValueError, OSError) as exc:
        # Expected access/size errors must reach the client, not become generic crashes.
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations=READ_ONLY)
def list_projects() -> dict:
    """List explicitly registered read-only sources and their source type; does not read document contents."""
    return call_bridge(bridge.list_projects)


@mcp.tool(annotations=READ_ONLY)
def get_project_files(project: str, path: str = "", cursor: int = 0, limit: int = 200) -> dict:
    """Inspect files before choosing what the current task needs. Git: complete tracked + untracked non-ignored file surface. Directory: immediate children of path, paged via next_cursor until complete=true; enter a child directory by passing its path. Directory listings do not read file contents."""
    return call_bridge(bridge.get_project_files, project, path, cursor, limit)


@mcp.tool(annotations=READ_ONLY)
def read_file(project: str, path: str, mode: str = "auto") -> dict:
    """Read one allowed file from the named source. Directory reads bypass Git and access only this file. auto returns text for text files and base64 for binary files."""
    return call_bridge(bridge.read_file, project, path, mode)


@mcp.tool(annotations=READ_ONLY)
def read_project_snapshot(
    project: str,
    cursor: int = 0,
    max_chars: int | None = None,
    snapshot_id: str | None = None,
    path: str = "",
) -> dict:
    """Read a full text snapshot when the user requests it or the task needs the entire scope; use read_file for selected files. path scoping is only for directory sources. Keep project/path/snapshot_id unchanged while following next_cursor to complete=true. Completion proves transfer, not model comprehension; report the actual read scope and material unread gaps. Directory binary entries are listed without reading/hashing all binary bytes. Exclusions and size-limit errors are explicit; no silent truncation."""
    return call_bridge(bridge.read_project_snapshot, project, cursor, max_chars, snapshot_id, path)


@mcp.tool(annotations=READ_ONLY)
def get_local_git_status(project: str) -> dict:
    """Read current branch, HEAD, working-tree status, and local ahead/behind information without fetching from the network."""
    return call_bridge(bridge.get_local_git_status, project)


@mcp.tool(annotations=READ_ONLY)
def get_local_diff(project: str, max_chars: int = 120000) -> dict:
    """Read current unstaged/staged diffs plus the list of untracked non-ignored files."""
    return call_bridge(bridge.get_local_diff, project, max_chars)


@mcp.tool(annotations=READ_ONLY)
def get_local_commits(project: str, limit: int = 50) -> dict:
    """Read commits ahead of the locally stored upstream tracking ref; if no upstream exists, return recent local history with that limitation stated."""
    return call_bridge(bridge.get_local_commits, project, limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Brain MCP v0.3 - Full Project Bridge")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps({"config": str(default_config_path()), **bridge.list_projects()}, ensure_ascii=False, indent=2))
        return
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
