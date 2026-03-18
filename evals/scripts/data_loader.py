"""
evals/scripts/data_loader.py
============================
Loads the LOCOMO benchmark dataset.

LOCOMO (Maharana et al., 2024) is hosted on HuggingFace:
  https://huggingface.co/datasets/snap-research/locomo

Dataset structure (per conversation):
  - id: str
  - sessions: list of sessions, each with turns
    - turns: [{speaker, text, image_caption?, timestamp}]
    - date: str
  - qa_pairs: [{question, answer, category, turn_ids}]
  - event_summaries: [{timeframe, events}]
  - personas: {speaker_1: str, speaker_2: str}

This loader normalises the HuggingFace format into the internal
representation expected by the eval runner.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class LocomoDataLoader:
    """
    Load LOCOMO from:
      1. A local JSON file (pre-downloaded, normalised format)
      2. HuggingFace datasets hub (auto-download if `datasets` is available)
    """

    HF_DATASET_ID = "snap-research/locomo"

    def __init__(self, local_path: str = "evals/locomo/locomo_dataset.json"):
        self.local_path = Path(local_path)

    # ------------------------------------------------------------------

    def load(
        self,
        limit: Optional[int] = None,
        ids: Optional[list[str]] = None,
        split: str = "test",
    ) -> list[dict]:
        """Return a list of normalised conversation dicts."""
        if self.local_path.exists():
            log.info("Loading LOCOMO from local file: %s", self.local_path)
            conversations = self._load_local()
        else:
            log.info("Local file not found — attempting HuggingFace download")
            conversations = self._load_hf(split=split)

        if ids:
            conversations = [c for c in conversations if c["id"] in ids]

        if limit is not None:
            conversations = conversations[:limit]

        log.info("Using %d conversations", len(conversations))
        return conversations

    # ------------------------------------------------------------------

    def _load_local(self) -> list[dict]:
        raw = json.loads(self.local_path.read_text())
        # Support both {conversations: [...]} envelope and bare list
        if isinstance(raw, dict):
            raw = raw.get("conversations", raw.get("data", list(raw.values())[0]))
        return [self._normalise(c) for c in raw]

    def _load_hf(self, split: str = "test") -> list[dict]:
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError:
            raise RuntimeError(
                "HuggingFace `datasets` package not installed.\n"
                "Run: pip install datasets\n"
                "Or download LOCOMO manually and place it at:\n"
                f"  {self.local_path}"
            )

        ds = load_dataset(self.HF_DATASET_ID, split=split)
        conversations = [self._normalise_hf_row(row) for row in ds]
        # Cache locally for future runs
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(json.dumps(conversations, indent=2))
        log.info("Cached LOCOMO to %s", self.local_path)
        return conversations

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    def _normalise(self, raw: dict) -> dict:
        """Normalise a locally-stored conversation dict."""
        # Handle different schema versions
        sessions = raw.get("sessions") or self._extract_sessions_from_turns(raw)
        return {
            "id": str(raw.get("id", raw.get("conversation_id", "unknown"))),
            "sessions": sessions,
            "qa_pairs": self._normalise_qa(raw.get("qa_pairs", raw.get("qas", []))),
            "event_summaries": self._normalise_summaries(
                raw.get("event_summaries", raw.get("event_graphs", []))
            ),
            "personas": raw.get("personas", {}),
        }

    def _normalise_hf_row(self, row: dict) -> dict:
        """
        Normalise a raw HuggingFace dataset row into our internal format.
        LOCOMO HF schema (as of Feb 2024):
          row["conversation"]      — list of {role, content, session_id, timestamp}
          row["question"]          — list of QA dicts
          row["event_graph"]       — list of event dicts
          row["personas"]          — dict
        """
        # Group turns by session_id
        sessions_map: dict[int, list[dict]] = {}
        for turn in row.get("conversation", []):
            sid = int(turn.get("session_id", 0))
            sessions_map.setdefault(sid, []).append({
                "speaker": turn.get("role", turn.get("speaker", "?")),
                "text": turn.get("content", turn.get("text", "")),
                "image_caption": turn.get("image_caption", ""),
                "timestamp": turn.get("timestamp", ""),
            })

        sessions = [
            {"session_id": sid, "turns": turns, "date": turns[0].get("timestamp", "")}
            for sid, turns in sorted(sessions_map.items())
        ]

        return {
            "id": str(row.get("id", row.get("conv_id", "unknown"))),
            "sessions": sessions,
            "qa_pairs": self._normalise_qa(row.get("question", [])),
            "event_summaries": self._normalise_summaries(row.get("event_graph", [])),
            "personas": row.get("personas", {}),
        }

    def _normalise_qa(self, raw_qas: list[dict]) -> list[dict]:
        normalised = []
        for qa in raw_qas:
            normalised.append({
                "question": qa.get("question", qa.get("q", "")),
                "answer": qa.get("answer", qa.get("a", qa.get("ground_truth", ""))),
                "category": qa.get("category", qa.get("type", "single_hop")),
                "turn_ids": qa.get("turn_ids", qa.get("evidence_turn_ids", [])),
            })
        return normalised

    def _normalise_summaries(self, raw: list[dict]) -> list[dict]:
        """
        LOCOMO event graphs are per-speaker event lists.
        We convert them into timeframe-scoped summary tasks.
        """
        normalised = []
        for item in raw:
            # Handle flat event list vs {speaker: events} dict
            if "events" in item:
                events = item["events"]
                speaker = item.get("speaker", "unknown")
            elif "event" in item:
                # Single event entry — group all into one task
                events = raw
                speaker = item.get("speaker", "unknown")
                normalised.append({
                    "timeframe": {"start": None, "end": None},
                    "events": [e.get("event", str(e)) for e in events],
                    "speaker": speaker,
                })
                break
            else:
                continue

            if events:
                dates = [e.get("date") for e in events if e.get("date")]
                normalised.append({
                    "timeframe": {
                        "start": min(dates) if dates else None,
                        "end": max(dates) if dates else None,
                    },
                    "events": [e.get("event", str(e)) for e in events],
                    "speaker": speaker,
                })
        return normalised

    def _extract_sessions_from_turns(self, raw: dict) -> list[dict]:
        """Fallback: build sessions from a flat turns list using session_id field."""
        turns = raw.get("turns", raw.get("dialogue", []))
        sessions_map: dict = {}
        for turn in turns:
            sid = turn.get("session_id", 0)
            sessions_map.setdefault(sid, []).append(turn)
        return [
            {"session_id": sid, "turns": t, "date": t[0].get("timestamp", "")}
            for sid, t in sorted(sessions_map.items())
        ]
