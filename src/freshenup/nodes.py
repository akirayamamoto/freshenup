"""Pure node-building: group outdated Items into the rows freshenup shows in fzf.

Both builders take injected lookups (`uses`, `deps_of`) for their brew/receipt queries, so the
grouping logic is unit-tested without any subprocess.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .models import Deps, Edge, Item, Kind, Node
from .tree import render_tree


def dependents_lookup(installed: dict[str, Deps]) -> Callable[[str], list[str]]:
    """Invert installed formulae's (already recursive) runtime dependencies into a `uses` lookup:
    formula name → the installed formulae that depend on it."""
    dependents: dict[str, list[str]] = {}
    for name, deps in installed.items():
        for dep in deps.runtime:
            dependents.setdefault(dep, []).append(name)
    return lambda name: dependents.get(name, [])


def build_formula_nodes(
    outdated: list[Item],
    leaves: set[str],
    uses: Callable[[str], Iterable[str]],
    installed: dict[str, Deps] | None = None,
) -> list[Node]:
    """Group outdated formulae under their leaf (installed-on-request) formula: an outdated leaf
    is its own node; an outdated dependency folds under the leaves that require it (`uses` gives a
    formula's recursive dependents). ``installed`` nests the folded dependencies under each other
    for the preview."""
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
            edges=_nesting(name, member_map.get(name, []), installed or {}),
        )
        for name in names
    ]


def _nesting(root: str, members: list[Item], installed: dict[str, Deps]) -> tuple[Edge, ...]:
    """Hang each member under its closest ancestor within the row. A dependency's closure is a
    subset of its dependents', so among the ancestors that need a member, the one with the
    smallest closure is the nearest. Not-outdated formulae in between are skipped."""
    names = [member.name for member in members]
    edges: list[Edge] = []
    for member in names:
        ancestors = [
            name for name in names if name != member and member in _closure(installed, name)
        ]
        if not ancestors:
            continue
        nearest = min(ancestors, key=lambda name: (len(_closure(installed, name)), name))
        edges.append(Edge(parent=nearest, child=member))
    return tuple(edges)


def _closure(installed: dict[str, Deps], name: str) -> frozenset[str]:
    deps = installed.get(name)
    return deps.runtime if deps is not None else frozenset()


def member_tree(node: Node) -> dict[str, list[str]]:
    """The row's members as a parent → children map rooted at the row's name."""
    nested = {edge.child: edge.parent for edge in node.edges}
    children: dict[str, list[str]] = {}
    for member in sorted(m.name for m in node.members):
        children.setdefault(nested.get(member, node.name), []).append(member)
    return children


_UNEXPLAINED = "rebuilt alongside your selection:"


def explain_ride_alongs(
    selected: Iterable[Node],
    targets: set[str],
    extras: Iterable[str],
    deps: dict[str, Deps],
) -> list[str]:
    """A tree of the formulae brew upgrades without being asked to, grouped by the selected
    dependency that drags them in. Deselecting such a formula does nothing on its own: brew
    upgrades the outdated dependents of everything it is given, so the rows that carry the
    dependency have to go too — which are the rows each group names."""
    selected = list(selected)
    by_cause: dict[str, list[str]] = {}
    carriers_of: dict[str, list[str]] = {}
    unexplained: list[str] = []
    for extra in sorted(extras):
        explained = False
        for culprit in sorted(_culprits(deps.get(extra), targets)):
            carriers = sorted(node.name for node in selected if _carries(node, {culprit}))
            if not carriers:
                continue
            carriers_of[culprit] = carriers
            by_cause.setdefault(culprit, []).append(extra)
            explained = True
        if not explained:
            unexplained.append(extra)
    count = len({*unexplained, *(extra for pulled in by_cause.values() for extra in pulled)})
    if not count:
        return []
    noun = "package" if count == 1 else "packages"
    lines = [f"Brew will also upgrade {count} {noun} you didn't pick:"]
    roots = {
        culprit: f"{culprit}  ← in your picks via {', '.join(carriers)}"
        for culprit, carriers in carriers_of.items()
    }
    for culprit, pulled in by_cause.items():
        lines += render_tree(culprit, {culprit: pulled}, lambda name: roots.get(name, name))
    if unexplained:
        lines += render_tree(_UNEXPLAINED, {_UNEXPLAINED: unexplained})
    if by_cause:
        lines.append("To skip one, deselect the picks named on its branch.")
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
