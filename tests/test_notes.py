"""Tests for the notes file and how notes and brew descriptions land on nodes."""

from freshenup.cli import annotate
from freshenup.models import Item, Kind, Node
from freshenup.notes import Note, parse_notes
from freshenup.parse import parse_descriptions
from freshenup.pick import render_preview


def _node(name: str) -> Node:
    return Node(kind=Kind.FORMULA, name=name, itself=Item(Kind.FORMULA, name, "1", "2"))


def test_parse_notes_reads_what_and_why() -> None:
    notes = parse_notes('[coreutils]\nwhy = "timeout"\n\n["npm:x"]\nwhat = "X CLI"\nwhy = "mise"\n')
    assert notes == {"coreutils": Note(why="timeout"), "npm:x": Note(what="X CLI", why="mise")}


def test_parse_descriptions_covers_formulae_and_casks() -> None:
    text = (
        '{"formulae": [{"full_name": "tap/yta", "desc": "YouTube audio"}],'
        ' "casks": [{"token": "vlc", "desc": "Media player"}]}'
    )
    assert parse_descriptions(text) == {"tap/yta": "YouTube audio", "vlc": "Media player"}


def test_annotate_prefers_note_what_over_brew_description() -> None:
    notes = {"go": Note(why="toolchain"), "uv": Note(what="mine", why="tools")}
    go, uv, jq = annotate([_node("go"), _node("uv"), _node("jq")], notes, {"go": "Go", "uv": "uv"})
    assert (go.what, go.why) == ("Go", "toolchain")
    assert (uv.what, uv.why) == ("mine", "tools")
    assert (jq.what, jq.why) == ("", "")


def test_preview_shows_what_and_why_separately() -> None:
    lines = render_preview(Node(kind=Kind.FORMULA, name="go", what="Go", why="toolchain"))
    assert "What: Go" in lines and "Why:  toolchain" in lines
    assert "no note" in render_preview(_node("jq"))
