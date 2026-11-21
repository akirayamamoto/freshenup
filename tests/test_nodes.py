"""Tests for node grouping — injected lookups stand in for brew/receipt queries."""

from collections.abc import Callable

from freshenup.models import Deps, Edge, Item, Kind, Node
from freshenup.nodes import (
    build_formula_nodes,
    collapse_casks,
    dependents_lookup,
    explain_ride_alongs,
    member_tree,
)


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
        "Brew will also upgrade 1 package you didn't pick:",
        "node  ← in your picks via agent-browser, playwright-cli",
        "└─ opencode",
        "To skip one, deselect the picks named on its branch.",
    ]


def test_ride_along_falls_back_to_the_installed_closure() -> None:
    # the declared dependency (node) wasn't selected, but libffi underneath it was
    lines = explain_ride_alongs(
        [_node("mpv", "libffi")],
        targets={"mpv", "libffi"},
        extras=["opencode"],
        deps={"opencode": _deps(["node"], runtime=["node", "libffi"])},
    )
    assert lines[1:3] == ["libffi  ← in your picks via mpv", "└─ opencode"]


def test_ride_along_without_a_known_cause_still_reports() -> None:
    lines = explain_ride_alongs([_node("mpv")], targets={"mpv"}, extras=["ffmpeg"], deps={})
    assert lines == [
        "Brew will also upgrade 1 package you didn't pick:",
        "rebuilt alongside your selection:",
        "└─ ffmpeg",
    ]


def test_dependency_not_outdated_is_ignored() -> None:
    nodes = collapse_casks(
        _casks("microsoft-word"), deps_of=_lookup({"microsoft-word": ["microsoft-auto-update"]})
    )
    assert len(nodes) == 1
    assert nodes[0].name == "microsoft-word"
    assert nodes[0].members == ()  # auto-update isn't outdated → not folded in


def test_dependents_lookup_inverts_runtime_deps() -> None:
    uses = dependents_lookup(
        {"mpv": _deps([], ["ffmpeg", "libass"]), "yt-dlp": _deps([], ["ffmpeg"])}
    )
    assert sorted(uses("ffmpeg")) == ["mpv", "yt-dlp"]
    assert uses("libass") == ["mpv"]
    assert uses("unused") == []


def test_ride_alongs_sharing_a_cause_group_under_it() -> None:
    lines = explain_ride_alongs(
        [_node("yta", "ca-certificates")],
        targets={"yta", "ca-certificates"},
        extras=["python@3.15", "curl-impersonate"],
        deps={
            "python@3.15": _deps(["ca-certificates"]),
            "curl-impersonate": _deps(["ca-certificates"]),
        },
    )
    assert lines[:4] == [
        "Brew will also upgrade 2 packages you didn't pick:",
        "ca-certificates  ← in your picks via yta",
        "├─ curl-impersonate",
        "└─ python@3.15",
    ]


def test_members_nest_under_their_nearest_outdated_ancestor() -> None:
    # yta → python → openssl → ca-certificates; curl (not outdated) sits between, so skipped
    installed = {
        "python@3.14": _deps([], ["openssl@4", "ca-certificates"]),
        "openssl@4": _deps([], ["ca-certificates"]),
    }
    outdated = [_item("python@3.14"), _item("openssl@4"), _item("ca-certificates")]
    uses = _lookup({name.name: ["yta"] for name in outdated})
    (node,) = build_formula_nodes(outdated, leaves={"yta"}, uses=uses, installed=installed)
    assert set(node.edges) == {
        Edge(parent="python@3.14", child="openssl@4"),
        Edge(parent="openssl@4", child="ca-certificates"),
    }
    assert member_tree(node) == {
        "yta": ["python@3.14"],
        "python@3.14": ["openssl@4"],
        "openssl@4": ["ca-certificates"],
    }
