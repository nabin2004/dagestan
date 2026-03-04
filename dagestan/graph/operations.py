"""
dagestan.graph.operations
~~~~~~~~~~~~~~~~~~~~~~~~~

Graph-level intelligence operations.

These are the operations that distinguish Dagestan from a simple store.
They run on the graph structure itself — the LLM is only called for
interpretation when needed, not for the computation.

v0.1 scope: contradiction detection, temporal decay.
Also includes centrality scoring, gap detection, and bridge detection
(used by retrieval and curation).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .schema import Edge, EdgeType, Node, NodeType
from .temporal_graph import TemporalGraph


# ── Contradiction Detection ────────────────────────────────────────


def detect_contradictions(
    graph: TemporalGraph,
) -> list[tuple[Node, Node, Node]]:
    """
    Find potential contradictions in the graph.

    Looks for pairs of PREFERENCE or GOAL nodes connected to the same
    ENTITY that might assert conflicting states. A contradiction is
    flagged when:
    - Two nodes of the same type (preference or goal) are connected
      to the same entity via has_preference or wants edges.
    - Both nodes still have confidence > 0.1 (not already decayed away).

    Returns:
        List of (entity_node, node_a, node_b) triples representing
        potential contradictions. The caller (or LLM) decides which
        are real conflicts.
    """
    contradictions: list[tuple[Node, Node, Node]] = []

    # Index: entity_id → list of (edge_type, connected_node)
    entity_connections: dict[str, list[tuple[EdgeType, Node]]] = defaultdict(list)

    for edge in graph.edges:
        # We care about has_preference and wants edges
        if edge.type not in (EdgeType.HAS_PREFERENCE, EdgeType.WANTS):
            continue

        source = graph.get_node(edge.source_id)
        target = graph.get_node(edge.target_id)

        if source is None or target is None:
            continue

        # The entity is typically the source of has_preference / wants
        if source.type == NodeType.ENTITY:
            entity_connections[source.id].append((edge.type, target))
        elif target.type == NodeType.ENTITY:
            entity_connections[target.id].append((edge.type, source))

    # Check for same-type pairs under each entity
    for entity_id, connections in entity_connections.items():
        entity = graph.get_node(entity_id)
        if entity is None:
            continue

        # Group by edge type → node type
        by_category: dict[tuple[EdgeType, NodeType], list[Node]] = defaultdict(list)
        for edge_type, node in connections:
            if node.confidence_score > 0.1:
                by_category[(edge_type, node.type)].append(node)

        # Any category with 2+ nodes is a potential contradiction set
        for _category, nodes in by_category.items():
            if len(nodes) < 2:
                continue
            # Generate all unique pairs
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    contradictions.append((entity, nodes[i], nodes[j]))

    return contradictions


# ── Temporal Decay ─────────────────────────────────────────────────


def apply_decay(
    graph: TemporalGraph,
    current_time: datetime | None = None,
    min_confidence: float = 0.01,
) -> int:
    """
    Apply temporal decay to all nodes in the graph.

    Confidence degrades based on time since last reinforcement
    and the node's decay_rate. Uses exponential decay:

        confidence *= exp(-decay_rate * days_since_reinforced)

    Args:
        graph: The temporal graph to update.
        current_time: Reference time (default: now UTC).
        min_confidence: Floor value — nodes don't drop below this.

    Returns:
        Number of nodes whose confidence was reduced.
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    decay_count = 0

    for node in graph.nodes:
        if node.confidence_score <= min_confidence:
            continue

        days_elapsed = (
            current_time - node.last_reinforced
        ).total_seconds() / 86400.0

        if days_elapsed <= 0:
            continue

        decay_rate = node.decay_rate or 0.02
        decay_factor = math.exp(-decay_rate * days_elapsed)
        new_confidence = node.confidence_score * decay_factor

        if new_confidence < min_confidence:
            new_confidence = min_confidence

        if new_confidence < node.confidence_score:
            node.confidence_score = round(new_confidence, 4)
            decay_count += 1

    # Also decay edge confidence based on connected node confidence
    for edge in graph.edges:
        source = graph.get_node(edge.source_id)
        target = graph.get_node(edge.target_id)
        if source and target:
            # Edge confidence is bounded by the weaker endpoint
            edge.confidence_score = min(
                edge.confidence_score,
                source.confidence_score,
                target.confidence_score,
            )

    return decay_count


# ── Centrality Scoring ─────────────────────────────────────────────


def compute_centrality(
    graph: TemporalGraph,
    recency_weight: float = 0.3,
) -> dict[str, float]:
    """
    Score each node by structural importance.

    Combines degree centrality (connection count) with
    recency-weighted confidence. No LLM needed — pure graph math.

    Args:
        graph: The temporal graph.
        recency_weight: How much to weight confidence/recency vs degree.

    Returns:
        Dict of node_id → centrality score (higher = more important).
    """
    if graph.node_count == 0:
        return {}

    scores: dict[str, float] = {}

    # Degree centrality: number of edges connected to each node
    max_degree = 1  # avoid div by zero
    degrees: dict[str, int] = {}
    for node in graph.nodes:
        degree = len(graph.get_edges(node_id=node.id))
        degrees[node.id] = degree
        if degree > max_degree:
            max_degree = degree

    for node in graph.nodes:
        # Normalized degree (0 to 1)
        degree_score = degrees.get(node.id, 0) / max_degree

        # Confidence already encodes recency via decay
        confidence = node.confidence_score

        # Combined score
        score = (1 - recency_weight) * degree_score + recency_weight * confidence
        scores[node.id] = round(score, 4)

    return scores


# ── Gap Detection ──────────────────────────────────────────────────


def detect_gaps(graph: TemporalGraph) -> list[dict[str, Any]]:
    """
    Find entities with incomplete knowledge profiles.

    Identifies:
    - Entities with goals but no preferences (or vice versa)
    - Entities with no outgoing edges at all
    - Nodes frequently referenced (high in-degree) but with sparse attributes

    Returns:
        List of gap descriptions with the entity and what's missing.
    """
    gaps: list[dict[str, Any]] = []

    for node in graph.get_nodes_by_type(NodeType.ENTITY):
        outgoing = graph.get_edges(node_id=node.id, direction="outgoing")
        incoming = graph.get_edges(node_id=node.id, direction="incoming")

        edge_types_out = {e.type for e in outgoing}

        # Entity with no outgoing edges — we know nothing about it
        if len(outgoing) == 0:
            gaps.append({
                "entity_id": node.id,
                "entity_label": node.label,
                "gap_type": "no_outgoing_edges",
                "description": f"Entity '{node.label}' has no relationships — isolated node.",
            })
            continue

        # Has goals but no preferences
        has_goals = EdgeType.WANTS in edge_types_out
        has_prefs = EdgeType.HAS_PREFERENCE in edge_types_out

        if has_goals and not has_prefs:
            gaps.append({
                "entity_id": node.id,
                "entity_label": node.label,
                "gap_type": "missing_preferences",
                "description": f"Entity '{node.label}' has goals but no known preferences.",
            })

        if has_prefs and not has_goals:
            gaps.append({
                "entity_id": node.id,
                "entity_label": node.label,
                "gap_type": "missing_goals",
                "description": f"Entity '{node.label}' has preferences but no known goals.",
            })

        # High in-degree but sparse outgoing (frequently mentioned but poorly understood)
        if len(incoming) >= 3 and len(outgoing) <= 1:
            gaps.append({
                "entity_id": node.id,
                "entity_label": node.label,
                "gap_type": "under_characterized",
                "description": (
                    f"Entity '{node.label}' is referenced by {len(incoming)} edges "
                    f"but has only {len(outgoing)} outgoing relationship(s)."
                ),
            })

    return gaps


# ── Bridge Node Detection ─────────────────────────────────────────


def detect_bridges(graph: TemporalGraph) -> list[Node]:
    """
    Find bridge nodes — nodes that connect otherwise disconnected clusters.

    These are semantically interesting: they represent unexpected
    connections or cross-domain links.

    Uses a simple approach: remove each node and check if connectivity
    decreases. O(N * (N + E)) — fine for the graph sizes we expect.

    Returns:
        List of nodes that are bridges.
    """
    if graph.node_count < 3:
        return []

    # Build a simple adjacency set for BFS
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adj[edge.source_id].add(edge.target_id)
        adj[edge.target_id].add(edge.source_id)

    all_ids = set(n.id for n in graph.nodes)
    base_components = _count_components(all_ids, adj)

    bridges: list[Node] = []

    for node in graph.nodes:
        # Temporarily remove this node
        remaining = all_ids - {node.id}
        filtered_adj: dict[str, set[str]] = defaultdict(set)
        for nid in remaining:
            for neighbor in adj.get(nid, set()):
                if neighbor in remaining:
                    filtered_adj[nid].add(neighbor)

        new_components = _count_components(remaining, filtered_adj)

        # If removing this node increases component count, it's a bridge
        if new_components > base_components:
            bridges.append(node)

    return bridges


def _count_components(
    node_ids: set[str],
    adj: dict[str, set[str]],
) -> int:
    """Count connected components via BFS."""
    if not node_ids:
        return 0

    visited: set[str] = set()
    components = 0

    for start in node_ids:
        if start in visited:
            continue
        components += 1
        queue = [start]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in adj.get(current, set()):
                if neighbor in node_ids and neighbor not in visited:
                    queue.append(neighbor)

    return components
