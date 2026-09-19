from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "projects.json"
EXAMPLE = ROOT / "data" / "projects.example.json"


def git_root(path: Path) -> Path | None:
    cp = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if cp.returncode != 0:
        return None
    return Path(cp.stdout.strip()).resolve()


def load() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    if EXAMPLE.exists():
        cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        cfg["projects"] = []
        return cfg
    return {"projects": [], "security": {}}


def main() -> None:
    cfg = load()
    print("\nProject Brain MCP v0.3 - register ONE Git project for read-only access\n")
    name = input("Project name (e.g. fortune-light): ").strip()
    if not name:
        raise SystemExit("Project name is required")
    raw = input(r"Full Git project root path (e.g. E:\workbench\fortune-light): ").strip().strip('"')
    path = Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise SystemExit(f"Folder does not exist: {path}")
    top = git_root(path)
    if top is None:
        raise SystemExit("The selected folder is not inside a Git repository")
    if top != path:
        raise SystemExit(f"Please register the Git repository root instead: {top}")
    desc = input("Short description (optional): ").strip()

    projects = [p for p in cfg.get("projects", []) if p.get("name") != name]
    projects.append({"name": name, "path": str(path), "description": desc})
    cfg["projects"] = projects
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nRegistered:")
    print(f"  {name} -> {path}")
    print("\nThe MCP can read only explicitly registered project roots. Run this script again to add or update another project.")
    print(f"Config: {CONFIG}")


if __name__ == "__main__":
    main()
