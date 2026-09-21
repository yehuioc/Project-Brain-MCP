from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .files import read_visible_file, safe_path, visible_files
from .directories import directory_snapshot, exclusions, list_directory, read_directory_file
from .gitops import git_root, git_text, local_commits, local_diff, local_status
from .model import Project


class ProjectBridge:
    """Minimal read-only bridge from selected local Git projects to MCP clients."""

    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.config = self._load_config()
        sec = self.config.get("security", {})
        self.default_snapshot_chars = int(sec.get("snapshot_chunk_chars", 80_000))
        self.max_snapshot_chars = int(sec.get("max_snapshot_chunk_chars", 200_000))
        self.max_text_file_bytes = int(sec.get("max_text_file_bytes", 20_000_000))
        self.max_binary_file_bytes = int(sec.get("max_binary_file_bytes", 20_000_000))
        self.max_snapshot_total_chars = int(sec.get("max_snapshot_total_chars", 50_000_000))
        self.projects = {}
        for raw in self.config.get("projects", []):
            name = raw["name"]
            source = raw.get("source", "git")
            patterns = raw.get("exclude", [])
            if not isinstance(name, str) or not name.strip() or name in self.projects:
                raise ValueError("Each registered source needs a unique, nonempty name")
            if source not in {"git", "directory"}:
                raise ValueError(f"Unknown source type: {source}")
            if not isinstance(patterns, list) or not all(isinstance(p, str) and p for p in patterns):
                raise ValueError("exclude must be a list of nonempty path patterns")
            root = Path(raw["path"]).expanduser()
            if not root.is_absolute():
                raise ValueError("Registered paths must be absolute")
            self.projects[name] = Project(name, root.resolve(), raw.get("description", ""),
                                          source, tuple(patterns))

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"projects": [], "security": {}}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _project(self, name: str) -> Project:
        if name not in self.projects:
            raise ValueError(f"Unknown project: {name}. Use list_projects first.")
        project = self.projects[name]
        if not project.root.exists() or not project.root.is_dir():
            raise ValueError(f"Project path unavailable: {project.root}")
        if project.source == "git" and git_root(project.root) != project.root:
            raise ValueError("Configured path must be the Git repository root")
        return project

    def _git_project(self, name: str) -> Project:
        project = self._project(name)
        if project.source != "git":
            raise ValueError("Git tools are unavailable for directory sources; the parent repository is never inspected")
        return project

    def list_projects(self) -> dict[str, Any]:
        out = []
        for p in self.projects.values():
            available = p.root.exists() and p.root.is_dir()
            is_root = p.source == "git" and available and git_root(p.root) == p.root
            branch = git_text(p.root, ["branch", "--show-current"]) if is_root else {"ok": False}
            out.append({
                "name": p.name, "path": str(p.root), "description": p.description,
                "available": available, "git_repository_root": is_root,
                "branch": branch.get("stdout") if branch.get("ok") else None,
                "source": p.source,
                "exclusions": exclusions(p) if p.source == "directory" else None,
                "git_tools_available": bool(is_root),
            })
        return {"projects": out}

    def get_project_files(self, project_name: str, path: str = "", cursor: int = 0,
                          limit: int = 200) -> dict[str, Any]:
        project = self._project(project_name)
        if project.source == "directory":
            return list_directory(project, path, cursor, limit)
        if path or cursor:
            raise ValueError("Directory browsing parameters apply only to directory sources")
        files = visible_files(project)
        counts: dict[str, int] = {}
        for item in files:
            counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        return {
            "project": project_name,
            "definition": "tracked files + untracked non-ignored files, as reported by Git",
            "files": files, "counts": counts, "total": len(files),
        }

    def read_file(self, project_name: str, relative_path: str, mode: str = "auto") -> dict[str, Any]:
        project = self._project(project_name)
        if project.source == "directory":
            result = read_directory_file(project, relative_path, mode, self.max_text_file_bytes, self.max_binary_file_bytes)
            return {"project": project_name, **result}
        result = read_visible_file(project, relative_path, mode, self.max_text_file_bytes, self.max_binary_file_bytes)
        return {"project": project_name, **result}

    def _build_snapshot(self, project: Project) -> tuple[str, str, dict[str, Any]]:
        files = visible_files(project)
        sections: list[str] = []
        text_count = binary_count = missing_count = blocked_count = 0
        for meta in files:
            rel = meta["path"]
            header = f"===== FILE: {rel} | tracked={str(meta['tracked']).lower()} | kind={meta['kind']}"
            if meta.get("size") is not None:
                header += f" | bytes={meta['size']} | sha256={meta['sha256']}"
            sections.append(header + " =====\n")
            if meta["kind"] == "text":
                data = safe_path(project, rel).read_bytes()
                sections.append(data.decode("utf-8", errors="replace"))
                if not sections[-1].endswith("\n"):
                    sections.append("\n")
                text_count += 1
            elif meta["kind"] == "binary":
                sections.append("[binary content omitted from text snapshot; use read_file(..., mode='base64') for exact bytes]\n")
                binary_count += 1
            elif meta["kind"] == "symlink":
                sections.append(f"[symlink target: {meta.get('link_target', '')}]\n")
            elif meta["kind"] == "missing":
                sections.append("[tracked path is deleted/missing in the current working tree]\n")
                missing_count += 1
            elif meta["kind"] == "blocked-link":
                sections.append("[symlink/junction target escapes project root and is blocked]\n")
                blocked_count += 1
            else:
                sections.append("[directory/submodule-like entry; no inline file content]\n")
            sections.append(f"===== END FILE: {rel} =====\n\n")
        payload = "".join(sections)
        snapshot_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return snapshot_id, payload, {
            "files_total": len(files), "text_files_included": text_count,
            "binary_files_listed": binary_count, "missing_files_listed": missing_count,
            "blocked_links_listed": blocked_count, "total_chars": len(payload),
        }

    def read_project_snapshot(self, project_name: str, cursor: int = 0, max_chars: int | None = None,
                              snapshot_id: str | None = None, path: str = "") -> dict[str, Any]:
        project = self._project(project_name)
        if project.source == "directory":
            payload, summary = directory_snapshot(project, path, self.max_text_file_bytes, self.max_snapshot_total_chars)
            current_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        else:
            if path:
                raise ValueError("Snapshot path selection applies only to directory sources")
            current_id, payload, summary = self._build_snapshot(project)
        if snapshot_id is not None and snapshot_id != current_id:
            return {
                "project": project_name, "error": "snapshot_changed",
                "requested_snapshot_id": snapshot_id, "current_snapshot_id": current_id,
                "message": "The local project changed while it was being read. Restart from cursor=0 with the new snapshot_id.",
            }
        size = self.default_snapshot_chars if max_chars is None else int(max_chars)
        size = max(1_000, min(size, self.max_snapshot_chars))
        cursor = max(0, int(cursor))
        if cursor > len(payload):
            raise ValueError("cursor is past the end of the current snapshot")
        end = min(len(payload), cursor + size)
        complete = end >= len(payload)
        return {
            "project": project_name, "snapshot_id": current_id, **summary,
            "cursor": cursor, "next_cursor": None if complete else end,
            "complete": complete, "content": payload[cursor:end],
        }

    def get_local_git_status(self, project_name: str) -> dict[str, Any]:
        return {"project": project_name, **local_status(self._git_project(project_name).root)}

    def get_local_diff(self, project_name: str, max_chars: int = 120_000) -> dict[str, Any]:
        return {"project": project_name, **local_diff(self._git_project(project_name).root, max_chars)}

    def get_local_commits(self, project_name: str, limit: int = 50) -> dict[str, Any]:
        return {"project": project_name, **local_commits(self._git_project(project_name).root, limit)}
