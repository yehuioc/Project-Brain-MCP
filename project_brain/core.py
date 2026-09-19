from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", ".next",
    ".idea", ".vscode", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "coverage", ".coverage", "target", "bin", "obj",
    ".ssh", "secrets", "private", ".env-data",
}
DEFAULT_EXCLUDED_FILE_PATTERNS = {
    ".env", ".env.*", "*.pem", "*.p12", "*.pfx", "*.key", "id_rsa*", "id_ed25519*",
    "credentials.json", "credentials.*.json", "service-account*.json",
}
DEFAULT_TEXT_EXTENSIONS = {
    ".md", ".mdx", ".txt", ".rst", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".html", ".css", ".scss", ".sql", ".sh", ".ps1", ".bat",
    ".cmd", ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".php", ".rb", ".swift", ".dart", ".vue", ".svelte", ".log",
    ".csv", ".properties",
}
DOC_NAMES = {"readme", "changelog", "contributing", "architecture", "design", "todo", "roadmap", "notes"}
TEST_PATTERNS = (
    "**/junit*.xml", "**/test-results*.xml", "**/pytest*.xml", "**/coverage.xml",
    "**/test-results/**/*.json", "**/test-results/**/*.xml", "**/reports/**/*.xml",
)
ERROR_RE = re.compile(r"\b(error|exception|traceback|fatal|failed|failure|panic)\b", re.I)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _run_git(root: Path, args: list[str], timeout: int = 8) -> dict[str, Any]:
    try:
        cp = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
        return {"ok": cp.returncode == 0, "stdout": cp.stdout.strip(), "stderr": cp.stderr.strip(), "code": cp.returncode}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "git executable not found", "code": 127}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "git command timed out", "code": 124}


@dataclass
class Area:
    name: str
    relative_path: str
    root: Path
    description: str = ""


@dataclass
class Workspace:
    name: str
    root: Path
    areas: dict[str, Area]
    root_files: set[str]
    description: str = ""


class ProjectBrain:
    """Read-only workspace context layer for MCP.

    A workspace may be broad (for example E:\\), but content access is only allowed
    through explicitly configured areas and root_files.
    """

    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.config = self._load_config()
        sec = self.config.get("security", {})
        self.max_file_bytes = int(sec.get("max_file_bytes", 300_000))
        self.max_search_file_bytes = int(sec.get("max_search_file_bytes", 1_000_000))
        self.max_walk_files = int(sec.get("max_walk_files", 50_000))
        self.excluded_dirs = set(sec.get("excluded_dirs", [])) | DEFAULT_EXCLUDED_DIRS
        self.excluded_file_patterns = set(sec.get("excluded_file_patterns", [])) | DEFAULT_EXCLUDED_FILE_PATTERNS
        self.allowed_extensions = set(sec.get("allowed_extensions", [])) or DEFAULT_TEXT_EXTENSIONS
        self.workspaces: dict[str, Workspace] = {}
        for item in self.config.get("workspaces", []):
            root = Path(item["path"]).expanduser().resolve()
            areas: dict[str, Area] = {}
            for raw in item.get("areas", []):
                rel = str(raw["path"]).replace("\\", "/").strip("/")
                if not rel or rel == ".":
                    continue
                area_root = (root / rel).resolve()
                try:
                    area_root.relative_to(root)
                except ValueError:
                    continue
                areas[raw["name"]] = Area(raw["name"], rel, area_root, raw.get("description", ""))
            root_files = {str(x).replace("\\", "/").lstrip("/") for x in item.get("root_files", [])}
            self.workspaces[item["name"]] = Workspace(
                item["name"], root, areas, root_files, item.get("description", "")
            )

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"workspaces": [], "security": {}}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _workspace(self, name: str) -> Workspace:
        if name not in self.workspaces:
            raise ValueError(f"Unknown workspace: {name}. Use list_workspaces first.")
        w = self.workspaces[name]
        if not w.root.exists() or not w.root.is_dir():
            raise ValueError(f"Workspace path unavailable: {w.root}")
        return w

    def _is_excluded_file(self, path: Path) -> bool:
        name = path.name.lower()
        return any(fnmatch.fnmatch(name, p.lower()) for p in self.excluded_file_patterns)

    def _is_text_candidate(self, path: Path) -> bool:
        if self._is_excluded_file(path):
            return False
        return path.suffix.lower() in self.allowed_extensions or path.name.lower() in {"dockerfile", "makefile", "license"}

    def _area(self, w: Workspace, area_name: str) -> Area:
        if area_name not in w.areas:
            raise ValueError(f"Unknown area: {area_name}. Use list_workspace_areas first.")
        a = w.areas[area_name]
        if not a.root.exists() or not a.root.is_dir():
            raise ValueError(f"Area path unavailable: {a.root}")
        return a

    def _selected_areas(self, w: Workspace, area: str) -> list[Area]:
        if area in {"*", "all", ""}:
            return [a for a in w.areas.values() if a.root.exists() and a.root.is_dir()]
        return [self._area(w, area)]

    def _path_allowed(self, w: Workspace, candidate: Path) -> bool:
        resolved = candidate.resolve()
        try:
            rel_to_workspace = resolved.relative_to(w.root)
        except ValueError:
            return False
        if any(part in self.excluded_dirs for part in rel_to_workspace.parts):
            return False
        if self._is_excluded_file(resolved):
            return False
        rel_posix = rel_to_workspace.as_posix()
        if rel_posix in w.root_files:
            return True
        for a in w.areas.values():
            try:
                resolved.relative_to(a.root)
                return True
            except ValueError:
                pass
        return False

    def _safe_path(self, w: Workspace, relative_path: str) -> Path:
        raw = relative_path.replace("\\", "/").lstrip("/")
        candidate = (w.root / raw).resolve()
        if not self._path_allowed(w, candidate):
            raise ValueError("Path is outside configured workspace areas/root_files or is excluded")
        return candidate

    def _walk_area_files(self, w: Workspace, a: Area, max_files: int | None = None) -> Iterable[Path]:
        limit = max_files or self.max_walk_files
        count = 0
        for base, dirs, files in os.walk(a.root, followlinks=False):
            basep = Path(base)
            safe_dirs = []
            for d in dirs:
                if d in self.excluded_dirs:
                    continue
                p = (basep / d)
                try:
                    rp = p.resolve()
                    rp.relative_to(a.root)
                    rp.relative_to(w.root)
                except (OSError, ValueError):
                    continue
                safe_dirs.append(d)
            dirs[:] = safe_dirs
            for name in files:
                path = basep / name
                if not self._is_text_candidate(path):
                    continue
                try:
                    rp = path.resolve()
                    rp.relative_to(a.root)
                    rp.relative_to(w.root)
                except (OSError, ValueError):
                    continue
                count += 1
                if count > limit:
                    return
                yield path

    def _walk_files(self, w: Workspace, area: str = "*", max_files_per_area: int | None = None) -> Iterable[tuple[str, Path]]:
        for a in self._selected_areas(w, area):
            for path in self._walk_area_files(w, a, max_files=max_files_per_area):
                yield a.name, path

    def list_workspaces(self) -> dict[str, Any]:
        out = []
        for w in self.workspaces.values():
            git = _run_git(w.root, ["rev-parse", "--is-inside-work-tree"]) if w.root.exists() else {"ok": False}
            out.append({
                "name": w.name,
                "path": str(w.root),
                "description": w.description,
                "available": w.root.exists(),
                "areas": len(w.areas),
                "root_files": len(w.root_files),
                "workspace_git_repository": bool(git.get("ok") and git.get("stdout") == "true"),
            })
        return {"generated_at": _now(), "workspaces": out}

    def list_workspace_areas(self, workspace: str) -> dict[str, Any]:
        w = self._workspace(workspace)
        areas = []
        for a in w.areas.values():
            areas.append({
                "name": a.name,
                "path": a.relative_path,
                "description": a.description,
                "available": a.root.exists(),
            })
        return {"workspace": workspace, "areas": areas, "root_files": sorted(w.root_files)}

    def get_workspace_overview(self, workspace: str) -> dict[str, Any]:
        w = self._workspace(workspace)
        areas = []
        for a in w.areas.values():
            count = 0
            newest: list[tuple[float, str]] = []
            if a.root.exists():
                for path in self._walk_area_files(w, a, max_files=3000):
                    count += 1
                    try:
                        newest.append((path.stat().st_mtime, path.relative_to(w.root).as_posix()))
                    except OSError:
                        pass
                newest.sort(reverse=True)
            areas.append({
                "name": a.name,
                "path": a.relative_path,
                "available": a.root.exists(),
                "text_files_sampled": count,
                "sample_capped": count >= 3000,
                "recent_files": [x[1] for x in newest[:5]],
            })
        root_files = []
        for rel in sorted(w.root_files):
            p = (w.root / rel)
            root_files.append({"path": rel, "available": p.exists() and p.is_file()})
        git_root = _run_git(w.root, ["status", "--porcelain=v1", "--branch"])
        return {
            "generated_at": _now(), "workspace": workspace, "root": str(w.root),
            "areas": areas, "root_files": root_files,
            "workspace_git": {"present": git_root.get("ok", False), "status_header": git_root.get("stdout", "").splitlines()[:1]},
        }

    def find_workspace_files(self, workspace: str, pattern: str = "*", area: str = "*", limit: int = 100) -> dict[str, Any]:
        w = self._workspace(workspace)
        limit = max(1, min(int(limit), 500))
        pat = pattern.lower()
        out = []
        if area in {"*", "all", ""}:
            for rel in sorted(w.root_files):
                if fnmatch.fnmatch(rel.lower(), pat) or pat in rel.lower() or pat == "*":
                    p = w.root / rel
                    if p.exists() and p.is_file() and self._is_text_candidate(p):
                        out.append({"area": "@root", "path": rel})
                        if len(out) >= limit:
                            return {"workspace": workspace, "area": area, "pattern": pattern, "files": out, "truncated": True}
        for area_name, path in self._walk_files(w, area):
            rel = path.relative_to(w.root).as_posix()
            if fnmatch.fnmatch(rel.lower(), pat) or pat in rel.lower() or pat == "*":
                out.append({"area": area_name, "path": rel})
                if len(out) >= limit:
                    return {"workspace": workspace, "area": area, "pattern": pattern, "files": out, "truncated": True}
        return {"workspace": workspace, "area": area, "pattern": pattern, "files": out, "truncated": False}

    def read_workspace_file(self, workspace: str, relative_path: str, start_line: int = 1, max_lines: int = 300) -> dict[str, Any]:
        w = self._workspace(workspace)
        path = self._safe_path(w, relative_path)
        if not path.exists() or not path.is_file():
            raise ValueError("File not found")
        if not self._is_text_candidate(path):
            raise ValueError("File type is not allow-listed as text")
        size = path.stat().st_size
        if size > self.max_file_bytes:
            raise ValueError(f"File exceeds read limit ({size} > {self.max_file_bytes} bytes)")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start_line = max(1, int(start_line))
        max_lines = max(1, min(int(max_lines), 1000))
        chunk = lines[start_line - 1:start_line - 1 + max_lines]
        return {
            "workspace": workspace, "path": path.relative_to(w.root).as_posix(),
            "start_line": start_line, "end_line": start_line + len(chunk) - 1,
            "total_lines": len(lines), "content": "\n".join(chunk),
            "truncated": start_line - 1 + len(chunk) < len(lines),
        }

    def _scope_matches(self, path: Path, rel: str, scope: str) -> bool:
        low = rel.lower()
        if scope == "all":
            return True
        if scope == "docs":
            return path.stem.lower() in DOC_NAMES or "/docs/" in f"/{low}" or path.name.lower().startswith("readme") or path.suffix.lower() in {".md", ".mdx", ".rst"}
        if scope == "logs":
            return path.suffix.lower() == ".log" or "/logs/" in f"/{low}" or path.name.lower().endswith(".out")
        if scope == "tests":
            return "test" in low or "pytest" in low or "junit" in low
        if scope == "code":
            return path.suffix.lower() not in {".md", ".mdx", ".txt", ".rst", ".log", ".csv"}
        return False

    def search_workspace_text(self, workspace: str, query: str, area: str = "*", scope: str = "all", limit: int = 30) -> dict[str, Any]:
        w = self._workspace(workspace)
        if not query.strip():
            raise ValueError("query must not be empty")
        scope = scope.lower()
        if scope not in {"all", "docs", "logs", "tests", "code"}:
            raise ValueError("scope must be one of all/docs/logs/tests/code")
        limit = max(1, min(int(limit), 100))
        q = query.lower()
        hits = []
        scanned = 0
        candidates: list[tuple[str, Path]] = []
        if area in {"*", "all", ""}:
            for rel in sorted(w.root_files):
                p = w.root / rel
                if p.exists() and p.is_file() and self._is_text_candidate(p):
                    candidates.append(("@root", p))
        candidates.extend(self._walk_files(w, area))
        for area_name, path in candidates:
            rel = path.relative_to(w.root).as_posix()
            if not self._scope_matches(path, rel, scope):
                continue
            try:
                if path.stat().st_size > self.max_search_file_bytes:
                    continue
                scanned += 1
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if q in line.lower():
                            hits.append({"area": area_name, "path": rel, "line": lineno, "text": line.rstrip()[:800]})
                            if len(hits) >= limit:
                                return {"workspace": workspace, "area": area, "query": query, "scope": scope, "hits": hits, "scanned_files": scanned, "truncated": True}
            except (OSError, UnicodeError):
                continue
        return {"workspace": workspace, "area": area, "query": query, "scope": scope, "hits": hits, "scanned_files": scanned, "truncated": False}

    def _repo_root_allowed(self, w: Workspace, repo_root: Path) -> bool:
        rr = repo_root.resolve()
        if rr == w.root:
            return True
        return self._path_allowed(w, rr)

    def list_git_repositories(self, workspace: str, area: str = "*", max_depth: int = 6, limit: int = 100) -> dict[str, Any]:
        w = self._workspace(workspace)
        max_depth = max(1, min(int(max_depth), 12))
        limit = max(1, min(int(limit), 200))
        repos: dict[str, dict[str, Any]] = {}
        if (w.root / ".git").exists():
            repos["."] = {"path": ".", "area": "@workspace-root"}
        for a in self._selected_areas(w, area):
            for base, dirs, _ in os.walk(a.root, followlinks=False):
                basep = Path(base)
                try:
                    depth = len(basep.relative_to(a.root).parts)
                except ValueError:
                    continue
                if depth >= max_depth:
                    dirs[:] = []
                    continue
                if ".git" in dirs:
                    rel = basep.relative_to(w.root).as_posix() or "."
                    repos[rel] = {"path": rel, "area": a.name}
                    dirs.remove(".git")
                    if len(repos) >= limit:
                        break
                dirs[:] = [d for d in dirs if d not in self.excluded_dirs]
            if len(repos) >= limit:
                break
        return {"workspace": workspace, "area": area, "repositories": list(repos.values())[:limit], "truncated": len(repos) >= limit}

    def _repo(self, workspace: str, repo_path: str) -> tuple[Workspace, Path]:
        w = self._workspace(workspace)
        raw = repo_path.replace("\\", "/").strip()
        root = w.root if raw in {"", "."} else (w.root / raw).resolve()
        if not self._repo_root_allowed(w, root):
            raise ValueError("Repository path is outside configured workspace areas")
        probe = _run_git(root, ["rev-parse", "--show-toplevel"])
        if not probe["ok"]:
            raise ValueError(f"Not a Git repository: {repo_path}")
        actual = Path(probe["stdout"]).resolve()
        if actual != root.resolve():
            if actual == w.root and root != w.root:
                raise ValueError("Use repo_path='.' for the workspace root Git repository")
            if not self._repo_root_allowed(w, actual):
                raise ValueError("Resolved Git repository is outside allowed areas")
            root = actual
        return w, root

    def get_git_repository_state(self, workspace: str, repo_path: str = ".") -> dict[str, Any]:
        w, root = self._repo(workspace, repo_path)
        branch = _run_git(root, ["branch", "--show-current"])
        status = _run_git(root, ["status", "--porcelain=v1", "--branch"])
        latest = _run_git(root, ["log", "-1", "--date=iso-strict", "--pretty=format:%H%x09%ad%x09%s"])
        rel = "." if root == w.root else root.relative_to(w.root).as_posix()
        return {
            "workspace": workspace, "repo_path": rel,
            "branch": branch.get("stdout") if branch.get("ok") else None,
            "status_header": status.get("stdout", "").splitlines()[:1],
            "working_tree_changes": status.get("stdout", "").splitlines()[1:101] if status.get("ok") else [],
            "latest_commit": latest.get("stdout") if latest.get("ok") else None,
        }

    def get_git_history(self, workspace: str, repo_path: str = ".", limit: int = 20) -> dict[str, Any]:
        _, root = self._repo(workspace, repo_path)
        limit = max(1, min(int(limit), 100))
        res = _run_git(root, ["log", f"-{limit}", "--date=iso-strict", "--pretty=format:%H%x09%ad%x09%an%x09%s"])
        if not res["ok"]:
            return {"ok": False, "error": res["stderr"]}
        commits = []
        for line in res["stdout"].splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                commits.append(dict(hash=parts[0], date=parts[1], author=parts[2], subject=parts[3]))
        return {"ok": True, "workspace": workspace, "repo_path": repo_path, "commits": commits}

    def get_git_diff(self, workspace: str, repo_path: str = ".", target: str = "working", max_chars: int = 30_000) -> dict[str, Any]:
        _, root = self._repo(workspace, repo_path)
        if target not in {"HEAD", "staged", "working"} and not re.fullmatch(r"[A-Za-z0-9._/@~^+-]{1,120}", target):
            raise ValueError("Unsafe git target")
        args = ["diff", "--no-ext-diff", "--unified=3"]
        if target == "staged":
            args.append("--cached")
        elif target not in {"HEAD", "working"}:
            args.append(target)
        res = _run_git(root, args, timeout=12)
        text = res.get("stdout", "")
        max_chars = max(1_000, min(int(max_chars), 100_000))
        return {"ok": res["ok"], "workspace": workspace, "repo_path": repo_path, "target": target, "diff": text[:max_chars], "truncated": len(text) > max_chars, "error": res.get("stderr") or None}

    def get_recent_errors(self, workspace: str, area: str = "*", limit: int = 50) -> dict[str, Any]:
        w = self._workspace(workspace)
        limit = max(1, min(int(limit), 100))
        candidates: list[tuple[float, str, Path]] = []
        for area_name, path in self._walk_files(w, area):
            rel = path.relative_to(w.root).as_posix().lower()
            if path.suffix.lower() == ".log" or "/logs/" in f"/{rel}" or path.name.lower().endswith(".out"):
                try:
                    candidates.append((path.stat().st_mtime, area_name, path))
                except OSError:
                    pass
        candidates.sort(reverse=True)
        hits = []
        for _, area_name, path in candidates[:80]:
            try:
                if path.stat().st_size > 5_000_000:
                    with path.open("rb") as bf:
                        bf.seek(-min(path.stat().st_size, 1_000_000), os.SEEK_END)
                        text = bf.read().decode("utf-8", errors="replace")
                    lines = text.splitlines()
                    offset = -len(lines)
                else:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                    offset = 0
                for i, line in enumerate(lines, 1):
                    if ERROR_RE.search(line):
                        hits.append({"area": area_name, "path": path.relative_to(w.root).as_posix(), "line": i + offset, "text": line[:1000]})
                if len(hits) >= limit:
                    break
            except OSError:
                continue
        return {"workspace": workspace, "area": area, "errors": hits[-limit:], "log_files_considered": len(candidates)}

    def get_test_results(self, workspace: str, area: str = "*", limit: int = 30) -> dict[str, Any]:
        w = self._workspace(workspace)
        limit = max(1, min(int(limit), 100))
        found: list[tuple[float, str, Path]] = []
        for area_name, path in self._walk_files(w, area):
            rel = path.relative_to(w.root).as_posix()
            low = rel.lower()
            if any(fnmatch.fnmatch(low, pattern.lower()) for pattern in TEST_PATTERNS) or ("test" in low and path.suffix.lower() in {".xml", ".json", ".log", ".txt"}):
                try:
                    found.append((path.stat().st_mtime, area_name, path))
                except OSError:
                    pass
        found.sort(reverse=True)
        items = []
        for mtime, area_name, path in found[:limit]:
            rel = path.relative_to(w.root).as_posix()
            preview = ""
            try:
                if path.stat().st_size <= self.max_file_bytes:
                    preview = path.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                pass
            items.append({"area": area_name, "path": rel, "modified": datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds"), "preview": preview})
        return {"workspace": workspace, "area": area, "result_files": items}
