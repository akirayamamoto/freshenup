"""Fixture-pinned parser tests — every historical bug has a regression case here."""

from pathlib import Path

from freshenup.models import Kind
from freshenup.parse import parse_brew_outdated, parse_mas, parse_mise, parse_receipt

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


def test_mas_parses_and_coerces_id_to_str() -> None:
    items = parse_mas(_read("mas.json"))
    assert items[0].kind is Kind.MAS
    assert items[0].mas_id == "497799835"
    assert (items[0].current, items[0].latest) == ("15.2", "15.3")


def test_mas_missing_version_defaults_empty() -> None:
    by_name = {i.name: i for i in parse_mas(_read("mas.json"))}
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
