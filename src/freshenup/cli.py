"""Command-line entry: parse flags, then orchestrate scan → pick → act."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass

from . import system
from .models import Item, Kind, Node
from .nodes import build_formula_nodes, collapse_casks
from .pick import pick, preview


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.preview is not None:
        print(preview(args.preview))
        return 0
    missing = _missing_tools(shutil.which)
    if missing:
        for tool in missing:
            print(f"freshenup needs {tool} — {_REQUIRED_TOOLS[tool]}", file=sys.stderr)
        return 1
    nodes = _gather(refresh=args.update)
    if not nodes:
        print("Nothing outdated.")
        return 0
    selection = pick(nodes)
    if selection is None:
        return 0
    if selection.uninstall is not None:
        _uninstall(selection.uninstall)
    else:
        _update(selection.nodes)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="freshenup",
        description="Pick outdated Homebrew and Mac App Store items to upgrade or uninstall.",
    )
    parser.add_argument("-u", "--update", action="store_true", help="run `brew update` first")
    parser.add_argument("--preview", metavar="NODE", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


# fzf and brew are shelled out to directly; without them freshenup can't run (mas is optional and
# detected separately). Values are how to install each, shown when it's missing.
_REQUIRED_TOOLS = {
    "brew": "install Homebrew from https://brew.sh",
    "fzf": "run: brew install fzf",
}


def _missing_tools(which: Callable[[str], str | None]) -> list[str]:
    return [tool for tool in _REQUIRED_TOOLS if which(tool) is None]


def _gather(*, refresh: bool) -> list[Node]:
    has_mas = shutil.which("mas") is not None
    kinds = "formulae, casks, and App Store apps" if has_mas else "formulae and casks"
    print(f"Scanning for outdated {kinds}…", file=sys.stderr)
    scanned = system.scan(refresh=refresh, has_mas=has_mas)
    return [
        *build_formula_nodes(scanned.formulae, scanned.leaves, system.uses),
        *collapse_casks(scanned.casks, system.deps_of),
        *_mas_nodes(scanned.mas),
    ]


def _mas_nodes(apps: list[Item]) -> list[Node]:
    # Display a slugified name + the last 3 id digits (near-unique, brew-like); the numeric id in
    # itself.mas_id drives the action.
    return [
        Node(kind=Kind.MAS, name=f"{_slug(app.name)}-{app.mas_id[-3:]}", itself=app) for app in apps
    ]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _items(node: Node) -> list[Item]:
    items = list(node.members)
    if node.itself is not None:
        items.append(node.itself)
    return items


@dataclass(frozen=True, slots=True)
class _Targets:
    formulae: list[str]
    casks: list[str]
    mas_ids: list[str]


def _route(nodes: list[Node]) -> _Targets:
    """Split selected nodes' items into deduped upgrade lists by kind (App Store apps route by
    numeric id, formulae and casks by name)."""
    formulae: list[str] = []
    casks: list[str] = []
    mas_ids: list[str] = []
    for node in nodes:
        for item in _items(node):
            if item.kind is Kind.CASK:
                casks.append(item.name)
            elif item.kind is Kind.MAS:
                mas_ids.append(item.mas_id)
            else:
                formulae.append(item.name)
    return _Targets(_unique(formulae), _unique(casks), _unique(mas_ids))


def _update(nodes: list[Node]) -> None:
    targets = _route(nodes)
    system.upgrade(Kind.FORMULA, targets.formulae)
    _upgrade_casks(targets.casks)
    system.upgrade(Kind.MAS, targets.mas_ids)


def _upgrade_casks(tokens: list[str]) -> None:
    """Upgrade casks, but first handle any whose .app is owned by another user (brew would need
    sudo and fail): offer to chown it back, else skip that cask."""
    if not tokens:
        return
    me = system.current_user()
    blocked = dict(system.blocked_casks(tokens, system.apps_of, system.owner_of, me))
    approved = [token for token in tokens if token not in blocked]
    for token, owner in blocked.items():
        prompt = (
            f"{token} is owned by {owner} — brew needs sudo to upgrade it. "
            "chown to you first? [y/N] "
        )
        if not _confirm(prompt):
            print(f"  skipped {token} (owned by {owner})", file=sys.stderr)
            continue
        print(
            f"  sudo chown {token} back to {me} — {owner} owns it, which blocks brew's upgrade",
            file=sys.stderr,
        )
        if system.chown_cask(token, me):
            approved.append(token)
        else:
            print(f"  chown failed; skipped {token}", file=sys.stderr)
    system.upgrade(Kind.CASK, sorted(approved))


def _uninstall(node: Node) -> None:
    if not _confirm(f"Uninstall {node.name} ({node.kind.value})? [y/N] "):
        print(f"  skipped {node.name}", file=sys.stderr)
        return
    mas_id = node.itself.mas_id if node.itself is not None else ""
    system.uninstall(node.kind, node.name, mas_id)


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() == "y"
    except EOFError:
        return False


def _unique(names: list[str]) -> list[str]:
    return sorted({name for name in names if name})
