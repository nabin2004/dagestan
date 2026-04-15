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
import re
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# LOCOMO JSON from GitHub (snap-research/locomo/data/locomo10.json) uses numeric QA categories.
_LOCOMO_INT_CATEGORY: dict[int, str] = {
    1: "single_hop",
    2: "temporal",
    3: "open_domain",
    4: "multi_hop",
    5: "adversarial",
}

_SESSION_NUM = re.compile(r"^session_(\d+)$")


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
        blob = json.loads(self.local_path.read_text())
        if isinstance(blob, list):
            convs: list[Any] = blob
        elif isinstance(blob, dict):
            convs = blob.get("conversations", blob.get("data"))
            if convs is None:
                list_children = [
                    v for v in blob.values()
                    if isinstance(v, list) and v and isinstance(v[0], dict)
                ]
                convs = list_children[0] if len(list_children) == 1 else []
        else:
            convs = []
        if not isinstance(convs, list):
            raise ValueError(
                f"Expected a JSON list or {{conversations: [...]}} in {self.local_path}"
            )
        return [self._normalise(c, index=i) for i, c in enumerate(convs)]

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
        conversations = [self._normalise_hf_row(row, index=i) for i, row in enumerate(ds)]
        # Cache locally for future runs
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(json.dumps(conversations, indent=2))
        log.info("Cached LOCOMO to %s", self.local_path)
        return conversations

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    def _normalise(self, raw: dict, *, index: int = 0) -> dict:
        """Normalise a locally-stored conversation dict."""
        if not isinstance(raw, dict):
            return {
                "id": f"invalid_{index}",
                "sessions": [],
                "qa_pairs": [],
                "event_summaries": [],
                "personas": {},
            }
        if self._is_snap_github_locomo(raw):
            return self._normalise_snap_github_locomo(raw, index=index)
        # Handle different schema versions
        sessions = raw.get("sessions") or self._extract_sessions_from_turns(raw)
        return {
            "id": str(raw.get("id", raw.get("conversation_id", f"conv_{index}"))),
            "sessions": sessions,
            "qa_pairs": self._normalise_qa(
                raw.get("qa_pairs", raw.get("qas", raw.get("qa", [])))
            ),
            "event_summaries": self._normalise_summaries(
                raw.get("event_summaries", raw.get("event_graphs", []))
            ),
            "personas": raw.get("personas", {}),
        }

    def _is_snap_github_locomo(self, raw: dict) -> bool:
        """True for locomo10.json from github.com/snap-research/locomo (data/)."""
        conv = raw.get("conversation")
        if not isinstance(conv, dict):
            return False
        return any(_SESSION_NUM.match(k) for k in conv)

    def _normalise_snap_github_locomo(self, raw: dict, *, index: int) -> dict:
        """Map snap-research GitHub LOCOMO JSON into the eval harness schema."""
        conv = raw["conversation"]
        speaker_a = str(conv.get("speaker_a", "speaker_a"))
        speaker_b = str(conv.get("speaker_b", "speaker_b"))

        session_indices: list[int] = []
        for key in conv:
            m = _SESSION_NUM.match(key)
            if m:
                session_indices.append(int(m.group(1)))
        session_indices = sorted(set(session_indices))

        sessions: list[dict[str, Any]] = []
        for sid in session_indices:
            date = str(conv.get(f"session_{sid}_date_time", ""))
            turns_raw = conv.get(f"session_{sid}", [])
            if not isinstance(turns_raw, list):
                continue
            turns: list[dict[str, str]] = []
            for t in turns_raw:
                if not isinstance(t, dict):
                    continue
                text = str(t.get("text", "")).strip()
                cap = t.get("blip_caption") or t.get("query") or ""
                cap_s = str(cap).strip() if cap else ""
                if t.get("img_url") and cap_s:
                    text = f"{text} [image: {cap_s}]".strip()
                turns.append({
                    "speaker": str(t.get("speaker", "?")),
                    "text": text,
                    "image_caption": cap_s,
                    "timestamp": str(t.get("dia_id", "")),
                })
            sessions.append({"session_id": sid, "turns": turns, "date": date})

        qa_src = raw.get("qa", raw.get("qa_pairs", []))
        qa_pairs = self._normalise_qa_github(qa_src if isinstance(qa_src, list) else [])

        event_summaries = self._event_summary_github_to_summaries(raw.get("event_summary"))

        cid = raw.get("id") or raw.get("conversation_id")
        if cid is None:
            cid = f"{speaker_a}_{speaker_b}_{index}"

        return {
            "id": str(cid),
            "sessions": sessions,
            "qa_pairs": qa_pairs,
            "event_summaries": event_summaries,
            "personas": {speaker_a: speaker_a, speaker_b: speaker_b},
        }

    def _normalise_qa_github(self, raw_qas: list[dict]) -> list[dict]:
        out: list[dict] = []
        for qa in raw_qas:
            if not isinstance(qa, dict):
                continue
            cat = qa.get("category", "single_hop")
            if isinstance(cat, int):
                cat = _LOCOMO_INT_CATEGORY.get(cat, "single_hop")
            else:
                cat = str(cat)
            ans = qa.get("answer", qa.get("ground_truth", qa.get("adversarial_answer", "")))
            if isinstance(ans, (int, float)):
                ans = str(ans)
            else:
                ans = str(ans or "")
            out.append({
                "question": str(qa.get("question", qa.get("q", ""))),
                "answer": ans,
                "category": cat,
                "turn_ids": qa.get("turn_ids", qa.get("evidence", qa.get("evidence_turn_ids", []))),
            })
        return out

    def _event_summary_github_to_summaries(
        self, event_summary: Any,
    ) -> list[dict]:
        if not isinstance(event_summary, dict):
            return []
        out: list[dict] = []
        for key, block in event_summary.items():
            if not key.startswith("events_session_") or not isinstance(block, dict):
                continue
            date = str(block.get("date", ""))
            events: list[str] = []
            speaker = "mixed"
            for spk, evs in block.items():
                if spk == "date":
                    continue
                if isinstance(evs, list):
                    if evs and not events:
                        speaker = str(spk)
                    for e in evs:
                        if isinstance(e, str) and e.strip():
                            events.append(e.strip())
            if events:
                out.append({
                    "timeframe": {"start": date or None, "end": date or None},
                    "events": events,
                    "speaker": speaker,
                })
        return out

    def _normalise_hf_row(self, row: dict, *, index: int = 0) -> dict:
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
            "id": str(row.get("id", row.get("conv_id", f"conv_{index}"))),
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

    def _normalise_summaries(self, raw: list) -> list[dict]:
        """
        LOCOMO event graphs are per-speaker event lists.
        We convert them into timeframe-scoped summary tasks.
        """
        normalised = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            # Hand-authored / smoke format: events are plain strings
            if "events" in item and isinstance(item.get("events"), list):
                evs = item["events"]
                if evs and all(isinstance(x, str) for x in evs):
                    tf = item.get("timeframe") or {"start": None, "end": None}
                    normalised.append({
                        "timeframe": tf if isinstance(tf, dict) else {"start": None, "end": None},
                        "events": list(evs),
                        "speaker": str(item.get("speaker", "unknown")),
                    })
                    continue
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
                    "events": [
                        e.get("event", str(e)) if isinstance(e, dict) else str(e)
                        for e in events
                    ],
                    "speaker": speaker,
                })
                break
            else:
                continue

            if events:
                dates = [
                    e["date"] for e in events
                    if isinstance(e, dict) and e.get("date")
                ]
                normalised.append({
                    "timeframe": {
                        "start": min(dates) if dates else None,
                        "end": max(dates) if dates else None,
                    },
                    "events": [
                        e.get("event", str(e)) if isinstance(e, dict) else str(e)
                        for e in events
                    ],
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
