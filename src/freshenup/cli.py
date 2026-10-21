"""Command-line entry: parse flags, then orchestrate scan → pick → act."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from . import system
from .models import Item, Kind, Node, SelfUpdating
from .nodes import (
    build_formula_nodes,
    collapse_casks,
    dependents_lookup,
    explain_ride_alongs,
)
from .notes import Note, Notes, load_notes, notes_path
from .parse import is_newer
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
        _update(selection.nodes, deselected=len(selection.nodes) < len(nodes))
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
    has_mise = shutil.which("mise") is not None
    print(f"Scanning for outdated {_kinds_label(has_mas, has_mise)}…", file=sys.stderr)
    scanned = system.scan(refresh=refresh, has_mas=has_mas, has_mise=has_mise)
    if has_mas:
        system.refresh_mas_index()
    others = [
        *build_formula_nodes(
            scanned.formulae, scanned.leaves, dependents_lookup(scanned.installed_deps)
        ),
        *collapse_casks(scanned.casks, system.deps_of),
        *_mise_nodes(scanned.mise),
        *app_nodes(
            scanned.self_updating, {cask.name for cask in scanned.casks}, system.installed_app
        ),
    ]
    nodes = [*others, *_mas_nodes(scanned.mas, {node.name for node in others})]
    return annotate(nodes, load_notes(notes_path()), scanned.descriptions)


# The notes file's source names, which match its other consumers rather than freshenup's Kinds.
_NOTE_SOURCES = {
    Kind.FORMULA: "brew",
    Kind.CASK: "cask",
    Kind.MAS: "mas",
    Kind.MISE: "mise",
    Kind.APP: "cask",
}


def _note_name(node: Node) -> str:
    # App Store rows show a slug; the notes file uses the app's real name.
    if node.kind is Kind.MAS and node.itself is not None:
        return node.itself.name
    return node.name


def annotate(nodes: list[Node], notes: Notes, descriptions: dict[str, str]) -> list[Node]:
    """Attach what/why from the notes file; brew's description fills in a missing what."""
    empty = Note()

    def with_note(node: Node) -> Node:
        note = notes.get(_NOTE_SOURCES[node.kind], {}).get(_note_name(node), empty)
        what = note.what or descriptions.get(node.name, "")
        return replace(node, what=what, why=note.why)

    return [with_note(node) for node in nodes]


def _kinds_label(has_mas: bool, has_mise: bool) -> str:
    kinds = ["formulae", "casks"]
    if has_mas:
        kinds.append("App Store apps")
    if has_mise:
        kinds.append("mise tools")
    if len(kinds) == 2:
        return " and ".join(kinds)
    return f"{', '.join(kinds[:-1])}, and {kinds[-1]}"


def _mas_nodes(apps: list[Item], taken: set[str]) -> list[Node]:
    # Display a slugified name; the numeric id in itself.mas_id drives the action. Rows are keyed
    # by name, so a slug that clashes with another row gets the last 3 id digits appended.
    slugs = Counter(_slug(app.name) for app in apps)

    def name(app: Item) -> str:
        slug = _slug(app.name)
        unique = slugs[slug] == 1 and slug not in taken
        return slug if unique else f"{slug}-{app.mas_id[-3:]}"

    return [Node(kind=Kind.MAS, name=name(app), itself=app) for app in apps]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _mise_nodes(tools: list[Item]) -> list[Node]:
    # mise tool ids are already unique and human-readable, so each is its own flat node — no slug
    # and no dependency folding (unlike formulae/casks).
    return [Node(kind=Kind.MISE, name=tool.name, itself=tool) for tool in tools]


def app_nodes(
    casks: Iterable[SelfUpdating],
    listed: set[str],
    installed_app: Callable[[SelfUpdating], system.InstalledApp | None],
) -> list[Node]:
    """Self-updating casks whose installed app is behind brew's latest. They are only reported:
    the app's own updater should install it, since a forced brew upgrade can downgrade an app that
    has run ahead of the cask. Casks brew already lists as outdated (``listed``) keep their normal
    row."""
    nodes: list[Node] = []
    for cask in casks:
        if cask.token in listed:
            continue
        app = installed_app(cask)
        if app is None or not is_newer(cask.latest, app.version):
            continue
        item = Item(
            kind=Kind.APP, name=cask.token, current=app.version, latest=cask.latest, app=app.path
        )
        nodes.append(Node(kind=Kind.APP, name=cask.token, itself=item))
    return nodes


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
    mise: list[str]
    apps: list[str]


def _route(nodes: list[Node]) -> _Targets:
    """Split selected nodes' items into deduped upgrade lists by kind (App Store apps route by
    numeric id; formulae, casks, and mise tools by name)."""
    formulae: list[str] = []
    casks: list[str] = []
    mas_ids: list[str] = []
    mise: list[str] = []
    apps: list[str] = []
    for node in nodes:
        for item in _items(node):
            if item.kind is Kind.CASK:
                casks.append(item.name)
            elif item.kind is Kind.MAS:
                mas_ids.append(item.mas_id)
            elif item.kind is Kind.MISE:
                mise.append(item.name)
            elif item.kind is Kind.APP:
                apps.append(item.app)
            else:
                formulae.append(item.name)
    return _Targets(
        _unique(formulae), _unique(casks), _unique(mas_ids), _unique(mise), _unique(apps)
    )


def _update(nodes: list[Node], *, deselected: bool) -> None:
    targets = _route(nodes)
    if deselected:
        _report_ride_alongs(nodes, targets.formulae)
    system.upgrade(Kind.FORMULA, targets.formulae)
    _upgrade_casks(targets.casks)
    system.upgrade(Kind.MAS, targets.mas_ids)
    system.upgrade(Kind.MISE, targets.mise)
    for app in targets.apps:
        print(f"  {app} updates itself — opening it to install the update", file=sys.stderr)
        system.open_app(app)


def _report_ride_alongs(nodes: list[Node], formulae: list[str]) -> None:
    """Name the formulae brew will upgrade beyond what was picked, before it starts."""
    extras = sorted(set(system.dry_run_formulae(formulae)) - set(formulae))
    if not extras:
        return
    lines = explain_ride_alongs(nodes, set(formulae), extras, system.formula_deps(extras))
    for line in lines:
        print(f"  {line}", file=sys.stderr)


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
