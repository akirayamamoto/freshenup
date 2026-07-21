# pyright: reportPrivateUsage=false
"""Tests for CLI-side pure helpers: slugging, MAS node naming, and upgrade routing."""

from freshenup.cli import _REQUIRED_TOOLS, _mas_nodes, _mise_nodes, _missing_tools, _route, _slug
from freshenup.models import Item, Kind, Node


def _cask(name: str) -> Item:
    return Item(kind=Kind.CASK, name=name, current="1", latest="2")


def _formula(name: str) -> Item:
    return Item(kind=Kind.FORMULA, name=name, current="1", latest="2")


def test_slug() -> None:
    assert _slug("Microsoft Word") == "microsoft-word"
    assert _slug("  Final Cut Pro!! ") == "final-cut-pro"
    assert _slug("1Password 7 — Password Manager") == "1password-7-password-manager"


def test_missing_tools() -> None:
    def which(tool: str) -> str | None:
        return None if tool == "fzf" else f"/opt/homebrew/bin/{tool}"

    assert _missing_tools(which) == ["fzf"]
    assert set(_REQUIRED_TOOLS) == {"brew", "fzf"}


def test_mas_nodes() -> None:
    apps = [Item(kind=Kind.MAS, name="Xcode", current="15.2", latest="15.3", mas_id="497799835")]
    (node,) = _mas_nodes(apps)
    assert node.kind is Kind.MAS
    assert node.name == "xcode-835"
    assert node.itself is not None
    assert node.itself.mas_id == "497799835"


def test_mise_nodes() -> None:
    tools = [Item(kind=Kind.MISE, name="npm:@google/gemini-cli", current="0.51.0", latest="0.52.0")]
    (node,) = _mise_nodes(tools)
    assert node.kind is Kind.MISE
    assert node.name == "npm:@google/gemini-cli"  # no slugging — the id is the upgrade target
    assert node.itself is not None
    assert node.itself.latest == "0.52.0"


def test_route_buckets_by_kind_and_dedups() -> None:
    xcode = Item(kind=Kind.MAS, name="Xcode", current="15.2", latest="15.3", mas_id="497799835")
    pnpm = Item(kind=Kind.MISE, name="pnpm", current="1", latest="2")
    nodes = [
        Node(kind=Kind.FORMULA, name="mpv", itself=_formula("mpv"), members=(_formula("ffmpeg"),)),
        Node(kind=Kind.CASK, name="slack", itself=_cask("slack")),
        Node(kind=Kind.CASK, name="slack-again", itself=_cask("slack")),
        Node(kind=Kind.MAS, name="xcode-835", itself=xcode),
        Node(kind=Kind.MISE, name="pnpm", itself=pnpm),
    ]
    targets = _route(nodes)
    assert targets.formulae == ["ffmpeg", "mpv"]
    assert targets.casks == ["slack"]
    assert targets.mas_ids == ["497799835"]
    assert targets.mise == ["pnpm"]
