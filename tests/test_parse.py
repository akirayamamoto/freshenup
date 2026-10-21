"""Fixture-pinned parser tests — every historical bug has a regression case here."""

from pathlib import Path

import pytest

from freshenup.models import Kind
from freshenup.parse import (
    is_newer,
    parse_brew_outdated,
    parse_mas,
    parse_mise,
    parse_receipt,
    parse_self_updating,
)

DATA = Path(__file__).parent / "data"


def _read(name: str) -> str:
    return (DATA / name).read_text()


def test_formula_current_is_newest_installed() -> None:
    by_name = {i.name: i for i in parse_brew_outdated(Kind.FORMULA, _read("outdated_formula.txt"))}
    assert (by_name["pnpm"].current, by_name["pnpm"].latest) == ("11.15.0", "11.15.1")
    # multiple installed versions → current is the last listed
    assert (by_name["foo"].current, by_name["foo"].latest) == ("1.1", "1.2")


def test_cask_comma_version_is_preserved() -> None:
    by_name = {i.name: i for i in parse_brew_outdated(Kind.CASK, _read("outdated_cask.txt"))}
    # regression: the comma-suffix is part of the version, not a build hash → keep it
    assert by_name["dotnet-sdk"].current == "8.0.422,8.0.28"
    assert by_name["dotnet-sdk"].latest == "8.0.423,8.0.28"


def test_cask_trailing_build_hash_is_stripped() -> None:
    by_name = {i.name: i for i in parse_brew_outdated(Kind.CASK, _read("outdated_cask.txt"))}
    assert (by_name["hashcask"].current, by_name["hashcask"].latest) == ("1.2.3", "1.2.4")


def test_mas_parses_ndjson_and_coerces_id_to_str() -> None:
    by_name = {i.name: i for i in parse_mas(_read("mas-outdated.ndjson"))}
    assert by_name["WhatsApp"].kind is Kind.MAS
    assert by_name["WhatsApp"].mas_id == "310633997"  # extra Spotlight keys are ignored
    assert (by_name["WhatsApp"].current, by_name["WhatsApp"].latest) == ("26.28.75", "26.29.73")


def test_mas_single_object_is_not_an_array() -> None:
    # regression: mas returns a lone object (no array) when exactly one app is outdated
    items = parse_mas('{"adamID":1,"name":"Solo","version":"1.0","newVersion":"2.0"}')
    assert len(items) == 1
    assert items[0].mas_id == "1"


def test_mas_missing_version_defaults_empty() -> None:
    by_name = {i.name: i for i in parse_mas(_read("mas-outdated.ndjson"))}
    assert by_name["NoVersionApp"].current == ""


def test_mise_parses_dict_keyed_by_tool_id() -> None:
    by_name = {i.name: i for i in parse_mise(_read("mise-outdated.json"))}
    assert by_name["pnpm"].kind is Kind.MISE
    assert (by_name["pnpm"].current, by_name["pnpm"].latest) == ("11.15.0", "11.15.1")
    # npm-backed ids keep their full "npm:@scope/pkg" form (that's the `mise upgrade` target)
    assert by_name["npm:@google/gemini-cli"].latest == "0.52.0"


def test_mise_null_current_defaults_empty() -> None:
    by_name = {i.name: i for i in parse_mise(_read("mise-outdated.json"))}
    assert by_name["node"].current == ""


def test_receipt_populated_deps_and_app() -> None:
    deps, apps = parse_receipt(_read("receipt_word.json"))
    assert deps == ["microsoft-auto-update"]
    assert apps == ["Microsoft Word.app"]


def test_receipt_empty_deps() -> None:
    deps, apps = parse_receipt(_read("receipt_beyond_compare.json"))
    assert deps == []
    assert apps == ["Beyond Compare.app"]


def test_self_updating_casks_and_where_to_find_their_app() -> None:
    by_token = {c.token: c for c in parse_self_updating(_read("info_casks.json"))}
    assert "ddpm" not in by_token  # no auto_updates
    assert by_token["warp"].app_paths == ("/Applications/Warp.app",)
    # a pkg cask lists no app; the bundle id it quits on uninstall finds it instead
    assert by_token["tailscale-app"].app_paths == ()
    assert by_token["tailscale-app"].bundle_ids == ("io.tailscale.ipn.macsys",)
    assert by_token["tailscale-app"].names == ("Tailscale",)
    assert "com.jabra.directonline" in by_token["jabra-direct"].bundle_ids


@pytest.mark.parametrize(
    ("latest", "installed", "newer"),
    [
        ("1.104.2", "1.98.8", True),  # numeric, not string, comparison
        ("1.104.2", "1.104.2", False),
        ("1.104.2", "1.105.0", False),  # the app ran ahead of the cask
        ("3.2.23,1241", "3.2.23", False),  # cask build suffix
        ("3.9,3.9.0.88839", "3.9.0.88839", False),
        ("2026.10.121159", "2026.10.121159-latest", False),  # app label
        ("0.2026.10.14.08.27.stable_02", "0.2026.10.14.08.27.02", False),
        ("1.2.0", "1.2", False),  # trailing zeros
        ("2.0", "", False),  # unreadable → never an update
    ],
)
def test_is_newer(latest: str, installed: str, newer: bool) -> None:
    assert is_newer(latest, installed) is newer
