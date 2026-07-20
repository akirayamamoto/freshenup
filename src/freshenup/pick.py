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

from .models import Node

_PAYLOAD = TypeAdapter(list[Node])
_ENV_PAYLOAD = "FRESHENUP_PAYLOAD"
_UNINSTALL = "%%UNINSTALL%%"
_HEADER = "enter=update  ctrl-x=uninstall highlighted  tab=toggle  ctrl-t=invert"


def render_preview(node: Node) -> str:
    header = node.name
    if node.itself is not None:
        header += f"  {node.itself.current} → {node.itself.latest}"
    header += f"  {node.kind.label}"
    members = [f"  {m.name:<22} {m.current} → {m.latest}" for m in node.members]
    return "\n".join([header, *members])


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


def pick(nodes: list[Node]) -> Selection | None:
    """Show the fzf menu; return the chosen nodes (or a single node to uninstall), or None."""
    by_name = {node.name: node for node in nodes}
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as tmp:
        tmp.write(_PAYLOAD.dump_json(nodes))
        payload = tmp.name
    preview_cmd = f"{shlex.quote(sys.executable)} -m freshenup --preview {{}}"
    try:
        proc = subprocess.run(
            [
                "fzf",
                "-m",
                "--bind",
                "load:select-all",
                "--bind",
                "ctrl-t:toggle-all",
                "--bind",
                f"ctrl-x:print({_UNINSTALL})+deselect-all+accept",
                "--header",
                _HEADER,
                "--preview",
                preview_cmd,
                "--preview-window",
                "right,55%",
            ],
            input="\n".join(sorted(by_name)),
            text=True,
            stdout=subprocess.PIPE,
            env={**os.environ, _ENV_PAYLOAD: payload},
        )
    finally:
        os.unlink(payload)
    if proc.returncode != 0:
        return None
    lines = [line for line in proc.stdout.splitlines() if line]
    if not lines:
        return None
    if lines[0] == _UNINSTALL:
        target = by_name.get(lines[1]) if len(lines) > 1 else None
        return Selection(nodes=[], uninstall=target)
    return Selection(nodes=[by_name[line] for line in lines if line in by_name], uninstall=None)
