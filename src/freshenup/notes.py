"""The user's notes file: what each package is and why it's installed, grouped by source.

The file is shared with other tooling, so it has sources freshenup never shows (manual apps,
IDEs, …); those are simply never looked up.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class Note(BaseModel):
    what: str = ""
    why: str = ""


Notes = dict[str, dict[str, Note]]
_NOTES = TypeAdapter(Notes)
_ENV_PATH = "FRESHENUP_NOTES"
DEFAULT_PATH = Path.home() / ".config" / "freshenup" / "notes.toml"


def notes_path() -> Path:
    return Path(os.environ.get(_ENV_PATH) or DEFAULT_PATH)


def parse_notes(text: str) -> Notes:
    return _NOTES.validate_python(tomllib.loads(text))


def load_notes(path: Path) -> Notes:
    """Notes from ``path``; none when the file doesn't exist (it's optional)."""
    if not path.exists():
        return {}
    return parse_notes(path.read_text())
