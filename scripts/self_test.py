from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_brain.core import ProjectBridge


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def git(repo: Path, *args: str) -> None:
    cp = run("git", "-C", str(repo), *args)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr)


def main() -> None:
    temp_root = ROOT / ".runtime" / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as td:
        td_path = Path(td)
        repo = td_path / "demo"
        repo.mkdir()
        git(repo, "init")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Project Brain Test")

        (repo / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
        (repo / "README.md").write_text("# Demo\nVersion one.\n", encoding="utf-8")
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("print('v1')\n", encoding="utf-8")
        (repo / "asset.bin").write_bytes(b"\x00\x01\x02binary")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "initial")

        # Current local state differs from HEAD: one modified file and one valid untracked file.
        (repo / "src" / "app.py").write_text("print('v2 local')\n", encoding="utf-8")
        (repo / "new_feature.py").write_text("FEATURE = True\n", encoding="utf-8")
        (repo / "ignored.log").write_text("must not be exposed\n", encoding="utf-8")

        outside = td_path / "outside.txt"
        outside.write_text("outside secret\n", encoding="utf-8")
        symlink_created = False
        try:
            (repo / "outside-link.txt").symlink_to(outside)
            # Git-visible because untracked and not ignored.
            symlink_created = True
        except OSError:
            pass

        cfg = td_path / "projects.json"
        cfg.write_text(json.dumps({
            "projects": [{"name": "demo", "path": str(repo), "description": "test repo"}],
            "security": {"snapshot_chunk_chars": 120, "max_snapshot_chunk_chars": 1000}
        }, ensure_ascii=False), encoding="utf-8")

        b = ProjectBridge(cfg)
        assert b.list_projects()["projects"][0]["name"] == "demo"

        manifest = b.get_project_files("demo")
        paths = {x["path"] for x in manifest["files"]}
        assert "README.md" in paths
        assert "src/app.py" in paths
        assert "new_feature.py" in paths
        assert "ignored.log" not in paths
        assert ".git/HEAD" not in paths

        assert "v2 local" in b.read_file("demo", "src/app.py")["content"]
        binary = b.read_file("demo", "asset.bin")
        assert binary["encoding"] == "base64"
        assert base64.b64decode(binary["content"]) == b"\x00\x01\x02binary"

        try:
            b.read_file("demo", "../outside.txt")
            raise AssertionError("Path traversal should have failed")
        except ValueError:
            pass
        for invalid in ("/README.md", str(repo / "README.md"), ".git/config", ".GIT/config"):
            try:
                b.read_file("demo", invalid)
                raise AssertionError(f"Absolute/internal Git path should fail: {invalid}")
            except ValueError:
                pass
        if symlink_created:
            linked = {x["path"]: x for x in manifest["files"]}.get("outside-link.txt")
            assert linked and linked["kind"] == "blocked-link"

        first = b.read_project_snapshot("demo", max_chars=120)
        assert first["snapshot_id"]
        chunks = [first["content"]]
        cursor = first["next_cursor"]
        while cursor is not None:
            part = b.read_project_snapshot("demo", cursor=cursor, max_chars=120, snapshot_id=first["snapshot_id"])
            assert "error" not in part
            chunks.append(part["content"])
            cursor = part["next_cursor"]
        whole = "".join(chunks)
        assert "print('v2 local')" in whole
        assert "FEATURE = True" in whole
        assert "must not be exposed" not in whole
        assert "asset.bin" in whole

        status = b.get_local_git_status("demo")
        assert status["head"]
        assert any("src/app.py" in line for line in status["status_lines"])
        diff = b.get_local_diff("demo")
        assert "v2 local" in (diff["unstaged_diff"] or "")
        assert "new_feature.py" in diff["untracked_files"]

        # Repository-defined helpers must never run through read-only MCP calls.
        (repo / ".gitattributes").write_text("*.py diff=forbidden\n", encoding="utf-8")
        git(repo, "config", "diff.forbidden.textconv", "project-brain-forbidden-command")
        git(repo, "config", "core.fsmonitor", "project-brain-forbidden-command")
        assert "v2 local" in b.get_local_diff("demo")["unstaged_diff"]
        assert b.get_local_git_status("demo")["head"]
        (repo / "src" / "app.py").write_text("x" * 5000 + "\n", encoding="utf-8")
        assert b.get_local_diff("demo", max_chars=6000)["truncated"]

        commits = b.get_local_commits("demo")
        assert commits["commits"]
        assert commits["classification"] == "recent-local-history-no-upstream"

        # If the project changes during paged snapshot reading, the old snapshot id must be rejected.
        (repo / "README.md").write_text("# Demo\nChanged during read.\n", encoding="utf-8")
        changed = b.read_project_snapshot("demo", cursor=0, max_chars=120, snapshot_id=first["snapshot_id"])
        assert changed.get("error") == "snapshot_changed"

        print("SELF_TEST_PASS")


if __name__ == "__main__":
    main()
