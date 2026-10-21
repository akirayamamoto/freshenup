"""Pure parsers: raw ``brew``/``mas`` output and cask receipts → domain Items.

The only I/O-free layer — every function takes text and returns data, so the bug-prone parsing
(version extraction, JSON shapes) is unit-tested against fixtures without invoking brew.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, TypeAdapter

from .models import Deps, Item, Kind

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


def parse_mas(text: str) -> list[Item]:
    # mas 7's `outdated --json` emits NDJSON — one JSON object per line, not a JSON array.
    apps = [_MasApp.model_validate_json(line) for line in text.splitlines() if line.strip()]
    return [
        Item(kind=Kind.MAS, name=a.name, current=a.current, latest=a.latest, mas_id=str(a.adam_id))
        for a in apps
    ]


class _MiseTool(BaseModel):
    current: str | None = None
    latest: str


_MISE_TOOLS = TypeAdapter(dict[str, _MiseTool])


def parse_mise(text: str) -> list[Item]:
    # `mise outdated --json` is an object keyed by tool id; that key is what `mise upgrade` takes
    # (npm-backed ids like "npm:@scope/pkg" included), so it — not any inner field — is the name.
    return [
        Item(kind=Kind.MISE, name=name, current=tool.current or "", latest=tool.latest)
        for name, tool in _MISE_TOOLS.validate_json(text).items()
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


class _InstalledFormula(BaseModel):
    # A formula's runtime_dependencies is a flat list, unlike a cask receipt's cask/formula object.
    runtime_dependencies: list[_Dep] = []


class _FormulaInfo(BaseModel):
    full_name: str
    desc: str | None = None
    dependencies: list[str] = []
    installed: list[_InstalledFormula] = []


class _CaskInfo(BaseModel):
    token: str
    desc: str | None = None


class _BrewInfo(BaseModel):
    formulae: list[_FormulaInfo] = []
    casks: list[_CaskInfo] = []


def parse_descriptions(text: str) -> dict[str, str]:
    """brew's one-line description per installed formula (tap-qualified) and cask (token)."""
    info = _BrewInfo.model_validate_json(text)
    formulae = {f.full_name: f.desc for f in info.formulae if f.desc}
    casks = {c.token: c.desc for c in info.casks if c.desc}
    return formulae | casks


def parse_formula_deps(text: str) -> dict[str, Deps]:
    """Dependencies per formula from `brew info --json=v2`, keyed by tap-qualified name — the same
    name brew prints, so it matches what an upgrade was asked for."""
    return {
        formula.full_name: Deps(
            declared=frozenset(formula.dependencies),
            runtime=frozenset(
                dep.full_name
                for installed in formula.installed
                for dep in installed.runtime_dependencies
            ),
        )
        for formula in _BrewInfo.model_validate_json(text).formulae
    }
