"""
Dagestan — Temporal Graph Memory Layer for LLMs.

A structured memory system that stores knowledge as a typed temporal graph,
not a flat vector store. Supports contradiction detection, temporal decay,
gap analysis, and relationship-aware retrieval.

Quick start:
    from dagestan import Dagestan

    mem = Dagestan(provider="openai")
    mem.ingest("User said they love coffee and want to build a startup.")
    context = mem.retrieve("What does the user care about?")
    print(context)
"""

from __future__ import annotations

__version__ = "0.1.0"

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .curation.curator import Curator, CurationReport
from .curation.strategy import generate_strategy, strategy_to_prompt
from .extraction.extractor import ConversationExtractor, LLMClient
from .graph.operations import (
    apply_decay,
    compute_centrality,
    detect_bridges,
    detect_contradictions,
    detect_gaps,
)
from .graph.schema import DEFAULT_DECAY_RATES, Edge, EdgeType, Node, NodeType
from .graph.temporal_graph import TemporalGraph
from .retrieval.retriever import RetrievalResult, Retriever
from .storage.store import get_storage

logger = logging.getLogger(__name__)


class Dagestan:
    """
    Main interface to the Dagestan memory system.

    Wraps all components behind a clean, minimal API:
    - ingest(conversation) — extract knowledge from conversation text
    - retrieve(query) — get relevant context from the graph
    - curate() — run maintenance operations (decay, contradiction, gaps)
    - snapshot() — save current graph state
    - strategy() — generate structured context summary
    """

    def __init__(
        self,
        storage: str = "json",
        db_path: str = "./dagestan_memory.json",
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        llm_client: LLMClient | None = None,
        auto_save: bool = True,
    ) -> None:
        """
        Args:
            storage: Backend type — "json" for v0.1.
            db_path: Path for the storage file.
            provider: LLM provider — "openai" or "anthropic".
            api_key: API key for the LLM provider.
            model: Model name override.
            llm_client: Custom LLM callable — overrides provider/api_key/model.
            auto_save: Whether to save after ingest/curate operations.
        """
        # Storage
        self._storage = get_storage(backend=storage, db_path=db_path)
        self._auto_save = auto_save

        # Graph
        self._graph = TemporalGraph()
        if self._storage.exists():
            self._storage.load(self._graph)
            logger.info(
                f"Loaded existing graph: {self._graph.node_count} nodes, "
                f"{self._graph.edge_count} edges"
            )

        # Extraction (requires LLM)
        self._extractor: ConversationExtractor | None = None
        if llm_client is not None or provider is not None:
            self._extractor = ConversationExtractor(
                llm_client=llm_client,
                provider=provider,
                api_key=api_key,
                model=model,
            )

        # Curation (LLM optional — works in flag-only mode without it)
        effective_llm = llm_client
        if effective_llm is None and provider is not None:
            # Reuse the extractor's LLM client for curation
            if self._extractor is not None:
                effective_llm = self._extractor._llm
        self._curator = Curator(llm_client=effective_llm)

        # Retrieval
        self._retriever = Retriever()

    # ── Core API ────────────────────────────────────────────────────

    def ingest(
        self,
        conversation: str | list[dict[str, str]],
        source: str = "",
    ) -> tuple[int, int]:
        """
        Extract knowledge from a conversation and add it to the graph.

        Args:
            conversation: Plain text or list of {"role": ..., "content": ...}.
            source: Optional tag for this ingestion (e.g., session ID).

        Returns:
            Tuple of (nodes_added, edges_added).

        Raises:
            RuntimeError: If no LLM client is configured.
        """
        if self._extractor is None:
            raise RuntimeError(
                "No LLM client configured. Provide provider or llm_client to use ingest()."
            )

        if source:
            self._extractor._source_tag = source

        nodes, edges = self._extractor.extract(conversation)

        # Add to graph, handling duplicates by label
        nodes_added = 0
        for node in nodes:
            # Check for existing node with same label and type
            existing = [
                n for n in self._graph.get_nodes_by_label(node.label)
                if n.type == node.type
            ]
            if existing:
                # Reinforce existing node instead of duplicating
                existing[0].reinforce()
                logger.debug(f"Reinforced existing node: {existing[0].label}")
            else:
                self._graph.add_node(node)
                nodes_added += 1

        edges_added = 0
        for edge in edges:
            try:
                self._graph.add_edge(edge)
                edges_added += 1
            except ValueError as e:
                logger.debug(f"Skipped edge: {e}")

        logger.info(f"Ingested: {nodes_added} new nodes, {edges_added} new edges")

        if self._auto_save:
            self.save()

        return nodes_added, edges_added

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        as_text: bool = True,
    ) -> str | list[RetrievalResult]:
        """
        Retrieve relevant context from the knowledge graph.

        Args:
            query: Natural language query.
            top_k: Maximum number of results.
            as_text: If True, return formatted text. If False, return result objects.

        Returns:
            Formatted text string or list of RetrievalResult.
        """
        if as_text:
            return self._retriever.retrieve_as_text(self._graph, query, top_k)
        return self._retriever.retrieve(self._graph, query, top_k)

    def curate(
        self,
        current_time: datetime | None = None,
    ) -> CurationReport:
        """
        Run the curation pipeline: decay → contradictions → gaps → bridges.

        Modifies the graph in place. Returns a report.
        """
        report = self._curator.run_curation(self._graph, current_time=current_time)

        if self._auto_save:
            self.save()

        return report

    def strategy(self, top_k: int = 15, as_text: bool = True) -> str | dict[str, Any]:
        """
        Generate a context strategy from the current graph state.

        Args:
            top_k: Max items per category.
            as_text: If True, return prompt-ready text. If False, return dict.
        """
        strat = generate_strategy(self._graph, top_k=top_k)
        if as_text:
            return strategy_to_prompt(strat)
        return strat

    # ── Persistence ─────────────────────────────────────────────────

    def save(self) -> None:
        """Save the current graph state to storage."""
        self._storage.save(self._graph)

    def snapshot(self) -> dict[str, Any]:
        """Get a full serialized snapshot of the current graph."""
        return self._graph.snapshot()

    def load(self) -> None:
        """Reload graph from storage."""
        self._storage.load(self._graph)

    # ── Direct graph access (for advanced use) ──────────────────────

    @property
    def graph(self) -> TemporalGraph:
        """Direct access to the underlying temporal graph."""
        return self._graph

    @property
    def node_count(self) -> int:
        return self._graph.node_count

    @property
    def edge_count(self) -> int:
        return self._graph.edge_count

    def add_node(self, node: Node) -> Node:
        """Add a node directly to the graph."""
        result = self._graph.add_node(node)
        if self._auto_save:
            self.save()
        return result

    def add_edge(self, edge: Edge) -> Edge:
        """Add an edge directly to the graph."""
        result = self._graph.add_edge(edge)
        if self._auto_save:
            self.save()
        return result

    # ── Dunder ──────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Dagestan(nodes={self._graph.node_count}, "
            f"edges={self._graph.edge_count})"
        )

    def __len__(self) -> int:
        return self._graph.node_count
