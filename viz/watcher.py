"""
viz.watcher
~~~~~~~~~~~

File watcher that monitors graph JSON files for changes.
Uses OS-level stat polling (no dependencies required).
Can be upgraded to use watchdog if available.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable


class FileWatcher:
    """
    Watch a file for changes and invoke callbacks.

    Uses stat-based polling as default (works everywhere).
    Falls back gracefully if file doesn't exist yet.
    """

    def __init__(
        self,
        path: str | Path,
        interval: float = 0.5,
        on_change: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.path = Path(path)
        self.interval = interval
        self.on_change = on_change
        self._last_mtime: float = 0
        self._last_size: int = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start watching in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                if self.path.exists():
                    stat = self.path.stat()
                    if stat.st_mtime != self._last_mtime or stat.st_size != self._last_size:
                        self._last_mtime = stat.st_mtime
                        self._last_size = stat.st_size
                        if self.on_change:
                            try:
                                with open(self.path) as f:
                                    data = json.load(f)
                                self.on_change(data)
                            except (json.JSONDecodeError, OSError):
                                pass
            except OSError:
                pass

            time.sleep(self.interval)

    @property
    def is_running(self) -> bool:
        return self._running
