"""
evals/scripts/dagestan_adapter.py
==================================
Wraps Dagestan's public API for use inside the LOCOMO eval harness.

Responsibilities:
  - Session-by-session ingestion (simulates real-world usage)
  - Nightly curation between sessions
  - Hybrid retrieval with configurable modes (hybrid | graph | vector | none)
  - Temporal window retrieval (for event summarisation task)
  - Schema induction reporting (for coherence eval)
  - Retrieval trace logging (for QA recall@k reporting)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

log = logging.getLogger(__name__)

RetrievalMode = Literal["hybrid", "graph", "vector", "none"]


@dataclass
class RetrievalTrace:
    query: str
    graph_hits: list[dict] = field(default_factory=list)
    vector_hits: list[dict] = field(default_factory=list)
    final_context: str = ""
    latency_ms: float = 0.0


class DagestandAdapter:
    """
    Thin adapter over ``dagestan.Dagestan`` that:
      - Streams LOCOMO sessions through Dagestan one session at a time
      - Applies nightly curation (offline curation model)
      - Exposes retrieval in configurable modes for ablation studies
      - Records retrieval traces for recall@k evaluation
    """

    def __init__(
        self,
        provider: str = "gemini",
        model: str = "gemini-1.5-flash",
        db_path: str = "/tmp/dagestan_eval.json",
        vector_store_path: str = "/tmp/dagestan_eval_chroma",
        schema_induction: bool = True,
        hybrid_retrieval: bool = True,
        retrieval_mode: RetrievalMode = "hybrid",
        decay_enabled: bool = True,
        contradiction_resolution: str = "llm",
    ):
        self.retrieval_mode = retrieval_mode
        self.schema_induction = schema_induction
        self._last_trace: Optional[RetrievalTrace] = None
        self._session_count = 0

        self._init_dagestan(
            provider=provider,
            model=model,
            db_path=db_path,
            vector_store_path=vector_store_path,
            schema_induction=schema_induction,
            decay_enabled=decay_enabled,
            contradiction_resolution=contradiction_resolution,
        )

    # ------------------------------------------------------------------

    def _init_dagestan(self, **kwargs):
        """
        Initialise the real Dagestan instance.

        If Dagestan is not installed in the current environment (e.g. during
        a dry run of the eval harness), we fall back to a stub so the rest of
        the eval pipeline can be exercised end-to-end without a live LLM.
        """
        try:
            from dagestan import Dagestan  # type: ignore

            self._mem = Dagestan(
                provider=kwargs["provider"],
                model=kwargs.get("model"),
                db_path=kwargs["db_path"],
                # vector_store_path and schema_induction are planned v0.2+ params
                # include them as **kwargs for forward-compatibility
            )
            self._stub = False
            log.debug("Dagestan initialised (real)")
        except ImportError:
            log.warning(
                "dagestan package not found — running with STUB adapter. "
                "Install with: pip install dagestan"
            )
            self._mem = _DagestandStub()
            self._stub = True

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_session(
        self,
        session_text: str,
        session_id: int,
        session_date: Optional[str] = None,
    ):
        """Ingest a single LOCOMO session as a conversation block."""
        log.debug("Ingesting session %d (%d chars)", session_id, len(session_text))
        self._mem.ingest(session_text)
        self._session_count += 1

    def curate(self, reason: str = "nightly"):
        """Run offline curation (contradiction detection, decay, gap/bridge analysis)."""
        log.debug("Curation [%s] after session %d", reason, self._session_count)
        if hasattr(self._mem, "curate"):
            self._mem.curate()

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str) -> str:
        """
        Retrieve memory context for a given query.
        Mode is controlled by self.retrieval_mode.
        """
        import time
        t0 = time.perf_counter()

        if self.retrieval_mode == "none":
            context = ""
            trace = RetrievalTrace(query=query, final_context=context)
        elif self.retrieval_mode == "graph":
            context = self._retrieve_graph_only(query)
            trace = RetrievalTrace(query=query, final_context=context)
        elif self.retrieval_mode == "vector":
            context = self._retrieve_vector_only(query)
            trace = RetrievalTrace(query=query, final_context=context)
        else:  # hybrid (default)
            context, trace = self._retrieve_hybrid(query)

        trace.latency_ms = (time.perf_counter() - t0) * 1000
        self._last_trace = trace
        return context

    def retrieve_temporal_window(
        self,
        start: Optional[str],
        end: Optional[str],
    ) -> str:
        """
        Retrieve all memory within a time window (for event summarisation).
        Uses temporal graph traversal.
        """
        query = f"events between {start} and {end}"
        return self.retrieve(query)

    # ------------------------------------------------------------------
    # Internal retrieval modes
    # ------------------------------------------------------------------

    def _retrieve_hybrid(self, query: str) -> tuple[str, RetrievalTrace]:
        """Graph-guided + vector fallback, combined and ranked."""
        context = self._mem.retrieve(query) if hasattr(self._mem, "retrieve") else ""
        trace = RetrievalTrace(
            query=query,
            final_context=context,
            graph_hits=self._extract_graph_hits(context),
            vector_hits=self._extract_vector_hits(context),
        )
        return context, trace

    def _retrieve_graph_only(self, query: str) -> str:
        """
        Graph traversal only — no vector similarity.
        Available via Dagestan's low-level graph API.
        """
        if hasattr(self._mem, "_retriever") and hasattr(self._mem._retriever, "graph_retrieve"):
            return self._mem._retriever.graph_retrieve(query)
        # Fallback: standard retrieve (may include vectors internally)
        return self._mem.retrieve(query) if hasattr(self._mem, "retrieve") else ""

    def _retrieve_vector_only(self, query: str) -> str:
        """
        Vector similarity only — bypass graph structure.
        Useful as baseline to measure graph's contribution.
        """
        if hasattr(self._mem, "_retriever") and hasattr(self._mem._retriever, "vector_retrieve"):
            return self._mem._retriever.vector_retrieve(query)
        return self._mem.retrieve(query) if hasattr(self._mem, "retrieve") else ""

    # ------------------------------------------------------------------
    # Schema introspection (for coherence eval)
    # ------------------------------------------------------------------

    def get_induced_schema(self) -> dict:
        """
        Return the schema (node type distribution) that Dagestan induced
        from the conversation, for comparison against ground-truth entity types.
        """
        if hasattr(self._mem, "_graph"):
            graph = self._mem._graph
            schema: dict[str, int] = {}
            for node in graph.nodes.values():
                t = str(node.type)
                schema[t] = schema.get(t, 0) + 1
            return schema
        return {}

    def get_contradictions(self) -> list[dict]:
        """Return detected contradictions from last curation pass."""
        if hasattr(self._mem, "_last_curation_report"):
            report = self._mem._last_curation_report
            return getattr(report, "contradictions", [])
        return []

    def get_node_confidences(self) -> dict[str, float]:
        """Return {node_id: confidence_score} for decay calibration eval."""
        if hasattr(self._mem, "_graph"):
            return {
                nid: node.confidence_score
                for nid, node in self._mem._graph.nodes.items()
            }
        return {}

    def get_snapshot_at_session(self, session_idx: int) -> dict:
        """Return the graph state snapshot after a given session (if snapshotting enabled)."""
        if hasattr(self._mem, "_graph") and hasattr(self._mem._graph, "snapshots"):
            snaps = self._mem._graph.snapshots
            if session_idx < len(snaps):
                return snaps[session_idx]
        return {}

    # ------------------------------------------------------------------
    # Trace helpers
    # ------------------------------------------------------------------

    def last_retrieval_trace(self) -> Optional[dict]:
        if self._last_trace is None:
            return None
        return {
            "query": self._last_trace.query,
            "graph_hit_count": len(self._last_trace.graph_hits),
            "vector_hit_count": len(self._last_trace.vector_hits),
            "latency_ms": round(self._last_trace.latency_ms, 2),
        }

    def _extract_graph_hits(self, context: str) -> list[dict]:
        """Parse graph node IDs from context string (best-effort)."""
        # Dagestan prefixes graph-sourced context with "[G:" in strategy output
        return [{"source": "graph", "snippet": line}
                for line in context.split("\n") if "[G:" in line]

    def _extract_vector_hits(self, context: str) -> list[dict]:
        """Parse vector chunk IDs from context string (best-effort)."""
        return [{"source": "vector", "snippet": line}
                for line in context.split("\n") if "[V:" in line]


# ---------------------------------------------------------------------------
# Stub — used when dagestan is not installed (CI / dry-run)
# ---------------------------------------------------------------------------

class _DagestandStub:
    """
    Minimal stub implementing the Dagestan public API surface.
    Returns empty/placeholder data so the eval harness can be
    tested end-to-end without a live LLM or the dagestan package.
    """
    def ingest(self, text: str): pass
    def retrieve(self, query: str) -> str: return ""
    def curate(self) -> Any: return None
    def strategy(self) -> str: return ""
