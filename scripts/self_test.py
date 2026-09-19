from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_brain.core import ProjectBrain


def git(*args: str) -> None:
    subprocess.run(["git", *args], capture_output=True, check=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "agent-v2"
        (root / "memory").mkdir(parents=True)
        (root / "workbench" / "demo").mkdir(parents=True)
        (root / "secrets").mkdir(parents=True)
        (root / "AGENTS.md").write_text("# Agent V2\nRead memory and workbench when needed.\n", encoding="utf-8")
        (root / "memory" / "MEMORY.md").write_text("# Memory\nImportant project decision: use MCP.\n", encoding="utf-8")
        (root / "workbench" / "demo" / "README.md").write_text("# Demo\nTODO: wire workspace MCP\n", encoding="utf-8")
        (root / "workbench" / "demo" / "run.log").write_text("INFO start\nERROR demo failure\n", encoding="utf-8")
        (root / "secrets" / "password.txt").write_text("do-not-read", encoding="utf-8")
        (root / ".env").write_text("TOKEN=secret", encoding="utf-8")

        git("init", str(root))
        git("-C", str(root), "config", "user.email", "test@example.invalid")
        git("-C", str(root), "config", "user.name", "Project Brain Test")
        git("-C", str(root), "add", "AGENTS.md", "memory/MEMORY.md")
        git("-C", str(root), "commit", "-m", "workspace root")

        demo = root / "workbench" / "demo"
        git("init", str(demo))
        git("-C", str(demo), "config", "user.email", "test@example.invalid")
        git("-C", str(demo), "config", "user.name", "Project Brain Test")
        git("-C", str(demo), "add", ".")
        git("-C", str(demo), "commit", "-m", "demo initial")

        cfg = Path(td) / "workspaces.json"
        cfg.write_text(json.dumps({
            "workspaces": [{
                "name": "agent-v2", "path": str(root),
                "areas": [
                    {"name": "memory", "path": "memory"},
                    {"name": "workbench", "path": "workbench"}
                ],
                "root_files": ["AGENTS.md"]
            }],
            "security": {"excluded_dirs": ["secrets"]}
        }, ensure_ascii=False), encoding="utf-8")

        b = ProjectBrain(cfg)
        assert b.list_workspaces()["workspaces"][0]["name"] == "agent-v2"
        assert {x["name"] for x in b.list_workspace_areas("agent-v2")["areas"]} == {"memory", "workbench"}
        assert "Agent V2" in b.read_workspace_file("agent-v2", "AGENTS.md")["content"]
        assert b.search_workspace_text("agent-v2", "Important project decision", "memory")["hits"]
        assert b.search_workspace_text("agent-v2", "TODO", "workbench", "docs")["hits"]
        assert b.get_recent_errors("agent-v2", "workbench")["errors"]
        repos = {r["path"] for r in b.list_git_repositories("agent-v2")["repositories"]}
        assert "." in repos
        assert "workbench/demo" in repos
        assert b.get_git_repository_state("agent-v2", ".")["latest_commit"]
        assert b.get_git_repository_state("agent-v2", "workbench/demo")["latest_commit"]
        try:
            b.read_workspace_file("agent-v2", "../outside.txt")
            raise AssertionError("Path traversal should have failed")
        except ValueError:
            pass
        try:
            b.read_workspace_file("agent-v2", "secrets/password.txt")
            raise AssertionError("Excluded directory should have failed")
        except ValueError:
            pass
        try:
            b.read_workspace_file("agent-v2", ".env")
            raise AssertionError("Unconfigured/excluded root file should have failed")
        except ValueError:
            pass
        print("SELF_TEST_PASS")


if __name__ == "__main__":
    main()
