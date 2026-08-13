"""Tests for node grouping — injected lookups stand in for brew/receipt queries."""

from collections.abc import Callable

from freshenup.models import Deps, Item, Kind, Node
from freshenup.nodes import build_formula_nodes, collapse_casks, explain_ride_alongs


def _item(name: str, kind: Kind = Kind.FORMULA) -> Item:
    return Item(kind=kind, name=name, current="1", latest="2")


def _casks(*names: str) -> list[Item]:
    return [_item(name, Kind.CASK) for name in names]


def _lookup(table: dict[str, list[str]]) -> Callable[[str], list[str]]:
    return lambda name: table.get(name, [])


def test_outdated_leaf_is_its_own_node() -> None:
    nodes = build_formula_nodes([_item("mpv")], leaves={"mpv"}, uses=_lookup({}))
    assert len(nodes) == 1
    assert nodes[0].name == "mpv"
    assert nodes[0].itself is not None
    assert nodes[0].members == ()


def test_outdated_dep_folds_under_its_leaf() -> None:
    # ffmpeg is a dependency used by the leaf mpv
    nodes = build_formula_nodes(
        [_item("ffmpeg")], leaves={"mpv"}, uses=_lookup({"ffmpeg": ["mpv"]})
    )
    assert len(nodes) == 1
    assert nodes[0].name == "mpv"  # node is the leaf, not the dep
    assert nodes[0].itself is None  # the leaf itself isn't outdated
    assert [m.name for m in nodes[0].members] == ["ffmpeg"]


def test_leaf_outdated_and_has_outdated_dep() -> None:
    nodes = build_formula_nodes(
        [_item("mpv"), _item("ffmpeg")], leaves={"mpv"}, uses=_lookup({"ffmpeg": ["mpv"]})
    )
    assert len(nodes) == 1
    assert nodes[0].itself is not None
    assert [m.name for m in nodes[0].members] == ["ffmpeg"]


def test_independent_casks_are_separate_nodes() -> None:
    nodes = collapse_casks(_casks("slack", "zoom"), deps_of=_lookup({}))
    assert {n.name for n in nodes} == {"slack", "zoom"}
    assert all(n.members == () for n in nodes)


def test_outdated_dep_cask_folds_under_parent() -> None:
    nodes = collapse_casks(
        _casks("dotnet-sdk8", "dotnet-sdk8-0-400"),
        deps_of=_lookup({"dotnet-sdk8": ["dotnet-sdk8-0-400"]}),
    )
    assert len(nodes) == 1
    assert nodes[0].name == "dotnet-sdk8"
    assert [m.name for m in nodes[0].members] == ["dotnet-sdk8-0-400"]


def _node(name: str, *members: str) -> Node:
    return Node(
        kind=Kind.FORMULA,
        name=name,
        itself=_item(name),
        members=tuple(_item(member) for member in members),
    )


def _deps(declared: list[str], runtime: list[str] | None = None) -> Deps:
    return Deps(declared=frozenset(declared), runtime=frozenset(runtime or []))


def test_ride_along_names_the_rows_carrying_the_dependency() -> None:
    # node isn't a row of its own — it is folded under every leaf that uses it
    selected = [_node("agent-browser", "node"), _node("playwright-cli", "node")]
    lines = explain_ride_alongs(
        selected,
        targets={"agent-browser", "playwright-cli", "node"},
        extras=["opencode"],
        deps={"opencode": _deps(["node", "ripgrep"])},
    )
    assert lines == [
        "Also upgrading opencode — pulled in by node "
        "because you selected agent-browser, playwright-cli."
    ]


def test_ride_along_falls_back_to_the_installed_closure() -> None:
    # the declared dependency (node) wasn't selected, but libffi underneath it was
    lines = explain_ride_alongs(
        [_node("mpv", "libffi")],
        targets={"mpv", "libffi"},
        extras=["opencode"],
        deps={"opencode": _deps(["node"], runtime=["node", "libffi"])},
    )
    assert lines == ["Also upgrading opencode — pulled in by libffi because you selected mpv."]


def test_ride_along_without_a_known_cause_still_reports() -> None:
    lines = explain_ride_alongs([_node("mpv")], targets={"mpv"}, extras=["ffmpeg"], deps={})
    assert lines == ["Also upgrading ffmpeg — brew rebuilds it alongside your selection."]


def test_dependency_not_outdated_is_ignored() -> None:
    nodes = collapse_casks(
        _casks("microsoft-word"), deps_of=_lookup({"microsoft-word": ["microsoft-auto-update"]})
    )
    assert len(nodes) == 1
    assert nodes[0].name == "microsoft-word"
    assert nodes[0].members == ()  # auto-update isn't outdated → not folded in
