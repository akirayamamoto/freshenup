"""Domain types: the outdated Item the rest of freshenup works with."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    FORMULA = "formula"
    CASK = "cask"
    MAS = "mas"
    MISE = "mise"
    APP = "app"

    @property
    def label(self) -> str:
        return {
            Kind.FORMULA: "(formula)",
            Kind.CASK: "(cask)",
            Kind.MAS: "(App Store)",
            Kind.MISE: "(mise)",
            Kind.APP: "(update in app)",
        }[self]


@dataclass(frozen=True, slots=True)
class Item:
    """One outdated package and its version bump. `mas_id` is set only for App Store apps, `app`
    (the bundle path) only for self-updating apps."""

    kind: Kind
    name: str
    current: str
    latest: str
    mas_id: str = ""
    app: str = ""


@dataclass(frozen=True, slots=True)
class SelfUpdating:
    """A cask whose app updates itself: brew's latest version and where to find the installed
    bundle — app paths from the cask, else the bundle ids it quits on uninstall. `names` are the
    cask's app names, which a bundle found by id must match."""

    token: str
    latest: str
    names: tuple[str, ...]
    app_paths: tuple[str, ...]
    bundle_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Deps:
    """A formula's dependencies: the ones it declares, and the flattened closure it was installed
    against — the closure also covers dependencies further down than the declared list reaches."""

    declared: frozenset[str]
    runtime: frozenset[str]


@dataclass(frozen=True, slots=True)
class Node:
    """One fzf row: a top-level package, optionally its own outdated Item (`itself`), plus any
    outdated members folded under it — a formula's outdated dependencies, or casks folded under a
    cask that depends on them."""

    kind: Kind
    name: str
    itself: Item | None = None
    members: tuple[Item, ...] = ()
    what: str = ""
    why: str = ""
