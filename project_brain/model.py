from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    name: str
    root: Path
    description: str = ""
    source: str = "git"
    exclude: tuple[str, ...] = ()
