from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "projects.json"
EXAMPLE = ROOT / "data" / "projects.example.json"
sys.path.insert(0, str(ROOT))
from project_brain.bridge import ProjectBridge


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


def register(name: str, path: Path, source: str, description: str) -> None:
    cfg = load()
    if not name:
        raise SystemExit("Project name is required")
    if source not in {"git", "directory"}:
        raise SystemExit("Source must be git or directory")
    path = path.expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise SystemExit(f"Folder does not exist: {path}")
    if source == "git":
        top = git_root(path)
        if top != path:
            raise SystemExit("Git mode requires a repository root. Use directory mode for an explicitly authorized folder; do not widen access to its parent.")
    existing = next((p for p in cfg.get("projects", []) if p.get("name") == name), None)
    if existing and (Path(existing["path"]).resolve() != path or existing.get("source", "git") != source):
        raise SystemExit("This name already refers to a different path/source. Choose a new name or explicitly remove the old registration first.")

    projects = [p for p in cfg.get("projects", []) if p.get("name") != name]
    projects.append({**(existing or {}), "name": name, "path": str(path),
                     "source": source, "description": description})
    cfg["projects"] = projects
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    pending = CONFIG.with_suffix(".json.tmp")
    try:
        pending.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        ProjectBridge(pending)
        os.replace(pending, CONFIG)
    finally:
        pending.unlink(missing_ok=True)

    print("\nRegistered:")
    print(f"  {name} -> {path}")
    print(f"Source: {source}. Restart the MCP/tunnel, then verify with list_projects.")
    print(f"Config: {CONFIG}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Register one explicitly authorized read-only source")
    parser.add_argument("--name")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--source", choices=["git", "directory"])
    parser.add_argument("--description", default="")
    args = parser.parse_args()
    if args.name is not None or args.path is not None:
        if not args.name or args.path is None or args.source is None:
            parser.error("Noninteractive registration requires --name, --path and --source")
        register(args.name, args.path, args.source, args.description)
    else:
        print("Register ONE explicitly authorized source for read-only access.")
        name = input("Source name: ").strip()
        path = Path(input("Full folder path: ").strip().strip('"'))
        source = input("Source type [git/directory] (default git): ").strip() or "git"
        description = input("Short description (optional): ").strip()
        register(name, path, source, description)


if __name__ == "__main__":
    main()
