"""Draw a name hierarchy as box-drawing lines, shared by the preview pane and the upgrade report."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence


def render_tree(
    root: str,
    children: Mapping[str, Sequence[str]],
    label: Callable[[str], str] = str,
) -> list[str]:
    """``root``'s label, then its descendants drawn beneath it. ``children`` maps a name to the
    names hanging directly under it."""
    lines = [label(root)]
    _branches(root, children, label, "", lines)
    return lines


def _branches(
    name: str,
    children: Mapping[str, Sequence[str]],
    label: Callable[[str], str],
    indent: str,
    lines: list[str],
) -> None:
    kids = children.get(name, ())
    for index, kid in enumerate(kids):
        last = index == len(kids) - 1
        lines.append(f"{indent}{'└─' if last else '├─'} {label(kid)}")
        _branches(kid, children, label, indent + ("   " if last else "│  "), lines)
