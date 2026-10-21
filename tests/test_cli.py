# pyright: reportPrivateUsage=false
"""Tests for CLI-side pure helpers: slugging, MAS node naming, and upgrade routing."""

from freshenup.cli import (
    _REQUIRED_TOOLS,
    _mas_nodes,
    _mise_nodes,
    _missing_tools,
    _route,
    _slug,
    app_nodes,
)
from freshenup.models import Item, Kind, Node, SelfUpdating
from freshenup.system import InstalledApp


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
    (node,) = _mas_nodes(apps, taken=set())
    assert node.kind is Kind.MAS
    assert node.name == "xcode"
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


def test_mas_nodes_suffix_only_on_clash() -> None:
    apps = [Item(kind=Kind.MAS, name="Slack", current="1", latest="2", mas_id="803453959")]
    (node,) = _mas_nodes(apps, taken={"slack"})
    assert node.name == "slack-959"


def test_app_nodes_report_only_apps_behind_brew() -> None:
    def cask(token: str) -> SelfUpdating:
        return SelfUpdating(token=token, latest="2.0", names=(), app_paths=(), bundle_ids=())

    versions = {"behind": "1.9", "current": "2.0", "brew-lists": "1.0"}

    def installed_app(c: SelfUpdating) -> InstalledApp | None:
        version = versions.get(c.token)
        if version is None:
            return None
        return InstalledApp(path=f"/Applications/{c.token}.app", version=version)

    casks = [cask(t) for t in ("behind", "current", "brew-lists", "not-found")]
    (node,) = app_nodes(casks, {"brew-lists"}, installed_app)
    assert node.kind is Kind.APP
    assert node.itself is not None
    assert (node.itself.current, node.itself.latest) == ("1.9", "2.0")
    # selecting it opens the app rather than upgrading through brew
    targets = _route([node])
    assert targets.apps == ["/Applications/behind.app"]
    assert targets.casks == []
