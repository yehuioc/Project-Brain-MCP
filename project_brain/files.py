from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any

from .gitops import run_git
from .model import Project


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def candidate_path(project: Project, relative_path: str) -> Path:
    if not relative_path or relative_path in {".", ".."}:
        raise ValueError("A project-relative file path is required")
    raw = relative_path.replace("\\", "/")
    if raw.startswith("/"):
        raise ValueError("Absolute paths are not allowed")
    parts = Path(raw).parts
    if any(part in {"..", ".git"} for part in parts):
        raise ValueError("Path traversal and direct .git access are not allowed")
    return project.root.joinpath(*parts)


def safe_path(project: Project, relative_path: str) -> Path:
    path = candidate_path(project, relative_path)
    try:
        path.resolve(strict=False).relative_to(project.root)
    except (OSError, ValueError):
        raise ValueError("Path escapes the configured project root")
    return path


def looks_text(data: bytes) -> bool:
    if not data:
        return True
    sample = data[:8192]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        controls = sum(1 for b in sample if b < 9 or (13 < b < 32))
        return controls / max(1, len(sample)) < 0.02


def visible_files(project: Project) -> list[dict[str, Any]]:
    res = run_git(project.root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if not res["ok"]:
        raise ValueError(f"git ls-files failed: {res['stderr']}")
    tracked_res = run_git(project.root, ["ls-files", "-z", "--cached"])
    tracked = {p for p in tracked_res["stdout"].split(b"\x00") if p} if tracked_res["ok"] else set()
    raw_paths = [p for p in res["stdout"].split(b"\x00") if p]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw_path in raw_paths:
        rel = raw_path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        if rel in seen:
            continue
        seen.add(rel)
        path = candidate_path(project, rel)
        item: dict[str, Any] = {"path": rel, "tracked": raw_path in tracked, "exists": path.exists() or path.is_symlink()}
        if not item["exists"]:
            item.update({"kind": "missing", "size": None, "sha256": None})
            items.append(item)
            continue
        try:
            path.resolve(strict=True).relative_to(project.root)
        except (OSError, ValueError):
            item.update({"kind": "blocked-link", "size": None, "sha256": None})
            items.append(item)
            continue
        if path.is_symlink():
            target = os.readlink(path)
            data = target.encode("utf-8", errors="surrogateescape")
            item.update({"kind": "symlink", "size": len(data), "sha256": sha256(data), "link_target": target})
        elif path.is_dir():
            item.update({"kind": "directory", "size": None, "sha256": None})
        else:
            data = path.read_bytes()
            item.update({"kind": "text" if looks_text(data) else "binary", "size": len(data), "sha256": sha256(data)})
        items.append(item)
    items.sort(key=lambda x: x["path"])
    return items


def read_visible_file(project: Project, relative_path: str, mode: str, max_text: int, max_binary: int) -> dict[str, Any]:
    files = {item["path"]: item for item in visible_files(project)}
    rel = relative_path.replace("\\", "/").lstrip("/")
    if rel not in files:
        raise ValueError("File is not part of the Git-defined project surface")
    meta = files[rel]
    if meta["kind"] in {"missing", "blocked-link", "directory"}:
        return {**meta, "content": None}
    path = safe_path(project, rel)
    if meta["kind"] == "symlink":
        return {**meta, "encoding": "symlink-target", "content": meta.get("link_target", "")}
    data = path.read_bytes()
    mode = mode.lower()
    if mode not in {"auto", "text", "base64"}:
        raise ValueError("mode must be auto, text, or base64")
    if mode == "auto":
        mode = "text" if meta["kind"] == "text" else "base64"
    if mode == "text":
        if len(data) > max_text:
            raise ValueError(f"Text file exceeds configured read limit: {len(data)} bytes")
        return {**meta, "encoding": "utf-8-with-replacement", "content": data.decode("utf-8", errors="replace")}
    if len(data) > max_binary:
        raise ValueError(f"Binary/base64 file exceeds configured read limit: {len(data)} bytes")
    return {**meta, "encoding": "base64", "content": base64.b64encode(data).decode("ascii")}
