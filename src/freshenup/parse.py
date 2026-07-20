"""Pure parsers: raw ``brew``/``mas`` output and cask receipts → domain Items.

The only I/O-free layer — every function takes text and returns data, so the bug-prone parsing
(version extraction, JSON shapes) is unit-tested against fixtures without invoking brew.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, TypeAdapter

from .models import Item, Kind

# brew outdated --verbose lines: "name (1.0, 1.1) < 1.2" (formula), "name (1.0) != 1.2" (cask).
# A cask version can carry a comma-suffix that is part of the version (e.g. dotnet
# "8.0.422,8.0.28"); keep it and strip only a trailing build hash.
_TRAILING_HASH = re.compile(r",[0-9a-fA-F]{16,}$")
_OP = re.compile(r"^\s*(?:<|!=)\s*")


def parse_brew_outdated(kind: Kind, text: str) -> list[Item]:
    items: list[Item] = []
    for line in text.splitlines():
        open_paren = line.find(" (")
        if open_paren < 0:
            continue
        rest = line[open_paren + 2 :]
        close_paren = rest.find(")")
        if close_paren < 0:
            continue
        installed = rest[:close_paren]
        latest = _OP.sub("", rest[close_paren + 1 :])
        current = installed.split(", ")[-1]  # newest of the installed versions
        items.append(
            Item(
                kind=kind,
                name=line[:open_paren],
                current=_TRAILING_HASH.sub("", current),
                latest=_TRAILING_HASH.sub("", latest),
            )
        )
    return items


class _MasApp(BaseModel):
    adam_id: int = Field(alias="adamID")
    name: str
    current: str = Field(alias="version", default="")
    latest: str = Field(alias="newVersion")


_MAS_APPS = TypeAdapter(list[_MasApp])


def parse_mas(text: str) -> list[Item]:
    return [
        Item(kind=Kind.MAS, name=a.name, current=a.current, latest=a.latest, mas_id=str(a.adam_id))
        for a in _MAS_APPS.validate_json(text)
    ]


class _Dep(BaseModel):
    full_name: str


class _RuntimeDeps(BaseModel):
    cask: list[_Dep] = []
    formula: list[_Dep] = []


class _Artifact(BaseModel):
    # A cask's uninstall_artifacts is a heterogeneous list ({"app": [...]}, {"zap": [...]}, …);
    # declaring only `app` (extra keys ignored) types the grab-bag without hand-digging.
    app: list[str] = []


class _Receipt(BaseModel):
    runtime_dependencies: _RuntimeDeps = Field(default_factory=_RuntimeDeps)
    uninstall_artifacts: list[_Artifact] = []


def parse_receipt(text: str) -> tuple[list[str], list[str]]:
    """Return (dependency cask tokens, installed .app names) from a cask install receipt."""
    receipt = _Receipt.model_validate_json(text)
    deps = [dep.full_name.rsplit("/", 1)[-1] for dep in receipt.runtime_dependencies.cask]
    apps = [name for artifact in receipt.uninstall_artifacts for name in artifact.app]
    return deps, apps
