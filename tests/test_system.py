"""Spotlight index maintenance: the pure mismatch diff and the fire-and-forget reindex."""

import subprocess

import pytest

from freshenup import system


@pytest.fixture
def popen_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    # Returns None, so any .wait()/.communicate() on the result would raise — the reindex staying
    # fire-and-forget is what keeps these tests passing.
    def fake_popen(args: list[str], **_kwargs: object) -> None:
        calls.append(args)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return calls


def test_unindexed_ignores_firmlink_path_form() -> None:
    # regression: comparing raw paths marks every app missing, since Spotlight reports the
    # /System/Volumes/Data form while the filesystem walk reports the /Applications firmlink
    installed = ["/Applications/WhatsApp.app"]
    indexed = ["/System/Volumes/Data/Applications/WhatsApp.app"]
    assert system.unindexed_apps(installed, indexed) == []


def test_unindexed_reports_missing_app() -> None:
    installed = ["/Applications/WhatsApp.app", "/Applications/MeetingBar.app"]
    indexed = ["/Applications/WhatsApp.app"]
    assert system.unindexed_apps(installed, indexed) == ["/Applications/MeetingBar.app"]


def test_unindexed_with_nothing_indexed_returns_all() -> None:
    installed = ["/Applications/B.app", "/Applications/A.app"]
    assert system.unindexed_apps(installed, []) == ["/Applications/A.app", "/Applications/B.app"]


def test_reindex_skips_when_nothing_missing(popen_calls: list[list[str]]) -> None:
    system.reindex([])
    assert popen_calls == []


def test_reindex_queues_mdimport(popen_calls: list[list[str]]) -> None:
    system.reindex(["/Applications/X.app"])
    assert popen_calls == [["/usr/bin/mdimport", "/Applications/X.app"]]
