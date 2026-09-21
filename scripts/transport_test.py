"""Exercise real stdio and HTTP MCP transports against the registered bridge."""
from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"list_projects", "get_project_files", "read_file", "read_project_snapshot",
            "get_local_git_status", "get_local_diff", "get_local_commits"}


async def check(target, label: str, directory_source: str | None = None, snapshot_path: str = "") -> None:
    async with Client(target) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == EXPECTED
        assert all(t.annotations and t.annotations.read_only_hint for t in tools.tools)

        async def call(name, **arguments):
            result = await client.call_tool(name, arguments)
            assert not result.is_error, result.content
            return result.structured_content or json.loads(result.content[0].text)

        projects = (await call("list_projects"))["projects"]
        assert any(p["name"] == "project-brain-mcp" and p["git_repository_root"] for p in projects)
        manifest = await call("get_project_files", project="project-brain-mcp")
        paths = {f["path"] for f in manifest["files"]}
        assert "README.md" in paths
        assert not any(p.startswith((".runtime/", ".venv/", ".git/")) for p in paths)
        assert "data/projects.json" not in paths
        content = await call("read_file", project="project-brain-mcp", path="README.md")
        assert content["content"] == (ROOT / "README.md").read_bytes().decode("utf-8")
        assert content["sha256"] == hashlib.sha256((ROOT / "README.md").read_bytes()).hexdigest()
        for tool in ("get_local_git_status", "get_local_diff", "get_local_commits"):
            await call(tool, project="project-brain-mcp")
        first = await call("read_project_snapshot", project="project-brain-mcp", max_chars=8000)
        chunks = [first["content"]]
        page = first
        while not page["complete"]:
            page = await call("read_project_snapshot", project="project-brain-mcp",
                              cursor=page["next_cursor"], max_chars=8000, snapshot_id=first["snapshot_id"])
            assert "error" not in page
            chunks.append(page["content"])
        assert hashlib.sha256("".join(chunks).encode("utf-8")).hexdigest() == first["snapshot_id"]
        assert len(chunks) > 1, "Expected an actual multipage read"
        for bad_path in ("../README.md", ".git/config", "/README.md", "data/projects.json"):
            result = await client.call_tool("read_file", {"project": "project-brain-mcp", "path": bad_path})
            assert result.is_error, bad_path
        result = await client.call_tool("get_project_files", {"project": "unregistered"})
        assert result.is_error
        print(f"{label}_PASS files={len(paths)} snapshot_pages={len(chunks)} tools={len(tools.tools)}")
        if directory_source:
            source = next(p for p in projects if p["name"] == directory_source)
            assert source["source"] == "directory" and not source["git_tools_available"]
            root = Path(source["path"])
            listing = await call("get_project_files", project=directory_source)
            assert listing["recursive"] is False
            sample = await call("read_file", project=directory_source, path="README.md")
            data = (root / "README.md").read_bytes()
            assert sample["content"] == data.decode("utf-8", errors="replace")
            assert sample["sha256"] == hashlib.sha256(data).hexdigest()
            page = await call("read_project_snapshot", project=directory_source, path=snapshot_path, max_chars=200000)
            sid = page["snapshot_id"]
            chunks = [page["content"]]
            while not page["complete"]:
                page = await call("read_project_snapshot", project=directory_source, path=snapshot_path,
                                  cursor=page["next_cursor"], snapshot_id=sid, max_chars=200000)
                assert "error" not in page
                chunks.append(page["content"])
            assert hashlib.sha256("".join(chunks).encode()).hexdigest() == sid
            result = await client.call_tool("read_file", {"project": directory_source, "path": "../memory/README.md"})
            assert result.is_error
            print(f"{label}_DIRECTORY_PASS source={directory_source} path={snapshot_path} text_files={page['text_files_included']} pages={len(chunks)}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory-source")
    parser.add_argument("--snapshot-path", default="")
    args = parser.parse_args()
    params = StdioServerParameters(command=sys.executable,
                                  args=["-m", "project_brain.server", "--transport", "stdio"],
                                  cwd=str(ROOT), env={**os.environ, "PYTHONUTF8": "1"})
    await check(params, "STDIO_TRANSPORT", args.directory_source, args.snapshot_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    logs = ROOT / ".runtime" / "transport-test.log"
    logs.parent.mkdir(parents=True, exist_ok=True)
    with logs.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "project_brain.server", "--transport", "streamable-http", "--port", str(port)],
            cwd=ROOT, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"HTTP server exited; inspect {logs}")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    await asyncio.sleep(0.1)
            else:
                raise TimeoutError("HTTP server did not start within 10 seconds")
            await check(f"http://127.0.0.1:{port}/mcp", "HTTP_TRANSPORT", args.directory_source, args.snapshot_path)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main())
