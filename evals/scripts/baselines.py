"""
evals/scripts/baselines.py
===========================
Baseline memory systems for comparison against Dagestan.

Baselines:
  1. NoMemory         — no retrieval, just the last N turns in context
  2. FlatRAG          — naive chunk embedding + cosine similarity (ChromaDB)
  3. SessionSummary   — incremental session summarisation (like LOCOMO paper)
  4. ObservationRAG   — assertions extracted from conversation (LOCOMO best baseline)

These implement the same .ingest_session() / .retrieve() / .curate() interface
as DagestandAdapter so they can be dropped into the eval runner with --baseline.
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


class BaselineAdapter:
    """Factory for baseline adapters."""

    @staticmethod
    def build(name: str, **kwargs) -> "BaselineAdapter":
        baselines = {
            "no_memory": NoMemoryBaseline,
            "flat_rag": FlatRAGBaseline,
            "session_summary": SessionSummaryBaseline,
            "observation_rag": ObservationRAGBaseline,
        }
        if name not in baselines:
            raise ValueError(f"Unknown baseline: {name}. Choose from {list(baselines)}")
        return baselines[name](**kwargs)


# ---------------------------------------------------------------------------

class NoMemoryBaseline:
    """
    No persistent memory — only the most recent N turns are available.
    Equivalent to LOCOMO's 'Base LLM with truncated context'.
    """

    def __init__(self, window_size: int = 20, **kwargs):
        self.window_size = window_size
        self._recent_turns: list[str] = []

    def ingest_session(self, session_text: str, session_id: int, **kwargs):
        lines = session_text.split("\n")
        self._recent_turns.extend(lines)
        self._recent_turns = self._recent_turns[-self.window_size:]

    def retrieve(self, query: str) -> str:
        return "\n".join(self._recent_turns)

    def retrieve_temporal_window(self, start, end) -> str:
        return self.retrieve("")

    def curate(self, **kwargs): pass
    def last_retrieval_trace(self) -> Optional[dict]: return None
    def get_induced_schema(self) -> dict: return {}
    def get_contradictions(self) -> list: return []
    def get_node_confidences(self) -> dict: return {}
    def get_snapshot_at_session(self, idx: int) -> dict: return {}


# ---------------------------------------------------------------------------

class FlatRAGBaseline:
    """
    Flat vector retrieval baseline.
    Embeds conversation chunks with sentence-transformers, retrieves by cosine sim.
    No graph, no temporal awareness, no contradiction detection.
    """

    def __init__(self, embed_model: str = "all-MiniLM-L6-v2",
                 top_k: int = 5, **kwargs):
        self.top_k = top_k
        self._chunks: list[str] = []
        self._embeddings = None
        self._embed_model_name = embed_model
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self._model = SentenceTransformer(self._embed_model_name)
            except ImportError:
                raise RuntimeError("pip install sentence-transformers")
        return self._model

    def ingest_session(self, session_text: str, session_id: int, **kwargs):
        # Chunk by sentence (~3 sentences each)
        sentences = [s.strip() for s in session_text.split(".") if s.strip()]
        for i in range(0, len(sentences), 3):
            chunk = ". ".join(sentences[i:i+3])
            if chunk:
                self._chunks.append(chunk)
        # Invalidate cached embeddings
        self._embeddings = None

    def retrieve(self, query: str) -> str:
        if not self._chunks:
            return ""
        try:
            import numpy as np  # type: ignore
            model = self._get_model()
            if self._embeddings is None:
                self._embeddings = model.encode(self._chunks)
            q_emb = model.encode([query])
            scores = np.dot(self._embeddings, q_emb.T).squeeze()
            top_idx = np.argsort(scores)[-self.top_k:][::-1]
            return "\n".join(self._chunks[i] for i in top_idx)
        except Exception as e:
            log.warning("FlatRAG retrieval failed: %s", e)
            return "\n".join(self._chunks[-self.top_k:])

    def retrieve_temporal_window(self, start, end) -> str:
        return self.retrieve(f"events between {start} and {end}")

    def curate(self, **kwargs): pass
    def last_retrieval_trace(self) -> Optional[dict]: return None
    def get_induced_schema(self) -> dict: return {}
    def get_contradictions(self) -> list: return []
    def get_node_confidences(self) -> dict: return {}
    def get_snapshot_at_session(self, idx: int) -> dict: return {}


# ---------------------------------------------------------------------------

class SessionSummaryBaseline:
    """
    Incremental session summarisation baseline.
    Mirrors the 'summary RAG' approach in the LOCOMO paper.
    """

    def __init__(self, provider: str = "gemini", model: str = "gemini-1.5-flash",
                 **kwargs):
        from evals.scripts.qa_eval import _build_llm_client
        self._client = _build_llm_client(provider, model)
        self._summaries: list[str] = []
        self._running_summary: str = ""

    def ingest_session(self, session_text: str, session_id: int, **kwargs):
        try:
            prompt = (
                f"Previous summary: {self._running_summary}\n\n"
                f"New conversation:\n{session_text}\n\n"
                "Update the summary to include key facts from the new conversation. "
                "Be concise. Include time references where mentioned."
            )
            self._running_summary = self._client.complete(
                system="You are a concise conversation summariser.",
                user=prompt,
            )
            self._summaries.append(self._running_summary)
        except Exception as e:
            log.warning("Session summarisation failed: %s", e)

    def retrieve(self, query: str) -> str:
        return self._running_summary

    def retrieve_temporal_window(self, start, end) -> str:
        return self._running_summary

    def curate(self, **kwargs): pass
    def last_retrieval_trace(self) -> Optional[dict]: return None
    def get_induced_schema(self) -> dict: return {}
    def get_contradictions(self) -> list: return []
    def get_node_confidences(self) -> dict: return {}
    def get_snapshot_at_session(self, idx: int) -> dict:
        if idx < len(self._summaries):
            return {"summary": self._summaries[idx]}
        return {}


# ---------------------------------------------------------------------------

class ObservationRAGBaseline:
    """
    Observation (assertion) RAG baseline.
    Best-performing RAG variant in the LOCOMO paper.
    Extracts factual assertions per speaker, retrieves by keyword match.
    """

    def __init__(self, provider: str = "gemini", model: str = "gemini-1.5-flash",
                 top_k: int = 10, **kwargs):
        from evals.scripts.qa_eval import _build_llm_client
        self._client = _build_llm_client(provider, model)
        self._observations: list[str] = []
        self.top_k = top_k

    def ingest_session(self, session_text: str, session_id: int, **kwargs):
        try:
            obs = self._client.complete(
                system=(
                    "Extract a concise list of factual observations about each speaker "
                    "from the conversation. One observation per line. "
                    "Format: '<Speaker>: <fact>'. Be specific and objective."
                ),
                user=session_text,
            )
            for line in obs.split("\n"):
                if line.strip():
                    self._observations.append(line.strip())
        except Exception as e:
            log.warning("Observation extraction failed: %s", e)

    def retrieve(self, query: str) -> str:
        if not self._observations:
            return ""
        query_tokens = set(query.lower().split())
        scored = []
        for obs in self._observations:
            obs_tokens = set(obs.lower().split())
            overlap = len(query_tokens & obs_tokens)
            scored.append((overlap, obs))
        scored.sort(reverse=True)
        top = [obs for _, obs in scored[:self.top_k]]
        return "\n".join(top)

    def retrieve_temporal_window(self, start, end) -> str:
        return self.retrieve(f"events {start} {end}")

    def curate(self, **kwargs): pass
    def last_retrieval_trace(self) -> Optional[dict]: return None
    def get_induced_schema(self) -> dict: return {}
    def get_contradictions(self) -> list: return []
    def get_node_confidences(self) -> dict: return {}
    def get_snapshot_at_session(self, idx: int) -> dict: return {}
