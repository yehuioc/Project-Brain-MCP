from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mcp.server import MCPServer
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
        "Read-only bridge to explicitly registered local Git projects. "
        "Use get_project_files to see the complete Git-defined project surface, or read_project_snapshot repeatedly until complete=true to consume the full current textual project snapshot. "
        "The server does not search, summarize, rank importance, write files, run arbitrary shell commands, commit, push, fetch, deploy, or mutate projects."
    ),
)


@mcp.tool(annotations=READ_ONLY)
def list_projects() -> dict:
    """List the local Git projects explicitly registered for MCP read access."""
    return bridge.list_projects()


@mcp.tool(annotations=READ_ONLY)
def get_project_files(project: str) -> dict:
    """List the complete Git-defined project surface: tracked files plus untracked non-ignored files."""
    return bridge.get_project_files(project)


@mcp.tool(annotations=READ_ONLY)
def read_file(project: str, path: str, mode: str = "auto") -> dict:
    """Read one Git-visible project file. auto returns text for text files and base64 for binary files."""
    return bridge.read_file(project, path, mode)


@mcp.tool(annotations=READ_ONLY)
def read_project_snapshot(
    project: str,
    cursor: int = 0,
    max_chars: int | None = None,
    snapshot_id: str | None = None,
) -> dict:
    """Read the full current textual project snapshot in deterministic chunks. Continue with next_cursor until complete=true. Pass snapshot_id on subsequent calls to detect mid-read local changes."""
    return bridge.read_project_snapshot(project, cursor, max_chars, snapshot_id)


@mcp.tool(annotations=READ_ONLY)
def get_local_git_status(project: str) -> dict:
    """Read current branch, HEAD, working-tree status, and local ahead/behind information without fetching from the network."""
    return bridge.get_local_git_status(project)


@mcp.tool(annotations=READ_ONLY)
def get_local_diff(project: str, max_chars: int = 120000) -> dict:
    """Read current unstaged/staged diffs plus the list of untracked non-ignored files."""
    return bridge.get_local_diff(project, max_chars)


@mcp.tool(annotations=READ_ONLY)
def get_local_commits(project: str, limit: int = 50) -> dict:
    """Read commits ahead of the locally stored upstream tracking ref; if no upstream exists, return recent local history with that limitation stated."""
    return bridge.get_local_commits(project, limit)


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
