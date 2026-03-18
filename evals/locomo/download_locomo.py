"""
evals/locomo/download_locomo.py
================================
Download and cache the LOCOMO dataset from HuggingFace Hub.

Usage:
  python evals/locomo/download_locomo.py

Requires:
  pip install datasets huggingface_hub
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent / "locomo_dataset.json"
HF_DATASET_ID = "snap-research/locomo"


def download():
    if OUTPUT_PATH.exists():
        log.info("LOCOMO already downloaded at %s", OUTPUT_PATH)
        log.info("Delete the file to re-download.")
        return

    log.info("Downloading LOCOMO from HuggingFace: %s", HF_DATASET_ID)

    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        print("Install HuggingFace datasets: pip install datasets")
        raise

    # LOCOMO is released under CC BY-NC 4.0
    ds = load_dataset(HF_DATASET_ID)
    log.info("Dataset splits: %s", list(ds.keys()))

    # Use 'test' split (the evaluation split with QA annotations)
    split = "test" if "test" in ds else list(ds.keys())[0]
    log.info("Using split: %s  (%d conversations)", split, len(ds[split]))

    # Convert to our normalised internal format
    from evals.scripts.data_loader import LocomoDataLoader
    loader = LocomoDataLoader(str(OUTPUT_PATH))
    conversations = [loader._normalise_hf_row(row) for row in ds[split]]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(conversations, indent=2))
    log.info("Saved %d conversations → %s", len(conversations), OUTPUT_PATH)
    log.info("File size: %.1f MB", OUTPUT_PATH.stat().st_size / 1e6)


if __name__ == "__main__":
    download()
