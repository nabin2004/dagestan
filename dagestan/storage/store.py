"""
dagestan.storage.store
~~~~~~~~~~~~~~~~~~~~~~

Persistence backends for the temporal graph.

v0.1: JSON file storage (zero dependencies, easy to inspect).
Future: SQLite (v0.2), Neo4j (v1.0).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..graph.temporal_graph import TemporalGraph


class StorageBackend:
    """Base interface for graph persistence."""

    def save(self, graph: TemporalGraph, **kwargs: Any) -> None:
        raise NotImplementedError

    def load(self, graph: TemporalGraph, **kwargs: Any) -> None:
        raise NotImplementedError

    def exists(self) -> bool:
        raise NotImplementedError


class JSONStorage(StorageBackend):
    """
    JSON file storage backend.

    Stores the complete graph state as a single JSON file.
    Human-readable, zero dependencies, easy to debug.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, graph: TemporalGraph, **kwargs: Any) -> None:
        """Save graph to JSON file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(graph.snapshot(), f, indent=2)

    def load(self, graph: TemporalGraph, **kwargs: Any) -> None:
        """Load graph from JSON file."""
        if not self.path.exists():
            return  # No saved state — start fresh
        with open(self.path) as f:
            data = json.load(f)
        graph.load_snapshot(data)

    def exists(self) -> bool:
        return self.path.exists()


def get_storage(backend: str = "json", **kwargs: Any) -> StorageBackend:
    """
    Factory for storage backends.

    Args:
        backend: "json" (v0.1), "sqlite" (v0.2), "neo4j" (v1.0).
        **kwargs: Backend-specific options (e.g., path, db_path).
    """
    if backend == "json":
        path = kwargs.get("path") or kwargs.get("db_path", "./dagestan_memory.json")
        return JSONStorage(path=path)
    elif backend == "sqlite":
        raise NotImplementedError(
            "SQLite backend is planned for v0.2. Use 'json' for now."
        )
    elif backend == "neo4j":
        raise NotImplementedError(
            "Neo4j backend is planned for v1.0. Use 'json' for now."
        )
    else:
        raise ValueError(f"Unknown storage backend: {backend!r}")
