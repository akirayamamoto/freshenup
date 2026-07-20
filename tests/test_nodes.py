"""Tests for node grouping — injected lookups stand in for brew/receipt queries."""

from collections.abc import Callable

from freshenup.models import Item, Kind
from freshenup.nodes import build_formula_nodes, collapse_casks


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


def test_dependency_not_outdated_is_ignored() -> None:
    nodes = collapse_casks(
        _casks("microsoft-word"), deps_of=_lookup({"microsoft-word": ["microsoft-auto-update"]})
    )
    assert len(nodes) == 1
    assert nodes[0].name == "microsoft-word"
    assert nodes[0].members == ()  # auto-update isn't outdated → not folded in
