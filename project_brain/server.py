from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mcp.server import MCPServer
from .core import ProjectBrain


def default_config_path() -> Path:
    env = os.environ.get("PROJECT_BRAIN_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "data" / "workspaces.json").resolve()


brain = ProjectBrain(default_config_path())

mcp = MCPServer(
    "Project Brain Workspace",
    instructions=(
        "Read-only workspace context server. Start with list_workspaces, then list_workspace_areas or get_workspace_overview. "
        "Only explicitly configured areas and root files are readable. Git tools are read-only. "
        "Never claim a write/deploy action occurred: this server exposes no write, shell, delete, commit, push, or SQL tools."
    ),
)


@mcp.tool()
def list_workspaces() -> dict:
    """List registered top-level workspaces and basic availability."""
    return brain.list_workspaces()


@mcp.tool()
def list_workspace_areas(workspace: str) -> dict:
    """List the explicitly allowed areas and root context files inside a workspace."""
    return brain.list_workspace_areas(workspace)


@mcp.tool()
def get_workspace_overview(workspace: str) -> dict:
    """Get a compact overview of configured areas, recent files, root context files, and root Git presence."""
    return brain.get_workspace_overview(workspace)


@mcp.tool()
def find_workspace_files(workspace: str, pattern: str = "*", area: str = "*", limit: int = 100) -> dict:
    """Find allow-listed text files across one configured area or all areas. area='*' searches all selected areas."""
    return brain.find_workspace_files(workspace, pattern, area, limit)


@mcp.tool()
def read_workspace_file(workspace: str, relative_path: str, start_line: int = 1, max_lines: int = 300) -> dict:
    """Read a bounded line range from a text file that is inside an allowed area or configured root_files."""
    return brain.read_workspace_file(workspace, relative_path, start_line, max_lines)


@mcp.tool()
def search_workspace_text(workspace: str, query: str, area: str = "*", scope: str = "all", limit: int = 30) -> dict:
    """Keyword-search across selected workspace areas. scope: all/docs/logs/tests/code."""
    return brain.search_workspace_text(workspace, query, area, scope, limit)


@mcp.tool()
def list_git_repositories(workspace: str, area: str = "*", max_depth: int = 6, limit: int = 100) -> dict:
    """Discover the workspace-root Git repository and nested Git repositories under selected areas."""
    return brain.list_git_repositories(workspace, area, max_depth, limit)


@mcp.tool()
def get_git_repository_state(workspace: str, repo_path: str = ".") -> dict:
    """Read branch/status/latest commit for a discovered Git repository. repo_path='.' means workspace root."""
    return brain.get_git_repository_state(workspace, repo_path)


@mcp.tool()
def get_git_history(workspace: str, repo_path: str = ".", limit: int = 20) -> dict:
    """Read recent commits from a workspace-root or nested allowed Git repository."""
    return brain.get_git_history(workspace, repo_path, limit)


@mcp.tool()
def get_git_diff(workspace: str, repo_path: str = ".", target: str = "working", max_chars: int = 30000) -> dict:
    """Read a repository diff. target: working, staged, HEAD, or a safe Git revision string."""
    return brain.get_git_diff(workspace, repo_path, target, max_chars)


@mcp.tool()
def get_recent_errors(workspace: str, area: str = "*", limit: int = 50) -> dict:
    """Scan log-like files across selected areas for recent error/exception/traceback/failure lines."""
    return brain.get_recent_errors(workspace, area, limit)


@mcp.tool()
def get_test_results(workspace: str, area: str = "*", limit: int = 30) -> dict:
    """Locate test result files across selected areas and return bounded previews."""
    return brain.get_test_results(workspace, area, limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Brain Workspace MCP")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps({"config": str(default_config_path()), "workspaces": brain.list_workspaces()}, ensure_ascii=False, indent=2))
        return
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
