"""fzf shell-out: present nodes for multi-select and render the preview pane."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from .models import Kind, Node
from .notes import notes_path

_PAYLOAD = TypeAdapter(list[Node])
_ENV_PAYLOAD = "FRESHENUP_PAYLOAD"
_UNINSTALL = "%%UNINSTALL%%"
_KEYS = "enter=select  ctrl-s=update selected  ctrl-x=uninstall highlighted  ctrl-t=invert"
_DIM = "\x1b[2m"
_DIM_YELLOW = "\x1b[2;33m"
_RESET = "\x1b[0m"
_SOURCES = {
    Kind.FORMULA: ("Homebrew", "\x1b[33m"),
    Kind.CASK: ("Homebrew app", "\x1b[35m"),
    Kind.MAS: ("App Store", "\x1b[34m"),
    Kind.MISE: ("mise", "\x1b[36m"),
    Kind.APP: ("Updates itself", "\x1b[32m"),
}
_SOURCE_WIDTH = max(len(source) for source, _color in _SOURCES.values())
_MAX_VERSION_WIDTH = 15
_UP_TO_DATE = "(up to date)"
_GAP = "  "


@dataclass(frozen=True, slots=True)
class _Cell:
    """Display text with optional ANSI styling; padding is measured on ``plain`` so escape codes
    don't throw the columns off."""

    plain: str
    styled: str

    def ljust(self, width: int) -> str:
        return self.styled + " " * (width - len(self.plain))

    def rjust(self, width: int) -> str:
        return " " * (width - len(self.plain)) + self.styled


def _dimmed(text: str, start: int, end: int) -> _Cell:
    if start >= end:
        return _Cell(text, text)
    return _Cell(text, f"{text[:start]}{_DIM}{text[start:end]}{_RESET}{text[end:]}")


_NOTE_MARK = " ⓘ"


def _name_cell(node: Node) -> _Cell:
    # Dim a tap prefix ("owner/tap/") so the formula's own name stands out; ⓘ marks a row whose
    # preview has a why note.
    cell = _dimmed(node.name, 0, node.name.rfind("/") + 1)
    if not node.why:
        return cell
    return _Cell(cell.plain + _NOTE_MARK, f"{cell.styled}{_DIM}{_NOTE_MARK}{_RESET}")


def _version_cell(version: str) -> _Cell:
    # Dim a cask's comma build suffix ("3.9,3.9.0.88839"): kept, but it isn't the version people
    # recognise.
    comma = version.find(",")
    return _dimmed(version, comma, len(version)) if comma > 0 else _Cell(version, version)


def _updates(node: Node) -> str:
    count = len(node.members)
    if not count:
        return ""
    noun = "dependency" if count == 1 else "dependencies"
    return f"{count} {noun}"


@dataclass(frozen=True, slots=True)
class _Widths:
    name: int
    current: int
    latest: int

    @staticmethod
    def of(nodes: list[Node]) -> _Widths:
        items = [node.itself for node in nodes if node.itself is not None]
        current = max((len(item.current) for item in items), default=0)
        latest = max((len(item.latest) for item in items), default=0)
        return _Widths(
            name=max(len(_name_cell(node).plain) for node in nodes),
            current=min(current, _MAX_VERSION_WIDTH),
            latest=min(latest, _MAX_VERSION_WIDTH),
        )

    @property
    def version(self) -> int:
        return self.current + len(" → ") + self.latest


def row_label(node: Node, widths: _Widths) -> str:
    """One aligned row: source, name, version bump, and what else updates with it."""
    source, color = _SOURCES[node.kind]
    if node.itself is None:
        version = _Cell(_UP_TO_DATE, f"{_DIM}{_UP_TO_DATE}{_RESET}").ljust(widths.version)
    else:
        current = _version_cell(node.itself.current).rjust(widths.current)
        version = f"{current} → {_version_cell(node.itself.latest).ljust(widths.latest)}"
    updates = _updates(node)
    return _GAP.join(
        [
            _Cell(source, f"{color}{source}{_RESET}").ljust(_SOURCE_WIDTH),
            _name_cell(node).ljust(widths.name),
            version,
            f"{_DIM_YELLOW}{updates}{_RESET}" if updates else "",
        ]
    ).rstrip()


def _header(widths: _Widths) -> str:
    titles = _GAP.join(
        [
            "SOURCE".ljust(_SOURCE_WIDTH),
            "NAME".ljust(widths.name),
            "VERSION".ljust(widths.version),
            "ALSO UPDATES",
        ]
    )
    return f"{_KEYS}\n{titles}"


def _sort_key(node: Node) -> tuple[int, str]:
    return list(Kind).index(node.kind), node.name


def render_preview(node: Node) -> str:
    header = node.name
    if node.itself is not None:
        header += f"  {node.itself.current} → {node.itself.latest}"
    header += f"  {node.kind.label}"
    what = f"What: {node.what or '—'}"
    why = f"Why:  {node.why or f'no note — add one to {notes_path()}'}"
    members = [f"  {m.name:<22} {m.current} → {m.latest}" for m in node.members]
    lines = [header, what, why]
    if members:
        lines += ["", "Dependencies updating:", *members]
    return "\n".join(lines)


def preview(name: str) -> str:
    """Render the preview for ``name``, reading the node payload written by ``pick``."""
    path = os.environ.get(_ENV_PAYLOAD)
    if not path:
        return name
    nodes = _PAYLOAD.validate_json(Path(path).read_bytes())
    return next((render_preview(n) for n in nodes if n.name == name), name)


@dataclass(frozen=True, slots=True)
class Selection:
    nodes: list[Node]
    uninstall: Node | None


def _selection_from(stdout: str, by_name: dict[str, Node]) -> Selection | None:
    """Parse fzf's stdout: the uninstall sentinel plus its highlighted row, or the chosen node
    names mapped back to nodes. None when nothing usable was selected."""
    lines = [line for line in stdout.splitlines() if line]
    if not lines:
        return None
    if lines[0] == _UNINSTALL:
        target = by_name.get(lines[1]) if len(lines) > 1 else None
        return Selection(nodes=[], uninstall=target)
    return Selection(nodes=[by_name[line] for line in lines if line in by_name], uninstall=None)


def pick(nodes: list[Node]) -> Selection | None:
    """Show the fzf menu; return the chosen nodes (or a single node to uninstall), or None."""
    by_name = {node.name: node for node in nodes}
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as tmp:
        tmp.write(_PAYLOAD.dump_json(nodes))
        payload = tmp.name
    preview_cmd = f"{shlex.quote(sys.executable)} -m freshenup --preview {{1}}"
    widths = _Widths.of(nodes)
    try:
        proc = subprocess.run(
            [
                "fzf",
                "-m",
                "--ansi",
                "--delimiter",
                "\t",
                "--with-nth",
                "2",
                "--accept-nth",
                "1",
                "--bind",
                "enter:toggle+down",
                # Updating needs a ticked row; otherwise fzf would accept the highlighted one.
                "--bind",
                "ctrl-s:transform:[ $FZF_SELECT_COUNT -gt 0 ] && echo accept",
                "--bind",
                "ctrl-t:toggle-all",
                "--bind",
                f"ctrl-x:print({_UNINSTALL})+deselect-all+accept",
                "--header",
                _header(widths),
                "--preview",
                preview_cmd,
                "--preview-window",
                "right,55%",
            ],
            input="\n".join(
                f"{node.name}\t{row_label(node, widths)}" for node in sorted(nodes, key=_sort_key)
            ),
            text=True,
            stdout=subprocess.PIPE,
            env={**os.environ, _ENV_PAYLOAD: payload},
        )
    finally:
        os.unlink(payload)
    if proc.returncode != 0:
        return None
    return _selection_from(proc.stdout, by_name)
