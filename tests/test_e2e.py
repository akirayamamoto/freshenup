# pyright: reportPrivateUsage=false
"""End-to-end: real brew and the CLI entry point. Runs on macOS (see the e2e marker)."""

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from freshenup import system
from freshenup.models import Item, Kind, Node
from freshenup.pick import _PAYLOAD

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(shutil.which("brew") is None, reason="needs Homebrew")
def test_scan_against_real_brew_is_well_formed() -> None:
    # Read-only (no `brew update`). Whatever brew reports, our parsers must yield well-formed
    # Items — this is the one thing fixtures can't catch: brew changing its output format.
    scan = system.scan(refresh=False, has_mas=False)
    assert isinstance(scan.leaves, set)
    for item in (*scan.formulae, *scan.casks):
        assert item.name and item.current and item.latest


def test_preview_subprocess_round_trips() -> None:
    # Exercises the real entry point + pydantic TypeAdapter read path, exactly as fzf calls it.
    node = Node(
        kind=Kind.FORMULA,
        name="mpv",
        itself=Item(kind=Kind.FORMULA, name="mpv", current="1.0", latest="1.1"),
    )
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as tmp:
        tmp.write(_PAYLOAD.dump_json([node]))
        payload = tmp.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "freshenup", "--preview", "mpv"],
            capture_output=True,
            text=True,
            env={**os.environ, "FRESHENUP_PAYLOAD": payload},
        )
    finally:
        os.unlink(payload)
    assert result.returncode == 0
    assert "1.0 → 1.1" in result.stdout


def test_help_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "freshenup", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "freshenup" in result.stdout


def test_preflight_blocks_when_tools_missing() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "freshenup"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": ""},
    )
    assert result.returncode == 1
    assert "brew" in result.stderr
    assert "fzf" in result.stderr
