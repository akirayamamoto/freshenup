"""The user's notes file: what each package is and why it's installed, keyed by menu row name."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class Note(BaseModel):
    what: str = ""
    why: str = ""


_NOTES = TypeAdapter(dict[str, Note])
_ENV_PATH = "FRESHENUP_NOTES"
DEFAULT_PATH = Path.home() / ".config" / "freshenup" / "notes.toml"


def notes_path() -> Path:
    return Path(os.environ.get(_ENV_PATH) or DEFAULT_PATH)


def parse_notes(text: str) -> dict[str, Note]:
    return _NOTES.validate_python(tomllib.loads(text))


def load_notes(path: Path) -> dict[str, Note]:
    """Notes from ``path``; none when the file doesn't exist (it's optional)."""
    if not path.exists():
        return {}
    return parse_notes(path.read_text())
