"""
dagestan.retrieval.retriever
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Query-driven graph traversal for context retrieval.

Unlike vector DB retrieval (similarity search over embeddings),
this does structural traversal: find relevant nodes by matching
query terms against labels/attributes, then expand via graph
relationships weighted by centrality and recency.

v0.1: keyword-based scoring. No embeddings required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..graph.operations import compute_centrality
from ..graph.schema import Node
from ..graph.temporal_graph import TemporalGraph


@dataclass
class RetrievalResult:
    """A single retrieved node with its relevance score."""

    node: Node
    score: float
    reason: str  # Why this node was retrieved

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node.id,
            "type": self.node.type.value,
            "label": self.node.label,
            "confidence": round(self.node.confidence_score, 3),
            "relevance_score": round(self.score, 4),
            "reason": self.reason,
            "attributes": self.node.attributes,
        }


class Retriever:
    """
    Query-driven graph retrieval.

    Scores nodes by a combination of:
    - Query relevance (keyword overlap with label + attributes)
    - Centrality (structural importance in the graph)
    - Confidence (temporal freshness)
    - Neighbor expansion (nodes connected to relevant nodes get a boost)
    """

    def __init__(
        self,
        query_weight: float = 0.4,
        centrality_weight: float = 0.3,
        confidence_weight: float = 0.3,
        neighbor_boost: float = 0.5,
    ) -> None:
        """
        Args:
            query_weight: Weight for keyword match score.
            centrality_weight: Weight for graph centrality.
            confidence_weight: Weight for temporal confidence.
            neighbor_boost: Score multiplier for neighbors of direct matches.
        """
        self.query_weight = query_weight
        self.centrality_weight = centrality_weight
        self.confidence_weight = confidence_weight
        self.neighbor_boost = neighbor_boost

    def retrieve(
        self,
        graph: TemporalGraph,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[RetrievalResult]:
        """
        Retrieve the most relevant nodes for a query.

        Args:
            graph: The temporal graph to search.
            query: Natural language query string.
            top_k: Maximum number of results.
            min_confidence: Exclude nodes below this confidence.

        Returns:
            Sorted list of RetrievalResult, highest score first.
        """
        if graph.node_count == 0:
            return []

        # Precompute centrality scores
        centrality = compute_centrality(graph)

        # Normalize centrality to 0-1
        max_centrality = max(centrality.values()) if centrality else 1.0
        if max_centrality == 0:
            max_centrality = 1.0

        # Tokenize query for keyword matching
        query_tokens = self._tokenize(query)

        if not query_tokens:
            # No meaningful query — return by centrality alone
            results = []
            for node in graph.nodes:
                if node.confidence_score < min_confidence:
                    continue
                c_score = centrality.get(node.id, 0) / max_centrality
                score = c_score * 0.5 + node.confidence_score * 0.5
                results.append(RetrievalResult(
                    node=node,
                    score=score,
                    reason="high centrality (no query terms matched)",
                ))
            results.sort(key=lambda r: r.score, reverse=True)
            return results[:top_k]

        # Phase 1: Score all nodes by direct query relevance
        node_scores: dict[str, float] = {}
        node_reasons: dict[str, str] = {}
        direct_matches: set[str] = set()

        for node in graph.nodes:
            if node.confidence_score < min_confidence:
                continue

            # Keyword match score
            match_score = self._keyword_score(query_tokens, node)

            # Centrality score (normalized)
            c_score = centrality.get(node.id, 0) / max_centrality

            # Confidence as-is (already 0-1)
            conf = node.confidence_score

            # Combined score
            total = (
                self.query_weight * match_score
                + self.centrality_weight * c_score
                + self.confidence_weight * conf
            )

            node_scores[node.id] = total

            if match_score > 0:
                direct_matches.add(node.id)
                node_reasons[node.id] = "direct query match"
            else:
                node_reasons[node.id] = "centrality + confidence"

        # Phase 2: Boost neighbors of direct matches
        for match_id in direct_matches:
            neighbors = graph.neighbors(match_id)
            for neighbor in neighbors:
                if neighbor.id in node_scores and neighbor.id not in direct_matches:
                    old_score = node_scores[neighbor.id]
                    boost = old_score * self.neighbor_boost
                    node_scores[neighbor.id] = old_score + boost
                    node_reasons[neighbor.id] = (
                        f"neighbor of '{graph.get_node(match_id).label}'"  # type: ignore
                        if graph.get_node(match_id)
                        else "neighbor expansion"
                    )

        # Build results
        results: list[RetrievalResult] = []
        for node_id, score in node_scores.items():
            node = graph.get_node(node_id)
            if node is None:
                continue
            results.append(RetrievalResult(
                node=node,
                score=score,
                reason=node_reasons.get(node_id, ""),
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def retrieve_as_text(
        self,
        graph: TemporalGraph,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> str:
        """
        Retrieve and format results as readable text for LLM context injection.
        """
        results = self.retrieve(graph, query, top_k, min_confidence)

        if not results:
            return "(No relevant memory found)"

        lines = [f"Memory retrieval for: '{query}'", ""]
        for i, r in enumerate(results, 1):
            lines.append(
                f"{i}. [{r.node.type.value}] {r.node.label} "
                f"(confidence: {r.node.confidence_score:.2f}, "
                f"relevance: {r.score:.3f})"
            )
            if r.node.attributes:
                for k, v in r.node.attributes.items():
                    lines.append(f"     {k}: {v}")
            if r.reason:
                lines.append(f"     reason: {r.reason}")
        return "\n".join(lines)

    # ── Internal helpers ────────────────────────────────────────────

    def _tokenize(self, text: str) -> set[str]:
        """Extract meaningful lowercase tokens from text."""
        # Remove punctuation, split, filter short/stop words
        words = re.findall(r"[a-zA-Z0-9]+", text.lower())
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "or", "but", "not", "no", "if", "then", "so", "as",
            "it", "its", "this", "that", "these", "those", "what", "which",
            "who", "how", "when", "where", "why", "i", "me", "my", "we",
            "our", "you", "your", "he", "she", "they", "them", "their",
            "about", "up", "out", "just", "also", "very", "much",
        }
        return {w for w in words if len(w) > 1 and w not in stop_words}

    def _keyword_score(self, query_tokens: set[str], node: Node) -> float:
        """
        Score a node against query tokens.

        Checks label and attribute values for token overlap.
        Returns 0.0 to 1.0.
        """
        if not query_tokens:
            return 0.0

        # Tokenize node content
        node_text = node.label
        for v in node.attributes.values():
            if isinstance(v, str):
                node_text += " " + v

        node_tokens = self._tokenize(node_text)

        if not node_tokens:
            return 0.0

        # Jaccard-like overlap weighted toward query coverage
        overlap = query_tokens & node_tokens
        if not overlap:
            return 0.0

        # What fraction of query tokens are found in this node?
        query_coverage = len(overlap) / len(query_tokens)

        # What fraction of node tokens match? (penalize very generic nodes)
        node_specificity = len(overlap) / len(node_tokens)

        # Weighted combination favoring query coverage
        return 0.7 * query_coverage + 0.3 * node_specificity
