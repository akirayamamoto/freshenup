"""Domain types: the outdated Item the rest of freshenup works with."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    FORMULA = "formula"
    CASK = "cask"
    MAS = "mas"

    @property
    def label(self) -> str:
        return {Kind.FORMULA: "(formula)", Kind.CASK: "(cask)", Kind.MAS: "(App Store)"}[self]


@dataclass(frozen=True, slots=True)
class Item:
    """One outdated package and its version bump. `mas_id` is set only for App Store apps."""

    kind: Kind
    name: str
    current: str
    latest: str
    mas_id: str = ""


@dataclass(frozen=True, slots=True)
class Node:
    """One fzf row: a top-level package, optionally its own outdated Item (`itself`), plus any
    outdated members folded under it — a formula's outdated dependencies, or casks folded under a
    cask that depends on them."""

    kind: Kind
    name: str
    itself: Item | None = None
    members: tuple[Item, ...] = ()
