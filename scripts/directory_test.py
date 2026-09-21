"""Directory-mode regression and real MCP transport boundary tests."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_brain.bridge import ProjectBridge
from mcp import Client
from mcp.client.stdio import StdioServerParameters


def rejected(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (ValueError, OSError):
        return
    raise AssertionError(f"Expected denial: {args} {kwargs}")


async def transport(config: Path, original: str) -> None:
    # There is deliberately no Git on PATH. Directory mode must not need it.
    params = StdioServerParameters(command=sys.executable, args=["-m", "project_brain.server"],
                                  cwd=str(ROOT), env={**os.environ, "PATH": "", "PYTHONUTF8": "1",
                                                     "PROJECT_BRAIN_CONFIG": str(config)})
    async with Client(params) as client:
        async def call(name, **args):
            result = await client.call_tool(name, args)
            assert not result.is_error, result.content
            return result.structured_content or json.loads(result.content[0].text)
        sources = (await call("list_projects"))["projects"]
        assert [p["name"] for p in sources] == ["library"]
        assert not sources[0]["git_tools_available"]
        listing = await call("get_project_files", project="library", path="notes", limit=1)
        assert not listing["complete"] and listing["next_cursor"] == 1
        second = await call("get_project_files", project="library", path="notes", cursor=1, limit=1)
        assert second["complete"]
        one = await call("read_file", project="library", path="notes/a.md")
        assert one["content"] == original
        page = await call("read_project_snapshot", project="library", path="notes", max_chars=1000)
        sid = page["snapshot_id"]
        chunks = [page["content"]]
        while not page["complete"]:
            page = await call("read_project_snapshot", project="library", path="notes",
                              cursor=page["next_cursor"], max_chars=1000, snapshot_id=sid)
            assert "error" not in page
            chunks.append(page["content"])
        payload = "".join(chunks)
        assert hashlib.sha256(payload.encode()).hexdigest() == sid
        assert original in payload and "other-scope-marker" not in payload
        assert len(chunks) > 1
        for name, args in [
            ("get_project_files", {"project": "memory"}),
            ("read_file", {"project": "library", "path": "../outside.txt"}),
            ("read_file", {"project": "library", "path": ".env"}),
            ("get_project_files", {"project": "library", "path": "../"}),
            ("read_project_snapshot", {"project": "library", "path": "../"}),
            ("get_local_git_status", {"project": "library"}),
            ("get_local_diff", {"project": "library"}),
            ("get_local_commits", {"project": "library"}),
        ]:
            result = await client.call_tool(name, args)
            assert result.is_error, (name, args)
            if args.get("project") == "memory":
                assert "Unknown project" in result.content[0].text
            if name.startswith("get_local_"):
                assert "unavailable for directory" in result.content[0].text
        print("DIRECTORY_STDIO_PASS")


def main() -> None:
    temp = ROOT / ".runtime" / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp) as td:
        base = Path(td)
        library = base / "library"
        (library / "notes").mkdir(parents=True)
        original = "# 中文资料\n" + "原始内容保持完整。\n" * 500
        (library / "notes" / "a.md").write_bytes(original.encode("utf-8"))
        (library / "notes" / "b.md").write_text("# 第二篇\n", encoding="utf-8")
        (library / "other.md").write_text("other-scope-marker", encoding="utf-8")
        (library / ".env").write_text("must stay excluded", encoding="utf-8")
        (library / ".git").mkdir()
        (library / ".git" / "config").write_text("private git config", encoding="utf-8")
        (library / "private").mkdir()
        (library / "private" / "secret.txt").write_text("excluded custom path", encoding="utf-8")
        (library / "asset.bin").write_bytes(b"\x00" * 4096)
        (base / "outside.txt").write_text("outside-marker", encoding="utf-8")
        config = base / "projects.json"
        raw = {"projects": [{"name": "library", "path": str(library), "source": "directory",
                              "exclude": ["private/**"]}], "security": {}}
        config.write_text(json.dumps(raw), encoding="utf-8")
        bridge = ProjectBridge(config)
        with patch("project_brain.bridge.git_root", side_effect=AssertionError("Git must not run")):
            assert bridge.list_projects()["projects"][0]["source"] == "directory"
            listing = bridge.get_project_files("library")
            assert {p["path"] for p in listing["files"]} == {"notes", "other.md", "asset.bin"}
            assert all(p["sha256"] is None for p in listing["files"])
            assert bridge.read_file("library", "notes/a.md")["content"] == original
            with patch("project_brain.directories.os.walk", side_effect=AssertionError("Do not scan a library to read one file")):
                assert bridge.read_file("library", "notes/a.md")["content"] == original
                assert bridge.get_project_files("library")["complete"]
            assert base64.b64decode(bridge.read_file("library", "asset.bin")["content"]) == b"\x00" * 4096
            for bad in ["../outside.txt", "/notes/a.md", str(library / "notes/a.md"),
                        ".git/config", ".GIT/config", ".git./config", ".env", "private/secret.txt",
                        "notes/a.md:stream", "notes/a.md ", "notes/../../outside.txt"]:
                rejected(bridge.read_file, "library", bad)
            rejected(bridge.get_project_files, "memory")
            rejected(bridge.get_project_files, "library", path="../")
            rejected(bridge.read_project_snapshot, "library", path="../")
            for fn in [bridge.get_local_git_status, bridge.get_local_diff, bridge.get_local_commits]:
                rejected(fn, "library")
        # Windows junctions must not make a sibling scope or excluded content readable.
        links = []
        try:
            (library / "outside-link.txt").symlink_to(base / "outside.txt")
            links.append(("outside-link.txt", "outside-link.txt"))
        except OSError:
            pass
        if os.name == "nt":
            cp = subprocess.run(["cmd", "/c", "mklink", "/J", str(library / "linked-private"),
                                 str(library / "private")], capture_output=True)
            assert cp.returncode == 0, cp.stderr
            links.append(("linked-private", "linked-private/secret.txt"))
        try:
            for entry, target in links:
                rejected(bridge.read_file, "library", target)
                row = next(x for x in bridge.get_project_files("library")["files"] if x["path"] == entry)
                assert row["kind"] == "blocked-link"
            snapshot = bridge.read_project_snapshot("library", max_chars=200000)
            assert snapshot["complete"]
            assert snapshot["blocked_links_listed"] == len(links)
            assert "outside-marker" not in snapshot["content"]
            assert "excluded custom path" not in snapshot["content"]
            assert "sha256=not_computed" in snapshot["content"]
            first = bridge.read_project_snapshot("library", path="notes", max_chars=1000)
            (library / "notes" / "b.md").write_text("Changed", encoding="utf-8")
            assert bridge.read_project_snapshot("library", path="notes", snapshot_id=first["snapshot_id"])["error"] == "snapshot_changed"
            raw["security"] = {"max_text_file_bytes": 20, "max_binary_file_bytes": 20,
                               "max_snapshot_total_chars": 20}
            config.write_text(json.dumps(raw), encoding="utf-8")
            limited = ProjectBridge(config)
            rejected(limited.read_file, "library", "notes/a.md")
            rejected(limited.read_file, "library", "asset.bin")
            rejected(limited.read_project_snapshot, "library", path="notes")
            raw["security"] = {}
            config.write_text(json.dumps(raw), encoding="utf-8")
            asyncio.run(transport(config, original))
            # Registration is explicit, repeatable, and does not widen an existing name.
            spec = importlib.util.spec_from_file_location("register_source", ROOT / "scripts/configure_project.py")
            registration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(registration)
            registration.CONFIG = config
            registration.register("library", library, "directory", "test")
            registration.register("library", library, "directory", "test")
            assert len(json.loads(config.read_text())["projects"]) == 1
            try:
                registration.register("library", base, "directory", "must fail")
                raise AssertionError("Repointing must not happen implicitly")
            except SystemExit:
                pass
            print("DIRECTORY_TEST_PASS links_tested=" + str(len(links)))
        finally:
            for entry, _ in links:
                target = library / entry
                if getattr(target, "is_junction", lambda: False)():
                    target.rmdir()  # Remove the verified junction itself, never its target.
                else:
                    target.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
