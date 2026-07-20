"""Tests for the cask-ownership predicate — filesystem lookups are injected."""

from collections.abc import Callable

from freshenup.system import blocked_casks


def _apps(table: dict[str, list[str]]) -> Callable[[str], list[str]]:
    return lambda token: table.get(token, [])


def _owners(table: dict[str, str]) -> Callable[[str], str | None]:
    return lambda app: table.get(app)


def test_root_owned_cask_is_blocked() -> None:
    blocked = blocked_casks(
        ["google-chrome"],
        apps_of=_apps({"google-chrome": ["Google Chrome.app"]}),
        owner_of=_owners({"Google Chrome.app": "root"}),
        me="akira",
    )
    assert blocked == [("google-chrome", "root")]


def test_user_owned_cask_is_not_blocked() -> None:
    blocked = blocked_casks(
        ["firefox"],
        apps_of=_apps({"firefox": ["Firefox.app"]}),
        owner_of=_owners({"Firefox.app": "akira"}),
        me="akira",
    )
    assert blocked == []


def test_missing_app_is_not_blocked() -> None:
    blocked = blocked_casks(
        ["ghost"],
        apps_of=_apps({}),
        owner_of=_owners({}),
        me="akira",
    )
    assert blocked == []
