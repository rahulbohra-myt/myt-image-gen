"""Read/write helpers for output/manifest.json — the durable log of every generate() call."""

import json
from pathlib import Path


def normalize_path(path: Path | str) -> str:
    """Convert a path to a forward-slash string regardless of host OS, for manifest storage."""
    return str(path).replace("\\", "/")


def read_entries(manifest_path: Path) -> list[dict]:
    """Load the manifest array, returning an empty list if the file doesn't exist yet."""
    if not manifest_path.exists():
        return []
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_entry(manifest_path: Path, entry: dict) -> None:
    """Append one generation record to the manifest — never overwrites existing entries."""
    entries = read_entries(manifest_path)
    entries.append(entry)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
