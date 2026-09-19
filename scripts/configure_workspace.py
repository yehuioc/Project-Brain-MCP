from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "workspaces.json"

SUGGESTED_DIRS = {
    ".agents", ".claude", ".codex", "automations", "config", "docs", "ingestion",
    "memory", "prompts", "runs", "scripts", "skills", "sources", "state", "workbench",
}
SUGGESTED_ROOT_FILES = {
    "AGENTS.md", "CLAUDE.md", "HEARTBEAT.md", "IDENTITY.md", "INGESTION.md",
    "MEMORY.md", "SOUL.md", "START-HERE.md", "TOOLS.md", "USER.md",
}
HARD_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".idea", ".vscode", "__pycache__", ".pytest_cache", ".ruff_cache"}
TEXT_ROOT_EXT = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def load() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"workspaces": [], "security": {}}


def save(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def area_name(folder: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", folder.lstrip(".")).strip("-") or "area"
    candidate = base
    i = 2
    while candidate in used:
        candidate = f"{base}-{i}"
        i += 1
    used.add(candidate)
    return candidate


def choose(items: list[Path], suggested_names: set[str], label: str) -> list[Path]:
    if not items:
        return []
    print(f"\n{label}:")
    for i, p in enumerate(items, 1):
        tag = " [suggested]" if p.name in suggested_names else ""
        print(f"  {i:>2}. {p.name}{tag}")
    suggested_idx = [str(i) for i, p in enumerate(items, 1) if p.name in suggested_names]
    default_desc = ",".join(suggested_idx) if suggested_idx else "none"
    print(f"\nPress Enter = use suggested selection ({default_desc}).")
    print("Or type comma-separated numbers/ranges (e.g. 1,3,5-8). Type 'all' to select every listed item. Type 'none' for none.")
    raw = input("Selection: ").strip().lower()
    if not raw:
        return [p for p in items if p.name in suggested_names]
    if raw == "all":
        return items
    if raw == "none":
        return []
    selected: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            if a.isdigit() and b.isdigit():
                lo, hi = sorted((int(a), int(b)))
                selected.update(range(lo, hi + 1))
        elif token.isdigit():
            selected.add(int(token))
    return [p for i, p in enumerate(items, 1) if i in selected]


def main() -> None:
    cfg = load()
    print("\nProject Brain MCP v0.2 - register a WORKSPACE (read-only)\n")
    print("A workspace is the big Agent/Codex root. You choose which top-level areas are exposed to MCP.\n")
    name = input("Workspace name (e.g. agent-v2): ").strip() or "agent-v2"
    raw = input(r"Full workspace folder path (e.g. E:\): ").strip().strip('"')
    desc = input("Short description (optional): ").strip()
    root = Path(raw).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Folder does not exist: {root}")

    dirs = sorted([p for p in root.iterdir() if p.is_dir() and p.name not in HARD_SKIP_DIRS], key=lambda p: p.name.lower())
    files = sorted([p for p in root.iterdir() if p.is_file() and p.suffix.lower() in TEXT_ROOT_EXT], key=lambda p: p.name.lower())

    selected_dirs = choose(dirs, SUGGESTED_DIRS, "Top-level folders found")
    selected_files = choose(files, SUGGESTED_ROOT_FILES, "Root context files found")

    used: set[str] = set()
    areas = [{"name": area_name(p.name, used), "path": p.name, "description": ""} for p in selected_dirs]
    entry = {
        "name": name,
        "path": str(root),
        "description": desc,
        "areas": areas,
        "root_files": [p.name for p in selected_files],
    }
    workspaces = [w for w in cfg.get("workspaces", []) if w.get("name") != name]
    workspaces.append(entry)
    cfg["workspaces"] = workspaces
    cfg.setdefault("security", {})
    save(cfg)

    print("\nSaved workspace:")
    print(f"  {name} -> {root}")
    print("  areas:", ", ".join(a["path"] for a in areas) if areas else "(none)")
    print("  root files:", ", ".join(entry["root_files"]) if entry["root_files"] else "(none)")
    print(f"\nConfig: {CONFIG}")
    print("You can re-run this script with the same workspace name to change the allow-list.")


if __name__ == "__main__":
    main()
