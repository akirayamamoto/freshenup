"""Pure node-building: group outdated Items into the rows freshenup shows in fzf.

Both builders take injected lookups (`uses`, `deps_of`) for their brew/receipt queries, so the
grouping logic is unit-tested without any subprocess.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .models import Deps, Item, Kind, Node


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


def explain_ride_alongs(
    selected: Iterable[Node],
    targets: set[str],
    extras: Iterable[str],
    deps: dict[str, Deps],
) -> list[str]:
    """One line per formula brew upgrades without being asked to. Deselecting such a formula does
    nothing on its own: brew upgrades the outdated dependents of everything it is given, so the row
    that carries the dependency has to go too — which is the row each line names."""
    lines: list[str] = []
    for extra in extras:
        culprits = _culprits(deps.get(extra), targets)
        carriers = sorted(node.name for node in selected if _carries(node, culprits))
        if not carriers:
            lines.append(f"Also upgrading {extra} — brew rebuilds it alongside your selection.")
            continue
        lines.append(
            f"Also upgrading {extra} — pulled in by {', '.join(sorted(culprits))} "
            f"because you selected {', '.join(carriers)}."
        )
    return lines


def _culprits(deps: Deps | None, targets: set[str]) -> set[str]:
    """What in the selection drags a ride-along in: its own declared dependencies where those
    explain it, else its installed closure, which reaches dependencies further down."""
    if deps is None:
        return set()
    return set(deps.declared & targets) or set(deps.runtime & targets)


def _carries(node: Node, culprits: set[str]) -> bool:
    return bool(culprits & {node.name, *(member.name for member in node.members)})


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
