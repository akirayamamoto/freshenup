# pyright: reportPrivateUsage=false
"""Tests for the fzf payload round-trip, preview rendering, and selection parsing."""

from freshenup.models import Item, Kind, Node
from freshenup.pick import _PAYLOAD, _UNINSTALL, _selection_from, render_preview


def _formula(name: str) -> Item:
    return Item(kind=Kind.FORMULA, name=name, current="1.0", latest="1.1")


def _nodes() -> list[Node]:
    xcode = Item(kind=Kind.MAS, name="Xcode", current="15.2", latest="15.3", mas_id="497799835")
    return [
        Node(kind=Kind.FORMULA, name="mpv", itself=_formula("mpv")),
        Node(kind=Kind.FORMULA, name="ffmpeg-tools", members=(_formula("ffmpeg"),)),
        Node(kind=Kind.MAS, name="xcode-835", itself=xcode),
    ]


def test_payload_round_trips() -> None:
    # The one pydantic path not covered by parse tests: TypeAdapter over the Node dataclass
    # (enum + nested Item + tuple members). If a pydantic bump breaks it, this fails.
    nodes = _nodes()
    assert _PAYLOAD.validate_json(_PAYLOAD.dump_json(nodes)) == nodes


def test_render_preview_with_members() -> None:
    node = Node(
        kind=Kind.FORMULA, name="mpv", itself=_formula("mpv"), members=(_formula("ffmpeg"),)
    )
    out = render_preview(node)
    assert "mpv" in out
    assert "1.0 → 1.1" in out
    assert "(formula)" in out
    assert "ffmpeg" in out


def test_render_preview_dep_only_header_has_no_version() -> None:
    node = Node(kind=Kind.FORMULA, name="mpv", members=(_formula("ffmpeg"),))
    header = render_preview(node).splitlines()[0]
    assert header.startswith("mpv")
    assert "(formula)" in header
    assert "→" not in header


def test_selection_normal_multi_select() -> None:
    by_name = {n.name: n for n in _nodes()}
    sel = _selection_from("mpv\nffmpeg-tools\n", by_name)
    assert sel is not None
    assert [n.name for n in sel.nodes] == ["mpv", "ffmpeg-tools"]
    assert sel.uninstall is None


def test_selection_uninstall_sentinel() -> None:
    by_name = {n.name: n for n in _nodes()}
    sel = _selection_from(f"{_UNINSTALL}\nmpv\n", by_name)
    assert sel is not None
    assert sel.nodes == []
    assert sel.uninstall is not None
    assert sel.uninstall.name == "mpv"


def test_selection_uninstall_without_target() -> None:
    sel = _selection_from(f"{_UNINSTALL}\n", {})
    assert sel is not None
    assert sel.nodes == []
    assert sel.uninstall is None


def test_selection_empty_is_none() -> None:
    assert _selection_from("\n", {}) is None


def test_selection_filters_unknown_lines() -> None:
    by_name = {n.name: n for n in _nodes()}
    sel = _selection_from("mpv\nbogus\n", by_name)
    assert sel is not None
    assert [n.name for n in sel.nodes] == ["mpv"]
