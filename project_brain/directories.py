"""Explicitly registered directory sources, independent of Git ignore rules."""
from __future__ import annotations

import base64
import fnmatch
import os
import stat
from pathlib import Path
from typing import Any

from .files import candidate_path, looks_text, safe_path, sha256
from .model import Project


EXCLUDED_NAMES = frozenset({
    ".git", ".hg", ".svn", ".runtime", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".obsidian",
})
EXCLUDED_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx")


def exclusions(project: Project) -> dict[str, list[str]]:
    return {"component_names": sorted(EXCLUDED_NAMES),
            "component_patterns": list(EXCLUDED_PATTERNS),
            "relative_patterns": list(project.exclude)}


def excluded(project: Project, relative: str) -> bool:
    parts = relative.replace("\\", "/").casefold().split("/")
    if any(p in EXCLUDED_NAMES or any(fnmatch.fnmatchcase(p, pat) for pat in EXCLUDED_PATTERNS)
           for p in parts):
        return True
    # Check each ancestor too: excluding a directory excludes all descendants.
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    return any(fnmatch.fnmatchcase(prefix, pat.casefold().rstrip("/"))
               or (pat.endswith("/**") and prefix == pat[:-3].casefold())
               for prefix in prefixes for pat in project.exclude)


def is_link(path: Path) -> bool:
    info = path.lstat()
    # Path.is_junction is only available in Python 3.12+. Reject Windows reparse
    # points with lstat as well, so older supported Pythons cannot follow junctions.
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def checked_path(project: Project, relative: str, *, allow_root: bool = False) -> Path:
    if allow_root and relative in {"", "."}:
        return project.root
    candidate_path(project, relative)
    if excluded(project, relative):
        raise ValueError("Path is excluded by the registered directory rules")
    path = safe_path(project, relative)
    current = project.root
    for part in path.relative_to(project.root).parts:
        current = current / part
        if is_link(current):
            raise ValueError("Directory sources do not follow symbolic links or junctions")
    return path


def metadata(project: Project, path: Path) -> dict[str, Any]:
    rel = path.relative_to(project.root).as_posix()
    if is_link(path):
        return {"path": rel, "kind": "blocked-link", "tracked": None,
                "size": None, "sha256": None}
    checked_path(project, rel)
    info = path.stat()
    return {"path": rel, "kind": "directory" if path.is_dir() else "file",
            "tracked": None, "size": None if path.is_dir() else info.st_size,
            "sha256": None, "hash_status": "not_computed"}


def list_directory(project: Project, path: str = "", cursor: int = 0, limit: int = 200) -> dict:
    folder = checked_path(project, path, allow_root=True)
    if not folder.is_dir():
        raise ValueError("Listing path must be an existing directory")
    entries = sorted((p for p in folder.iterdir()
                      if not excluded(project, p.relative_to(project.root).as_posix())),
                     key=lambda p: p.name)
    if cursor < 0 or cursor > len(entries):
        raise ValueError("cursor is outside this directory listing")
    limit = max(1, min(int(limit), 1000))
    page = [metadata(project, p) for p in entries[cursor:cursor + limit]]
    end = cursor + len(page)
    return {"project": project.name, "source": "directory", "path": path,
            "definition": "Immediate children of the registered directory; Git is not consulted",
            "files": page, "total": len(entries), "cursor": cursor,
            "next_cursor": end if end < len(entries) else None,
            "complete": end >= len(entries), "recursive": False,
            "exclusions": exclusions(project)}


def read_directory_file(project: Project, relative: str, mode: str, max_text: int, max_binary: int) -> dict:
    path = checked_path(project, relative)
    if not path.is_file():
        raise ValueError("Requested path must be an existing regular file")
    if mode not in {"auto", "text", "base64"}:
        raise ValueError("mode must be auto, text, or base64")
    with path.open("rb") as stream:
        sample = stream.read(8192)
        kind = "text" if looks_text(sample) else "binary"
        selected = ("text" if kind == "text" else "base64") if mode == "auto" else mode
        limit = max_text if selected == "text" else max_binary
        if os.fstat(stream.fileno()).st_size > limit:
            raise ValueError(f"File exceeds configured {selected} read limit: {limit} bytes")
        stream.seek(0)
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("File grew beyond its configured read limit")
    return {"path": path.relative_to(project.root).as_posix(), "tracked": None,
            "kind": kind, "size": len(data), "sha256": sha256(data),
            "encoding": "utf-8-with-replacement" if selected == "text" else "base64",
            "content": data.decode("utf-8", errors="replace") if selected == "text"
                       else base64.b64encode(data).decode("ascii")}


def directory_snapshot(project: Project, path: str, max_text: int, max_chars: int) -> tuple[str, dict]:
    folder = checked_path(project, path, allow_root=True)
    if not folder.is_dir():
        raise ValueError("Snapshot path must be an existing directory")
    sections: list[str] = []
    counts = {"files_total": 0, "text_files_included": 0, "binary_files_listed": 0,
              "missing_files_listed": 0, "blocked_links_listed": 0}
    total = 0

    def add(text: str) -> None:
        nonlocal total
        total += len(text)
        if total > max_chars:
            raise ValueError("Snapshot exceeds max_snapshot_total_chars; choose a smaller path. No complete snapshot was returned.")
        sections.append(text)

    def fail(error: OSError) -> None:
        raise error  # Never silently label an incomplete walk complete.

    for base, dirs, files in os.walk(folder, followlinks=False, onerror=fail):
        base_path = Path(base)
        for name in sorted(dirs + files):
            candidate = base_path / name
            rel = candidate.relative_to(project.root).as_posix()
            if excluded(project, rel):
                if name in dirs:
                    dirs.remove(name)
                continue
            if is_link(candidate):
                if name in dirs:
                    dirs.remove(name)
                counts["blocked_links_listed"] += 1
                counts["files_total"] += 1
                add(f"===== FILE: {rel} | kind=blocked-link =====\n[link not followed]\n===== END FILE: {rel} =====\n\n")
                continue
            if name in dirs:
                continue
            checked_path(project, rel)
            counts["files_total"] += 1
            with candidate.open("rb") as stream:
                sample = stream.read(8192)
                size = os.fstat(stream.fileno()).st_size
                if looks_text(sample):
                    if size > max_text:
                        raise ValueError(f"Text file exceeds snapshot file limit: {rel}")
                    stream.seek(0)
                    data = stream.read(max_text + 1)
                    if len(data) > max_text:
                        raise ValueError(f"File grew beyond snapshot file limit: {rel}")
                    counts["text_files_included"] += 1
                    add(f"===== FILE: {rel} | kind=text | bytes={len(data)} | sha256={sha256(data)} =====\n")
                    add(data.decode("utf-8", errors="replace") + "\n")
                else:
                    counts["binary_files_listed"] += 1
                    add(f"===== FILE: {rel} | kind=binary | bytes={size} | sha256=not_computed =====\n")
                    add("[binary content omitted; use read_file(mode='base64') for bytes and hash within the read limit]\n")
            add(f"===== END FILE: {rel} =====\n\n")
        dirs.sort()
    payload = "".join(sections)
    return payload, {**counts, "total_chars": len(payload), "source": "directory", "path": path,
                     "binary_hashes_computed": False, "exclusions": exclusions(project)}
