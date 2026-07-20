"""Pure node-building: group outdated Items into the rows freshenup shows in fzf.

Both builders take injected lookups (`uses`, `deps_of`) for their brew/receipt queries, so the
grouping logic is unit-tested without any subprocess.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .models import Item, Kind, Node


def build_formula_nodes(
    outdated: list[Item],
    leaves: set[str],
    uses: Callable[[str], Iterable[str]],
) -> list[Node]:
    """Group outdated formulae under their leaf (installed-on-request) formula: an outdated leaf
    is its own node; an outdated dependency folds under the leaves that require it (`uses` gives a
    formula's recursive dependents)."""
    selves: dict[str, Item] = {}
    member_map: dict[str, list[Item]] = {}
    for item in outdated:
        if item.name in leaves:
            selves[item.name] = item
        else:
            for dependent in uses(item.name):
                if dependent in leaves:
                    member_map.setdefault(dependent, []).append(item)
    names = sorted(selves.keys() | member_map.keys())
    return [
        Node(
            kind=Kind.FORMULA,
            name=name,
            itself=selves.get(name),
            members=tuple(member_map.get(name, ())),
        )
        for name in names
    ]


def collapse_casks(
    casks: list[Item],
    deps_of: Callable[[str], Iterable[str]],
) -> list[Node]:
    """Fold an outdated cask under an outdated cask that depends on it (e.g. a version-band cask
    under its wrapper) so the pair shows as one row. `deps_of` gives a cask's cask dependencies."""
    by_name = {cask.name: cask for cask in casks}
    outdated = by_name.keys()
    deps = {cask.name: [d for d in deps_of(cask.name) if d in outdated] for cask in casks}
    folded = {dep for dep_list in deps.values() for dep in dep_list}
    return [
        Node(
            kind=Kind.CASK,
            name=cask.name,
            itself=cask,
            members=tuple(by_name[d] for d in deps[cask.name]),
        )
        for cask in casks
        if cask.name not in folded
    ]
