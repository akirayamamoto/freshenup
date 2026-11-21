"""Tests for the shared box-drawing tree renderer."""

from freshenup.tree import render_tree


def test_nesting_corners_and_continuation_bars() -> None:
    children = {"root": ["a", "b"], "a": ["a1", "a2"], "b": ["b1"]}
    assert render_tree("root", children) == [
        "root",
        "├─ a",
        "│  ├─ a1",
        "│  └─ a2",
        "└─ b",
        "   └─ b1",
    ]


def test_label_decorates_every_name() -> None:
    assert render_tree("r", {"r": ["x"]}, str.upper) == ["R", "└─ X"]
