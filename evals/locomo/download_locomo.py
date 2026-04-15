"""
evals/locomo/download_locomo.py
================================
Download and cache the LOCOMO dataset from GitHub (snap-research/locomo).

Usage:
  python evals/locomo/download_locomo.py

Requires:
  (no extra deps)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

# Allow `uv run evals/locomo/download_locomo.py` without PYTHONPATH=.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent / "locomo_dataset.json"

# Source repo: https://github.com/snap-research/locomo/tree/main/data
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/snap-research/locomo/main/data"
DEFAULT_SOURCE_FILES = [
    "locomo10.json",
]


def _http_get_json(url: str) -> object:
    req = Request(url, headers={"User-Agent": "dagestan-locomo-downloader"})
    with urlopen(req, timeout=60) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def download(*, force: bool = False) -> None:
    if OUTPUT_PATH.exists() and not force:
        log.info("LOCOMO already present at %s", OUTPUT_PATH)
        log.info("Use --force to replace it with a fresh download from GitHub.")
        return

    log.info("Downloading LOCOMO from GitHub (raw): %s", GITHUB_RAW_BASE)

    # Convert to our normalised internal format.
    # We reuse the loader's local normalisation for compatibility with the eval runner.
    from evals.scripts.data_loader import LocomoDataLoader
    loader = LocomoDataLoader(str(OUTPUT_PATH))

    conversations: list[dict] = []
    for fname in DEFAULT_SOURCE_FILES:
        url = f"{GITHUB_RAW_BASE}/{fname}"
        log.info("Fetching %s", url)
        try:
            raw = _http_get_json(url)
        except HTTPError as e:
            raise RuntimeError(f"HTTP error fetching {url}: {e.code} {e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e

        # The repo may store either:
        # - {"conversations": [...]} envelope, or
        # - a bare list of conversations.
        if isinstance(raw, dict):
            raw_convs = raw.get("conversations") or raw.get("data")
        else:
            raw_convs = raw

        if not isinstance(raw_convs, list):
            raise RuntimeError(f"Unexpected JSON schema in {fname}: expected list")

        base = len(conversations)
        conversations.extend(
            loader._normalise(c, index=base + i)
            for i, c in enumerate(raw_convs)
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"conversations": conversations}, indent=2))
    log.info("Saved %d conversations → %s", len(conversations), OUTPUT_PATH)
    log.info("File size: %.1f MB", OUTPUT_PATH.stat().st_size / 1e6)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Download LOCOMO JSON from snap-research/locomo (GitHub).")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite %s even if it already exists." % OUTPUT_PATH.name,
    )
    args = p.parse_args()
    download(force=args.force)
