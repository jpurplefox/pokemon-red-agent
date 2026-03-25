"""File-based JSON persistence adapter.

Satisfies the JSONStore protocol: load() → list, save(data) → None.
"""

import json
from pathlib import Path


class FileJSONStore:
    """Persists a list of dicts to a JSON file on disk."""

    def __init__(self, path: str):
        self._path = Path(path)

    def load(self) -> list:
        """Load data from the JSON file, or return empty list if missing."""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, data: list) -> None:
        """Write data to the JSON file."""
        self._path.write_text(json.dumps(data, indent=2))
