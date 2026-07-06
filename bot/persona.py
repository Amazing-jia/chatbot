from __future__ import annotations

from pathlib import Path


def load_persona(path: Path) -> str:
    """Load the system persona prompt from a Markdown file."""
    if not path.exists():
        raise FileNotFoundError(f"找不到人格提示词文件：{path}")

    return path.read_text(encoding="utf-8")

