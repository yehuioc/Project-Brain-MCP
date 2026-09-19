from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def run_git(root: Path, args: list[str], timeout: int = 15) -> dict[str, Any]:
    try:
        cp = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=False,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": cp.returncode == 0,
            "stdout": cp.stdout,
            "stderr": cp.stderr.decode("utf-8", errors="replace").strip(),
            "code": cp.returncode,
        }
    except FileNotFoundError:
        return {"ok": False, "stdout": b"", "stderr": "git executable not found", "code": 127}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": b"", "stderr": "git command timed out", "code": 124}


def git_text(root: Path, args: list[str], timeout: int = 15) -> dict[str, Any]:
    res = run_git(root, args, timeout=timeout)
    return {**res, "stdout": res["stdout"].decode("utf-8", errors="replace").strip()}


def git_root(root: Path) -> Path | None:
    res = git_text(root, ["rev-parse", "--show-toplevel"])
    if not res["ok"]:
        return None
    return Path(res["stdout"]).resolve()


def local_status(root: Path) -> dict[str, Any]:
    branch = git_text(root, ["branch", "--show-current"])
    head = git_text(root, ["rev-parse", "HEAD"])
    upstream = git_text(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    ahead = behind = None
    if upstream["ok"]:
        counts = git_text(root, ["rev-list", "--left-right", "--count", "HEAD...@{u}"])
        if counts["ok"]:
            parts = counts["stdout"].split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
    status = git_text(root, ["status", "--porcelain=v1", "--branch"])
    lines = status["stdout"].splitlines() if status["ok"] else []
    return {
        "branch": branch["stdout"] if branch["ok"] else None,
        "head": head["stdout"] if head["ok"] else None,
        "upstream": upstream["stdout"] if upstream["ok"] else None,
        "ahead": ahead,
        "behind": behind,
        "status_lines": lines,
        "clean": bool(status["ok"] and len(lines) <= 1),
        "note": "ahead/behind are relative to the local remote-tracking ref; this tool never runs git fetch",
    }


def local_diff(root: Path, max_chars: int = 120_000) -> dict[str, Any]:
    max_chars = max(2_000, min(int(max_chars), 500_000))
    unstaged = git_text(root, ["diff", "--no-ext-diff", "--unified=3", "--"])
    staged = git_text(root, ["diff", "--cached", "--no-ext-diff", "--unified=3", "--"])
    untracked = run_git(root, ["ls-files", "-z", "--others", "--exclude-standard"])
    untracked_files = [
        p.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for p in untracked["stdout"].split(b"\x00") if p
    ] if untracked["ok"] else []
    combined = (unstaged["stdout"] if unstaged["ok"] else "") + (staged["stdout"] if staged["ok"] else "")
    half = max_chars // 2
    return {
        "unstaged_diff": unstaged["stdout"][:half] if unstaged["ok"] else None,
        "staged_diff": staged["stdout"][:max_chars - half] if staged["ok"] else None,
        "untracked_files": sorted(untracked_files),
        "truncated": len(combined) > max_chars,
    }


def local_commits(root: Path, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    upstream = git_text(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    fmt = "%H%x09%ad%x09%an%x09%s"
    if upstream["ok"]:
        log = git_text(root, ["log", f"-{limit}", "--date=iso-strict", f"--pretty=format:{fmt}", "@{u}..HEAD"])
        classification = "ahead-of-local-upstream-ref"
        note = "These commits are absent from the locally stored upstream tracking ref. MCP never runs git fetch, so verify remote truth with GitHub when needed."
    else:
        log = git_text(root, ["log", f"-{limit}", "--date=iso-strict", f"--pretty=format:{fmt}"])
        classification = "recent-local-history-no-upstream"
        note = "No upstream branch is configured, so pushed/unpushed status cannot be classified locally."
    commits = []
    if log["ok"]:
        for line in log["stdout"].splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return {
        "upstream": upstream["stdout"] if upstream["ok"] else None,
        "classification": classification,
        "note": note,
        "commits": commits,
    }
