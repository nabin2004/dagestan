"""
dagestan.curation.strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~

Generates actionable context summaries from the curated graph.

After curation runs, this module produces a structured summary
that can be injected into the next LLM conversation as context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..graph.operations import compute_centrality, detect_gaps
from ..graph.schema import EdgeType, NodeType
from ..graph.temporal_graph import TemporalGraph


def generate_strategy(
    graph: TemporalGraph,
    top_k: int = 15,
    min_confidence: float = 0.2,
) -> dict[str, Any]:
    """
    Generate a structured context summary from the current graph state.

    This is what gets injected into the next conversation. It includes:
    - Top entities by importance
    - Active goals
    - Known preferences
    - Recent events
    - Knowledge gaps worth exploring

    Args:
        graph: The curated temporal graph.
        top_k: Maximum number of items per category.
        min_confidence: Minimum confidence to include a node.

    Returns:
        Dict with structured context ready for LLM consumption.
    """
    centrality = compute_centrality(graph)

    # Filter by minimum confidence
    active_nodes = [n for n in graph.nodes if n.confidence_score >= min_confidence]

    # Sort by centrality score
    active_nodes.sort(
        key=lambda n: centrality.get(n.id, 0),
        reverse=True,
    )

    # Categorize
    entities = []
    goals = []
    preferences = []
    events = []
    concepts = []

    for node in active_nodes:
        entry = {
            "label": node.label,
            "confidence": round(node.confidence_score, 2),
            "centrality": centrality.get(node.id, 0),
        }
        if node.attributes:
            entry["attributes"] = node.attributes

        if node.type == NodeType.ENTITY and len(entities) < top_k:
            entities.append(entry)
        elif node.type == NodeType.GOAL and len(goals) < top_k:
            goals.append(entry)
        elif node.type == NodeType.PREFERENCE and len(preferences) < top_k:
            preferences.append(entry)
        elif node.type == NodeType.EVENT and len(events) < top_k:
            events.append(entry)
        elif node.type == NodeType.CONCEPT and len(concepts) < top_k:
            concepts.append(entry)

    # Get knowledge gaps
    gaps = detect_gaps(graph)
    gap_summaries = [g["description"] for g in gaps[:5]]

    # Build the strategy object
    strategy: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graph_stats": {
            "total_nodes": graph.node_count,
            "total_edges": graph.edge_count,
            "active_nodes": len(active_nodes),
        },
        "key_entities": entities,
        "active_goals": goals,
        "known_preferences": preferences,
        "recent_events": events,
        "domain_concepts": concepts,
        "knowledge_gaps": gap_summaries,
    }

    return strategy


def strategy_to_prompt(strategy: dict[str, Any]) -> str:
    """
    Convert a strategy dict into a natural-language context block
    suitable for injection into an LLM system prompt.
    """
    lines = ["=== Memory Context (from Dagestan) ===", ""]

    # Entities
    if strategy.get("key_entities"):
        lines.append("Key entities:")
        for e in strategy["key_entities"]:
            lines.append(f"  - {e['label']} (confidence: {e['confidence']})")
        lines.append("")

    # Goals
    if strategy.get("active_goals"):
        lines.append("Active goals:")
        for g in strategy["active_goals"]:
            lines.append(f"  - {g['label']} (confidence: {g['confidence']})")
        lines.append("")

    # Preferences
    if strategy.get("known_preferences"):
        lines.append("Known preferences:")
        for p in strategy["known_preferences"]:
            lines.append(f"  - {p['label']} (confidence: {p['confidence']})")
        lines.append("")

    # Events
    if strategy.get("recent_events"):
        lines.append("Recent events:")
        for ev in strategy["recent_events"]:
            lines.append(f"  - {ev['label']} (confidence: {ev['confidence']})")
        lines.append("")

    # Gaps
    if strategy.get("knowledge_gaps"):
        lines.append("Knowledge gaps (consider asking about):")
        for gap in strategy["knowledge_gaps"]:
            lines.append(f"  - {gap}")
        lines.append("")

    lines.append("=== End Memory Context ===")
    return "\n".join(lines)
