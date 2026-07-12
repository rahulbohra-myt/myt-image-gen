"""Tests for utils/manifest.py read/append helpers."""

import json
from pathlib import Path

from utils.manifest import append_entry, normalize_path, read_entries


def test_read_entries_missing_file_returns_empty_list(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    assert read_entries(manifest_path) == []


def test_append_entry_creates_file_and_appends(tmp_path):
    manifest_path = tmp_path / "output" / "manifest.json"
    append_entry(manifest_path, {"id": "1"})
    append_entry(manifest_path, {"id": "2"})

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert entries == [{"id": "1"}, {"id": "2"}]


def test_append_entry_never_overwrites_existing_entries(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    append_entry(manifest_path, {"id": "1"})
    append_entry(manifest_path, {"id": "2"})

    entries = read_entries(manifest_path)
    assert len(entries) == 2
    assert entries[0] == {"id": "1"}


def test_normalize_path_uses_forward_slashes():
    assert normalize_path(Path("output") / "foo.png") == "output/foo.png"
    assert normalize_path("a\\b\\c.png") == "a/b/c.png"
