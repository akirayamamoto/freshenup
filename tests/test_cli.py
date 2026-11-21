# pyright: reportPrivateUsage=false
"""Tests for CLI-side pure helpers: slugging, MAS node naming, and upgrade routing."""

import pytest

from freshenup import cli, system
from freshenup.cli import (
    _REQUIRED_TOOLS,
    _mas_nodes,
    _mise_nodes,
    _missing_tools,
    _offer_missing_mise_tools,
    _route,
    _slug,
    app_nodes,
    cask_nodes,
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


def test_app_nodes_judge_self_updating_casks_by_the_installed_app() -> None:
    def cask(token: str) -> SelfUpdating:
        return SelfUpdating(token=token, latest="2.0", names=(), app_paths=(), bundle_ids=())

    # brew's record for a self-updating cask goes stale, so even a cask brew lists is judged by
    # the app on disk
    versions = {"behind": "1.9", "current": "2.0"}

    def installed_app(c: SelfUpdating) -> InstalledApp | None:
        version = versions.get(c.token)
        if version is None:
            return None
        return InstalledApp(path=f"/Applications/{c.token}.app", version=version)

    casks = [cask(t) for t in ("behind", "current", "not-found")]
    rows = app_nodes(casks, installed_app)
    # found apps replace their brew rows; an app not found keeps its brew row
    assert rows.found == {"behind", "current"}
    (node,) = rows.nodes
    assert node.kind is Kind.APP
    assert node.itself is not None
    assert (node.itself.current, node.itself.latest) == ("1.9", "2.0")
    # selecting it opens the app rather than upgrading through brew
    targets = _route([node])
    assert targets.apps == ["/Applications/behind.app"]
    assert targets.casks == []


@pytest.mark.parametrize(("answer", "installs"), [("y", True), ("n", False)])
def test_missing_mise_tools_install_only_when_confirmed(
    monkeypatch: pytest.MonkeyPatch, answer: str, installs: bool
) -> None:
    installed: list[bool] = []
    monkeypatch.setattr(system, "missing_mise_tools", lambda: ["node@26.13.1"])
    monkeypatch.setattr(system, "install_missing_mise_tools", lambda: installed.append(True))

    def confirm(_prompt: str) -> bool:
        return answer == "y"

    monkeypatch.setattr(cli, "_confirm", confirm)
    _offer_missing_mise_tools(has_mise=True)
    assert installed == ([True] if installs else [])


def test_found_self_updating_cask_loses_its_brew_row() -> None:
    # brew lists all three; only the app on disk decides for self-updating ones
    def cask(token: str) -> SelfUpdating:
        return SelfUpdating(token=token, latest="2.0", names=(), app_paths=(), bundle_ids=())

    versions = {"behind": "1.9", "current": "2.0", "unreadable": "beta"}

    def installed_app(c: SelfUpdating) -> InstalledApp | None:
        version = versions.get(c.token)
        return InstalledApp(path=f"/A/{c.token}.app", version=version) if version else None

    listed = [_cask(t) for t in ("behind", "current", "not-found", "unreadable", "slack")]
    self_updating = [cask(t) for t in ("behind", "current", "not-found", "unreadable")]
    nodes = cask_nodes(listed, self_updating, installed_app, lambda _token: [])
    assert {(n.kind, n.name) for n in nodes} == {
        (Kind.APP, "behind"),
        (Kind.CASK, "not-found"),
        # versions that can't be compared keep brew's row rather than vanish
        (Kind.CASK, "unreadable"),
        (Kind.CASK, "slack"),
    }
